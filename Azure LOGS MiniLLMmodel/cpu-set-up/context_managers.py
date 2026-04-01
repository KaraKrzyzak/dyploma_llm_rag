# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

from __future__ import print_function

import os
import re
import sys
import traceback
import datetime

import azureml_globals
from log_history_status import set_run_error


class dummy():
    def __enter__(self):
        return None

    def __exit__(self, exc_type, exc_value, traceback):
        pass


def get_dependency_timer(**kwargs):
    if not azureml_globals.is_hdi:
        from utility_context_managers import DependencyTimer
        return DependencyTimer(**kwargs)
    else:
        return dummy()


def get_timeout_handler(timeout_enabled=True, *args, **kwargs):
    if not azureml_globals.is_hdi and timeout_enabled:
        from utility_context_managers import TimeoutHandler
        return TimeoutHandler(*args, **kwargs)
    else:
        return dummy()


class ProjectPythonPath(object):
    def __init__(self, config):
        self.single_instance = False

    def __enter__(self):
        project_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
        sys.path.append(project_dir)

    def __exit__(self, *args):
        pass


class FidelityLogUpload(object):
    def __init__(self, config):
        self.timeout_envvar = 'AZUREML_DATASTORE_UPLOAD_TIMEOUT_SEC'
        self.exit_timeout_sec = int(os.getenv(self.timeout_envvar, "600"))
        self.timeout_enabled = True
        self.telemetry_client = None
        self.data_references = None
        self.is_fidelity_log_ready = True

        print("Initializing FidelityLogUpload Context Manager.")
        try:
            from azureml.data.context_managers import DatastoreContextManager
        except ImportError:
            print("Warning: Unable to import azureml.data. Fidelity log upload disabled.")
            self.is_fidelity_log_ready = False
            return

        self.fidelity_log_datastore = azureml_globals.get_fidelity_log_data_store()
        self.fidelity_log_directory = azureml_globals.get_fidelity_log_directory()
        self.fidelity_log_path_on_datastore = azureml_globals.get_fidelity_log_path_on_data_store()

        if not self.fidelity_log_datastore:
            print("Warning: Fidelity log datastore has not been provided. Fidelity log upload disabled.")
            self.is_fidelity_log_ready = False
            return
        if not self.fidelity_log_directory:
            print("Warning: Fidelity log directory has not been provided. Fidelity log upload disabled.")
            self.is_fidelity_log_ready = False
            return

        if self.is_fidelity_log_ready:
            print("Fidelity log upload directory:", self.fidelity_log_directory)
            print("Fidelity log upload datastore:", self.fidelity_log_datastore)
            print("Fidelity log upload path on datastore:", self.fidelity_log_path_on_datastore)

        fidelity_log_config = {'fidelity_log': {'DataStoreName': self.fidelity_log_datastore,
                                                'Mode':'upload',
                                                'PathOnDataStore': self.fidelity_log_path_on_datastore,
                                                'PathOnCompute': self.fidelity_log_directory,
                                                'ForceRead': True,
                                                'Overwrite': True }}

        # If Sidecar Container is running then DatastoreContextManager will have been run there, so don't import it.
        if not azureml_globals.sidecar_running:
            self.data_references = DatastoreContextManager(fidelity_log_config)

    def __enter__(self):
        print("Entering FidelityLogUpload Context Manager.")
        pass

    def __exit__(self, *args):
        print("Exiting FidelityLogUpload Context Manager.")

        if self.is_fidelity_log_ready:
            print("Starting full fidelity log upload")
            try:
                if self.data_references:
                    with get_dependency_timer(name="FidelityLogUpload"):
                        with get_timeout_handler(timeout_enabled=self.timeout_enabled,
                                                 operation_name="FidelityLogUpload",
                                                 timeout_sec=self.exit_timeout_sec,
                                                 timeout_envvar=self.timeout_envvar):
                            self.data_references.__exit__(*args)
            except Exception:
                print("Exception encountered while uploading fidelity log. Exception will be ignored to avoid a run failure.")
                traceback.print_exc()


class TrackUserError(object):
    def __init__(self, config):
        self.single_instance = False
        self.track_error_context_manager = TrackError(user_error=True)
        self.compliant_user_error_path = azureml_globals.get_compliant_user_error_path()
        self.history_available = False
        # Check for the need to track user error regardless of azureml presence.
        # One such case is when output collection is disabled - even though azureml is
        # present, run history context manager will not run.
        skip_import_check_key = "SkipHistoryImportCheck"
        if config is None or skip_import_check_key not in config or not config[skip_import_check_key] == "True":
            try:
                from azureml.history._tracking import get_history_context_manager
                self.history_available = True
            except ImportError:
                pass

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.compliant_user_error_path:
            if exc_type is None:
                return

            # sys.exit(0) also shouldn't get flagged as a user error.
            if exc_type == SystemExit and (exc_val.code is None or exc_val.code == 0):
                return

            error_response = {
                "Error": {
                    "Code": "UserError",
                    "Message": str(exc_val)
                }
            }
            if isinstance(exc_val, BaseException):
                error_response["Error"]["DebugInfo"] = {
                    "Type": type(exc_val).__name__,
                    "Message": str(exc_val),
                    "StackTrace": ''.join(traceback.format_tb(exc_tb))
                }
            payload = {
                "Name": "Microsoft.MachineLearning.Run.Error",
                "Data": {
                    "RunId": "{0}".format(azureml_globals.run_id),
                    "ErrorResponse": error_response,
                    "MessageLogMode": "NotAllowed"
                }
            }
            import json
            with open(self.compliant_user_error_path, 'w') as outfile:
                json.dump(payload, outfile)
            print("[{}] User error detected and reported on compliant job.".format(datetime.datetime.utcnow().isoformat()))
            return

        if not self.history_available:
            self.track_error_context_manager.__exit__(exc_type, exc_val, exc_tb)


class TrackError(object):
    def __init__(self, error_message_prefix=None, user_error=False, check_user_error_by_type=False, is_compliant=False):
        self.single_instance = False
        self.error_message_prefix = error_message_prefix if error_message_prefix else ""
        self.user_error = user_error
        self._check_user_error_by_type = check_user_error_by_type
        self.job_task_error_path = azureml_globals.get_job_task_error_path()
        self.is_compliant = is_compliant

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type is None:
            return

        # sys.exit(0) also shouldn't get flagged as a user error.
        if exc_type == SystemExit and (exc_val.code is None or exc_val.code == 0):
            return

        # Job execution mode is a concept specific to Singularity, it determines how user program will be launched. AML only supports basic mode. 
        # For basic mode, CR will be used, and jobs will not use control scripts. For managed mode, we classify all the errors as UserError
        job_execution_mode = os.getenv('JOB_EXECUTION_MODE')
        user_error_for_unsupported_mode = job_execution_mode != None

        error_code = "UserError" if self.user_error or user_error_for_unsupported_mode else "ServiceError"
        if self._check_user_error_by_type:
            try:
                from azureml.exceptions import UserErrorException
                if issubclass(exc_type, UserErrorException):
                    error_code = "UserError"
            except Exception:
                pass
        
        try:
            exception_message = str(exc_val)
        except Exception:
            exception_message = "No explicit exception message with error code {}".format(error_code)
            print("Failed to parse the exception message with exception type {} and error code {}".format(type(exc_val).__name__, error_code))

        if error_code != "UserError" and isinstance(exc_val, BaseException):
            if ("UserError" in exception_message
                    and "Received too many requests in a short amount of time" in exception_message):
                error_code = "UserError"
            elif ('It is required that you pass in a value for the \"algorithms\" argument when calling decode()' in exception_message
                        or "No module named 'ruamel'" in exception_message):
                error_code = "UserError"
            elif ('Using \'method_whitelist\' with Retry is deprecated and will be removed in v2.0.' in exception_message
                    and 'Use \'allowed_methods\' instead' in exception_message):
                error_code = "UserError"
            elif 'cannot import name \'ParamSpec\' from \'typing_extensions\'' in exception_message:
                exception_message = "The python environment contains incompatible version of \"azure-core\" and \"typing-extensions\". Please rebuild the environment with the latest version of \"azureml-core\" to fix it. Original exception: " + exception_message
                error_code = "UserError"
            elif 'cannot import name \'SerializationError\' from \'azure.core.exceptions\'' in exception_message:
                exception_message = "The python environment contains incompatible version of \"azure-core\" and \"msrest\". Please rebuild the environment with the latest version of \"azureml-core\" to fix it. "  \
                                    "For more details, please refer to: https://docs.microsoft.com/en-us/azure/machine-learning/how-to-troubleshoot-serialization-error. Original exception: " + exception_message
                error_code = "UserError"
            elif 'your generated code is out of date and must be regenerated with protoc' in exception_message:
                exception_message = "The python environment is broken by breaking change from \"protobuf\". Please rebuild the environment with the latest version of \"azureml-core\" to fix it. " \
                                    "For more details, please refer to: https://docs.microsoft.com/en-us/azure/machine-learning/how-to-troubleshoot-protobuf-descriptor-error. Original exception: " + exception_message
                error_code = "UserError"
            elif type(exc_val).__name__ == "ServiceException":
                # Set metrics related errors as user errors
                if "Code: 400" in exception_message:
                    if (("(ValidationError) Metric Document is too large" in exception_message)
                            or ("(UserError) Too many metrics for this run" in exception_message)
                            or ("(UserError) A field of the entity is over the size limit" in exception_message)
                            or ("(UserError) Metric value count exceeds limit of 1000000" in exception_message)
                            or ("(UserError) MetricV2Dto.Name/Length" in exception_message and "exceeds the limit" in exception_message)
                            or ("(UserError) MetricV2Dto.Columns/Count" in exception_message and "exceeds the limit" in exception_message)
                            or ("(UserError) MetricV2Dto.Value/Count" in exception_message and "exceeds the limit" in exception_message)):
                        error_code = "UserError"
                elif "Code: 429" in exception_message:
                    if ("(RequestThrottled) Too Many requests" in exception_message):
                        error_code = "UserError"
            elif type(exc_val).__name__ == "HttpOperationError":
                if ("Operation returned an invalid status code 'Metric Document is too large" in exception_message):
                    error_code = "UserError"
            elif type(exc_val).__name__ == "RuntimeError":
                # Set write streams authentication exception as user error explicitly
                if ("ScriptExecution.WriteStreams.Authentication" in exception_message and
                        "failed with status code 'Forbidden'" in exception_message):
                    error_code = "UserError"
                if ("can't start new thread" in exception_message and self.is_compliant == False):
                    error_code = "UserError"
            elif type(exc_val).__name__ == "HTTPError":
                if "HTTP Error 400" in exception_message:
                    if (("Blob for" in exception_message and "not present in" in exception_message)
                            or "Failed to create snapshot.  Please delete the snapshot cache and resubmit" in exception_message):
                        error_code = "UserError"
                if "HTTP Error 403" in exception_message:
                    if "Identity does not have permissions" in exception_message:
                        error_code = "UserError"
                if "HTTP Error 404" in exception_message:
                    if "Unable to find snapshot with id" in exception_message:
                        error_code = "UserError"
                    if "The specified blob does not exist" in exception_message:
                        error_code = "UserError"
                if "HTTP Error 401" in exception_message:
                    if "Unauthorized" in exception_message:
                        error_code = "UserError"
                if "HTTP Error 409" in exception_message:
                    if "This operation is not permitted on an archived blob" in exception_message:
                        error_code = "UserError"
            elif type(exc_val).__name__ == "AzureMLException":
                if "Failed to flush task queue within" in exception_message:
                    exception_message = "Timeout occurred while sending metrics. The timeout can be adjusted using AZUREML_RUN_KILL_SIGNAL_TIMEOUT_SEC environment variable. " + exception_message
                    error_code = "UserError"
                if "Compute has no identity provisioned." in exception_message:
                    error_code = "UserError"
                if ("403: AuthorizationPermissionMismatch" in exception_message
                        and "Please make sure the compute or login identity has 'Storage Blob Data Contributor' or 'Storage Blob Data Owner' role in the storage" in exception_message):
                    exception_message = "Authorization Error: please configure storage blob datastore to have the correct role permissions. " + exception_message
                    error_code = "UserError"
            elif type(exc_val).__name__ == "SystemExit":
                if ("Operation RunHistoryFinalization timed out" in exception_message
                        and "The timeout can be adjusted using AZUREML_OUTPUT_UPLOAD_TIMEOUT_SEC environment variable" in exception_message):
                    error_code = "UserError"
            elif type(exc_val).__name__ == "ErrorResponseException":
                if "(UserError) Could not find datastore" in exception_message:
                    error_code = "UserError"
            elif type(exc_val).__name__ == "RecursionError":
                if "maximum recursion depth" in exception_message:
                    error_code = "UserError"
            elif type(exc_val).__name__ == "ExecutionError":
                if ("Error Code: ScriptExecution.WriteStreams" in exception_message
                        and "WriteStreamsException was caused by AuthenticationException" in exception_message):
                    error_code = "UserError"
            elif type(exc_val).__name__ == "NotSupportedDatastoreTypeError":
                    error_code = "UserError"
            elif type(exc_val).__name__ == "DatasetExecutionException":
                if "Error Code: ScriptExecution.WriteStreams.NotFound" in exception_message:
                    error_code = "UserError"
            elif type(exc_val).__name__ == "IsADirectoryError":
                exception_message = "Directory and file have the same name. Please change either name. " + exception_message
                error_code = "UserError"
            elif ('Git is not installed.' in exception_message
                  or "Authentication failed for git repository" in exception_message):
                error_code = "UserError"

        error_response = {
            "Error": {
                "Code": error_code,
                "Message": str(self.error_message_prefix) + exception_message
            }
        }
        if isinstance(exc_val, BaseException):
            error_response["Error"]["DebugInfo"] = {
                "Type": type(exc_val).__name__,
                "Message": exception_message,
                "StackTrace": ''.join(traceback.format_tb(exc_tb))
            }

        # CM communication to hosttool to log the exception in error file, in given format
        if self.job_task_error_path:
            details = []
            message = ""
            if error_code == "ServiceError":
                message = exception_message # checking compliant ServiceError, to classify as non-PII
                if self.is_compliant:
                    details.append({"Key":"Reason", "Value": message})
                    details.append({"Key":"StackTrace",  "Value":''.join(traceback.format_tb(exc_tb))})
            else: # if UserError it should be considered as NonCompliantReason, indepedent of script
                details.append({"Key":"NonCompliantReason", "Value":exception_message})
            error_hierarchy = error_code + "/" + type(exc_val).__name__
            error_format = {
                "Code": error_code,
                "Message": message,
                "Category":error_code ,
                "ExitCode": None,
                "ErrorHierarchy": error_hierarchy,
                "Details": details
            }
            print("[{}] Writing error with error_code {} and error_hierarchy {} to hosttool error file located at {}".format(datetime.datetime.utcnow().isoformat(), error_code, error_hierarchy, self.job_task_error_path))
            import json
            try:
                with open(self.job_task_error_path, 'w') as outfile:
                    json.dump(error_format, outfile)
            except Exception as ex:
                print("[{}]Failed to write to hosttool error file {} with exception {}".format(datetime.datetime.utcnow().isoformat(), self.job_task_error_path, ex))
        else:
            print("[{}]Hosttool Job Error file path is not set".format(datetime.datetime.utcnow().isoformat()))

        # Report error to RH for all the run types, and report UserError only, in case of PT runs
        if ((os.getenv("AZ_BATCHAI_IS_PARALLEL_TASKS", "False") == "False") or (error_code == "UserError")):
            set_run_error(error_response, caller="context_managers")



class RunHistory(object):
    def __init__(self, config):
        self.single_instance = True
        try:
            from azureml.history._tracking import is_multi_instance_supported
            self.single_instance = not is_multi_instance_supported()
        except ImportError:
            pass
        self.history_config = config if config is not None else {}
        self.history_context = None
        self.timeout_envvar = 'AZUREML_OUTPUT_UPLOAD_TIMEOUT_SEC'
        self.exit_timeout_sec = int(os.getenv(self.timeout_envvar, "3600"))
        # For older versions of SDK there is no way to tell SDK to not upload outputs.
        # Double upload results in run failure.
        # Therefore, as a work around set OUTPUTS_DIR to a non existent folder (random guid).
        # OutputDirReset takes care of that.
        import uuid
        self.output_dir_reset = OutputDirReset("azureml_{}".format(str(uuid.uuid4())))

    def __enter__(self):
        if azureml_globals.get_compliant_user_error_path():
            print("[{}] RunHistoryCM disabled for the compliant job.".format(datetime.datetime.utcnow().isoformat()))
            return
        try:
            from azureml.history._tracking import get_history_context_manager
        except ImportError:
            print("Warning: Unable to import azureml.history. Output collection disabled.")
            return
        print("[{}] Entering Run History Context Manager.".format(datetime.datetime.utcnow().isoformat()))
        if azureml_globals.is_batchai_target_type:
            self.history_config["only_in_process_features"] = True
            # for backward compatibility with older versions of SDK
            # setting skip_track_logs_dir to True disables ./logs upload by sdk
            self.history_config["skip_track_logs_dir"] = True
            # set to empty so run history does not attempt to double upload the files
            self.history_config["DirectoriesToWatch"] = []
        with self.output_dir_reset:
            self.history_context = get_history_context_manager(**self.history_config)
            self.history_context.__enter__()

    def __exit__(self, *args):
        if self.history_context:
            with get_dependency_timer(name="RunHistoryFinalization"):
                with get_timeout_handler(operation_name="RunHistoryFinalization",
                                         timeout_sec=self.exit_timeout_sec,
                                         timeout_envvar=self.timeout_envvar):
                    with self.output_dir_reset:
                        self.history_context.__exit__(*args)

class OutputDirReset(object):

    def __init__(self, dir_name):
        self.new_dir_name = dir_name
        self.old_dir_name = ""
        self.should_redirect = self._should_disable_output_upload()
        try:
            import azureml.history._tracking
        except ImportError:
            self.should_redirect = False
            pass

    def __enter__(self):
        if self.should_redirect:
            import azureml.history._tracking
            self.old_dir_name = azureml.history._tracking.OUTPUTS_DIR
            azureml.history._tracking.OUTPUTS_DIR = self.new_dir_name

    def __exit__(self, *args):
        if self.should_redirect:
            import azureml.history._tracking
            azureml.history._tracking.OUTPUTS_DIR = self.old_dir_name

    def _should_disable_output_upload(self):
        if not azureml_globals.is_batchai_target_type:
            return False
        try:
            # output upload was removed from user space when execute_job_release was added
            from azureml.history._tracking import execute_job_release
            return False
        except ImportError:
            return True


try:
    from azureml.exceptions import AzureMLException, UserErrorException

    class DatasetMountValidationException(UserErrorException):
        def __init__(self, exception_message, **kwargs):
            super(DatasetMountValidationException, self).__init__(exception_message, **kwargs)

    class DatasetExecutionException(UserErrorException):
        def __init__(self, exception_message, **kwargs):
            super(DatasetExecutionException, self).__init__(exception_message, **kwargs)
except:
    UserErrorException = RuntimeError
    pass


class Datasets(object):
    _input_regex = re.compile("DatasetConsumptionConfig:([a-zA-Z0-9_]+)")
    _output_regex = re.compile("DatasetOutputConfig:([a-zA-Z0-9_]+)")
    _input_env_var_prefix = 'AZURE_ML_INPUT'
    _output_env_var_prefix = 'AZURE_ML_OUTPUT'

    def __init__(self, config):
        self.config = config
        self.telemetry_client = None
        self.datasets = None
        self.host_dirs_to_clean_up = []

        # If Sidecar Container is running then DatasetContextManager will have been run there, so don't import it.
        if not azureml_globals.sidecar_running and not azureml_globals.common_runtime_data_cap_running:
            try:
                from azureml.data.context_managers import DatasetContextManager
            except ImportError:
                if len(config) > 0:
                    raise ImportError(
                        "azureml-core is not installed. Dataset cannot be used without azureml-core. Please "
                        "make sure azureml-core is installed by specifying it in the conda dependencies."
                    )

            self._ensure_dataprep(config)

            self.datasets = DatasetContextManager(self.config)

    def set_telemetry_client(self, telemetry_client):
        self.telemetry_client = telemetry_client

    @staticmethod
    def process_arguments(arguments):
        if not arguments:
            return

        def sub(search_fn, sub_fn, value, prefix):
            match = search_fn(value)
            while match:
                if os.getenv('{}_{}'.format(prefix, match.group(1))) is None:
                    value = sub_fn('${}'.format(match.group(1)), value, count=1)
                else:
                    value = sub_fn('${}_{}'.format(prefix, match.group(1)), value, count=1)
                match = search_fn(value)
            return value

        for i in range(len(arguments)):
            arguments[i] = sub(Datasets._input_regex.search, Datasets._input_regex.sub, arguments[i], Datasets._input_env_var_prefix)
            arguments[i] = sub(Datasets._output_regex.search, Datasets._output_regex.sub, arguments[i], Datasets._output_env_var_prefix)

    def __enter__(self):
        if self.datasets:
            with get_dependency_timer(name="Dataset", telemetry_client=self.telemetry_client):
                self._generate_path_on_compute()
                try:
                    self.datasets.__enter__()
                except Exception as e:
                    # Python error which is not derived from UserErrorException is categorized as system error and triggers alert like
                    # this incident https://portal.microsofticm.com/imp/v3/incidents/details/192705581/home.
                    # The try-catch here is to re-categorized error raised by old SDK.
                    self._map_and_reraise_user_error(e)
                    raise
                if azureml_globals.in_sidecar:
                    self._strip_hostfs_from_path_on_compute()

    def __exit__(self, *args):
        if self.datasets:
            with get_dependency_timer(name="DatasetFinalization", telemetry_client=self.telemetry_client):
                try:
                    self.datasets.__exit__(*args)
                except Exception as e:
                    self._map_and_reraise_user_error(e)
                    raise
                finally:
                    if azureml_globals.in_sidecar:
                        self._cleanup_host_dirs()

    def _add_host_dir_for_clean_up(self, path):
        self.host_dirs_to_clean_up.append(path)

    def _cleanup_host_dirs(self):
        try:
            import shutil
            print("[{}] Removing absolute paths from host...".format(datetime.datetime.utcnow().isoformat()))
            for dir in self.host_dirs_to_clean_up:
                shutil.rmtree(dir, ignore_errors=True)
        except Exception as e:
            print("[{}] Got Exception when removing paths from host: {}".format(datetime.datetime.utcnow().isoformat(), e))
            pass

    def _update_dataset_env_vars(self, dataset_name, target_path, env_var_prefix):
        os.environ[dataset_name] = target_path
        # added for backwards compatibility with older SDKs
        os.environ[dataset_name.upper()] = target_path
        os.environ["AZUREML_DATAREFERENCE_{}".format(dataset_name)] = target_path
        os.environ['{}_{}'.format(env_var_prefix, dataset_name)] = target_path

    def _is_input(self, config):
        return config.get("DataLocation") and config.get("Mechanism", "").lower() in ["mount", "download"]

    def _is_output(self, config):
        return config.get("OutputLocation") and config.get("Mechanism", "").lower() in ["mount", "upload"]

    def _generate_path_on_compute(self):
        def do_generate_path_on_compute(user_path_on_compute, unique_name):
            import tempfile
            path_on_compute = None
            if azureml_globals.in_sidecar:
                # In Sidecar use Job temp dir.
                drive, temp_path = os.path.splitdrive(azureml_globals.job_temp_dir)
                hostfs_tmp = os.path.join(azureml_globals.sidecar_hostfs, temp_path.lstrip('/').lstrip('\\'))
                path_on_compute = hostfs_tmp
            else:
                # Otherwise use system default temp.
                path_on_compute = tempfile.gettempdir()
            path_on_compute = os.path.join(path_on_compute, unique_name)
            os.makedirs(path_on_compute, exist_ok=True)
            os.chmod(path_on_compute, mode=0o777)
            # user_path_on_compute is the path the user requested, which can be None.
            if user_path_on_compute:
                # Ensure user_path_on_compute is absolute so no ambiguity when accessing path.
                user_path_on_compute = os.path.abspath(user_path_on_compute)
                if not azureml_globals.in_sidecar:
                    # When not in AzureML-Sidecar the users requested path is the path_on_compute to use.
                    path_on_compute = user_path_on_compute
            else:
                # When `user_path_on_compute` is None a path is generated for the user.
                user_path_on_compute = path_on_compute

            if azureml_globals.in_sidecar and user_path_on_compute.startswith(azureml_globals.sidecar_hostfs):
                # Strip hostfs from user_path_on_compute for a clean view of the path the user wants.
                user_path_on_compute = user_path_on_compute[len(azureml_globals.sidecar_hostfs):]
                user_path_on_compute = self._adjust_root_path(user_path_on_compute)

            # For back compat with pre single data dir we add hostfs to the user_path_on_compute and set path_on_compute to that new path.
            if azureml_globals.in_sidecar and not azureml_globals.single_data_dir:
                drive, path = os.path.splitdrive(user_path_on_compute)
                path_on_compute = os.path.join(azureml_globals.sidecar_hostfs, path.lstrip('/').lstrip('\\'))
                self._add_host_dir_for_clean_up(path_on_compute)

            return path_on_compute, user_path_on_compute

        def get_unique_name(name, unique_id):
            return '{}_{}_{}'.format(name, azureml_globals.run_id, unique_id)

        def prepare_input(input_name, config):
            user_path_on_compute = config.get("PathOnCompute", None)
            dataset_name = config.get("EnvironmentVariableName")
            mechanism = config.get("Mechanism", None)
            mechanism = mechanism.lower() if mechanism is not None else None

            if azureml_globals.enable_detonation_chamber and mechanism == 'download' and user_path_on_compute:
                raise UserErrorException("Detonation Chamber does not support specifying path_on_compute for downloaded data. "
                                         "Please set path_on_compute to None and resubmit.")

            data_loc = config.get("DataLocation", None)
            dataset_json = data_loc.get('Dataset', None) if data_loc else None
            dataset_id = dataset_json.get('Id', dataset_json.get('Name', None)) if dataset_json else None
            path_on_compute, user_path_on_compute = do_generate_path_on_compute(
                user_path_on_compute,
                get_unique_name(input_name, dataset_id))
            config["PathOnCompute"] = path_on_compute
            config["UserPathOnCompute"] = user_path_on_compute

            self._update_dataset_env_vars(dataset_name, path_on_compute, self._input_env_var_prefix)
            if not azureml_globals.in_sidecar:
                print("Set Dataset {}'s target path to {}".format(dataset_name, path_on_compute))

        def prepare_output(output_name, config):
            additional_options = config.get("AdditionalOptions", {})
            user_path_on_compute = additional_options.get("PathOnCompute")

            output_loc = config.get("OutputLocation", None)
            data_path = output_loc.get('DataPath', None) if output_loc else None
            datastore_name = data_path.get('DatastoreName', None) if data_path else None
            path_on_compute, user_path_on_compute = do_generate_path_on_compute(
                user_path_on_compute,
                get_unique_name(output_name, datastore_name))
            if not os.path.exists(path_on_compute):
                azureml_globals._ensure_directory_exists(path_on_compute)
            additional_options["PathOnCompute"] = path_on_compute
            additional_options["UserPathOnCompute"] = user_path_on_compute
            config["AdditionalOptions"] = additional_options

            os.environ[output_name] = path_on_compute
            os.environ['{}_{}'.format(self._output_env_var_prefix, output_name)] = path_on_compute

        
        if isinstance(self.config, list):
            for instance in self.config:
                name = instance.get("Name", None)
                if self._is_input(instance):
                    if not name:
                        raise RuntimeError("Missing name for input data.")
                    prepare_input(name, instance)
                if self._is_output(instance):
                    if not name:
                        raise RuntimeError("Missing name for output data.")
                    prepare_output(name, instance)
        else:
            for key, value in self.config.items():
                if self._is_input(value):
                    prepare_input(key, value)
                if self._is_output(value):
                    prepare_output(key, value)

    @staticmethod
    def _append_paths_to_bind(to_append):
        import json
        extra_args = os.environ.get(azureml_globals.env_sidecar_paths_to_bind)
        if extra_args is not None:
            current_args = json.loads(extra_args)
            to_append = current_args + to_append

        os.environ[azureml_globals.env_sidecar_paths_to_bind] = json.dumps(to_append)

    @staticmethod
    def _adjust_root_path(target):
        # Given a target path starting with "/" or "\": In Windows, drive letter of the job temp dir will be added.
        # In Linux, this function has no effect.
        root_path = os.path.abspath(os.sep)
        job_temp_dir = os.getenv(azureml_globals.env_var_az_batchai_job_temp)
        if job_temp_dir and os.path.exists(job_temp_dir):
            drive, path = os.path.splitdrive(job_temp_dir)
            root_path = drive or root_path
        return os.path.abspath(os.path.join(root_path, target))

    def _strip_hostfs_from_path_on_compute(self):
        paths_to_bind = []

        def do_strip_hostfs_from_path_on_compute(name, config):
            if self._is_input(config):
                dataset_name = config.get("EnvironmentVariableName")

                path_on_compute = config.get("PathOnCompute", None)
                user_path_on_compute = config.get("UserPathOnCompute", None)

                # Default behavior is single file input dataset. Read the new path_on_compute from env var as
                # dataset modifies the var to add file path.
                if azureml_globals.single_file_input_dataset:
                    single_file_path_on_compute = os.environ.get('{}_{}'.format(self._input_env_var_prefix, dataset_name)) if dataset_name else None
                    if azureml_globals.single_data_dir:
                        # Get single file path relative to actual path_on_compute, then join user_path_on_compute and the single file together.
                        relative_single_file_path = os.path.relpath(single_file_path_on_compute, path_on_compute)
                        if relative_single_file_path != '.':
                            user_path_on_compute = os.path.join(user_path_on_compute, relative_single_file_path)
                    path_on_compute = single_file_path_on_compute

                path_on_compute = strip_hostfs_prefix(path_on_compute)

                if azureml_globals.single_data_dir:
                    # Set Dataset Environment Variables to reference user_path_on_compute
                    print("Set Dataset {}'s target path to {}".format(dataset_name, user_path_on_compute))
                    self._update_dataset_env_vars(dataset_name, user_path_on_compute, self._input_env_var_prefix)
                    # Setup path binding from host path to user specified path.
                    paths_to_bind.append('{}:{}'.format(path_on_compute, user_path_on_compute))
                else:
                    paths_to_bind.append(path_on_compute)
                    print("Set Dataset {}'s target path to {}".format(dataset_name, path_on_compute))
                    self._update_dataset_env_vars(dataset_name, path_on_compute, self._input_env_var_prefix)
            else:  # Output
                additional_options = config.get("AdditionalOptions", {})
                path_on_compute = additional_options.get("PathOnCompute")
                user_path_on_compute = additional_options.get("UserPathOnCompute")

                path_on_compute = strip_hostfs_prefix(path_on_compute)

                if azureml_globals.single_data_dir:
                    print("Set OutputDataset {}'s target path to {}".format(name, user_path_on_compute))
                    paths_to_bind.append('{}:{}'.format(path_on_compute, user_path_on_compute))
                    os.environ[name] = user_path_on_compute
                    os.environ['{}_{}'.format(self._output_env_var_prefix, name)] = user_path_on_compute
                elif os.path.isabs(path_on_compute):
                    print("Set OutputDataset {}'s target path to {}".format(name, path_on_compute))
                    paths_to_bind.append(path_on_compute)
                    os.environ[name] = path_on_compute
                    os.environ['{}_{}'.format(self._output_env_var_prefix, name)] = path_on_compute

        def strip_hostfs_prefix(path):
            # Remove sidecar_hostfs from absolute paths so that environment variables reflect the path on compute
            # the user script will see. If path is absolute we need to tell hosttools to make it available in user
            # container.
            if os.path.isabs(path):
                path = path[len(azureml_globals.sidecar_hostfs):]
                path = self._adjust_root_path(path)
            return path
                    
        if isinstance(self.config, list):
            for instance in self.config:
                name = instance.get("Name", None)
                if not name:
                    raise RuntimeError("Missing data name.")
                do_strip_hostfs_from_path_on_compute(name, instance)
        else:
            for key, value in self.config.items():
                do_strip_hostfs_from_path_on_compute(key, value)

        if len(paths_to_bind) > 0:
            self._append_paths_to_bind(paths_to_bind)

    def _ensure_dataprep(self, config):
        if len(config) == 0:
            return

        try:
            import azureml.dataprep
        except ImportError:
            raise ImportError(
                "azureml-dataprep is not installed. Dataset cannot be used without azureml-dataprep. Please "
                "make sure azureml-dataprep[fuse,pandas] is installed by specifying it in the conda dependencies. "
                "pandas is optional and should be only installed if you intend to create a pandas DataFrame from the "
                "dataset."
            )

        def ensure_fuse(data_config):
            mode = data_config.get("Mechanism")
            if mode == "mount":
                try:
                    from fuse import FUSE
                except ImportError:
                    raise ImportError(
                        "fusepy is not installed. Dataset cannot be mounted without fusepy. Please make sure "
                        "azureml-dataprep[fuse] is installed by specifying it in the conda dependencies. "
                        "if you intend to create a pandas DataFrame from the dataset, then you should install "
                        "azureml-dataprep[fuse,pandas]."
                    )

        if isinstance(config, list):
            for instance in config:
                ensure_fuse(instance)
        else:
            for value in config.values():
                ensure_fuse(value)

    def _map_and_reraise_user_error(self, e):
        mapped = None
        try:
            if not isinstance(e, AzureMLException):  # new version of SDK will raise AzureMLException
                if 'Cannot mount dataset.' in str(e) or 'is already mounted.' in str(e):
                    mapped = DatasetMountValidationException(str(e))
                elif 'Unable to find libfuse' in str(e):
                    mapped = DatasetExecutionException(str(e))
                else:
                    from azureml.dataprep import ExecutionError
                    if isinstance(e, ExecutionError):
                        mapped = DatasetExecutionException(str(e))
        except Exception:
            pass
        if mapped is not None:
            # raise mapped from e  # This syntax is not supported in py2 and will fail at import time. More details in https://icm.ad.msft.net/imp/v3/incidents/details/194193871/home
            raise mapped


class DataStores(object):
    def __init__(self, config):
        self.config = config
        self.timeout_envvar = 'AZUREML_DATASTORE_UPLOAD_TIMEOUT_SEC'
        self.exit_timeout_sec = int(os.getenv(self.timeout_envvar, "600"))
        self.timeout_enabled = True
        self.telemetry_client = None
        self.data_references = None

        # If Sidecar Container is running then DatastoreContextManager will have been run there, so don't import it.
        if not azureml_globals.sidecar_running:
            try:
                from azureml.data.context_managers import DatastoreContextManager
            except ImportError:
                print("Warning: Unable to import azureml.data. Download/Upload disabled.")
                return

            self.data_references = DatastoreContextManager(self.config)

    def set_telemetry_client(self, telemetry_client):
        self.telemetry_client = telemetry_client

    def __enter__(self):
        if self.data_references:
            with get_dependency_timer(name="DataStoreDownload", telemetry_client=self.telemetry_client):
                if azureml_globals.in_sidecar:
                    self._process_paths_for_sidecar()
                self.start_download()

    def __exit__(self, *args):
        if self.data_references:
            with get_dependency_timer(name="DataStoreUpload", telemetry_client=self.telemetry_client):
                with get_timeout_handler(timeout_enabled=self.timeout_enabled,
                                         operation_name="DataStoreUpload",
                                         timeout_sec=self.exit_timeout_sec,
                                         timeout_envvar=self.timeout_envvar):
                    self.data_references.__exit__(*args)

    def start_download(self):
        import tempfile

        run_id = azureml_globals.run_id
        temp_dir = tempfile.gettempdir()
        lock_file = os.path.join(temp_dir, '{}-datastore.lock'.format(run_id))
        success_file = os.path.join(temp_dir, '{}-datastore.success'.format(run_id))
        waiter = azureml_globals.BackoffWaiter()

        if not run_id:
            raise RuntimeError("No Run ID is present. Datastore Context Manager cannot be used outside of a run.")

        azureml_globals.run_once_multiprocess(
            self.data_references.__enter__, "downloading input data references", waiter, lock_file, success_file
        )

    @staticmethod
    def _is_upload(config):
        return config.get("Mode", "mount").lower() == 'upload'

    @staticmethod
    def _is_download(config):
        return config.get("Mode", "mount").lower() == 'download'

    def _process_paths_for_sidecar(self):
        paths_to_bind = []
        for key, value in self.config.items():

            target_path = value.get("PathOnCompute", None)
            datastore_name = value.get("DataStoreName")

            if azureml_globals.enable_detonation_chamber and self._is_download(value) and not os.path.abspath(target_path):
                raise UserErrorException("Detonation Chamber does not support specifying path_on_compute for downloaded data. "
                                         "Please set path_on_compute to None and resubmit.")

            # If target_path is set need to figure out if it is using `../` to get out of cwd.
            # In DatastoreContextManager path_on_compute is always prepended with `datastore_name` so it should be a child of cwd,
            # it is possible for a customer to use `../` in a path to go above cwd.
            if target_path:
                norm_target_path = ""
                if os.path.isabs(target_path):
                    drive, path = os.path.splitdrive(target_path)
                    target_path = os.path.join(azureml_globals.sidecar_hostfs, path.lstrip('/').lstrip('\\'))
                    value["PathOnCompute"] = target_path
                    if self._is_upload(value):
                        target_path = os.path.dirname(target_path)
                    norm_target_path = target_path
                else:
                    # Path is relative so we need to check if it uses '..' to escape cwd.
                    if self._is_upload(value):
                        target_path = os.path.dirname(target_path)
                        norm_target_path = os.path.normpath(target_path)
                    else:
                        # Prepend DataStoreName to non-upload target_path because that's what DatastoreContextManager does.
                        target_path = os.path.join(datastore_name, target_path)
                        # Normalize target path to not include redundant `../`
                        norm_target_path = os.path.normpath(target_path)

                abs_norm_target_path = os.path.abspath(norm_target_path)
                # If abs_norm_target_path doesn't start with cwd then we need to make sure it's mounted into main Container.
                if not abs_norm_target_path.startswith(os.getcwd()):
                    path_to_bind = abs_norm_target_path
                    if abs_norm_target_path.startswith(azureml_globals.sidecar_hostfs):
                        path_to_bind = path_to_bind[len(azureml_globals.sidecar_hostfs):]
                    if azureml_globals.single_data_dir:
                        import tempfile
                        # In Sidecar use Job temp dir.
                        _, temp_path = os.path.splitdrive(azureml_globals.job_temp_dir)
                        hostfs_tmp = os.path.join(azureml_globals.sidecar_hostfs, temp_path.lstrip('/').lstrip('\\'))
                        path_on_compute = tempfile.mkdtemp(dir=hostfs_tmp)
                        value["PathOnCompute"] = path_on_compute
                        # Strip hostfs from temp dir
                        path_to_bind = '{}:{}'.format(path_on_compute[len(azureml_globals.sidecar_hostfs):], path_to_bind)

                    paths_to_bind.append(path_to_bind)

        if len(paths_to_bind) > 0:
            print('Sidecar adding paths_to_bind: {}'.format(paths_to_bind))
            Datasets._append_paths_to_bind(paths_to_bind)


class UserExceptions(object):
    def __init__(self, config):
        self.single_instance = True
        self.config = config
        self.client = None

    def __enter__(self):
        pass

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class ParallelRunBackend(object):
    def __init__(self, config):
        self.process = None

    def __enter__(self):
        print("Enter ParallelRunBackend context ...")
        is_backend_run_in_sidecar = self._get_env("AZ_BATCH_IS_BACKEND_RUN_IN_SIDECAR")
        if not is_backend_run_in_sidecar:
            print("ParallelRunBackend is configured to run in user container.")
            return

        # Step 1: check if it's a parallel task job
        is_parallel_tasks  = self._get_env("AZ_BATCHAI_IS_PARALLEL_TASKS")
        if not is_parallel_tasks:
            print("It's not a Parallel Task job. Do Nothing in ParallelRunBackend context manager.")
            return

        cwd = os.getcwd()
        print("Current working directory: {}".format(cwd))

        # Step 2: extract the PRS launch command line from AZ_LS_JOB_INFO
        import json
        job_json_file_path = os.path.join(os.getenv("AZ_BATCH_TASK_WORKING_DIR"), "job.json")
        print("Found job json file: {}".format(job_json_file_path))
        job_json_file_path_in_sidecar = self._to_sidecar_fs_path(job_json_file_path)
        if os.path.exists(job_json_file_path_in_sidecar):
            print("Loading job json from: {}".format(job_json_file_path_in_sidecar))
            with open(job_json_file_path_in_sidecar) as f:
                job_info = json.load(f)
        else:
            # This branch is for dev testing only
            # We only target to run PRS backend in sidecar when in detonation chamber
            # TODO: handle the job json download from blob url case when targeting to support non-dc compute
            print("Loading job json from env: AZ_LS_JOB_INFO")
            AZ_LS_JOB_INFO = os.getenv('AZ_LS_JOB_INFO')
            job_info = json.loads(AZ_LS_JOB_INFO)

        parallel_tasks_settings = job_info["parallel_tasks_settings"]
        command_line_args = parallel_tasks_settings["worker_settings"]["command_line_args"]

        # Step 3: Expand and resolve the commandline arguments.
        import shlex
        all_args = shlex.split(command_line_args)

        # Find entry script argument and remove redundant arguments for context_manager_injector,
        # e.g. "-i xxx:xxxContextManager".
        driver_args = [arg for arg in all_args if 'driver/amlbi_main.py' in arg or 'driver\\amlbi_main.py' in arg]
        if len(driver_args) < 1:
            raise RuntimeError("Invalid entry script for ParallelRunStep job. Expected: 'driver/amlbi_main.py',"
                               " actual: {}.".format(command_line_args))
        driver_pos = all_args.index(driver_args[0])
        prs_args = all_args[driver_pos:]

        # Resolve and expand arguments
        print("Before resolved command line args: {}".format(prs_args))
        Datasets.process_arguments(prs_args)
        prs_args = [self._convert_powershell_style_env_to_cmd_style(arg) for arg in prs_args]
        prs_args = [os.path.expandvars(arg) for arg in prs_args]

        prs_cmd = ['python'] + prs_args
        print("Launch PRS cmd: {}".format(prs_cmd))

        import subprocess
        self.process = subprocess.Popen(prs_cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        print("Start ParallelRunBackend done.")

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.process:
            print("Wait for ParallelRunBackend process exit ...")
            self.process.communicate()
            print("ParallelRunBackend process exit successfully.")
        else:
            print("ParallelRunBackend process is none.")

    @staticmethod
    def _get_env(env_name):
        return os.environ.get(env_name, "").lower().strip() in ["true", "1", "yes"]

    @staticmethod
    def _to_sidecar_fs_path(input_path):
        drive, path = os.path.splitdrive(input_path)
        path_in_sidecar = os.path.join(azureml_globals.sidecar_hostfs, path.lstrip('/').lstrip('\\'))
        return path_in_sidecar

    @staticmethod
    def _convert_powershell_style_env_to_cmd_style(s: str):
        if "$env:" in s:
            return s.replace("$env:", "$")
        else:
            return s
