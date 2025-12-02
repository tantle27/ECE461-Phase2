#!/usr/bin/env bash
set -euo pipefail

# ===== Config =====
BASE="${BASE:-https://ot47z7sef6wrgsvcw3bmrh752e0hzclv.lambda-url.us-east-2.on.aws}"
USER="ece30861defaultadminuser"
PASS='correcthorsebatterystaple123(!__+@**(A'"'"'"`;DROP TABLE packages;'

echo "Base URL: $BASE"

# Optional: start from a clean state
curl -s -X DELETE "$BASE/reset" -H "X-Authorization: admin" >/dev/null || true

# ===== Health =====
curl -s "$BASE/health" | jq .

# ===== Authenticate =====
TOKEN="$(curl -s -X PUT "$BASE/authenticate" \
  -H 'Content-Type: application/json' \
  -d "{\"user\":{\"name\":\"$USER\",\"is_admin\":true},\"secret\":{\"password\":\"$PASS\"}}" \
  | jq -r '.' | tr -d '"')"
echo "TOKEN: $TOKEN"
AUTH=(-H "X-Authorization: $TOKEN")

# ===== Create a model artifact (initial version is typically 1.0.0) =====
CREATE_RES="$(curl -s -X POST "$BASE/artifact/model" \
  "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d '{"url":"https://huggingface.co/google-bert/bert-base-uncased"}')"

echo "$CREATE_RES" | jq .
MODEL_ID="$(echo "$CREATE_RES" | jq -r '.metadata.id')"
CURR_VER="$(echo "$CREATE_RES" | jq -r '.metadata.version')"
NAME="$(echo "$CREATE_RES" | jq -r '.metadata.name')"

curl -s -X PUT "$BASE/artifacts/model/$MODEL_ID" \
  -H "Content-Type: application/json" "${AUTH[@]}" \
  -d "{
        \"metadata\": { \"name\": \"$NAME\", \"version\": \"$CURR_VER\" },
        \"data\": {
          \"model_link\": \"https://huggingface.co/google-bert/bert-base-uncased\",
          \"code_link\":  \"https://github.com/huggingface/transformers\",
          \"dataset_link\": \"https://huggingface.co/datasets/bookcorpus/bookcorpus\"
        }
      }" | jq .

# ===== Compute rating then PERSIST it back to the artifact =====
RATER="$(curl -s "$BASE/artifact/model/$MODEL_ID/rate" "${AUTH[@]}")"
echo "$RATER" | jq .

TRUST="$(echo "$RATER" | jq '.net_score')"
METRICS_JSON="$(echo "$RATER" | jq '{metrics: .}')"

# Merge links + metrics + trust_score into data, keep same version
PUT_DATA="$(jq -n \
  --arg ml "https://huggingface.co/google-bert/bert-base-uncased" \
  --arg cl "https://github.com/huggingface/transformers" \
  --arg dl "https://huggingface.co/datasets/bookcorpus/bookcorpus" \
  --argjson metrics "$METRICS_JSON" \
  --argjson trust "$TRUST" \
  '{metadata:{},data:{}} |
  .data = ({model_link:$ml, code_link:$cl, dataset_link:$dl} + $metrics + {trust_score:$trust})' )"
curl -s -X PUT "$BASE/artifacts/model/$MODEL_ID" \
  -H "Content-Type: application/json" "${AUTH[@]}" \
  -d "$(jq -n --arg name "$NAME" --arg ver "$CURR_VER" --argjson data "$(echo "$PUT_DATA" | jq '.data')" \
        '{metadata:{name:$name,version:$ver},data:$data}')" | jq .

# ===== Verify it’s stored (trust_score should now appear) =====
curl -s -X POST "$BASE/artifacts" "${AUTH[@]}" -H 'Content-Type: application/json' \
  -d "[{\"name\":\"$NAME\",\"artifact_type\":\"model\",\"page_size\":10}]" | jq .

# Optional: show audit trail
curl -s "$BASE/artifact/model/$MODEL_ID/audit" "${AUTH[@]}" | jq .