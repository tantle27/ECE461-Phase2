
---

# Trustworthy Model Registry – System Overview

## Overview

A lightweight, serverless **model registry** that stores and evaluates ML artifacts for trustworthiness. It runs as a Flask API on AWS Lambda (container image), with DynamoDB for metadata and optional S3 for blob storage.

---

## Architecture

### Deployment

* **Platform:** AWS Lambda (Function URL)
* **Region:** `us-east-2`
* **Runtime:** Python 3.11

### Storage

* **Metadata:** DynamoDB (`ArtifactsTable`, PK/SK single-table pattern)
* **Files:** S3 bucket `model-registry-bucket-useast2` (versioned)
* **Fallback:** In-memory (Lambda warm state only)
* **Temp Path:** `/tmp/uploads`

### Core Components

| Component                   | Role                                                                                                           |
| --------------------------- | -------------------------------------------------------------------------------------------------------------- |
| **`app/core.py`**           | Flask REST API (artifact management, routing, validation)                                                      |
| **`app/db_adapter.py`**     | DynamoDB CRUD with in-memory fallback                                                                          |
| **`app/s3_adapter.py`**     | S3 uploads/downloads, presigned URLs                                                                           |
| **`app/scoring.py`**        | Trustworthiness metrics (bus factor, code quality, license, dataset quality, ramp-up time, performance claims) |
| **`app/lambda_handler.py`** | Function URL → WSGI adapter using `awsgi`                                                                      |

---

## AWS Resources

| Resource      | Name / Example                                                               |
| ------------- | ---------------------------------------------------------------------------- |
| **Lambda**    | `model-registry-api`                                                         |
| **DynamoDB**  | `ArtifactsTable`                                                             |
| **S3 Bucket** | `model-registry-bucket-useast2`                                              |
| **IAM Role**  | Grants `dynamodb:*` and `s3:*` (Put/Get/Delete/List/ACL) for these resources |

---

## Environment Variables

| Variable                  | Description                      |
| ------------------------- | -------------------------------- |
| `USE_DYNAMODB` = `true`   | Enable DynamoDB persistence      |
| `DYNAMODB_TABLE_NAME`     | Table name (`ArtifactsTable`)    |
| `USE_S3` = `true`         | Enable S3 uploads/downloads      |
| `S3_BUCKET_NAME`          | Target S3 bucket                 |
| `S3_REGION` = `us-east-2` | Region                           |
| `S3_ACL` (optional)       | e.g. `bucket-owner-full-control` |
| `GH_TOKEN`                | GitHub token for metric analysis |
| `UPLOAD_DIR` (optional)   | Override upload path             |

**Note:** Without `GH_TOKEN`, trust metrics default to zero.

---

## Key Endpoints

| Method & Path                   | Description                        |
| ------------------------------- | ---------------------------------- |
| `POST /login`                   | Auth (returns bearer token)        |
| `GET /health`                   | System health                      |
| `POST /artifact/<type>`         | Create artifact                    |
| `GET /artifacts/<type>/<id>`    | Retrieve artifact                  |
| `PUT /artifacts/<type>/<id>`    | Update artifact                    |
| `POST /upload`                  | Upload file (S3 or `/tmp`)         |
| `GET /artifact/model/<id>/rate` | Compute trustworthiness metrics    |
| `POST /ingest/hf`               | Ingest Hugging Face model by ID    |
| `DELETE /reset`                 | Clear in-memory cache (admin-only) |

---

## DynamoDB Schema

* **PK:** `ART#{type}#{id}`
* **SK:** `META#{version}`
* **GSI1:** type index → `TYPE#{type}`
* **GSI2:** search index → lowercase `name`
* **Billing:** `PAY_PER_REQUEST`

---

## Verification Checklist

```bash
# Check Lambda env
aws lambda get-function-configuration \
  --function-name model-registry-api \
  --region us-east-2 --query 'Environment.Variables'

# Upload test file
curl -X POST "$FUNCTION_URL/upload" -F "file=@examples/input.txt"

# Create artifact
curl -X POST "$FUNCTION_URL/artifact/model" \
  -H 'Content-Type: application/json' \
  -d '{"metadata":{"id":"demo","name":"Demo","version":"1.0.0"},"data":{"model_link":"https://huggingface.co/bert-base-uncased"}}'

# Rate artifact
curl "$FUNCTION_URL/artifact/model/demo/rate"
```

---

## Current Status

* **S3 Uploads:** Functional in `us-east-2` (bucket region fixed).
* **DynamoDB:** Persists metadata and metrics (`trust_score`, `last_rated`).
* **Downloads:** Text works via Function URL; binary via presigned S3 URL.
* **CI/CD:** GitHub Actions builds Docker → pushes to ECR → updates Lambda.


---

**Maintained By:** ECE 461 Team 9
**Version:** 1.0.0  |  **Last Updated:** Oct 21 2025

---
