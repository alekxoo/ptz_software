## ended up using the website to create instance and it came with ssh 
sudo apt update
# 535 is longest supported version of NVIDIA driver to provide information on nvidia-smi (monitoring), 
# cuda, pytorch/tensor flow, video encoding 
sudo apt install -y nvidia-driver-535

# install cuda toolkit to interface with gpu
sudo apt install -y nvidia-cuda-toolkit

# reboot after
sudo reboot







# gsutil is a Python application that lets you access Cloud Storage from the command line
gsutil mb gs://simulation-model-processing-$(date +%s)


# Create the organized folders
# /dev/null is a special file that discards all data written to it
# ./keep files are used to ensure that the folders are created in Cloud Storage
gsutil cp /dev/null gs://simulation-model-processing-1750446091/input-videos/.keep
gsutil cp /dev/null gs://simulation-model-processing-1750446091/output-csv/.keep  
gsutil cp /dev/null gs://simulation-model-processing-1750446091/output-screenshots/.keep
gsutil cp /dev/null gs://simulation-model-processing-1750446091/models/.keep


# copy video 
gsutil cp /home/machvision/Downloads/training_video1.mkv gs://simulation-model-processing-1750446091/input-videos/

# Create a Google Compute Engine instance with GPU support
# 4 vCPUs, 15GB RAM (older generation)
#  Single NVIDIA Tesla T4 GPU
# --maintenance-policy=TERMINATE: VM shuts down during Google maintenance (required for GPUs)
# Pre-installed PyTorch with GPU support
# Google's ML-optimized image

gcloud compute instances create video-processor \ --zone=us-central1-a \ --machine-type=n1-standard-4 \
      --accelerator=type=nvidia-tesla-t4,count=1 \ --image-family=pytorch-latest-gpu \
        --image-project=deeplearning-platform-release \ --boot-disk-size=100GB \ --maintenance-policy=TERMINATE

# Create L4 GPU VM (better performance)
gcloud compute instances create video-processor \
    --zone=us-central1-a \
    --machine-type=g2-standard-4 \
    --image-family=pytorch-latest-gpu \
    --image-project=deeplearning-platform-release \
    --boot-disk-size=200GB \
    --maintenance-policy=TERMINATE \
    --no-address # no address means no external IP, only accessible via IAP (Identity-Aware Proxy)


# received error on external IP 
# you need to enable external IP to ssh to VM 
# if not, you can use google secure shell 
# google secure shell is enabled from setting up gcloud auth login - since you can't ask everyone to set up this everytime you need access,
# when you have publicly accessible needed program, you can set up external IP

# 1. connecting to the virtual
gcloud compute ssh video-processor --zone=us-central1-a --tunnel-through-iap

gcloud compute instances delete video-processor --zone=us-central1-a

# request quota for GPU 
https://console.cloud.google.com/iam-admin/quotas
> request for l4 and general gpus


# Stop the VM (keeps disk, stops charging for compute/GPU)
gcloud compute instances stop video-processor --zone=us-central1-a

# Start it later
gcloud compute instances start video-processor --zone=us-central1-a



# add myself as IAP 
gcloud projects add-iam-policy-binding cs-poc-4jlkxvpsrk0l3pt3i0ktiob \
    --member="user:alex.koo@machdynamics.ai" \
    --role="roles/iap.tunnelResourceAccessor"