set -e
mkdir -p /work && cd /src && cp -r services tools .github infra /work/ && cd /work
pip install -q -r services/api/requirements-dev.txt -r services/dev_runtime/requirements.lock toon-format >/dev/null 2>&1
export DB_HOST=127.0.0.1 CATALOG_INTEGRATION=1 EMBEDDING_INTEGRATION=1 ANALYSIS_IMAGE_DIR=/tmp/analysis CATALOG_PASSWORD=$CATALOG_APP_PASSWORD
reco() { python -m pytest -q -p no:cacheprovider services/recommendation/tests services/dev_runtime 2>&1 | grep -E "passed|failed|^FAILED|^E " | head -20; }
api() { (cd services/api && python -m pytest -q -p no:cacheprovider tests --ignore=tests/test_sample_mutations.py 2>&1 | grep -E "passed|failed|^FAILED|^E " | head -20); }
echo "=== CI order: reco then api"; reco; api
echo "=== reverse order: api then reco"; api; reco
echo "=== sample mutations"; (cd services/api && python -m pytest -q -p no:cacheprovider tests/test_sample_mutations.py 2>&1 | tail -1)
