# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import atexit
import logging
import os
import enum
import random
import traceback
import threading
import json
from urllib import request
from uuid import uuid4

from abc import ABC, abstractmethod
from datetime import datetime
from queue import Queue, Empty
from threading import Event as ThreadEvent, Thread
from time import perf_counter, sleep
from typing import List, Sequence

try:
    import contextvars
except ImportError:
    contextvars = None


###############################################
# The code below are vendored from azureml-core
###############################################

# _runtime_context.py
class _RuntimeContext(object):
    @classmethod
    def clear(cls):
        """Clear all slots to their default value."""

        raise NotImplementedError  # pragma: NO COVER

    @classmethod
    def register_slot(cls, name, default=None):
        """Register a context slot with an optional default value.

        :type name: str
        :param name: The name of the context slot.

        :type default: object
        :param name: The default value of the slot, can be a value or lambda.

        :returns: The registered slot.
        """

        raise NotImplementedError  # pragma: NO COVER

    def apply(self, snapshot):
        """Set the current context from a given snapshot dictionary"""

        for name in snapshot:
            setattr(self, name, snapshot[name])

    def snapshot(self):
        """Return a dictionary of current slots by reference."""

        return dict((n, self._slots[n].get()) for n in self._slots.keys())

    def __repr__(self):
        return ('{}({})'.format(type(self).__name__, self.snapshot()))

    def __getattr__(self, name):
        if name not in self._slots:
            raise AttributeError('{} is not a registered context slot'
                                 .format(name))
        slot = self._slots[name]
        return slot.get()

    def __setattr__(self, name, value):
        if name not in self._slots:
            raise AttributeError('{} is not a registered context slot'
                                 .format(name))
        slot = self._slots[name]
        slot.set(value)

    def with_current_context(self, func):
        """Capture the current context and apply it to the provided func"""

        caller_context = self.snapshot()

        def call_with_current_context(*args, **kwargs):
            try:
                backup_context = self.snapshot()
                self.apply(caller_context)
                return func(*args, **kwargs)
            finally:
                self.apply(backup_context)

        return call_with_current_context


class _ThreadLocalRuntimeContext(_RuntimeContext):
    _lock = threading.Lock()
    _slots = {}

    class Slot(object):
        _thread_local = threading.local()

        def __init__(self, name, default):
            self.name = name
            self.default = default if callable(default) else (lambda: default)

        def clear(self):
            setattr(self._thread_local, self.name, self.default())

        def get(self):
            try:
                return getattr(self._thread_local, self.name)
            except AttributeError:
                value = self.default()
                self.set(value)
                return value

        def set(self, value):
            setattr(self._thread_local, self.name, value)

    @classmethod
    def clear(cls):
        with cls._lock:
            for name in cls._slots:
                slot = cls._slots[name]
                slot.clear()

    @classmethod
    def register_slot(cls, name, default=None):
        with cls._lock:
            if name in cls._slots:
                raise ValueError('slot {} already registered'.format(name))
            slot = cls.Slot(name, default)
            cls._slots[name] = slot
            return slot


class _AsyncRuntimeContext(_RuntimeContext):
    _lock = threading.Lock()
    _slots = {}

    class Slot(object):
        def __init__(self, name, default):
            self.name = name
            self.contextvar = contextvars.ContextVar(name)
            self.default = default if callable(default) else (lambda: default)

        def clear(self):
            self.contextvar.set(self.default())

        def get(self):
            try:
                return self.contextvar.get()
            except LookupError:
                value = self.default()
                self.set(value)
                return value

        def set(self, value):
            self.contextvar.set(value)

    @classmethod
    def clear(cls):
        with cls._lock:
            for name in cls._slots:
                slot = cls._slots[name]
                slot.clear()

    @classmethod
    def register_slot(cls, name, default=None):
        with cls._lock:
            if name in cls._slots:
                raise ValueError('slot {} already registered'.format(name))
            slot = cls.Slot(name, default)
            cls._slots[name] = slot
            return slot


RuntimeContext = _ThreadLocalRuntimeContext()
if contextvars:
    RuntimeContext = _AsyncRuntimeContext()


# _execution_context.py
_current_span_slot = RuntimeContext.register_slot('current_span', None)


def get_current_span():
    return RuntimeContext.current_span


def set_current_span(current_span):
    RuntimeContext.current_span = current_span


# _constants.py
USER_FACING_NAME = 'aml.user_facing_name'
VERBOSITY = 'aml.verbosity'
EXCEPTION_EVENT_NAME = 'exception'

EXCEPTION_TYPE = 'exception.type'
EXCEPTION_MESSAGE = 'exception.message'
EXCEPTION_STACKTRACE = 'exception.stacktrace'

AML_DEV_ATTR_PREFIX = 'aml.attr.dev'
AML_USER_ATTR_PREFIX = 'aml.attr.user'

TRACEPARENT_ENV_VAR = 'AZUREML_SDK_TRACEPARENT'
TRACEEXPORTDIR_ENV_VAR = 'AZUREML_SDK_TRACEEXPORTDIR'


# _context.py
class Context:
    def __init__(self, trace_id, span_id):
        self.trace_id = trace_id
        self.span_id = span_id
        self.is_remote = False
        self.trace_state = {}


# _tracer_factory.py
_logger = logging.getLogger('azureml.control_script' + __name__)
_trace_provider = None


def _get_trace_provider():
    global _trace_provider
    if _trace_provider:
        return _trace_provider

    processors = []
    if 'AZUREML_OTEL_EXPORT_RH' in os.environ:
        processors.append(AggregatedSpanProcessor([AmlContextSpanProcessor(UserFacingSpanProcessor(ExporterSpanProcessor(
            RunHistoryExporter(logger=_logger), logger=_logger
        )))]))

    export_dir = os.getenv(TRACEEXPORTDIR_ENV_VAR)
    if export_dir:
        processors.append(AggregatedSpanProcessor([ExporterSpanProcessor(
            JsonLineExporter(export_dir)
        )]))

    if len(processors) == 0:
        print("Cannot provide tracer without any exporter configured.")
        return None

    _trace_provider = DefaultTraceProvider(AmlTracer(processors))
    return _trace_provider


# _tracer.py
class AmlTracer:
    def __init__(self, span_processors):
        self._span_processors = span_processors

    def start_as_current_span(self, name, parent=None, user_facing_name=None):
        parent = parent or self.__class__._get_ambient_parent()
        span = Span(name, parent, self._span_processors)
        self.__class__.decorate_span(span, user_facing_name)
        span.__enter__()
        return span

    def start_span(self, name, parent=None, user_facing_name=None):
        span = Span(name, parent, self._span_processors)
        self.__class__.decorate_span(span, user_facing_name)
        return span

    @staticmethod
    def decorate_span(span, user_facing_name):
        if user_facing_name:
            span.attributes[USER_FACING_NAME] = user_facing_name

    @staticmethod
    def _get_ambient_parent():
        current_parent = get_current_span()
        if current_parent:
            return current_parent
        traceparent = os.environ.get(TRACEPARENT_ENV_VAR, '').split('-')
        if not traceparent or len(traceparent) != 4:
            return None
        return Span._from_traceparent(*traceparent)


class DefaultTraceProvider:
    def __init__(self, tracer):
        self._tracer = tracer

    def get_tracer(self, name):
        return self._tracer

    def get_current_span(self):
        return get_current_span()


# _status.py
class StatusCode(enum.Enum):
    OK = 0

    """Internal errors."""
    INTERNAL = 13


class Status:
    def __init__(self, canonical_code=StatusCode.OK):
        self._canonical_code = canonical_code

    @property
    def canonical_code(self):
        return self._canonical_code

    @property
    def is_ok(self):
        return self._canonical_code == StatusCode.OK


# _span_processor.py
class SpanProcessor(ABC):
    def on_start(self, span):
        pass

    @abstractmethod
    def on_end(self, span):
        pass

    def shutdown(self):
        pass

    def force_flush(self, timeout_millis=30000):
        return True


class _ChainedSpanProcessor(SpanProcessor):
    def __init__(self, span_processor):
        self._next_processor = span_processor

    def on_start(self, span):
        self._next_processor.on_start(span)

    def on_end(self, span):
        self._next_processor.on_end(span)

    def shutdown(self):
        self._next_processor.shutdown()

    def force_flush(self, timeout_millis=30000):
        return self._next_processor.force_flush(timeout_millis)


class ExporterSpanProcessor(SpanProcessor):
    def __init__(self, span_exporter, logger=None):
        self._span_exporter = span_exporter
        self._logger = logger or logging.getLogger(__name__)

    def on_end(self, span):
        try:
            self._span_exporter.export((span,))
        except Exception as e:
            self._logger.error('Exception of type {} while exporting spans.'.format(type(e).__name__))

    def shutdown(self):
        self._span_exporter.shutdown()


class UserFacingSpanProcessor(_ChainedSpanProcessor):
    def __init__(self, span_processor):
        super().__init__(span_processor)

    def on_end(self, span):
        if USER_FACING_NAME not in span.attributes:
            return

        span = _clone_span(span)
        _remove_dev_attributes(span.attributes)
        for event in span.events:
            _remove_dev_attributes(event.attributes)

        super().on_end(span)


class AmlContextSpanProcessor(_ChainedSpanProcessor):
    def __init__(self, span_processor):
        super().__init__(span_processor)
        self._run_id = None

    def on_end(self, span):
        self._add_aml_context(span)
        super().on_end(span)

    def _add_aml_context(self, span):
        span.set_user_facing_attribute('run_id', self._get_run_id())

    def _get_run_id(self):
        return os.environ.get('AZUREML_RUN_ID')


class AggregatedSpanProcessor(SpanProcessor):
    def __init__(self, span_processors):
        self._span_processors = span_processors
        self._event = ThreadEvent()
        self._start_queue = Queue()
        self._end_queue = Queue()
        self._start_task = None
        self._end_task = None
        if any(span_processors):
            on_start = lambda processor, span: processor.on_start(span)
            on_end = lambda processor, span: processor.on_end(span)
            self._start_task = Thread(
                target=AggregatedSpanProcessor._worker,
                args=(self._start_queue, self._event, self._span_processors, on_start)
            )
            self._end_task = Thread(
                target=AggregatedSpanProcessor._worker,
                args=(self._end_queue, self._event, self._span_processors, on_end)
            )
            self._start_task.daemon = True
            self._start_task.start()
            self._end_task.daemon = True
            self._end_task.start()
            atexit.register(self.__class__._atexit, self._event, self._end_task, self._span_processors)

    def on_end(self, span):
        self._end_queue.put(span)

    def shutdown(self):
        self.__class__._atexit(self._event, self._end_task, self._span_processors)

    def force_flush(self, timeout_millis):
        all_successful = True
        for span_processor in self._span_processors:
            all_successful = span_processor.force_flush(timeout_millis) and all_successful
        return all_successful

    def __del__(self):
        self._event.set()
        self._end_task.join(5)

    @staticmethod
    def _worker(queue, event, span_processors, action):
        while not event.is_set() or not queue.empty():
            try:
                span = queue.get(block=True, timeout=1)  # type: 'Span'
                for span_processor in span_processors:
                    action(span_processor, span)
            except Empty:
                pass

    @staticmethod
    def _atexit(event, task, processors):
        event.set()
        task.join(5)
        for span_processor in processors:
            span_processor.shutdown()


def _clone_span(span):
    def clone_event(event):
        return Event(event.name, event.timestamp, event.attributes.copy())

    cloned = Span(span.name, span.parent, span._span_processors)
    cloned._trace_id = span.trace_id
    cloned._span_id = span.span_id
    cloned._start_time = span.start_time
    cloned._end_time = span.end_time
    cloned._attributes = span.attributes.copy()
    cloned._events = [clone_event(event) for event in span.events]
    cloned._status = span.status
    return cloned


def _remove_dev_attributes(attributes):
    for key in attributes:
        if key.startswith(AML_DEV_ATTR_PREFIX + '.'):
            del attributes[key]


# _span.py
class Span:
    def __init__(self, name, parent, span_processors):
        self._name = name
        self._parent = parent
        self._trace_id = parent.trace_id if parent else generate_trace_id()
        self._span_id = generate_span_id()
        self._span_processors = span_processors
        self._start_time = None
        self._end_time = None
        self._attributes = {}
        self._events = []
        self._status = Status()
        self._w3c_traceparent = None
        self._context = None

    @property
    def parent(self):
        return self._parent

    @property
    def name(self):
        return self._name

    @property
    def trace_id(self):
        return self._trace_id

    @property
    def span_id(self):
        return self._span_id

    @property
    def start_time(self):
        return self._start_time

    @property
    def end_time(self):
        return self._end_time

    @property
    def kind(self):
        return 'Internal'

    @property
    def attributes(self):
        return self._attributes

    @property
    def events(self):
        return self._events

    @property
    def status(self):
        return self._status

    def set_attribute(self, key, value):
        self._attributes[key] = value

    def set_user_facing_attribute(self, key, value):
        self._attributes['{}.{}'.format(AML_USER_ATTR_PREFIX, key)] = value

    def set_dev_facing_attribute(self, key, value):
        self._attributes['{}.{}'.format(AML_DEV_ATTR_PREFIX, key)] = value

    def add_event(self, name, attributes):
        self._events.append(Event(name, datetime.utcnow(), attributes))

    def add_exception(self, exception, additional_attributes={}):
        pass

    def start(self):
        if self._start_time is not None:
            return

        self._start_time = datetime.utcnow()

        for span_processor in self._span_processors:
            span_processor.on_start(self)

    def set_as_current(self):
        set_current_span(self)

    def end(self):
        if self._end_time is not None:
            return

        self._end_time = datetime.utcnow()

        for span_processor in self._span_processors:
            span_processor.on_end(self)

    def set_parent_as_current(self):
        set_current_span(self._parent)

    def get_context(self):
        if not self._context:
            self._context = Context(self._trace_id, self._span_id)
        return self._context

    def __enter__(self):
        self.set_as_current()
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.set_parent_as_current()
        self._handle_exceptions(exc_type, exc_val, exc_tb)
        self.end()

    def _handle_exceptions(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return
        import traceback

        self._status = Status(StatusCode.INTERNAL)
        self._attributes[EXCEPTION_TYPE] = exc_type.__name__
        try:
            self._attributes[EXCEPTION_MESSAGE] = exc_val.message
        except AttributeError:
            self._attributes[EXCEPTION_MESSAGE] = str(exc_val)
        self._attributes[EXCEPTION_STACKTRACE] = traceback.format_tb(exc_tb)

    def to_w3c_traceparent(self):
        if not self._w3c_traceparent:
            self._w3c_traceparent = '00-{}-{}-{}'.format(
                self.trace_id.to_bytes(16, 'big').hex(),
                self.span_id.to_bytes(8, 'big').hex(),
                '01'
            )
        return self._w3c_traceparent

    @staticmethod
    def _from_traceparent(version, hex_trace_id, hex_span_id, traceflag):
        trace_id = int(hex_trace_id, 16)
        span_id = int(hex_span_id, 16)
        span = Span('', None, [])
        span._trace_id = trace_id
        span._span_id = span_id
        return span


def generate_span_id():
    return random.getrandbits(64)


def generate_trace_id():
    return random.getrandbits(128)


# _exporter.py
class SpanExporter(ABC):
    @abstractmethod
    def export(self, spans):
        pass

    @abstractmethod
    def shutdown(self):
        pass


def to_iso_8601(time):
    if isinstance(time, datetime):
        return time.strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    return time


# _run_history_exporter.py
class RunHistoryExporter(SpanExporter):
    def __init__(self, max_buffer_size=512, max_flush_interval=1, logger=None):
        logger = logger or logging.getLogger(__name__)
        self._queue = Queue()
        self._event = ThreadEvent()
        self._task = Thread(target=RunHistoryExporter.worker,
                            args=(self._queue, self._event, max_buffer_size, max_flush_interval, logger))
        self._task.daemon = True
        self._task.start()
        atexit.register(self.__class__.on_exit, self._event, self._task)

    def export(self, spans):
        self._queue.put(spans)

    def shutdown(self):
        self.__class__.on_exit(self._event, self._task)

    def __del__(self):
        self.__class__.on_exit(self._event, self._task)

    @staticmethod
    def worker(queue, event, max_buffer_size, max_flush_interval, logger):
        buffer = []  # type: List[Span]
        last_flushed = 0

        while not event.is_set() or not queue.empty():
            try:
                new_spans = queue.get(block=True, timeout=1)  # type: Sequence[Span]
                buffer.extend(new_spans)
            except Empty:
                pass
            last_flushed = RunHistoryExporter.flush(buffer, max_buffer_size,
                                                    max_flush_interval, last_flushed, logger)

    @staticmethod
    def flush(buffer, max_buffer_size, max_flush_interval, last_flush, logger):
        def flush_internal():
            host = os.environ.get('AZUREML_RUN_HISTORY_SERVICE_ENDPOINT') or os.environ.get('AZUREML_SERVICE_ENDPOINT')
            token = os.environ.get('AZUREML_RUN_TOKEN')
            scope = os.environ.get('AZUREML_WORKSPACE_SCOPE')
            run_id = os.environ.get('AZUREML_RUN_ID')

            if not (host and token and scope and run_id):
                print('Unexpected error - unable to send spans as either host, token, scope, or run_id is missing.')
                print('host: {}\nhas token: {}\nscope: {}\nrun id: {}'.format(host, bool(token), scope, run_id))
                return

            payload = RunHistoryExporter.to_json(buffer)
            path = 'history/v1.0/private{}/runs/{}/spans'.format(scope, run_id)
            url = '{}/{}'.format(host.rstrip('/'), path)
            headers = {
                'Authorization': 'Bearer {}'.format(token)
            }
            headers['Content-Type'] = 'application/json; charset=utf-8'

            def make_req():
                req = request.Request(url, data=json.dumps(payload).encode(), headers=headers, method='POST')
                try:
                    with request.urlopen(req) as res:
                        if res.status >= 400:
                            logger.warn('Failed to upload spans to {} with status code {} and reason {}'.format(
                                url, res.status, res.reason
                            ))
                            raise Exception('Failed to upload, retrying')
                except Exception as e:
                    logger.warn('Failed to upload spans to {} due to an unexpected exception {}: {}'.format(
                        url, type(e).__name__, e
                    ))
            RunHistoryExporter._retry(make_req, 'Export Spans', logger)

            buffer.clear()

        elapsed = perf_counter() - last_flush
        if elapsed <= max_flush_interval and len(buffer) <= max_buffer_size:
            return last_flush

        if len(buffer) == 0:
            return last_flush

        flush_internal()
        return perf_counter()


    @staticmethod
    def to_json(buffer):
        def serialize_event(event):
            return {
                'Name': event.name,
                'Timestamp': to_iso_8601(event.timestamp),
                'Attributes': serialize_attributes(event.attributes)
            }

        def serialize_attributes(attributes):
            return [{
                'key': key,
                'value': value
            } for key, value in attributes.items()]

        payload = []
        for span in buffer:
            span_context = span.get_context()
            payload.append({
                'Context': {
                    'TraceId': span_context.trace_id.to_bytes(16, 'big').hex(),
                    'SpanId': span_context.span_id.to_bytes(8, 'big').hex(),
                    'IsRemote': span_context.is_remote,
                    'IsValid': True,
                    'Tracestate': None
                },
                'Name': span.name,
                'Status': 'Running',
                'ParentSpanId': span.parent.span_id.to_bytes(8, 'big').hex() if span.parent else '',
                'Attributes': serialize_attributes(span.attributes),
                'Events': list(map(serialize_event, span.events)),
                'Links': [],
                'StartTimestamp': to_iso_8601(span.start_time),
                'EndTimestamp': to_iso_8601(span.end_time)
            })

        return {'Spans': payload}

    @staticmethod
    def on_exit(event, task):
        event.set()
        task.join(5)

    @staticmethod
    def _retry(func, name, logger, max_attempt=3, wait=1):
        for i in range(1, max_attempt + 1):
            try:
                return func()
            except Exception as e:
                logger.debug('{} failed. Attempt: {}. Error: {}'.format(name, i + 1, e))
                if i == max_attempt:
                    raise
                sleep(wait)


# _event.py
class Event:
    def __init__(self, name, timestamp, attributes):
        self._name = name
        self._timestamp = timestamp
        self._attributes = attributes

    @property
    def name(self):
        return self._name

    @property
    def timestamp(self):
        return self._timestamp

    @property
    def attributes(self):
        return self._attributes


# JSONLine exporter
class JsonLineExporter(SpanExporter):
    def __init__(self, base_directory: str):
        self._path = os.path.join(base_directory, 'cs_spans_{}.jsonl'.format(uuid4()))
        self._write_lock = threading.Lock()
        self._file = None

    def export(self, spans: Sequence[Span]) -> None:
        json_lines = list(map(self.__class__.to_json, spans))
        with self._write_lock:
            if self._file is None:
                try:
                    os.makedirs(os.path.dirname(self._path), exist_ok=True)
                except:
                    pass
                self._file = open(self._path, 'a+')
            for l in json_lines:
                self._file.write('{}\n'.format(l))
            self._file.flush()

    def shutdown(self) -> None:
        if self._file is None:
            return
        with self._write_lock:
            self._file.flush()
            self._file.close()


    @staticmethod
    def to_json(span_data: Span) -> str:
        if not span_data:
            return ''

        def serialize_span(span: Span):
            context = span.get_context()
            return json.dumps({
                'traceId': context.trace_id.to_bytes(16, 'big').hex(),
                'spanId': context.span_id.to_bytes(8, 'big').hex(),
                'parentSpanId': span.parent.span_id.to_bytes(8, 'big').hex() if span.parent else '',
                'name': span.name,
                'kind': str(span.kind),
                'startTime': to_iso_8601(span.start_time),
                'endTime': to_iso_8601(span.end_time),
                'attributes': convert_attributes(span.attributes),
                'events': convert_events(span.events),
                'status': span.status.canonical_code.value
            })

        def convert_events(events: Sequence[Event]):
            return list(map(lambda event: {
                'name': event.name,
                'timeStamp': to_iso_8601(event.timestamp),
                'attributes': convert_attributes(event.attributes)
            }, events))

        def convert_attributes(attributes):
            return attributes

        return serialize_span(span_data)