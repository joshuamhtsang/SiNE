# SiNE Network Node Container
# Lightweight Alpine-based container with network testing tools
#
# Build:
#   docker build -t sine-node:latest .
#
# This image is used for emulated network nodes (clients, servers, etc.)

FROM alpine:latest

LABEL maintainer="SiNE Project"
LABEL description="Network node container for SiNE wireless network emulation"

# Install network utilities
RUN apk add --no-cache \
    iperf3 \
    iproute2 \
    iputils \
    tcpdump \
    curl \
    wget \
    bash \
    bind-tools \
    netcat-openbsd \
    openssh-client

# Create a non-root user (optional, for security)
# RUN adduser -D -s /bin/bash sine
# USER sine

# Set working directory
WORKDIR /root

# Default command - keep container running
CMD ["/bin/sh", "-c", "while true; do sleep 3600; done"]
