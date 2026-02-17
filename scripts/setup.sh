#!/bin/bash

echo "Creating virtual environment..."
python -m venv venv
source venv/bin/activate

echo "Installing control-plane dependencies..."
pip install -r control-plane/requirements.txt

echo "Installing data-plane dependencies..."
pip install -r data-plane/requirements.txt

echo "Setup complete."
echo "Run: source venv/bin/activate"
