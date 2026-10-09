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

# ==== [EFFICIENCY UPDATE] install dependencies only when requirements.txt changes ====
# Previously pip upgraded itself and re-checked every requirement on every launch.
REQ_HASH=$(python -c "import hashlib; print(hashlib.sha256(open('requirements.txt', 'rb').read()).hexdigest())")
STAMP_FILE="venv/.requirements.sha256"
if [ ! -f "$STAMP_FILE" ] || [ "$(cat "$STAMP_FILE")" != "$REQ_HASH" ]; then
  echo "Installing dependencies..."
  python -m pip install --quiet --upgrade pip
  python -m pip install --quiet -r requirements.txt && echo "$REQ_HASH" > "$STAMP_FILE"
fi
# ==== [END EFFICIENCY UPDATE] ====

# Run the app
echo "Starting app..."
python app/firecan_main.py