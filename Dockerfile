FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SNAPSHOT_DIR=/app/snapshots
WORKDIR /app
# curl: FRED and some UK sites reset Python's HTTP client, plain curl is accepted
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
# rclone: the month-end archive goes to OneDrive (app/cloud.py), same pinned release as the trading bot; amd64 (Railway)
RUN curl -fsSL https://downloads.rclone.org/v1.68.2/rclone-v1.68.2-linux-amd64.deb -o /tmp/rclone.deb && apt-get update \
    && apt-get install -y --no-install-recommends /tmp/rclone.deb && rm -f /tmp/rclone.deb && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY data ./data
# Downloaded snapshots live in /app/snapshots: mount a persistent volume there so a source outage never blanks a chart after a redeploy.
CMD ["python", "-m", "app.server"]
