#!/bin/bash
set -e

echo "=== WB-Ready Post-Build Setup ==="

# Install Python dependencies
echo "Installing Python requirements..."
pip install --upgrade pip
pip install -r /project/.project/requirements.txt

# Initialize Git LFS
echo "Initializing Git LFS..."
git lfs install

# Create directory structure
mkdir -p /project/data /project/models /project/data/scratch

echo ""
echo "=== Setup Complete ==="
echo "Launch WB-Ready Converter from the Workbench apps panel."
