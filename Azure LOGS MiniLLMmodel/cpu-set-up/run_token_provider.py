import threading
import time
import os
import json
import traceback
import logging

import azureml_globals
from request_utilities import get_default_headers, send_request
from _vendor_jwt_decode import jwt_decode

try:
    # For Python 3.0 and later
    from urllib.request import urlopen, Request, HTTPError
except ImportError:
    # Fall back to Python 2's urllib2
    from urllib2 import urlopen, Request, HTTPError


class RunTokenProvider(object):
    _daemon_thread = None
    _daemon_thread_lock = threading.Lock()

    # We check token expiry time every 5 s.
    _PERIODIC_CHECK_INTERVAL_SECS = 5

    # We refresh token if it is about to expire in next 10 minutes.
    _REFRESH_TOKEN_INTERVAL_SECS = 10 * 60

    @classmethod
    def get_run_token(cls):
        # In case, daemon thread hasn't started.
        cls._start_refresh_token_daemon_thread()
        return os.environ[azureml_globals.env_var_run_token]

    @classmethod
    def _send_request_with_retry(cls, request_args):
        for _ in range(3):
            try:
                return send_request(**request_args)
            except HTTPError:
                time.sleep(5)
        logging.warning("Failed to refresh the run token.")

    @classmethod
    def _start_refresh_token_daemon_thread(cls):
        # Checking it without lock so that we don't need to acquire lock when _daemon_thread is not None
        if not cls._daemon_thread:
            try:
                cls._daemon_thread_lock.acquire()
                # Final check
                if not cls._daemon_thread:
                    print("Starting the daemon thread to refresh tokens in background for "
                          "process with pid = {}".format(os.getpid()))
                    cls._daemon_thread = threading.Thread(target=cls._check_and_refresh_token_periodically,
                                                          name="RunTokenProviderDaemonThread")
                    # setDaemon is both python 2.7 and python 3 compatible. daemon=True in threading.Thread is only
                    # available in python 3.
                    cls._daemon_thread.setDaemon(True)
                    cls._daemon_thread.start()
            finally:
                cls._daemon_thread_lock.release()

    @classmethod
    def _check_and_refresh_token_periodically(cls):
        while True:
            time.sleep(cls._PERIODIC_CHECK_INTERVAL_SECS)
            try:
                curr_token = os.environ.get(azureml_globals.env_var_run_token)
                curr_token_expiry_time = jwt_decode(curr_token)["exp"]

                if (curr_token_expiry_time - time.time()) < cls._REFRESH_TOKEN_INTERVAL_SECS:
                    new_run_token = cls._get_new_token_from_history(curr_token)
                    if not new_run_token:
                        logging.warning("Couldn't refresh token from run history.")
                    else:
                        new_expiry_time = jwt_decode(new_run_token)["exp"]
                        # Setting this in the env variable, to keep envs up-to-date.
                        os.environ[azureml_globals.env_var_run_token] = new_run_token
                        os.environ[azureml_globals.env_var_run_token_expiry] = str(new_expiry_time)

            except Exception:
                traceback.print_exc()
                logging.warning("Couldn't refresh token. Trying again in {} secs".format(
                    cls._PERIODIC_CHECK_INTERVAL_SECS))

    @classmethod
    def _get_new_token_from_history(cls, current_run_token):
        history_token_url = azureml_globals.run_history_endpoint + "/history/v1.0" + azureml_globals.experiment_scope \
                            + "/runs/" + azureml_globals.run_id + "/token"
        request_args = {
            "url": history_token_url,
            "headers": get_default_headers(current_run_token,
                                           content_type='application/json; charset=utf-8'),
            "method": "GET"
        }
        response = cls._send_request_with_retry(request_args)

        if response:
            response_dict = json.loads(response.read().decode("utf-8"))
            new_run_token = response_dict["token"]
            return new_run_token
