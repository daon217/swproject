FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home api
COPY . .
RUN mkdir -p /var/lib/kkulpick/analysis && chown api:api /var/lib/kkulpick/analysis
USER api
# --proxy-headers: FORWARDED_ALLOW_IPS(기본 127.0.0.1)에 적은 프록시의 X-Forwarded-For만 믿는다(#17).
CMD ["uvicorn","kkulpick.api:app","--host","0.0.0.0","--port","8000","--proxy-headers"]
