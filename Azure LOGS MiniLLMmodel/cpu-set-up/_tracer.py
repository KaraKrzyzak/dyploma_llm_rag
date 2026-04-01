import os


def get_tracer(name):
    # RunHistory perf tracing is in preview.
    # The flighting is controlled by this environment variable.
    try:
        from _tracing import _get_trace_provider
        provider = _get_trace_provider()
        if provider is not None:
            return provider.get_tracer(name)
    except Exception as e:
        print("Cannot import tracer due to unknown exception {} with message {}.".format(type(e).__name__, e))
    return _NullTracer()


class _NullTracer:
    def start_as_current_span(self, name, parent=None, user_facing_name=None):
        return _NullSpan()

    def start_span(self, name, parent=None, user_facing_name=None):
        return _NullSpan()

    @staticmethod
    def decorate_span(span, user_facing_name):
        pass


class _NullSpan:
    @property
    def parent(self):
        return None

    @property
    def name(self):
        return None

    @property
    def trace_id(self):
        return None

    @property
    def span_id(self):
        return None

    @property
    def start_time(self):
        return None

    @property
    def end_time(self):
        return None

    @property
    def kind(self):
        return None

    @property
    def attributes(self):
        return None

    @property
    def events(self):
        return None

    @property
    def status(self):
        return None

    def set_attribute(self, key, value):
        pass

    def set_user_facing_attribute(self, key, value):
        pass

    def set_dev_facing_attribute(self, key, value):
        pass

    def add_event(self, name, attributes):
        pass

    def add_exception(self, exception, additional_attributes={}):
        pass

    def start(self):
        pass

    def set_as_current(self):
        pass

    def end(self):
        pass

    def set_parent_as_current(self):
        pass

    def get_context(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass
