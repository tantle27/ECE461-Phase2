#!/usr/bin/env bash
set -euo pipefail

BASE="https://ot47z7sef6wrgsvcw3bmrh752e0hzclv.lambda-url.us-east-2.on.aws"

echo "=== Health Check ==="
curl -s "$BASE/health" | jq .

echo ""
echo "=== Authenticating ==="

# Create proper JSON payload
cat > /tmp/auth_payload.json <<'EOF'
{
  "user": {
    "name": "ece30861defaultadminuser",
    "is_admin": true
  },
  "secret": {
    "password": "correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;"
  }
}
EOF

TOKEN=$(curl -s -X PUT "$BASE/authenticate" \
  -H 'Content-Type: application/json' \
  -d @/tmp/auth_payload.json | jq -r '.' | tr -d '"')

echo "TOKEN: $TOKEN"

if [[ "$TOKEN" == *"message"* ]] || [[ -z "$TOKEN" ]]; then
  echo "❌ Authentication failed"
  exit 1
fi

echo ""
echo "=== Creating Model Artifact ==="
CREATE_RES=$(curl -s -X POST "$BASE/artifact/model" \
  -H "X-Authorization: $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"url":"https://huggingface.co/google-bert/bert-base-uncased"}')

echo "$CREATE_RES" | jq .

MODEL_ID=$(echo "$CREATE_RES" | jq -r '.metadata.id')
echo ""
echo "Model ID: $MODEL_ID"

if [[ "$MODEL_ID" == "null" ]] || [[ -z "$MODEL_ID" ]]; then
  echo "❌ Failed to create artifact"
  exit 1
fi

echo ""
echo "=== Rating Model ==="
curl -s "$BASE/artifact/model/$MODEL_ID/rate" \
  -H "X-Authorization: $TOKEN" | jq .

echo ""
echo "✅ Test completed successfully"
