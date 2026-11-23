FROM python:3.11-slim
WORKDIR /app
COPY services/collector/domeggook_live/requirements.txt /tmp/runtime-requirements.txt
RUN pip install --no-cache-dir -r /tmp/runtime-requirements.txt && useradd --uid 10001 --create-home collector && mkdir /state && chown 10001:10001 /state
COPY services/collector/domeggook_live/*.py /app/services/collector/domeggook_live/
COPY services/collector/domeggook_live/config.json /app/services/collector/domeggook_live/config.json
COPY services/collector/marketplace_live/*.py /app/services/collector/marketplace_live/
COPY services/collector/marketplace_live/vendor/*.py /app/services/collector/marketplace_live/vendor/
COPY services/collector/marketplace_live/config.example.json /app/services/collector/marketplace_live/config.example.json
COPY services/collector/used_market_live/*.py /app/services/collector/used_market_live/
COPY services/collector/used_market_live/ebay_used.example.json /app/services/collector/used_market_live/ebay_used.example.json
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
CMD ["python", "-m", "services.collector.used_market_live", "--provider", "ebay_used", "--status", "--state-dir", "/state"]
