FROM python:3.11-slim
WORKDIR /app
COPY services/collector/collector_ops/deploy/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock && useradd --uid 10001 --create-home collector && mkdir /state /datasets && chown 10001:10001 /state /datasets
COPY services/collector/domeggook_live/*.py /app/services/collector/domeggook_live/
COPY services/collector/domeggook_live/config.json /app/services/collector/domeggook_live/config.json
COPY services/collector/marketplace_live/*.py /app/services/collector/marketplace_live/
COPY services/collector/marketplace_live/vendor/*.py /app/services/collector/marketplace_live/vendor/
COPY services/collector/marketplace_live/config.example.json /app/services/collector/marketplace_live/config.example.json
COPY services/collector/used_market_live/*.py /app/services/collector/used_market_live/
COPY services/collector/used_market_live/ebay_used.example.json /app/services/collector/used_market_live/ebay_used.example.json
COPY services/collector/real_feed_collectors/product_refinement/clean.py /app/services/collector/real_feed_collectors/product_refinement/clean.py
COPY services/collector/real_feed_collectors/detail_enrichment_v1/clean.py /app/services/collector/real_feed_collectors/detail_enrichment_v1/clean.py
COPY services/collector/food_evidence/*.py /app/services/collector/food_evidence/
COPY services/collector/collector_ops/*.py /app/services/collector/collector_ops/
COPY services/collector/synthetic_catalog/*.py /app/services/collector/synthetic_catalog/
COPY services/collector/unified_live/*.py /app/services/collector/unified_live/
COPY services/collector/unified_live/seed_sites.json /app/services/collector/unified_live/seed_sites.json
COPY services/collector/real_feed_collectors/real_collectors/core.py /app/services/collector/real_feed_collectors/real_collectors/core.py
COPY services/collector/real_feed_collectors/real_collectors/__init__.py /app/services/collector/real_feed_collectors/real_collectors/__init__.py
USER 10001:10001
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 PYTHONPATH=/app:/app/services/collector/real_feed_collectors
CMD ["python", "-m", "services.collector.collector_ops", "--provider", "ebay", "--status", "--state-dir", "/state", "--config", "/run/config.json"]
