#!/bin/bash
# Script to create an AWS Lambda Layer from requirements.txt

# Set variables
LAYER_NAME="python-dependencies"
PYTHON_VERSION="python3.12"  # Change this to match your Lambda runtime
REQUIREMENTS_FILE="requirements.txt"

# Create directory structure
mkdir -p ${LAYER_NAME}/python/lib/${PYTHON_VERSION}/site-packages

# Install packages to the directory
pip install -r ${REQUIREMENTS_FILE} --target ${LAYER_NAME}/python/lib/${PYTHON_VERSION}/site-packages --upgrade

# Create zip file
cd ${LAYER_NAME} && zip -r ../${LAYER_NAME}.zip . && cd ..

echo "Layer zip file created: ${LAYER_NAME}.zip"
echo "You can now upload this zip file as a Lambda Layer"
