set -e
mkdir -p /work && cd /src && cp -r services /work/ && cd /work
pip install -q -r services/api/requirements-dev.txt -r services/dev_runtime/requirements.lock >/dev/null 2>&1
export DB_HOST=127.0.0.1 CATALOG_PASSWORD=$CATALOG_APP_PASSWORD RECO_EMBEDDER=hash
PYTHONPATH=/work python /b/bench_embed.py ${N:-3000}
