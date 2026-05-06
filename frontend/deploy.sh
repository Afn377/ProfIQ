#!/usr/bin/env bash
# Build and deploy the frontend to Vercel. VITE_* values are baked in at build
# time, so the API url has to be passed to the build, not set afterwards.
set -euo pipefail
cd "$(dirname "$0")"

ENV_FILE="../backend/.env.deploy"
if [ ! -f "$ENV_FILE" ]; then
  echo "missing backend/.env.deploy, copy backend/.env.deploy.example and fill it in" >&2
  exit 1
fi
set -a
source "$ENV_FILE"
set +a

: "${VITE_API_BASE_URL:?set VITE_API_BASE_URL in backend/.env.deploy to the cloud run url plus /api}"

npx vercel --prod --yes --build-env VITE_API_BASE_URL="$VITE_API_BASE_URL"
