#!/bin/bash
# ═══════════════════════════════════════════════════════════
# Import pre-built workflows into n8n
# ═══════════════════════════════════════════════════════════
# Run after docker compose up and n8n is healthy:
#   ./scripts/init-workflows.sh
#
# Prerequisites:
#   1. docker compose up -d (all services running)
#   2. N8N_API_KEY set in .env (generate in n8n: Settings → API → Create API Key)
#
# This script is NOT idempotent — running it twice will create duplicate workflows.
# Check n8n UI first if you've already run it.

set -euo pipefail

N8N_URL="${N8N_URL:-http://localhost:5678}"
N8N_API_KEY="${N8N_API_KEY:-}"
WORKFLOW_DIR="$(dirname "$0")/../workflows"

# ── Validate prerequisites ──
if [ -z "$N8N_API_KEY" ]; then
  # Try loading from .env
  ENV_FILE="$(dirname "$0")/../.env"
  if [ -f "$ENV_FILE" ]; then
    N8N_API_KEY=$(grep -E "^N8N_API_KEY=" "$ENV_FILE" 2>/dev/null | cut -d= -f2- | tr -d '"' || true)
  fi
fi

if [ -z "$N8N_API_KEY" ]; then
  echo "ERROR: N8N_API_KEY is not set."
  echo ""
  echo "To generate an API key:"
  echo "  1. Open n8n at $N8N_URL"
  echo "  2. Go to Settings → API → Create API Key"
  echo "  3. Add it to your .env file: N8N_API_KEY=your-key-here"
  echo "  4. Run this script again"
  exit 1
fi

# ── Check n8n is reachable ──
echo "Checking n8n at $N8N_URL..."
HTTP_STATUS=$(curl -s -o /dev/null -w "%{http_code}" "$N8N_URL/healthz" 2>/dev/null || echo "000")

if [ "$HTTP_STATUS" != "200" ]; then
  echo "ERROR: n8n is not reachable at $N8N_URL (HTTP $HTTP_STATUS)"
  echo "Make sure 'docker compose up -d' is running and n8n is healthy."
  exit 1
fi

echo "n8n is healthy. Importing workflows..."
echo ""

# ── Import workflows ──
SUCCESS=0
FAILED=0

for file in "$WORKFLOW_DIR"/*.json; do
  [ -f "$file" ] || continue  # Skip if no JSON files found
  name=$(basename "$file" .json)
  echo -n "  Importing $name... "

  response=$(curl -s -w "\n%{http_code}" \
    -X POST "$N8N_URL/api/v1/workflows" \
    -H "Content-Type: application/json" \
    -H "X-N8N-API-KEY: $N8N_API_KEY" \
    -d @"$file" 2>/dev/null)

  http_code=$(echo "$response" | tail -1)
  body=$(echo "$response" | head -n -1)

  if [ "$http_code" = "200" ] || [ "$http_code" = "201" ]; then
    echo "OK"
    SUCCESS=$((SUCCESS + 1))
  else
    echo "FAILED (HTTP $http_code)"
    echo "    $body" | head -1
    FAILED=$((FAILED + 1))
  fi
done

echo ""
echo "═══════════════════════════════════════════"
echo "  Import complete: $SUCCESS succeeded, $FAILED failed"
echo "═══════════════════════════════════════════"
echo ""
echo "Next steps:"
echo "  1. Open n8n at $N8N_URL"
echo "  2. Configure credentials for each workflow (API keys, tokens)"
echo "  3. Test with sample payloads before activating"
echo "  4. Set active: true only after testing"
