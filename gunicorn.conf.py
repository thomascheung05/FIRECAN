# Gunicorn settings for FIRECAN. Run from the repo root with:  gunicorn firecan_main:app
# Any setting here can be overridden on the command line, e.g.  gunicorn -b 0.0.0.0:8000 -w 2 firecan_main:app
from pathlib import Path
import sys

# The app logs with print(), flush each line so output shows up live and isn't duplicated into every forked worker
sys.stdout.reconfigure(line_buffering=True)

pythonpath = str(Path(__file__).resolve().parent / 'app')     # firecan_main imports firecan_fx as a top level module
bind = '127.0.0.1:5050'

# Each worker keeps its own copy of the fire data in memory, so scale with threads first and add workers only if there's RAM for it
workers = 1
worker_class = 'gthread'
threads = 8
timeout = 120                   # large exports read full detail geometry from disk and can take a while

# Arrow/GEOS native libraries initialized before fork can crash on macOS.
# Linux retains preloading to share watershed memory. Prepare local watershed
# files before starting multiple non-preloaded workers on a fresh installation.
preload_app = sys.platform != 'darwin'


def post_fork(server, worker):
    # Threads don't survive the fork, so each worker starts its own fire data loader (downloads are shared through a file lock)
    import firecan_main
    firecan_main.start_fire_data_loading()
