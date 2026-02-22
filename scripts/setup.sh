#!/bin/bash

echo "Creating virtual environment..."
python -m venv venv
source venv/bin/activate

echo "Installing control-plane dependencies..."
pip install -r control_plane/requirements.txt

echo "Installing data-plane dependencies..."
pip install -r data_plane/requirements.txt

echo "Setup complete."
echo "Run: source venv/bin/activate"
