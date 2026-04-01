# ---------------------------------------------------------
# Copyright (c) Microsoft Corporation. All rights reserved.
# ---------------------------------------------------------

import datetime

# log as early as possible to get a more accurate time of start.
print("[{}] Entering job preparation.".format(datetime.datetime.utcnow().isoformat()))

import argparse
import errno
from distutils.dir_util import copy_tree
import os
import platform
import shutil
import subprocess
import sys
import zipfile
import time
import json
import multiprocessing


if sys.version_info.major != 3 or sys.version_info.minor < 5:
    raise RuntimeError("Python version " + str(sys.version_info) + " is not supported. Please use python>=3.5")


from azureml_globals import (run_id, env_var_target_type, target_type,
                      cluster_target_type, batchai_target_type,
                      container_target_type, is_cluster_target_type,
                      is_hdi, is_batchai_target_type, is_container_target_type,
                      _ensure_directory_exists, get_input_dir, get_job_work_dir,
                      az_batch_is_current_node_master, log_directory_path,
                      get_datastore_context_manager, get_dataset_context_manager, get_run_starttime_filepath,
                      env_var_job_prep_timeout, job_prep_timeout_sec, BackoffWaiter, run_once_master_node_or_wait,
                      in_sidecar)
from _tracer import get_tracer

cloud_source_dir = os.getenv("AZUREML_CLOUD_SOURCE_DIR")
az_batchai_job_mount_root = os.getenv("AZ_BATCHAI_JOB_MOUNT_ROOT")
azureml_setup = "azureml-setup"

_tracer = get_tracer(__name__)


def extract_project(project_dir, project_zip, snapshots):
    # Only extract the project on the primary instance.
    print("[{}] Starting extract_project.".format(datetime.datetime.utcnow().isoformat()))
    setup_path = os.path.abspath(azureml_setup)
    zip_name = "{}.zip".format(project_dir)

    if cloud_source_dir and az_batchai_job_mount_root:
        print("Retrieving project from cloud directory: " + cloud_source_dir)
        source = os.path.join(az_batchai_job_mount_root, cloud_source_dir)
        if not os.path.exists(source):
            message = "Please verify that the source code data reference path in the run definition is correct."
            raise Exception("The following path does not exist:{}.".format(source, message))
        if os.path.isfile(source):
            shutil.copy(source, project_dir)
        else:
            copy_tree(source, project_dir)
        if os.path.exists(os.path.join(project_dir, azureml_setup)):
            # Do not allow a working directory from another run to be used as a source for this run.
            raise Exception("Found azureml-setup in the source code data reference directory." +
                            "Source code directory cannot be a working directory from another run.")

    print("[{}] Starting to extract zip file.".format(datetime.datetime.utcnow().isoformat()))
    try:
        with zipfile.ZipFile(zip_name, "r") as archive:
            archive.extractall(".")
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

    print("[{}] Finished extracting zip file.".format(datetime.datetime.utcnow().isoformat()))

    sys.path.append(setup_path)

    import project_fetcher
    # snapshots is a json document containing a list of snapshotId|List of Folder Path pairs.
    if snapshots:
        print("[{}] Start fetching snapshots.".format(datetime.datetime.utcnow().isoformat()))
        for snapshot in json.loads(snapshots):
            print("[{}] Start fetching snapshot.".format(datetime.datetime.utcnow().isoformat()))
            snapshot_id = snapshot.get("SnapshotAssetId") or snapshot.get("Id")  # Use SnapshotAssetId if it is set to enable snapshot in AssetStore
            project_fetcher.fetch_project_snapshot(snapshot_id, snapshot["PathStack"], snapshot.get("SnapshotEntityId", None))
            print("[{}] Finished fetching snapshot.".format(datetime.datetime.utcnow().isoformat()))
        print("[{}] Finished fetching snapshots.".format(datetime.datetime.utcnow().isoformat()))

    if project_zip:
        print("[{}] Start fetching project zip.".format(datetime.datetime.utcnow().isoformat()))
        project_fetcher.fetch_project_zip(project_zip)
        print("[{}] Finished fetching project zip.".format(datetime.datetime.utcnow().isoformat()))

    print("[{}] Finished extract_project.".format(datetime.datetime.utcnow().isoformat()))

def run_history_prep():
    print("[{}] Start run_history_prep.".format(datetime.datetime.utcnow().isoformat()))
    from utility_context_managers import DependencyTimer
    try:
        from azureml.history._tracking import execute_job_prep
    except ImportError:
        return

    with DependencyTimer(name="RunHistoryJobPrep"):
        if not is_batchai_target_type:
            execute_job_prep(**{"DirectoriesToWatch": os.path.join("logs","azureml", "job_prep_azureml.log")})
        else:
            execute_job_prep()

def run_cms_in_sidecar(options):
    with _tracer.start_as_current_span('job_prep.run_cms_in_sidecar'):
        print("[{}] Entering Data Context Managers in Sidecar".format(datetime.datetime.utcnow().isoformat()))
        pre_args = sys.argv
        # Only run Datasets, Datastore, and FidelityLogUpload Context Managers in Sidecar
        injected_cm = os.environ.get('AZUREML_CONTEXT_MANAGER_INJECTION_ARGS')
        injected_cm = iter(injected_cm.split(' ')) if injected_cm is not None else []
        to_enter_context_managers = []
        # injected_cm looks like ['-i', 'Dataset:context_managers.Datasets', '-i', ...]
        for flag in injected_cm:
            cm = next(injected_cm)
            if cm.startswith(('Dataset', 'Datastore', 'FidelityLogUpload')):
                to_enter_context_managers += [flag, cm]
        # Add DatastoreCopy ContextManager if injected to job_prep
        for cm in options.inject:
            if cm.startswith("DataStoreCopy"):
                to_enter_context_managers += ['-i', cm]

        # Add ParallelRunBackend ContextManager if injected to job_prep
        for cm in options.inject:
            if cm.startswith("ParallelRunBackend"):
                to_enter_context_managers += ['-i', cm]

        sidecar_prep_cmd = json.loads(os.environ.get('AZUREML_SIDECAR_PREP_CMD'))
        sys.argv = sidecar_prep_cmd + to_enter_context_managers
        import runpy
        print("[{}] Running Sidecar prep cmd...".format(datetime.datetime.utcnow().isoformat()))
        runpy.run_module(sidecar_prep_cmd[0], run_name='__main__', alter_sys=True)
        print("[{}] Ran Sidecar prep cmd.".format(datetime.datetime.utcnow().isoformat()))

def invoke():
    argument_parser = argparse.ArgumentParser()
    argument_parser.add_argument('-i', '--inject', action='append', default=[])
    argument_parser.add_argument("--project-zip", default=None)
    argument_parser.add_argument("--snapshots", default=None)
    options = argument_parser.parse_args()

    print("[{}] Starting job preparation.".format(datetime.datetime.utcnow().isoformat()))
    # UNZIP THE PROJECT

    print("[{}] Extracting the control code.".format(datetime.datetime.utcnow().isoformat()))
    input_dir = get_input_dir()
    project_dir = os.path.join(input_dir, run_id)

    is_running_on_windows = os.name == 'nt' # TODO: isolated working dir pre-reqs not available on windows (common mount root, expandable work dir env var)
    working_dir = None
    if is_batchai_target_type and not is_running_on_windows:
        working_dir = os.path.expandvars(get_job_work_dir())
    else:
        working_dir = project_dir

    _ensure_directory_exists(working_dir)
    os.chdir(working_dir)
    try:
        _ensure_directory_exists(log_directory_path)
    except Exception as e:
        print("[{}] Warning: Failed to create logging directory `{}` due to: {}".format(datetime.datetime.utcnow().isoformat(), log_directory_path, e))

    # code needs to be extracted first before executing everything else
    is_working_dir_mounted = working_dir.startswith(os.path.expandvars(az_batchai_job_mount_root)) or is_running_on_windows
    with _tracer.start_as_current_span('job_prep.invoke.extract_control_code'):
        if is_working_dir_mounted:
            success_file = os.path.join(working_dir, "extract_project.success")
            waiter = BackoffWaiter()
            run_once_master_node_or_wait(
                lambda: extract_project(project_dir, options.project_zip, options.snapshots),
                "fetching and extracting the control code", waiter, success_file
            )
        else:
            extract_project(project_dir, options.project_zip, options.snapshots)

    print("[{}] Finished fetching and extracting the control code.".format(datetime.datetime.utcnow().isoformat()))

    # Adding setup_path to sys path because non master nodes will not have its path updated since
    # they don't run extract_project
    setup_path = os.path.join(working_dir, azureml_setup)
    sys.path.append(setup_path)

    if not az_batch_is_current_node_master and is_batchai_target_type and is_working_dir_mounted:
        if not in_sidecar:
            downloadDataStore(options)
        print("[{}] Not a master node. Skipping rest of the context managers.".format(datetime.datetime.utcnow().isoformat()))
    else:
        parallelJobs = []
        # NORMALLY RUN DATASTORE DOWNLOAD, IF IN SIDECAR IT WILL HAVE BEEN RUN ABOVE.
        if not in_sidecar:
            parallelJobs.append(multiprocessing.Process(target=downloadDataStore, args=[options]))

        # RUN HISTORY SETUP
        parallelJobs.append(multiprocessing.Process(target=run_history_prep))

        for j in parallelJobs:
            j.start()

        for j in parallelJobs:
            j.join()

        try:
            with open(get_run_starttime_filepath(), "w") as file:
                file.write(str(time.time()))
        except Exception as ex:
            print(ex)

        print("[{}] Job preparation is complete.".format(datetime.datetime.utcnow().isoformat()))

    # IF IN SIDECAR, ENTER USER CONTEXT MANAGERS
    if in_sidecar:
        run_cms_in_sidecar(options)
        print("[{}] Running Context Managers in Sidecar complete.".format(datetime.datetime.utcnow().isoformat()))


def downloadDataStore(options):
    with _tracer.start_as_current_span('job_prep.downloadDataStore'):
        print("[{}] downloadDataStore - Download from datastores if requested.".format(datetime.datetime.utcnow().isoformat()))
        datastore_context_manager = get_datastore_context_manager(options)
        if datastore_context_manager:
            datastore_context_manager.__enter__()
        print("[{}] downloadDataStore completed".format(datetime.datetime.utcnow().isoformat()))

if __name__ == "__main__":
    from context_managers import TrackError
    from utility_context_managers import TimeoutHandler
    with _tracer.start_as_current_span('job_prep.__main__', user_facing_name='Job preparation'):
        with TrackError(error_message_prefix = "Job preparation failed: ", user_error = False, check_user_error_by_type = True, is_compliant=True):
            with TimeoutHandler("JobPreparation", job_prep_timeout_sec, env_var_job_prep_timeout):
                invoke()
