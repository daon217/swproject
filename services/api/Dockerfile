FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt requirements.lock ./
RUN pip install --no-cache-dir -r requirements.lock && useradd --uid 10001 --create-home api
COPY . .
USER api
CMD ["uvicorn","kkulpick.api:app","--host","0.0.0.0","--port","8000"]
