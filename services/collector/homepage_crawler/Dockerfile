# 박정우 홈페이지 크롤러를 백엔드 전송 모드(--backend --watch)로 계속 돌리는 이미지.
# 빌드 위치는 저장소 루트(infra/integration/compose.yaml의 homepage-crawler 서비스).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
RUN pip install --no-cache-dir requests==2.32.3 beautifulsoup4==4.12.3 lxml==5.3.0 \
    && useradd --create-home --uid 10001 crawler
WORKDIR /app
COPY services/collector/__init__.py services/collector/__init__.py
COPY services/collector/food_evidence services/collector/food_evidence
COPY services/collector/homepage_crawler services/collector/homepage_crawler
USER crawler
CMD ["python", "-m", "services.collector.homepage_crawler.crawler", "--backend", "--watch"]
