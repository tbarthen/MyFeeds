FROM python:3.11-slim

WORKDIR /app

# curl for the Docker health check; procps for ps/top when debugging a hang
RUN apt-get update && apt-get install -y --no-install-recommends curl procps && rm -rf /var/lib/apt/lists/*

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# py-spy: dump a live Python stack trace if a worker wedges (needs SYS_PTRACE)
RUN pip install --no-cache-dir py-spy

# Copy application code
COPY . .

# Create non-root user and data directory
RUN useradd -r -s /bin/false appuser && mkdir -p /app/data && chown -R appuser:appuser /app/data

COPY entrypoint.sh /app/entrypoint.sh
RUN chmod +x /app/entrypoint.sh

EXPOSE 5000

ENTRYPOINT ["/app/entrypoint.sh"]
