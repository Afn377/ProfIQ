#!/usr/bin/env bash
# Deploy the backend to Cloud Run from source. Reads secrets from .env.deploy.
set -euo pipefail
cd "$(dirname "$0")"

if [ ! -f .env.deploy ]; then
  echo "missing backend/.env.deploy, copy .env.deploy.example and fill it in" >&2
  exit 1
fi
set -a
source .env.deploy
set +a

: "${GCP_PROJECT_ID:?set GCP_PROJECT_ID in .env.deploy}"
: "${DJANGO_SECRET_KEY:?set DJANGO_SECRET_KEY in .env.deploy}"
GCP_REGION="${GCP_REGION:-us-central1}"
CLOUD_RUN_SERVICE="${CLOUD_RUN_SERVICE:-profiq-backend}"

ENV_VARS_FILE=$(mktemp)
trap 'rm -f "$ENV_VARS_FILE"' EXIT
cat > "$ENV_VARS_FILE" <<YAML
DJANGO_SECRET_KEY: "${DJANGO_SECRET_KEY}"
DJANGO_DEBUG: "${DJANGO_DEBUG:-0}"
USE_POSTGRES: "1"
DB_NAME: "${DB_NAME:-}"
DB_USER: "${DB_USER:-}"
DB_PASSWORD: "${DB_PASSWORD:-}"
DB_HOST: "${DB_HOST:-}"
DB_PORT: "${DB_PORT:-26257}"
DB_SSLROOTCERT: "${DB_SSLROOTCERT:-}"
CORS_EXTRA_ORIGINS: "${CORS_EXTRA_ORIGINS:-}"
YAML

gcloud run deploy "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --source . \
  --memory 2Gi \
  --cpu 2 \
  --timeout 300 \
  --allow-unauthenticated \
  --env-vars-file "$ENV_VARS_FILE"

echo "deployed, service url:"
gcloud run services describe "$CLOUD_RUN_SERVICE" \
  --project "$GCP_PROJECT_ID" \
  --region "$GCP_REGION" \
  --format='value(status.url)'
