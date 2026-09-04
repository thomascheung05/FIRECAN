#!/bin/bash

# Move to the directory this script lives in
cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# Activate venv based on OS structure
if [ -f "venv/Scripts/activate" ]; then
  # Windows (Git Bash / MSYS2)
  source venv/Scripts/activate
elif [ -f "venv/bin/activate" ]; then
  # macOS / Linux / WSL
  source venv/bin/activate
else
  echo "Error: Could not find activation script."
  exit 1
fi

# Install/update dependencies
python -m pip install --quiet --upgrade pip
python -m pip install --quiet -r requirements.txt

# Run the app
echo "Starting app..."
python firecan_main.py