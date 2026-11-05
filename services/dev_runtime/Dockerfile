FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /workspace
COPY services/dev_runtime/requirements.lock /tmp/requirements.lock
RUN pip install --no-cache-dir -r /tmp/requirements.lock \
    && useradd --uid 10001 --create-home developer \
    && mkdir -p /var/lib/kkulpick/images \
    && chown developer /var/lib/kkulpick/images
COPY services/dev_runtime services/dev_runtime
COPY services/vision/devapp.py services/vision/devapp.py
COPY services/recommendation/devapp.py services/recommendation/devapp.py
COPY services/collector/devapp.py services/collector/devapp.py
USER developer
CMD ["celery", "-A", "services.dev_runtime.tasks:app", "worker", "--concurrency=1", "--loglevel=WARNING", "-Q", "development"]
