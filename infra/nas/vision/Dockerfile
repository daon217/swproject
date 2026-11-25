# 빌드 context: kkulpick_vision/  (infra/nas/vision.compose.yaml에서 지정)
FROM python:3.11-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK=True
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libglib2.0-0 libgl1 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /srv
COPY requirements.txt /tmp/requirements.txt
# 코드가 PaddleOCR 2.x API(show_log, ocr(cls=))를 사용하므로 3.x가 설치되지 않도록 고정합니다.
RUN printf 'paddlepaddle==2.6.2\npaddleocr==2.10.0\nnumpy<2\nopencv-python<4.11\nopencv-python-headless<4.11\nopencv-contrib-python<4.11\n' > /tmp/constraints.txt \
    && pip install --no-cache-dir -r /tmp/requirements.txt -c /tmp/constraints.txt
RUN useradd --uid 10001 --create-home app && mkdir -p /home/app/.paddleocr && chown -R app:app /home/app
COPY --chown=app:app app ./app
USER app
