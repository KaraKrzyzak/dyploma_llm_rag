import os
from dotenv import load_dotenv
from azure.ai.ml import MLClient, command, Input, Output
from azure.ai.ml.entities import Environment, AmlCompute, Data
from azure.identity import DefaultAzureCredential
from azure.ai.ml.constants import AssetTypes

load_dotenv()  # search for .env file and load environment variables

SUBSCRIPTION_ID = os.environ["AZURE_SUBSCRIPTION_ID"]
RESOURCE_GROUP  = os.environ["AZURE_RESOURCE_GROUP"]
WORKSPACE_NAME  = os.environ["AZURE_WORKSPACE_NAME"]
TXT_FOLDER = './TEXT_data_engineering'
NORMALIZED_TRAIN_FILE = 'final_train_data_normalized.txt'

#Connect to Azure ML workspace
credential = DefaultAzureCredential()
ml_client = MLClient(
    credential=credential,
    subscription_id=SUBSCRIPTION_ID,
    resource_group_name=RESOURCE_GROUP,
    workspace_name=WORKSPACE_NAME
)
print(f"Connected to Azure ML workspace: {WORKSPACE_NAME}")

#  Standard_NC6s_v3   — 1x V100 16GB,  ~$3/h  
#  Standard_NC12s_v3  — 2x V100 32GB,  ~$6/h
#  Standard_NC24s_v3  — 4x V100 64GB,  ~$12/h
#  Standard_ND40rs_v2 — 8x V100 320GB, ~$22/h
#  Standard_NC4as_T4  — 1x T4 16GB,    ~$0.9/h 

COMPUTE_NAME  = "cpu-cluster"
VM_SIZE  = "Standard_DS12_v2" 

def create_compute(ml_client, compute_name, vm_size):
    try:
        ml_client.compute.get(compute_name)
        print(f"Compute '{compute_name}' already exists.")
    except Exception:
        cluster = AmlCompute(
            name=compute_name,
            type="amlcompute",
            size=vm_size,
            min_instances=0,
            max_instances=4,
            idle_time_before_scale_down=120
        )
        ml_client.compute.begin_create_or_update(cluster).result()
        print(f"Compute '{compute_name}' created.")

create_compute(ml_client, COMPUTE_NAME, VM_SIZE) 

conda_yaml = """
name: llm-training
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.10
  - pip
  - pip:
    - tensorflow==2.15.0
    - tiktoken
    - numpy
    - matplotlib
    - mlflow        
    - azureml-mlflow  
"""

with open("CC_conda.yml", "w") as f:
    f.write(conda_yaml)

environment = Environment(
    name = "minillm-training-env_v2",
    description="Environment for training MiniLLM model",
    conda_file="CC_conda.yml",
    image = "mcr.microsoft.com/azureml/openmpi4.1.0-cuda11.8-cudnn8-ubuntu22.04:latest"
)

environment = ml_client.environments.create_or_update(environment)
print(f"Environment '{environment.name}' created/updated successfully.")


txt_file = f"{TXT_FOLDER}/{NORMALIZED_TRAIN_FILE}"

try:
    dataset = ml_client.data.get(name="normalized_train_data", version="1")
    print(f"Dataset '{dataset.name}' already exists, using version: {dataset.version}")
except Exception:
    dataset = ml_client.data.create_or_update(
        Data(
            path=txt_file,
            type=AssetTypes.URI_FILE,
            name="normalized_train_data",
            version="1",
            description="Normalized training data for MiniLLM model"
        )
    )
    print(f"Dataset '{dataset.name}' registered, version: {dataset.version}")


job = command(
    name="train-minillm_cpu",
    description="Train MiniLLM model on Azure ML compute",
    command="python CB_Minillm.py --train_data ${{inputs.train_data}} --output_dir ${{outputs.model_output}}",
    inputs={
        "train_data": Input(type=AssetTypes.URI_FILE, path=dataset.id)
    },
    outputs={
        "model_output": Output(type=AssetTypes.URI_FOLDER)  
    },
    environment=f"{environment.name}@latest",
    compute=COMPUTE_NAME,             
    code=".",                       
)

returned_job = ml_client.jobs.create_or_update(job)
print(f"Job '{returned_job.name}' submitted: {returned_job.studio_url}")