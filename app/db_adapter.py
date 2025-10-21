"""
DynamoDB adapter for the Model Registry.

Provides abstraction over DynamoDB operations with fallback to in-memory storage
for local development.
"""

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

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
        """Save an artifact."""
        if self.use_dynamodb and dynamodb_table:
            try:
                version = artifact_data.get("metadata", {}).get("version", "1.0.0")
                item = {
                    "PK": self._make_pk(artifact_type, artifact_id),
                    "SK": self._make_sk(version),
                    "artifact_type": artifact_type,
                    "artifact_id": artifact_id,
                    "data": json.dumps(artifact_data),  # Store as JSON string
                    # GSI keys for querying
                    "GSI1PK": f"TYPE#{artifact_type}",
                    "GSI1SK": artifact_id,
                    "GSI2PK": "SEARCH",
                    "GSI2SK": artifact_data.get("metadata", {}).get("name", "").lower(),
                }
                dynamodb_table.put_item(Item=item)
                logger.info(f"Saved to DynamoDB: {artifact_type}/{artifact_id}")
            except Exception as e:
                logger.error(f"DynamoDB save failed: {e}, falling back to memory")
                self._memory_store[f"{artifact_type}:{artifact_id}"] = artifact_data
        else:
            self._memory_store[f"{artifact_type}:{artifact_id}"] = artifact_data

    def get(self, artifact_type: str, artifact_id: str) -> dict[str, Any] | None:
        """Get a specific artifact."""
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
                    return json.loads(items[0]["data"])
                return None
            except Exception as e:
                logger.error(f"DynamoDB get failed: {e}, falling back to memory")
                return self._memory_store.get(f"{artifact_type}:{artifact_id}")
        else:
            return self._memory_store.get(f"{artifact_type}:{artifact_id}")

    def list_all(self, artifact_type: str | None = None) -> list[dict[str, Any]]:
        """List all artifacts, optionally filtered by type."""
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
                logger.info(f"Listed {len(results)} artifacts from DynamoDB")
                return results
            except Exception as e:
                logger.error(f"DynamoDB list failed: {e}, falling back to memory")
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

    def delete(self, artifact_type: str, artifact_id: str) -> None:
        """Delete an artifact."""
        if self.use_dynamodb and dynamodb_table:
            try:
                # Delete all versions (query then batch delete)
                response = dynamodb_table.query(
                    KeyConditionExpression="PK = :pk",
                    ExpressionAttributeValues={":pk": self._make_pk(artifact_type, artifact_id)},
                )
                for item in response.get("Items", []):
                    dynamodb_table.delete_item(Key={"PK": item["PK"], "SK": item["SK"]})
                logger.info(f"Deleted from DynamoDB: {artifact_type}/{artifact_id}")
            except Exception as e:
                logger.error(f"DynamoDB delete failed: {e}, falling back to memory")
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
                response = dynamodb_table.get_item(
                    Key={"PK": "TOKEN#AUTH", "SK": f"TOKEN#{token}"}
                )
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
