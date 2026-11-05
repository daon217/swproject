FROM python:3.12-slim
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home api
COPY . .
USER api
CMD ["uvicorn","kkulpick.api:app","--host","0.0.0.0","--port","8000"]
