#!/bin/sh
chown -R appuser:appuser /app/data 2>/dev/null

MODE=${1:-web}

if [ "$MODE" = "web" ]; then
    mkdir -p /tmp/gunicorn && chown appuser:appuser /tmp/gunicorn
    exec su -s /bin/sh appuser -c 'gunicorn --bind 0.0.0.0:5000 --workers 4 --timeout 30 --graceful-timeout 10 --max-requests 1000 --max-requests-jitter 100 --worker-tmp-dir /dev/shm --control-socket /tmp/gunicorn/control.sock --access-logfile - run:app'
elif [ "$MODE" = "scheduler" ]; then
    exec su -s /bin/sh appuser -c 'python -m src.scheduler_runner'
else
    echo "Unknown mode: $MODE (expected 'web' or 'scheduler')" >&2
    exit 1
fi
