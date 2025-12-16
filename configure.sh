#!/bin/bash
# SiNE Configuration Script
# Installs system-level dependencies for SiNE

set -e

echo "=== SiNE Configuration Script ==="
echo ""

# Check if running as root for system installs
check_sudo() {
    if [ "$EUID" -ne 0 ]; then
        echo "Note: Some installations require sudo. You may be prompted for your password."
    fi
}

# Install Containerlab
install_containerlab() {
    echo "--- Checking Containerlab ---"
    if command -v containerlab &> /dev/null; then
        echo "Containerlab already installed: $(containerlab version | head -n1)"
    else
        echo "Installing Containerlab..."
        # Official install script from containerlab.dev
        sudo bash -c "$(curl -sL https://get.containerlab.dev)"
        echo "Containerlab installed: $(containerlab version | head -n1)"
    fi
    echo ""
}

# Install NVIDIA CUDA Toolkit for GPU support
install_cuda() {
    echo "--- Checking NVIDIA CUDA Toolkit ---"
    if command -v nvcc &> /dev/null; then
        echo "CUDA Toolkit already installed: $(nvcc --version | grep release)"
    else
        echo "Installing NVIDIA CUDA Toolkit..."
        sudo apt update
        sudo apt install -y nvidia-cuda-toolkit
        echo "CUDA Toolkit installed"
    fi
    echo ""
}

# Check Docker
check_docker() {
    echo "--- Checking Docker ---"
    if command -v docker &> /dev/null; then
        echo "Docker installed: $(docker --version)"
        # Check if user can run docker without sudo
        if ! docker ps &> /dev/null; then
            echo "Warning: Cannot run docker commands. You may need to:"
            echo "  1. Start the Docker daemon: sudo systemctl start docker"
            echo "  2. Add yourself to the docker group: sudo usermod -aG docker $USER"
            echo "     Then log out and back in."
        fi
    else
        echo "Warning: Docker not installed. Install from: https://docs.docker.com/engine/install/"
    fi
    echo ""
}

# Install Python dependencies with uv
install_python_deps() {
    echo "--- Installing Python Dependencies ---"
    if command -v uv &> /dev/null; then
        echo "Using uv to install dependencies..."
        # Remove stale lockfile if it exists (may have old tensorflow refs)
        if [ -f "uv.lock" ]; then
            echo "Removing stale uv.lock..."
            rm uv.lock
        fi
        uv sync
        echo "Python dependencies installed (including Sionna v1.2)"
    else
        echo "Warning: uv not installed. Install from: https://docs.astral.sh/uv/getting-started/installation/"
    fi
    echo ""
}

# Main
main() {
    check_sudo
    echo ""

    # Parse arguments
    INSTALL_CUDA=false
    SKIP_PYTHON=false

    for arg in "$@"; do
        case $arg in
            --cuda)
                INSTALL_CUDA=true
                ;;
            --no-python)
                SKIP_PYTHON=true
                ;;
            --help)
                echo "Usage: ./configure.sh [OPTIONS]"
                echo ""
                echo "Options:"
                echo "  --cuda       Install NVIDIA CUDA Toolkit for GPU acceleration"
                echo "  --no-python  Skip Python dependency installation"
                echo "  --help       Show this help message"
                exit 0
                ;;
        esac
    done

    check_docker
    install_containerlab

    if [ "$INSTALL_CUDA" = true ]; then
        install_cuda
    else
        echo "--- CUDA Toolkit ---"
        echo "Skipping CUDA installation. Use --cuda flag to install."
        echo "GPU acceleration requires: sudo apt install nvidia-cuda-toolkit"
        echo ""
    fi

    if [ "$SKIP_PYTHON" = false ]; then
        install_python_deps
    fi

    echo "=== Configuration Complete ==="
    echo ""
    echo "Next steps:"
    echo "  1. Start the channel server:  uv run sine channel-server"
    echo "  2. Deploy an emulation:       uv run sine deploy examples/two_room_wifi/network.yaml"
}

main "$@"
