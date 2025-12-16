# SiNE Channel Computation Server
# Based on TensorFlow 2.15.0 GPU image with Sionna
#
# Build:
#   docker build -t sine-channel-server:latest .
#
# Run:
#   docker run --gpus all -p 8000:8000 sine-channel-server:latest
#
# Note: Requires NVIDIA Container Toolkit for GPU support

FROM tensorflow/tensorflow:2.15.0-gpu

LABEL maintainer="SiNE Project"
LABEL description="Channel computation server for SiNE wireless network emulation"

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    sionna>=1.0.0 \
    fastapi>=0.100 \
    uvicorn>=0.23 \
    pydantic>=2.0 \
    numpy>=1.24 \
    httpx>=0.24

# Create app directory
WORKDIR /app

# Copy SiNE channel module
# In production, this would be installed from PyPI or a wheel
COPY src/sine/channel /app/sine/channel
COPY src/sine/__init__.py /app/sine/

# Create empty __init__.py files for package structure
RUN touch /app/sine/channel/__init__.py

# Set Python path
ENV PYTHONPATH=/app

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run server
CMD ["uvicorn", "sine.channel.server:app", "--host", "0.0.0.0", "--port", "8000"]
