#!/usr/bin/env bash

BASE="https://ot47z7sef6wrgsvcw3bmrh752e0hzclv.lambda-url.us-east-2.on.aws"

echo "Testing authentication..."

# Create the JSON payload properly
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

echo "Payload:"
cat /tmp/auth_payload.json | jq .

echo ""
echo "Sending request..."
curl -s -X PUT "$BASE/authenticate" \
  -H 'Content-Type: application/json' \
  -d @/tmp/auth_payload.json | jq .
