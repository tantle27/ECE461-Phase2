"""
DynamoDB adapter for the Model Registry.

Provides abstraction over DynamoDB operations with fallback to in-memory storage
for local development.
"""

import json
import logging
import os
import time
from decimal import Decimal
from typing import Any

logger = logging.getLogger(__name__)

# import audit helpers lazily to avoid import cycles during app startup
try:
    from app.audit_logging import db_audit, security_alert  # type: ignore
except Exception:
    # fallback no-op implementations
    def db_audit(operation: str, **fields: Any) -> None:  # type: ignore
        logger.debug("db_audit noop: %s %s", operation, fields)

    def security_alert(message: str, **fields: Any) -> None:  # type: ignore
        logger.warning("security_alert noop: %s %s", message, fields)

# Environment variable to enable DynamoDB (set to "true" in Lambda)
USE_DYNAMODB = os.environ.get("USE_DYNAMODB", "false").lower() == "true"
TABLE_NAME = os.environ.get("DYNAMODB_TABLE_NAME", "ArtifactsTable")
REGION = os.environ.get("AWS_REGION", "us-east-2")

# Import boto3 only if DynamoDB is enabled
dynamodb_table = None
dynamodb_client = None

if USE_DYNAMODB:
    try:
        import boto3

        dynamodb_resource = boto3.resource("dynamodb", region_name=REGION)
        dynamodb_table = dynamodb_resource.Table(TABLE_NAME)
        dynamodb_client = boto3.client("dynamodb", region_name=REGION)
        logger.info(f"DynamoDB enabled: table={TABLE_NAME}, region={REGION}")
    except Exception as e:
        logger.error(f"Failed to initialize DynamoDB: {e}")
        USE_DYNAMODB = False


class ArtifactStore:
    """Artifact storage abstraction - uses DynamoDB or in-memory dict."""

    def __init__(self):
        self._memory_store: dict[str, Any] = {}
        self.use_dynamodb = USE_DYNAMODB

    def _make_pk(self, artifact_type: str, artifact_id: str) -> str:
        """Create partition key: ART#{type}#{id}"""
        return f"ART#{artifact_type}#{artifact_id}"

    def _make_sk(self, version: str) -> str:
        """Create sort key: META#{version}"""
        return f"META#{version}"

    def save(self, artifact_type: str, artifact_id: str, artifact_data: dict[str, Any]) -> None:
        """Save an artifact with metrics and scores."""
        start = time.time()
        if self.use_dynamodb and dynamodb_table:
            try:
                metadata = artifact_data.get("metadata", {})
                data = artifact_data.get("data", {})
                version = metadata.get("version", "1.0.0")
                # Extract metrics and scores (may be None if not yet rated)
                metrics = data.get("metrics") or {}
                trust_score = data.get("trust_score") or metrics.get("net_score", 0.0)
                # Build DynamoDB item (convert floats to Decimal for DynamoDB)
                item = {
                    "PK": self._make_pk(artifact_type, artifact_id),
                    "SK": self._make_sk(version),
                    "artifact_type": artifact_type,
                    "artifact_id": artifact_id,
                    "data": json.dumps(artifact_data),  # Store complete artifact as JSON
                    # Metadata fields for querying
                    "name": metadata.get("name", ""),
                    "version": version,
                    "status": metadata.get("status") or data.get("status", "unvetted"),
                    "tags": metadata.get("tags") or data.get("tags", []),
                    # Metrics and scores (use Decimal for DynamoDB)
                    "trust_score": Decimal(str(trust_score)) if trust_score else Decimal("0.0"),
                    # "metrics": json.dumps(metrics) if metrics else json.dumps({}),
                    # GSI keys for fast enumeration
                    "GSI1PK": f"TYPE#{artifact_type}",
                    "GSI1SK": artifact_id,
                    "GSI2PK": "STATUS",
                    "GSI2SK": (
                        f"{metadata.get('status') or data.get('status', 'unvetted')}"
                        f"#{artifact_id}"
                    ),
                }
                # Optional fields (S3, license, etc.)
                if data.get("s3_key"):
                    item["s3_key"] = data["s3_key"]
                if data.get("s3_bucket"):
                    item["s3_bucket"] = data["s3_bucket"]
                if data.get("size"):
                    item["size_bytes"] = int(data["size"])
                if data.get("license"):
                    item["license"] = data["license"]
                dynamodb_table.put_item(Item=item)
                duration_ms = int((time.time() - start) * 1000)
                db_audit(
                    "dynamodb_put_item",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    trust_score=trust_score,
                    duration_ms=duration_ms,
                )
                logger.info(
                    f"Saved to DynamoDB: {artifact_type}/{artifact_id} (trust_score={trust_score})"
                )
            except Exception as e:
                logger.error(f"DynamoDB save failed: {e}, falling back to memory")
                security_alert(
                    "dynamodb_save_failed",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    error=str(e),
                )
                self._memory_store[f"{artifact_type}:{artifact_id}"] = artifact_data
        else:
            self._memory_store[f"{artifact_type}:{artifact_id}"] = artifact_data

    def get(self, artifact_type: str, artifact_id: str) -> dict[str, Any] | None:
        """Get a specific artifact."""
        start = time.time()
        if self.use_dynamodb and dynamodb_table:
            try:
                # Query by PK, get latest version (or you can specify version)
                response = dynamodb_table.query(
                    KeyConditionExpression="PK = :pk",
                    ExpressionAttributeValues={":pk": self._make_pk(artifact_type, artifact_id)},
                    ScanIndexForward=False,  # Latest version first
                    Limit=1,
                )
                items = response.get("Items", [])
                if items:
                    duration_ms = int((time.time() - start) * 1000)
                    db_audit(
                        "dynamodb_query",
                        table=TABLE_NAME,
                        artifact_type=artifact_type,
                        artifact_id=artifact_id,
                        duration_ms=duration_ms,
                        result_count=len(items),
                    )
                    return json.loads(items[0]["data"])
                return None
            except Exception as e:
                logger.error(f"DynamoDB get failed: {e}, falling back to memory")
                security_alert(
                    "dynamodb_get_failed",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    error=str(e),
                )
                return self._memory_store.get(f"{artifact_type}:{artifact_id}")
        else:
            return self._memory_store.get(f"{artifact_type}:{artifact_id}")

    def list_all(self, artifact_type: str | None = None) -> list[dict[str, Any]]:
        """List all artifacts, optionally filtered by type."""
        start = time.time()
        if self.use_dynamodb and dynamodb_table:
            try:
                if artifact_type:
                    # Use GSI1 to filter by type
                    response = dynamodb_table.query(
                        IndexName="GSI1",
                        KeyConditionExpression="GSI1PK = :type_key",
                        ExpressionAttributeValues={":type_key": f"TYPE#{artifact_type}"},
                    )
                else:
                    # Scan entire table (expensive, but needed for listing all)
                    response = dynamodb_table.scan()

                items = response.get("Items", [])
                results = [json.loads(item["data"]) for item in items]
                duration_ms = int((time.time() - start) * 1000)
                db_audit(
                    "dynamodb_list",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    result_count=len(results),
                    duration_ms=duration_ms,
                )
                logger.info(f"Listed {len(results)} artifacts from DynamoDB")
                return results
            except Exception as e:
                logger.error(f"DynamoDB list failed: {e}, falling back to memory")
                security_alert(
                    "dynamodb_list_failed",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    error=str(e),
                )
                return [
                    v
                    for k, v in self._memory_store.items()
                    if artifact_type is None or k.startswith(f"{artifact_type}:")
                ]
        else:
            return [
                v
                for k, v in self._memory_store.items()
                if artifact_type is None or k.startswith(f"{artifact_type}:")
            ]

    def list_by_status(self, status: str, limit: int = 100) -> list[dict[str, Any]]:
        """List artifacts by status (e.g., 'unvetted', 'approved', 'rejected')."""
        start = time.time()
        if self.use_dynamodb and dynamodb_table:
            try:
                key_cond = "GSI2PK = :status_key AND " "begins_with(GSI2SK, :status_val)"
                response = dynamodb_table.query(
                    IndexName="GSI2",
                    KeyConditionExpression=key_cond,
                    ExpressionAttributeValues={
                        ":status_key": "STATUS",
                        ":status_val": status,
                    },
                    Limit=limit,
                )
                items = response.get("Items", [])
                duration_ms = int((time.time() - start) * 1000)
                db_audit(
                    "dynamodb_list_by_status",
                    table=TABLE_NAME,
                    status=status,
                    result_count=len(items),
                    duration_ms=duration_ms,
                )
                return [json.loads(item["data"]) for item in items]
            except Exception as e:
                logger.error(f"DynamoDB list_by_status failed: {e}, falling back to memory")
                security_alert(
                    "dynamodb_list_by_status_failed",
                    table=TABLE_NAME,
                    status=status,
                    error=str(e),
                )
                return [
                    v
                    for v in self._memory_store.values()
                    if v.get("metadata", {}).get("status") == status
                    or v.get("data", {}).get("status") == status
                ]
        else:
            return [
                v
                for v in self._memory_store.values()
                if v.get("metadata", {}).get("status") == status
                or v.get("data", {}).get("status") == status
            ]

    def list_by_min_trust_score(
        self, min_score: float, artifact_type: str | None = None, limit: int = 100
    ) -> list[dict[str, Any]]:
        """List artifacts with trust_score >= min_score."""
        start = time.time()
        if self.use_dynamodb and dynamodb_table:
            try:
                # Scan with filter (convert float to Decimal for DynamoDB comparison)
                filter_expr = "trust_score >= :min_score"
                expr_values: dict[str, Any] = {":min_score": Decimal(str(min_score))}
                if artifact_type:
                    filter_expr += " AND artifact_type = :type"
                    expr_values[":type"] = artifact_type
                response = dynamodb_table.scan(
                    FilterExpression=filter_expr,
                    ExpressionAttributeValues=expr_values,
                    Limit=limit,
                )
                items = response.get("Items", [])
                # Sort by trust_score descending (convert Decimal to float for sorting)
                items.sort(key=lambda x: float(x.get("trust_score", 0)), reverse=True)
                duration_ms = int((time.time() - start) * 1000)
                db_audit(
                    "dynamodb_list_by_min_trust",
                    table=TABLE_NAME,
                    min_score=min_score,
                    artifact_type=artifact_type,
                    result_count=len(items),
                    duration_ms=duration_ms,
                )
                return [json.loads(item["data"]) for item in items]
            except Exception as e:
                logger.error(
                    f"DynamoDB list_by_min_trust_score failed: {e}, falling back to memory"
                )
                security_alert(
                    "dynamodb_list_by_min_trust_failed",
                    table=TABLE_NAME,
                    min_score=min_score,
                    error=str(e),
                )
                results = [
                    v
                    for v in self._memory_store.values()
                    if v.get("data", {}).get("trust_score", 0.0) >= min_score
                ]
                if artifact_type:
                    results = [
                        r for r in results if r.get("metadata", {}).get("type") == artifact_type
                    ]
                return sorted(
                    results, key=lambda x: x.get("data", {}).get("trust_score", 0.0), reverse=True
                )
        else:
            results = [
                v
                for v in self._memory_store.values()
                if v.get("data", {}).get("trust_score", 0.0) >= min_score
            ]
            if artifact_type:
                results = [r for r in results if r.get("metadata", {}).get("type") == artifact_type]
            return sorted(
                results, key=lambda x: x.get("data", {}).get("trust_score", 0.0), reverse=True
            )

    def delete(self, artifact_type: str, artifact_id: str) -> None:
        """Delete an artifact."""
        start = time.time()
        if self.use_dynamodb and dynamodb_table:
            try:
                # Delete all versions (query then batch delete)
                response = dynamodb_table.query(
                    KeyConditionExpression="PK = :pk",
                    ExpressionAttributeValues={":pk": self._make_pk(artifact_type, artifact_id)},
                )
                for item in response.get("Items", []):
                    dynamodb_table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                duration_ms = int((time.time() - start) * 1000)
                db_audit(
                    "dynamodb_delete",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    duration_ms=duration_ms,
                )
                logger.info(f"Deleted from DynamoDB: {artifact_type}/{artifact_id}")
            except Exception as e:
                logger.error(f"DynamoDB delete failed: {e}, falling back to memory")
                security_alert(
                    "dynamodb_delete_failed",
                    table=TABLE_NAME,
                    artifact_type=artifact_type,
                    artifact_id=artifact_id,
                    error=str(e),
                )
                self._memory_store.pop(f"{artifact_type}:{artifact_id}", None)
        else:
            self._memory_store.pop(f"{artifact_type}:{artifact_id}", None)

    def clear(self) -> None:
        """Clear all artifacts (for reset endpoint)."""
        if self.use_dynamodb and dynamodb_table:
            try:
                # Scan and delete all items
                response = dynamodb_table.scan()
                with dynamodb_table.batch_writer() as batch:
                    for item in response.get("Items", []):
                        pk = item.get("PK", "")
                        # Preserve auth tokens and other non-artifact entries
                        if pk.startswith("TOKEN#"):
                            continue
                        batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                logger.warning("Cleared all items from DynamoDB")
            except Exception as e:
                logger.error(f"DynamoDB clear failed: {e}, falling back to memory")
                self._memory_store.clear()
        else:
            self._memory_store.clear()


class TokenStore:
    """Token storage abstraction - uses DynamoDB or in-memory set."""

    def __init__(self):
        self._memory_tokens: set[str] = set()
        self.use_dynamodb = USE_DYNAMODB

    def add(self, token: str) -> None:
        """Add a token."""
        if self.use_dynamodb and dynamodb_table:
            try:
                dynamodb_table.put_item(
                    Item={
                        "PK": "TOKEN#AUTH",
                        "SK": f"TOKEN#{token}",
                        "token": token,
                    }
                )
            except Exception as e:
                logger.error(f"DynamoDB token add failed: {e}")
                self._memory_tokens.add(token)
        else:
            self._memory_tokens.add(token)

    def contains(self, token: str) -> bool:
        """Check if token exists."""
        if self.use_dynamodb and dynamodb_table:
            try:
                response = dynamodb_table.get_item(Key={"PK": "TOKEN#AUTH", "SK": f"TOKEN#{token}"})
                return "Item" in response
            except Exception as e:
                logger.error(f"DynamoDB token check failed: {e}")
                return token in self._memory_tokens
        else:
            return token in self._memory_tokens

    def clear(self) -> None:
        """Clear all tokens."""
        if self.use_dynamodb and dynamodb_table:
            try:
                response = dynamodb_table.query(
                    KeyConditionExpression="PK = :pk",
                    ExpressionAttributeValues={":pk": "TOKEN#AUTH"},
                )
                with dynamodb_table.batch_writer() as batch:
                    for item in response.get("Items", []):
                        batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
            except Exception as e:
                logger.error(f"DynamoDB token clear failed: {e}")
                self._memory_tokens.clear()
        else:
            self._memory_tokens.clear()


class RatingsCache:
    """Ratings cache abstraction - uses DynamoDB or in-memory dict."""

    def __init__(self):
        self._memory_cache: dict[str, Any] = {}
        self.use_dynamodb = USE_DYNAMODB

    def get(self, artifact_id: str) -> Any | None:
        """Get cached rating."""
        if self.use_dynamodb and dynamodb_table:
            try:
                response = dynamodb_table.get_item(
                    Key={"PK": "RATING#CACHE", "SK": f"RATING#{artifact_id}"}
                )
                if "Item" in response:
                    return json.loads(response["Item"]["data"])
                return None
            except Exception as e:
                logger.error(f"DynamoDB rating get failed: {e}")
                return self._memory_cache.get(artifact_id)
        else:
            return self._memory_cache.get(artifact_id)

    def set(self, artifact_id: str, rating: Any) -> None:
        """Set cached rating."""
        if self.use_dynamodb and dynamodb_table:
            try:
                dynamodb_table.put_item(
                    Item={
                        "PK": "RATING#CACHE",
                        "SK": f"RATING#{artifact_id}",
                        "artifact_id": artifact_id,
                        "data": json.dumps(rating.__dict__, default=str),
                    }
                )
            except Exception as e:
                logger.error(f"DynamoDB rating set failed: {e}")
                self._memory_cache[artifact_id] = rating
        else:
            self._memory_cache[artifact_id] = rating

    def clear(self) -> None:
        """Clear all ratings."""
        if self.use_dynamodb and dynamodb_table:
            try:
                response = dynamodb_table.query(
                    KeyConditionExpression="PK = :pk",
                    ExpressionAttributeValues={":pk": "RATING#CACHE"},
                )
                with dynamodb_table.batch_writer() as batch:
                    for item in response.get("Items", []):
                        batch.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
            except Exception as e:
                logger.error(f"DynamoDB rating clear failed: {e}")
                self._memory_cache.clear()
        else:
            self._memory_cache.clear()
