# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import errno
import os
import datetime

try:
    # For Python 3.0 and later
    from urllib.parse import quote
except ImportError:
    # Fall back to Python 2's urllib
    from urllib import quote


def int_env_var_or_default(key, default):
    value = os.environ.get(key)
    return int(value) if value else default


# Azure Batch(AI) nodes
az_batch_master_node = os.environ.get("AZ_BATCH_MASTER_NODE", os.environ.get("AZ_BATCHAI_JOB_MASTER_NODE_IP"))
env_var_az_batchai_cluster_name = "AZ_BATCHAI_CLUSTER_NAME"
env_var_prefix_az_batch = "AZ_BATCH"
env_var_az_batchai_run_status = "AZ_BATCHAI_RUN_STATUS"
env_var_az_batchai_stdouterr_dir = "AZ_BATCHAI_STDOUTERR_DIR"
env_var_az_batchai_log_upload_failed = "AZ_BATCHAI_LOG_UPLOAD_FAILED"
env_var_az_batch_node_id = "AZ_BATCH_NODE_ID"
env_var_az_batchai_job_config = "AZ_BATCHAI_JOB_CONFIG"
env_var_az_batchai_job_temp = "AZ_BATCHAI_JOB_TEMP"
env_var_az_batchai_job_work_dir = "AZ_BATCHAI_JOB_WORK_DIR"
env_var_az_batchai_enable_detonation_chamber = "AZ_BATCHAI_ENABLE_DETONATION_CHAMBER"


def get_process_name():
    process_name = "{}{}".format(os.environ.get("AZ_BATCHAI_TASK_TYPE", ""),
                         os.environ.get("AZ_BATCHAI_TASK_INDEX", ""))
    return process_name if process_name else "main"


run_id = os.environ.get("AZUREML_RUN_ID")
data_container_id = os.environ.get("AZUREML_DATA_CONTAINER_ID")

env_var_target_type = "AZUREML_TARGET_TYPE"
target_type = str(os.environ.get(env_var_target_type))
cluster_target_type = "cluster"
batchai_target_type = "batchai"
container_target_type = "container"
aisc_target_type = "aisc"

is_cluster_target_type = target_type.lower() == cluster_target_type
is_hdi = is_cluster_target_type
is_batchai_target_type = target_type.lower() == batchai_target_type
is_container_target_type = target_type.lower() == container_target_type
is_aisc_target_type = target_type.lower() == aisc_target_type

log_directory_path = os.environ.get("AZUREML_LOGDIRECTORY_PATH")
az_batch_is_current_node_master = os.environ.get("AZ_BATCH_IS_CURRENT_NODE_MASTER", "true").lower() == "true"


def _ensure_directory_exists(directory):
    try:
        os.makedirs(directory)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise


def get_compliant_user_error_path():
    error_path = os.environ.get("AZ_BATCHAI_COMPLIANT_USER_ERROR_PATH")
    if error_path and os.path.isdir(os.path.dirname(error_path)):
        return error_path


def get_fidelity_log_data_store():
    return os.environ.get("AZ_BATCHAI_FULL_FIDELITY_DATA_STORE")


def get_fidelity_log_directory():
    return os.environ.get("AZ_BATCHAI_JOB_TEMP_FULL_LOG_DIRECTORY")


def get_fidelity_log_path_on_data_store():
    return os.environ.get("AZ_BATCHAI_FULL_FIDELITY_PATH_ON_DATA_STORE", "/logs/" + run_id)


def get_input_dir():
    if is_batchai_target_type:
        return os.environ.get("AZ_BATCHAI_INPUT_AZUREML")
    elif is_container_target_type:
        return os.environ.get("AZUREML_ACI_MOUNT_PATH")
    elif is_aisc_target_type:
        return os.environ.get("AZ_BATCHAI_INPUT_AZUREML")
    else:
        raise Exception("input dir not yet defined for this target type: " + target_type)


def get_job_work_dir():
    return os.environ.get(env_var_az_batchai_job_work_dir)


def get_datastore_context_manager(options):
    from context_manager_injector import create_wrapped_context_manager
    for pair in options.inject:
        if pair.split(":")[0] == "DataStoreCopy":
            datastore_cm = create_wrapped_context_manager(pair)
            return datastore_cm
    return None


def get_dataset_context_manager(options):
    from context_manager_injector import create_wrapped_context_manager
    for pair in options.inject:
        if pair.split(":")[0] == "Dataset":
            dataset_cm = create_wrapped_context_manager(pair)
            return dataset_cm
    return None


def get_job_task_error_path():
    return os.environ.get("AZUREML_JOB_TASK_ERROR_PATH")


# Azure ML environment variable prefix
env_var_prefix_azureml = "AZUREML"

# Azure ML nodes
env_var_node_count = "AZUREML_NODE_COUNT"
# secondary instance is changed at runtime
env_var_secondary_instance = "AZUREML_SECONDARY_INSTANCE"

# process
env_var_process_name = "AZUREML_PROCESS_NAME"
pidfile_path = os.environ.get("AZUREML_PIDFILE_PATH")


def write_pid_to_pidfile():
    with open(pidfile_path, "a+") as file:
        file.write(str(os.getpid()))


# ARM related constants
arm_subscription = os.environ.get("AZUREML_ARM_SUBSCRIPTION", "")
arm_resource_group = os.environ.get("AZUREML_ARM_RESOURCEGROUP")
arm_workspace_name = os.environ.get("AZUREML_ARM_WORKSPACE_NAME", "")
workspace_scope = quote(os.environ.get("AZUREML_WORKSPACE_SCOPE"))

# service endpoint
service_endpoint = os.environ.get("AZUREML_SERVICE_ENDPOINT")
service_cert_endpoint = os.environ.get("AZUREML_SERVICE_CERT_ENDPOINT")
run_history_endpoint = os.environ.get("AZUREML_RUN_HISTORY_SERVICE_ENDPOINT")

# experiment and run related constants
project_name = os.environ.get("AZUREML_ARM_PROJECT_NAME", "")
experiment_scope = quote(os.environ.get("AZUREML_EXPERIMENT_SCOPE"))
env_var_framework = "AZUREML_FRAMEWORK"

spark_scheduler_type = "spark"
dask_scheduler_type = "dask"
none_scheduler_type = "none"

setup_directory_name = "azureml-environment-setup"

# Run token related constants.
env_var_run_token_expiry = "AZUREML_RUN_TOKEN_EXPIRY"
env_var_run_token = "AZUREML_RUN_TOKEN"

# log constants
# distrib logs changes dynamically
env_var_distrib_logs = "AZUREML_DISTRIB_LOGS"
instrumentation_key = os.environ.get("AZUREML_INSTRUMENTATION_KEY")
env_var_azure_core_collect_telemetry = "AZURE_CORE_COLLECT_TELEMETRY"

control_log_path = os.environ.get("AZUREML_CONTROLLOG_PATH")

# driver log path can change dynamically
env_var_driverlog_path = "AZUREML_DRIVERLOG_PATH"
env_var_driver_log_timeout = 'AZUREML_DRIVERLOG_WAIT_TIMEOUT_SEC'
driver_log_timeout_sec = int(os.getenv(env_var_driver_log_timeout, "300"))

env_var_send_telemetry_timeout = 'AZUREML_TELEMETRY_TIMEOUT_SEC'
send_telemetry_timeout_sec = int(os.getenv(env_var_send_telemetry_timeout, "60"))

env_var_job_prep_timeout = 'AZUREML_JOB_PREP_TIMEOUT_SEC'
job_prep_timeout_sec = int(os.getenv(env_var_job_prep_timeout, "7200"))

env_var_job_release_timeout = 'AZUREML_JOB_RELEASE_TIMEOUT_SEC'
job_release_timeout_sec = int(os.getenv(env_var_job_release_timeout, "7200"))

# python constants
env_var_pythonpath = "PYTHONPATH"

# spark constants
pyspark_framework_constant = "PySpark"
pyspark_interactive_framework_constant = "PySparkInteractive"
pyspark_frameworks = [
    pyspark_framework_constant,
    pyspark_interactive_framework_constant
]
env_var_spark_home = "SPARK_HOME"
env_var_pyspark_python = "PYSPARK_PYTHON"
env_var_spark_opts = "SPARK_OPTS"

relay_namespace = os.environ.get("AZUREML_RELAY_NAMESPACE", None)
relay_name = os.environ.get("AZUREML_RELAY_NAME", None)
relay_key = os.environ.get("AZUREML_RELAY_KEY", None)
use_jeg = os.environ.get("AZUREML_RELAY_USE_JEG", "False") == "True"
interactive_run_time_in_mins = int(os.environ.get("AZUREML_INTERACTIVE_RUN_TIME_IN_MINS", 10))
use_jupyter_lab = os.environ.get("AZUREML_RELAY_USE_JLAB", "False") == "True"

# HDI constants
env_var_local_data_root = "LOCAL_DATA_ROOT"
env_var_local_data_root_override = "LOCAL_DATA_ROOT_OVERRIDE"

# PMI and OMPI constants
env_var_pmi_rank = "PMI_RANK"
env_var_pmi_size = "PMI_SIZE"
env_var_ompi_comm_world_rank = "OMPI_COMM_WORLD_RANK"
env_var_ompi_comm_world_size = "OMPI_COMM_WORLD_SIZE"

# Jupyter constants for the PySpark prototype
jupyter_min_port_range_size = int(os.getenv('EG_MIN_PORT_RANGE_SIZE', '1000'))
jupyter_max_port_range_retries = int(os.getenv('EG_MAX_PORT_RANGE_RETRIES', '5'))
jupyter_log_level = int(os.getenv('EG_LOG_LEVEL', '10'))

# artifact upload constants
# default to a little less than 4 MB, the size limit for artifact chunks
artifact_upload_chunk_size_bytes = int_env_var_or_default("AZUREML_UPLOAD_CHUNK_SIZE_BYTES", 4 * 1000 * 1024)
artifact_upload_upload_max_attempts = int_env_var_or_default("AZUREML_UPLOAD_CHUNK_MAX_ATTEMPTS", 3)
artifact_upload_sleep_interval_sec = int_env_var_or_default("AZUREML_UPLOAD_SLEEP_INTERVAL_SEC", 2)
artifact_upload_secondary_multiplier = int_env_var_or_default("AZUREML_UPLOAD_SECONDARY_MULTIPLIER", 10)

compute_record_artifact_path = os.environ.get("AZUREML_COMPUTE_RECORD_ARTIFACT_PATH")
compute_record_artifact_origin = os.environ.get("AZUREML_COMPUTE_RECORD_ARTIFACT_ORIGIN")

# Data constants
single_file_input_dataset = os.getenv("AZ_BATCHAI_CONFIG_EnableSingleFileInputDataset", "True").lower() == "True".lower()
enable_detonation_chamber = os.getenv(env_var_az_batchai_enable_detonation_chamber, 'False').lower() == 'True'.lower()
job_temp_dir = os.getenv(env_var_az_batchai_job_temp)
if job_temp_dir is None:
    import tempfile
    job_temp_dir = tempfile.gettempdir()
else:
    job_temp_dir = os.path.expandvars(job_temp_dir)

single_data_dir = os.getenv('AZUREML_SIDECAR_SINGLE_DATA_DIRECTORY', 'false').lower() == 'true'

# Sidecar constants
in_sidecar = os.getenv('SIDECAR_HOSTFS') is not None
sidecar_hostfs = os.getenv('SIDECAR_HOSTFS')
sidecar_running = os.getenv('SIDECAR_RUNNING')
env_sidecar_paths_to_bind = 'AZUREML_SIDECAR_PATHS_TO_BIND'

# common runtime constants
common_runtime_data_cap_running = bool(os.getenv('AZUREML_CR_DATA_CAPABILITY_RUNNING'))

# Git based runs
git_integration_enabled = os.environ.get("AZUREML_GIT_SNAPSHOTS_ENABLED", "false").lower() == "true"
default_snapshot_permissions = int(os.environ.get("AZUREML_SNAPSHOT_DEFAULT_PERMISSION_OCTAL", "775"), 8) # Parse permission bits as base 8 int (octal).


def get_run_starttime_filepath():
    return os.path.join(os.environ.get(env_var_az_batchai_job_temp, "./"), "runstarttime.txt")


def setup_project_dir():
    is_running_on_windows = os.name == 'nt' # TODO: isolated working dir pre-reqs not available on windows (common mount root, expandable work dir env var)
    project_dir = None
    if is_batchai_target_type and not is_running_on_windows:
        project_dir = os.path.expandvars(get_job_work_dir())
    else:
        input_dir = get_input_dir()
        project_dir = os.path.join(input_dir, run_id)

    _ensure_directory_exists(project_dir)
    os.chdir(project_dir)
    _ensure_directory_exists(log_directory_path)
    return project_dir


class BackoffWaiter(object):
        def __init__(self, initial_wait=1, max_wait=15, increment=2):
            self.max_wait = max_wait
            self.current_wait = initial_wait
            self.increment = increment

        def wait(self):
            import time

            time.sleep(self.current_wait)

            # picked an arbitrary increment of 2 seconds
            self.current_wait = min(self.current_wait + self.increment, self.max_wait)


def run_once_multiprocess(action, action_name, waiter, lockfile_path, success_file_path):
    while True:
        try:
            if os.path.exists(success_file_path):
                break
            os.open(lockfile_path, os.O_CREAT | os.O_EXCL)
            print("Acquired lockfile {} to {}".format(lockfile_path, action_name))
            action()
            open(success_file_path, 'a+').close()
            break
        except OSError as e:
            if e.errno != errno.EEXIST:
                raise
            print("Another process is {}. Waiting for ".format(action_name) +
                  "{} second(s) before checking again.".format(waiter.current_wait))
            waiter.wait()


def run_once_master_node_or_wait(action, action_name, waiter, success_file_path):
    while True:
        if os.path.exists(success_file_path):
            break
        if not az_batch_is_current_node_master:
            print("[{}] Waiting for master node to finish {}. Will check again in {} seconds.".format(
                datetime.datetime.utcnow().isoformat(), action_name, waiter.current_wait
            ))
            waiter.wait()
            continue
        print("[{}] {} on master node.".format(datetime.datetime.utcnow().isoformat(), action_name))
        action()
        open(success_file_path, 'a+').close()
        break