#!/bin/sh
chown -R appuser:appuser /app/data 2>/dev/null

MODE=${1:-web}

if [ "$MODE" = "web" ]; then
    exec su -s /bin/sh appuser -c 'gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 2 --timeout 60 --worker-tmp-dir /dev/shm run:app'
elif [ "$MODE" = "scheduler" ]; then
    exec su -s /bin/sh appuser -c 'python -m src.scheduler_runner'
else
    echo "Unknown mode: $MODE (expected 'web' or 'scheduler')" >&2
    exit 1
fi
