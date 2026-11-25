FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends graphviz fonts-nanum poppler-utils && rm -rf /var/lib/apt/lists/* && fc-cache -f
RUN pip install -q reportlab pypdf
