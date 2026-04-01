# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import datetime
import json
import time
import os

from run_token_provider import RunTokenProvider
import azureml_globals
from request_utilities import get_default_headers, send_request

try:
    # For Python 3.0 and later
    from urllib.request import HTTPError
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import HTTPError

MAX_RETRIES = 5
SLEEP_DURATION_BASE = 1


def try_request(request_args, error_text):
    for i in range(MAX_RETRIES):
        try:
            return send_request(**request_args)
        except HTTPError as ex:
            print(error_text)
            print(ex.code)
            print(ex.read())
            if ex.code >= 500:
                time.sleep(SLEEP_DURATION_BASE * (2 ** i))
                print("")
                print("Retrying...")
            else:
                return
        except Exception as e:
            print(error_text)
            print(e)
            time.sleep(SLEEP_DURATION_BASE * (2 ** i))
            print("")
            print("Retrying...")


def send_history_event(payload, error_text, caller=None):
    history_url = azureml_globals.run_history_endpoint + "/history/v1.0" + azureml_globals.experiment_scope \
                  + "/runs/" + azureml_globals.run_id + "/"
    events_url = history_url + "events"

    json_data = json.dumps(payload)
    headers = get_default_headers(RunTokenProvider.get_run_token(),
                                       content_type='application/json')
    if caller is None:
        headers['User-Agent'] = 'ExecutionService ControlScript'
    else:
        headers['User-Agent'] = 'ExecutionService ControlScript' + '/' + caller

    request_args = {
        "url": events_url,
        "data": json_data,
        "headers": headers
    }

    try_request(request_args, error_text)


def set_run_error(error_response, caller=None):
    message_log_mode = "Allowed"
    try:
        if error_response["Error"]["Code"]=="UserError":
            message_log_mode = "NotAllowed"
    except KeyError:
        pass
    payload = {
        "Name": "Microsoft.MachineLearning.Run.Error",
        "Data": {
            "RunId": "{0}".format(azureml_globals.run_id),
            "ErrorResponse": error_response,
            "MessageLogMode": message_log_mode
        }
    }

    send_history_event(payload, "Failed to set run error", caller)


def log_status(status, message=None, caller=None):
    payload = {
        "Name": "Microsoft.MachineLearning.Run." + status,
        "Data": {
            "RunId": "{0}".format(azureml_globals.run_id)
        }
    }

    if status == "Start" or status == "Preparing":
        payload["Data"]["StartTime"] = "{0}".format(datetime.datetime.utcnow().isoformat())
    elif status == "Completed" or status == "Failed" or status == "Canceled":
        payload["Data"]["EndTime"] = "{0}".format(datetime.datetime.utcnow().isoformat())
    elif status == "Warning" and message:
        payload["Data"]["Message"] = "{0}".format(message)
    elif status == "Error" and message:
        payload["Data"]["ErrorResponse"] = {"Error": {"Message": "{}".format(message)}}

    send_history_event(payload, "Failed to set run status: {}".format(status), caller)


def logStatusMessage(status):
    print("[{0}] Logging experiment {1} status in history service.".format(datetime.datetime.utcnow().isoformat(), status))


def log_preparing(caller=None):
    logStatusMessage("preparation")
    log_status("Preparing", caller=caller)


def log_running(caller=None):
    logStatusMessage("running")
    log_status("Start", caller=caller)


def log_finalizing(caller=None):
    if os.getenv("AZ_BATCHAI_IS_PARALLEL_TASKS", "False") == "False":
        logStatusMessage("finalizing")
        log_status("Finalizing", caller=caller)


def log_completed(caller=None):
    logStatusMessage("completed")
    try:
        log_status("Completed", caller=caller)
    except Exception as e:
        if "is in a terminal state and cannot be updated" in str(e):
            pass
        else:
            raise


def log_failed(caller=None):
    logStatusMessage("failed")
    log_status("Failed", caller=caller)


def log_canceled(caller=None):
    logStatusMessage("canceled")
    log_status("Canceled", caller=caller)


def log_warning(warning_message, caller=None):
    print("[{0}] Logging warning in history service: {1}".format(datetime.datetime.utcnow().isoformat(), warning_message))
    log_status("Warning", warning_message, caller=caller)


def log_error(error_message, error_code=None, caller=None):
    print("[{0}] Logging error in history service: {1}".format(datetime.datetime.utcnow().isoformat(), error_message))
    if not error_code:
        error_code = "ServiceError"

    error_response = {
        "Error": {
            "Code": error_code,
            "Message": error_message
        }
    }
    set_run_error(error_response, caller=caller)
