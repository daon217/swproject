FROM python:3.11-slim
WORKDIR /app
COPY services/collector/domeggook_live/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt && useradd --uid 10001 --create-home collector
# Explicit allowlist prevents copying .env, state, backups or teammate files.
COPY services/collector/domeggook_live/*.py /app/services/collector/domeggook_live/
COPY services/collector/domeggook_live/config.json /app/services/collector/domeggook_live/config.json
USER 10001:10001
CMD ["python", "-m", "services.collector.domeggook_live", "--watch", "--interval", "7200"]
