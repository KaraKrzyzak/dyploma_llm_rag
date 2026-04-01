from __future__ import print_function

import datetime
import json
import logging
import os
import signal
import sys
import traceback
import time

import azureml_globals


def get_telemetry_client():
    """
    :return: Returns a timeout based telemetry client or None
    :rtype: TimeoutBasedTelemetryClient
    """
    client = None

    # AppInsights currently turned off for HDI... TODO: turn it on for HDI
    if (azureml_globals.instrumentation_key is not None) and not azureml_globals.is_hdi:
        client = TimeoutBasedTelemetryClient()
    return client


class TimeoutBasedTelemetryClient(object):
    """
    A timeout based telemetry client that forwards telemetry to our execution service
    telemetry API which uploads it to AppInsights.
    """

    def log(self, message, message_context=None, additional_context=None, level=logging.INFO):
        # telemetry calls to ES API are retired
        pass


class DependencyTimer(object):
    def __init__(self, name, type="Finalization", target=None, message="",
                 suppress_logging=False, swallow_errors=False, telemetry_client=None,
                 exceptions_in_telemetry=False):
        self.name = name
        self.type = type
        self.target = target
        self.message = message
        self.suppress_logging = suppress_logging
        self.swallow_errors = swallow_errors
        self.telemetry_client = telemetry_client
        self.exceptions_in_telemetry = exceptions_in_telemetry

    def __enter__(self):
        self.start_time = datetime.datetime.now()
        return self

    def __exit__(self, exc_type, exc_val, tb):
        try:
            duration = datetime.datetime.now() - self.start_time
            duration_ms = duration.total_seconds() * 1000
            success = exc_val is None or (exc_type == SystemExit and (exc_val.code is None or exc_val.code == 0))
            if not success:
                if not self.suppress_logging:
                    from log_history_status import log_warning
                    target_msg = " to {}".format(self.target) if self.target else ""
                    error_message = "{}: {} {} failed. {}. Exception Details:{}".format(
                        "WARNING" if self.swallow_errors else "ERROR:",
                        self.name, target_msg, self.message,
                        "".join(traceback.format_exception(exc_type, exc_val, tb)))
                    log_warning(error_message, caller="utility_context_managers")
        except Exception as ex:
            print("Exception in DependencyTimer __Exit__ {}".format(ex))
        if self.swallow_errors:
            return True


# The timeout fires in POSIX compliant OS
class TimeoutHandler(object):
    def __init__(self, operation_name, timeout_sec, timeout_envvar=None):
        self.timeout_sec = timeout_sec
        self.operation_name = operation_name
        self.posix = os.name == "posix"
        self.timeout_envvar = timeout_envvar

    def _raise_timeout_error(self, signum, frame):
        action_message = ""
        if self.timeout_envvar:
            action_message = "The timeout can be adjusted using {} environment variable".format(self.timeout_envvar)
            print("[{}] {}".format(datetime.datetime.utcnow().isoformat(),action_message))
        else:
            print("[{}] Operation {} timed out after {} sec. {}".format(datetime.datetime.utcnow().isoformat(),self.operation_name,self.timeout_sec,action_message))
        sys.exit("Operation {} timed out after {} sec. {}".format(self.operation_name,
                                                                  self.timeout_sec,
                                                                  action_message))

    def __enter__(self):
        if self.posix:
            signal.signal(signal.SIGALRM, self._raise_timeout_error)
            signal.alarm(self.timeout_sec)

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.posix:
            signal.alarm(0)


class EventTracker(object):
    def __init__(self, telemetry_client, event_name, custom_properties=None, log_exceptions=False):
        self.client = telemetry_client
        self.event_name = event_name
        self.custom_properties = custom_properties
        self.start_time = None
        self.process_name = azureml_globals.get_process_name()
        self.log_exceptions = log_exceptions

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class SimpleOpTracker(object):
    """
    A simple context manager to log operation start and end time information to
    help debugging when there is failure with control script
    """
    def __init__(self, operation_name):
        self.operation_name = operation_name

    def __enter__(self):
        print("[{0}] {1} starting...".format(datetime.datetime.utcnow().isoformat(), self.operation_name))

    def __exit__(self, exc_type, exc_val, exc_tb):
        print("[{0}] {1} completed...".format(datetime.datetime.utcnow().isoformat(), self.operation_name))
