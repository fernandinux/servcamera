# base image with PyTorch + CUDA
FROM tensorflow/tensorflow:2.11.0-gpu

# Install system dependencies
RUN apt-get update && \
    apt-get install -y git libgl1 && \
    rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Clone DeepFace repository
# RUN git clone https://github.com/serengil/deepface.git

# Install dependencies
RUN pip install deepface jupyter

# Expose port for Jupyter Notebook
EXPOSE 8888

# Default command
CMD ["jupyter", "notebook", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]
