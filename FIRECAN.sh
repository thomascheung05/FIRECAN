#!/bin/bash
set -e  # exit on any error

# Move to the directory this script lives in, so it works regardless of where it's called from
cd "$(dirname "$0")"

# Create venv if it doesn't exist
if [ ! -d "venv" ]; then
  echo "Creating virtual environment..."
  python3 -m venv venv
fi

# Activate venv
source venv/bin/activate

# Install/update dependencies
pip install --quiet --upgrade pip
pip install --quiet -r requirements.txt

# Run the app
echo "Starting app..."
python firecan_main.py