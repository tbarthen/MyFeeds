#!/bin/sh
chown -R appuser:appuser /app/data 2>/dev/null
exec su -s /bin/sh appuser -c 'gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 2 --timeout 60 run:app'
