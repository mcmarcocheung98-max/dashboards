FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 SNAPSHOT_DIR=/app/snapshots
WORKDIR /app
# curl: FRED and some UK sites reset Python's HTTP client, plain curl is accepted
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt .
RUN pip install -r requirements.txt
COPY app ./app
COPY data ./data
# Downloaded snapshots live in /app/snapshots: mount a persistent volume there so a source outage never blanks a chart after a redeploy.
CMD ["python", "-m", "app.server"]
