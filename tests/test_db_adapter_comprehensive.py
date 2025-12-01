"""
Comprehensive test coverage for app/db_adapter.py.

Tests all major functionality including:
- ArtifactStore class with DynamoDB and memory fallback
- TokenStore class with authentication token management
- RatingsCache class with rating persistence
- DynamoDB operations and error handling
- Memory fallback mechanisms
- JSON serialization and data validation
- Key generation and data modeling
"""

import json
from decimal import Decimal
from unittest.mock import Mock, patch

# Import from app.db_adapter
from app.db_adapter import REGION, TABLE_NAME, USE_DYNAMODB, ArtifactStore, RatingsCache, TokenStore


class TestEnvironmentSetup:
    """Test environment variable configuration."""

    def test_environment_variables(self):
        """Test environment variable defaults."""
        # These are set at module import time
        assert TABLE_NAME == "ArtifactsTable"
        assert REGION == "us-east-2"
        # USE_DYNAMODB depends on environment
        assert isinstance(USE_DYNAMODB, bool)

    @patch.dict("os.environ", {"USE_DYNAMODB": "true"})
    def test_dynamodb_enabled_env(self):
        """Test DynamoDB enabled environment."""
        import importlib

        import app.db_adapter

        importlib.reload(app.db_adapter)
        # Would require boto3 to be properly initialized

    @patch.dict("os.environ", {"USE_DYNAMODB": "false"})
    def test_dynamodb_disabled_env(self):
        """Test DynamoDB disabled environment."""
        import importlib

        import app.db_adapter

        importlib.reload(app.db_adapter)


class TestArtifactStore:
    """Test ArtifactStore class functionality."""

    def setup_method(self):
        """Set up test instances."""
        self.store = ArtifactStore()

    def test_init(self):
        """Test ArtifactStore initialization."""
        store = ArtifactStore()
        assert isinstance(store._memory_store, dict)
        assert isinstance(store.use_dynamodb, bool)

    def test_make_pk(self):
        """Test partition key generation."""
        pk = self.store._make_pk("model", "test-id")
        assert pk == "ART#model#test-id"

    def test_make_sk(self):
        """Test sort key generation."""
        sk = self.store._make_sk("1.0.0")
        assert sk == "META#1.0.0"

    def test_save_memory_only(self):
        """Test saving artifact to memory store."""
        self.store.use_dynamodb = False

        artifact_data = {
            "metadata": {"id": "test", "name": "test-model", "type": "model", "version": "1.0.0"},
            "data": {"model_link": "https://example.com"},
        }

        self.store.save("model", "test", artifact_data)

        # Check memory store
        key = "model:test"
        assert key in self.store._memory_store
        assert self.store._memory_store[key] == artifact_data

    @patch("app.db_adapter.dynamodb_table")
    def test_save_dynamodb_success(self, mock_table):
        """Test successful DynamoDB save."""
        self.store.use_dynamodb = True
        mock_table.put_item = Mock()

        artifact_data = {
            "metadata": {
                "id": "test",
                "name": "test-model",
                "type": "model",
                "version": "1.0.0",
                "status": "unvetted",
            },
            "data": {
                "model_link": "https://example.com",
                "trust_score": 0.8,
                "metrics": {"accuracy": 0.95},
                "s3_key": "test-key",
                "s3_bucket": "test-bucket",
                "size": 1048576,
                "license": "MIT",
            },
        }

        self.store.save("model", "test", artifact_data)

        # Verify DynamoDB call
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args[1]["Item"]

        assert call_args["PK"] == "ART#model#test"
        assert call_args["SK"] == "META#1.0.0"
        assert call_args["artifact_type"] == "model"
        assert call_args["artifact_id"] == "test"
        assert call_args["name"] == "test-model"
        assert call_args["version"] == "1.0.0"
        assert call_args["status"] == "unvetted"
        assert call_args["trust_score"] == Decimal("0.8")
        assert call_args["s3_key"] == "test-key"
        assert call_args["s3_bucket"] == "test-bucket"
        assert call_args["size_bytes"] == 1048576
        assert call_args["license"] == "MIT"
        assert call_args["GSI1PK"] == "TYPE#model"
        assert call_args["GSI1SK"] == "test"
        assert call_args["GSI2PK"] == "STATUS"
        assert call_args["GSI2SK"] == "unvetted#test"

        # Verify JSON data storage
        stored_data = json.loads(call_args["data"])
        assert stored_data == artifact_data

    @patch("app.db_adapter.dynamodb_table")
    def test_save_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB save failure falls back to memory."""
        self.store.use_dynamodb = True
        mock_table.put_item.side_effect = Exception("DynamoDB error")

        artifact_data = {
            "metadata": {"id": "test", "name": "test", "type": "model", "version": "1.0.0"},
            "data": {},
        }

        self.store.save("model", "test", artifact_data)

        # Should fallback to memory
        assert "model:test" in self.store._memory_store
        assert self.store._memory_store["model:test"] == artifact_data

    def test_get_memory_only(self):
        """Test getting artifact from memory store."""
        self.store.use_dynamodb = False

        artifact_data = {
            "metadata": {"id": "test", "name": "test", "type": "model", "version": "1.0.0"},
            "data": {"model_link": "https://example.com"},
        }

        self.store._memory_store["model:test"] = artifact_data

        result = self.store.get("model", "test")
        assert result == artifact_data

    def test_get_memory_not_found(self):
        """Test getting non-existent artifact from memory."""
        self.store.use_dynamodb = False
        result = self.store.get("model", "nonexistent")
        assert result is None

    @patch("app.db_adapter.dynamodb_table")
    def test_get_dynamodb_success(self, mock_table):
        """Test successful DynamoDB get."""
        self.store.use_dynamodb = True

        artifact_data = {
            "metadata": {"id": "test", "name": "test", "type": "model", "version": "1.0.0"},
            "data": {"model_link": "https://example.com"},
        }

        mock_table.query.return_value = {"Items": [{"data": json.dumps(artifact_data)}]}

        result = self.store.get("model", "test")
        assert result == artifact_data

        # Verify query parameters
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["KeyConditionExpression"] == "PK = :pk"
        assert call_kwargs["ExpressionAttributeValues"][":pk"] == "ART#model#test"
        assert call_kwargs["ScanIndexForward"] is False
        assert call_kwargs["Limit"] == 1

    @patch("app.db_adapter.dynamodb_table")
    def test_get_dynamodb_not_found(self, mock_table):
        """Test DynamoDB get with no results."""
        self.store.use_dynamodb = True
        mock_table.query.return_value = {"Items": []}

        result = self.store.get("model", "test")
        assert result is None

    @patch("app.db_adapter.dynamodb_table")
    def test_get_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB get failure falls back to memory."""
        self.store.use_dynamodb = True
        mock_table.query.side_effect = Exception("DynamoDB error")

        # Set up memory fallback
        artifact_data = {"test": "data"}
        self.store._memory_store["model:test"] = artifact_data

        result = self.store.get("model", "test")
        assert result == artifact_data

    def test_list_all_memory_no_filter(self):
        """Test listing all artifacts from memory without filter."""
        self.store.use_dynamodb = False

        # Add test data
        artifacts = {
            "model:test1": {"metadata": {"type": "model"}, "data": {}},
            "dataset:test2": {"metadata": {"type": "dataset"}, "data": {}},
            "model:test3": {"metadata": {"type": "model"}, "data": {}},
        }
        self.store._memory_store.update(artifacts)

        result = self.store.list_all()
        assert len(result) == 3
        assert all(artifact in result for artifact in artifacts.values())

    def test_list_all_memory_with_filter(self):
        """Test listing artifacts from memory with type filter."""
        self.store.use_dynamodb = False

        # Add test data
        artifacts = {
            "model:test1": {"metadata": {"type": "model"}, "data": {}},
            "dataset:test2": {"metadata": {"type": "dataset"}, "data": {}},
            "model:test3": {"metadata": {"type": "model"}, "data": {}},
        }
        self.store._memory_store.update(artifacts)

        result = self.store.list_all("model")
        assert len(result) == 2
        model_artifacts = [artifacts["model:test1"], artifacts["model:test3"]]
        assert all(artifact in result for artifact in model_artifacts)

    @patch("app.db_adapter.dynamodb_table")
    def test_list_all_dynamodb_with_filter(self, mock_table):
        """Test listing artifacts from DynamoDB with type filter."""
        self.store.use_dynamodb = True

        artifact_data = [
            {"data": json.dumps({"metadata": {"type": "model"}, "data": {}})},
            {"data": json.dumps({"metadata": {"type": "model"}, "data": {}})},
        ]

        mock_table.query.return_value = {"Items": artifact_data}

        result = self.store.list_all("model")
        assert len(result) == 2

        # Verify query for GSI1
        mock_table.query.assert_called_once()
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["IndexName"] == "GSI1"
        assert call_kwargs["KeyConditionExpression"] == "GSI1PK = :type_key"
        assert call_kwargs["ExpressionAttributeValues"][":type_key"] == "TYPE#model"

    @patch("app.db_adapter.dynamodb_table")
    def test_list_all_dynamodb_no_filter(self, mock_table):
        """Test listing all artifacts from DynamoDB without filter."""
        self.store.use_dynamodb = True

        artifact_data = [
            {"data": json.dumps({"metadata": {"type": "model"}, "data": {}})},
            {"data": json.dumps({"metadata": {"type": "dataset"}, "data": {}})},
        ]

        mock_table.scan.return_value = {"Items": artifact_data}

        result = self.store.list_all()
        assert len(result) == 2

        # Verify scan operation
        mock_table.scan.assert_called_once()

    @patch("app.db_adapter.dynamodb_table")
    def test_list_all_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB list failure falls back to memory."""
        self.store.use_dynamodb = True
        mock_table.query.side_effect = Exception("DynamoDB error")
        mock_table.scan.side_effect = Exception("DynamoDB error")

        # Set up memory data
        self.store._memory_store["model:test"] = {"metadata": {"type": "model"}, "data": {}}

        result = self.store.list_all("model")
        assert len(result) == 1

    @patch("app.db_adapter.dynamodb_table")
    def test_list_by_status_dynamodb(self, mock_table):
        """Test listing artifacts by status from DynamoDB."""
        self.store.use_dynamodb = True

        artifact_data = [
            {"data": json.dumps({"metadata": {"status": "approved"}, "data": {}})},
            {"data": json.dumps({"metadata": {"status": "approved"}, "data": {}})},
        ]

        mock_table.query.return_value = {"Items": artifact_data}

        result = self.store.list_by_status("approved", 50)
        assert len(result) == 2

        # Verify GSI2 query
        call_kwargs = mock_table.query.call_args[1]
        assert call_kwargs["IndexName"] == "GSI2"
        assert (
            call_kwargs["KeyConditionExpression"]
            == "GSI2PK = :status_key AND begins_with(GSI2SK, :status_val)"
        )
        assert call_kwargs["ExpressionAttributeValues"][":status_key"] == "STATUS"
        assert call_kwargs["ExpressionAttributeValues"][":status_val"] == "approved"
        assert call_kwargs["Limit"] == 50

    def test_list_by_status_memory(self):
        """Test listing artifacts by status from memory."""
        self.store.use_dynamodb = False

        artifacts = {
            "model:test1": {"metadata": {"status": "approved"}, "data": {}},
            "model:test2": {"metadata": {"status": "rejected"}, "data": {}},
            "model:test3": {"data": {"status": "approved"}},  # Status in data field
        }
        self.store._memory_store.update(artifacts)

        result = self.store.list_by_status("approved")
        assert len(result) == 2

    @patch("app.db_adapter.dynamodb_table")
    def test_list_by_min_trust_score_dynamodb(self, mock_table):
        """Test listing artifacts by minimum trust score from DynamoDB."""
        self.store.use_dynamodb = True

        artifact_data = [
            {"trust_score": Decimal("0.9"), "data": json.dumps({"test": "data1"})},
            {"trust_score": Decimal("0.8"), "data": json.dumps({"test": "data2"})},
        ]

        mock_table.scan.return_value = {"Items": artifact_data}

        result = self.store.list_by_min_trust_score(0.7, "model", 100)
        assert len(result) == 2

        # Verify scan with filter
        call_kwargs = mock_table.scan.call_args[1]
        assert "FilterExpression" in call_kwargs
        assert call_kwargs["ExpressionAttributeValues"][":min_score"] == Decimal("0.7")
        assert call_kwargs["ExpressionAttributeValues"][":type"] == "model"
        assert call_kwargs["Limit"] == 100

    def test_list_by_min_trust_score_memory(self):
        """Test listing artifacts by minimum trust score from memory."""
        self.store.use_dynamodb = False

        artifacts = {
            "model:test1": {"metadata": {"type": "model"}, "data": {"trust_score": 0.9}},
            "model:test2": {"metadata": {"type": "model"}, "data": {"trust_score": 0.6}},
            "dataset:test3": {"metadata": {"type": "dataset"}, "data": {"trust_score": 0.8}},
        }
        self.store._memory_store.update(artifacts)

        result = self.store.list_by_min_trust_score(0.7, "model")
        assert len(result) == 1
        assert result[0]["data"]["trust_score"] == 0.9

    @patch("app.db_adapter.dynamodb_table")
    def test_delete_dynamodb(self, mock_table):
        """Test deleting artifact from DynamoDB."""
        self.store.use_dynamodb = True

        # Mock query response
        mock_table.query.return_value = {
            "Items": [
                {"PK": "ART#model#test", "SK": "META#1.0.0"},
                {"PK": "ART#model#test", "SK": "META#1.0.1"},
            ]
        }
        mock_table.delete_item = Mock()

        self.store.delete("model", "test")

        # Verify query and deletes
        mock_table.query.assert_called_once()
        assert mock_table.delete_item.call_count == 2

    def test_delete_memory(self):
        """Test deleting artifact from memory."""
        self.store.use_dynamodb = False

        self.store._memory_store["model:test"] = {"test": "data"}

        self.store.delete("model", "test")
        assert "model:test" not in self.store._memory_store

    def test_delete_nonexistent_memory(self):
        """Test deleting non-existent artifact from memory."""
        self.store.use_dynamodb = False

        # Should not raise exception
        self.store.delete("model", "nonexistent")

    @patch("app.db_adapter.dynamodb_table")
    def test_clear_dynamodb(self, mock_table):
        """Test clearing all artifacts from DynamoDB."""
        self.store.use_dynamodb = True

        mock_table.scan.return_value = {
            "Items": [
                {"PK": "ART#model#test1", "SK": "META#1.0.0"},
                {"PK": "ART#model#test2", "SK": "META#1.0.0"},
            ]
        }

        # Mock batch writer
        mock_batch = Mock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch

        self.store.clear()

        # Verify scan and batch delete
        mock_table.scan.assert_called_once()
        assert mock_batch.delete_item.call_count == 2

    def test_clear_memory(self):
        """Test clearing all artifacts from memory."""
        self.store.use_dynamodb = False

        self.store._memory_store["test1"] = {"data": "1"}
        self.store._memory_store["test2"] = {"data": "2"}

        self.store.clear()
        assert len(self.store._memory_store) == 0


class TestTokenStore:
    """Test TokenStore class functionality."""

    def setup_method(self):
        """Set up test instances."""
        self.store = TokenStore()

    def test_init(self):
        """Test TokenStore initialization."""
        store = TokenStore()
        assert isinstance(store._memory_tokens, set)
        assert isinstance(store.use_dynamodb, bool)

    def test_add_memory(self):
        """Test adding token to memory store."""
        self.store.use_dynamodb = False

        self.store.add("test-token")
        assert "test-token" in self.store._memory_tokens

    @patch("app.db_adapter.dynamodb_table")
    def test_add_dynamodb_success(self, mock_table):
        """Test adding token to DynamoDB."""
        self.store.use_dynamodb = True
        mock_table.put_item = Mock()

        self.store.add("test-token")

        # Verify DynamoDB call
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args[1]["Item"]
        assert call_args["PK"] == "TOKEN#AUTH"
        assert call_args["SK"] == "TOKEN#test-token"
        assert call_args["token"] == "test-token"

    @patch("app.db_adapter.dynamodb_table")
    def test_add_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB add failure falls back to memory."""
        self.store.use_dynamodb = True
        mock_table.put_item.side_effect = Exception("DynamoDB error")

        self.store.add("test-token")

        # Should fallback to memory
        assert "test-token" in self.store._memory_tokens

    def test_contains_memory_found(self):
        """Test checking token exists in memory."""
        self.store.use_dynamodb = False
        self.store._memory_tokens.add("test-token")

        assert self.store.contains("test-token") is True

    def test_contains_memory_not_found(self):
        """Test checking token doesn't exist in memory."""
        self.store.use_dynamodb = False

        assert self.store.contains("nonexistent") is False

    @patch("app.db_adapter.dynamodb_table")
    def test_contains_dynamodb_found(self, mock_table):
        """Test checking token exists in DynamoDB."""
        self.store.use_dynamodb = True
        mock_table.get_item.return_value = {"Item": {"token": "test-token"}}

        result = self.store.contains("test-token")
        assert result is True

        # Verify get_item call
        mock_table.get_item.assert_called_once()
        call_args = mock_table.get_item.call_args[1]["Key"]
        assert call_args["PK"] == "TOKEN#AUTH"
        assert call_args["SK"] == "TOKEN#test-token"

    @patch("app.db_adapter.dynamodb_table")
    def test_contains_dynamodb_not_found(self, mock_table):
        """Test checking token doesn't exist in DynamoDB."""
        self.store.use_dynamodb = True
        mock_table.get_item.return_value = {}  # No "Item" key

        result = self.store.contains("test-token")
        assert result is False

    @patch("app.db_adapter.dynamodb_table")
    def test_contains_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB contains failure falls back to memory."""
        self.store.use_dynamodb = True
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        # Set up memory fallback
        self.store._memory_tokens.add("test-token")

        result = self.store.contains("test-token")
        assert result is True

    @patch("app.db_adapter.dynamodb_table")
    def test_clear_dynamodb(self, mock_table):
        """Test clearing all tokens from DynamoDB."""
        self.store.use_dynamodb = True

        mock_table.query.return_value = {
            "Items": [
                {"PK": "TOKEN#AUTH", "SK": "TOKEN#token1"},
                {"PK": "TOKEN#AUTH", "SK": "TOKEN#token2"},
            ]
        }

        # Mock batch writer
        mock_batch = Mock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch

        self.store.clear()

        # Verify query and batch delete
        mock_table.query.assert_called_once()
        assert mock_batch.delete_item.call_count == 2

    def test_clear_memory(self):
        """Test clearing all tokens from memory."""
        self.store.use_dynamodb = False

        self.store._memory_tokens.add("token1")
        self.store._memory_tokens.add("token2")

        self.store.clear()
        assert len(self.store._memory_tokens) == 0


class TestRatingsCache:
    """Test RatingsCache class functionality."""

    def setup_method(self):
        """Set up test instances."""
        self.cache = RatingsCache()

    def test_init(self):
        """Test RatingsCache initialization."""
        cache = RatingsCache()
        assert isinstance(cache._memory_cache, dict)
        assert isinstance(cache.use_dynamodb, bool)

    def test_get_memory(self):
        """Test getting rating from memory cache."""
        self.cache.use_dynamodb = False

        test_rating = {"score": 0.8, "timestamp": "2023-01-01"}
        self.cache._memory_cache["test-artifact"] = test_rating

        result = self.cache.get("test-artifact")
        assert result == test_rating

    def test_get_memory_not_found(self):
        """Test getting non-existent rating from memory."""
        self.cache.use_dynamodb = False

        result = self.cache.get("nonexistent")
        assert result is None

    @patch("app.db_adapter.dynamodb_table")
    def test_get_dynamodb_found(self, mock_table):
        """Test getting rating from DynamoDB."""
        self.cache.use_dynamodb = True

        test_rating = {"score": 0.8, "timestamp": "2023-01-01"}
        mock_table.get_item.return_value = {"Item": {"data": json.dumps(test_rating)}}

        result = self.cache.get("test-artifact")
        assert result == test_rating

        # Verify get_item call
        call_args = mock_table.get_item.call_args[1]["Key"]
        assert call_args["PK"] == "RATING#CACHE"
        assert call_args["SK"] == "RATING#test-artifact"

    @patch("app.db_adapter.dynamodb_table")
    def test_get_dynamodb_not_found(self, mock_table):
        """Test getting non-existent rating from DynamoDB."""
        self.cache.use_dynamodb = True
        mock_table.get_item.return_value = {}  # No "Item" key

        result = self.cache.get("test-artifact")
        assert result is None

    @patch("app.db_adapter.dynamodb_table")
    def test_get_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB get failure falls back to memory."""
        self.cache.use_dynamodb = True
        mock_table.get_item.side_effect = Exception("DynamoDB error")

        # Set up memory fallback
        test_rating = {"score": 0.8}
        self.cache._memory_cache["test-artifact"] = test_rating

        result = self.cache.get("test-artifact")
        assert result == test_rating

    def test_set_memory(self):
        """Test setting rating in memory cache."""
        self.cache.use_dynamodb = False

        # Mock rating object with __dict__ attribute
        mock_rating = Mock()
        mock_rating.__dict__ = {"score": 0.8, "timestamp": "2023-01-01"}

        self.cache.set("test-artifact", mock_rating)

        assert "test-artifact" in self.cache._memory_cache
        assert self.cache._memory_cache["test-artifact"] == mock_rating

    @patch("app.db_adapter.dynamodb_table")
    def test_set_dynamodb_success(self, mock_table):
        """Test setting rating in DynamoDB."""
        self.cache.use_dynamodb = True
        mock_table.put_item = Mock()

        # Mock rating object
        mock_rating = Mock()
        mock_rating.__dict__ = {"score": 0.8, "timestamp": "2023-01-01"}

        self.cache.set("test-artifact", mock_rating)

        # Verify put_item call
        mock_table.put_item.assert_called_once()
        call_args = mock_table.put_item.call_args[1]["Item"]
        assert call_args["PK"] == "RATING#CACHE"
        assert call_args["SK"] == "RATING#test-artifact"
        assert call_args["artifact_id"] == "test-artifact"

        # Verify JSON serialization
        stored_data = json.loads(call_args["data"])
        assert stored_data["score"] == 0.8

    @patch("app.db_adapter.dynamodb_table")
    def test_set_dynamodb_failure_fallback(self, mock_table):
        """Test DynamoDB set failure falls back to memory."""
        self.cache.use_dynamodb = True
        mock_table.put_item.side_effect = Exception("DynamoDB error")

        mock_rating = Mock()
        mock_rating.__dict__ = {"score": 0.8}

        self.cache.set("test-artifact", mock_rating)

        # Should fallback to memory
        assert "test-artifact" in self.cache._memory_cache
        assert self.cache._memory_cache["test-artifact"] == mock_rating

    @patch("app.db_adapter.dynamodb_table")
    def test_clear_dynamodb(self, mock_table):
        """Test clearing all ratings from DynamoDB."""
        self.cache.use_dynamodb = True

        mock_table.query.return_value = {
            "Items": [
                {"PK": "RATING#CACHE", "SK": "RATING#artifact1"},
                {"PK": "RATING#CACHE", "SK": "RATING#artifact2"},
            ]
        }

        # Mock batch writer
        mock_batch = Mock()
        mock_table.batch_writer.return_value.__enter__.return_value = mock_batch

        self.cache.clear()

        # Verify query and batch delete
        mock_table.query.assert_called_once()
        assert mock_batch.delete_item.call_count == 2

    def test_clear_memory(self):
        """Test clearing all ratings from memory."""
        self.cache.use_dynamodb = False

        self.cache._memory_cache["artifact1"] = {"score": 0.8}
        self.cache._memory_cache["artifact2"] = {"score": 0.9}

        self.cache.clear()
        assert len(self.cache._memory_cache) == 0


class TestDataSerialization:
    """Test JSON serialization and data handling."""

    def test_complex_data_serialization(self):
        """Test serialization of complex artifact data."""
        store = ArtifactStore()
        store.use_dynamodb = False

        complex_data = {
            "metadata": {
                "id": "complex-artifact",
                "name": "Complex Model",
                "type": "model",
                "version": "2.1.0",
                "tags": ["nlp", "transformer", "bert"],
                "status": "approved",
            },
            "data": {
                "model_link": "https://example.com/model",
                "code_link": "https://github.com/example/repo",
                "dataset_link": "https://dataset.example.com",
                "trust_score": 0.85,
                "metrics": {"accuracy": 0.92, "f1_score": 0.89, "precision": 0.91, "recall": 0.87},
                "dependencies": ["torch", "transformers", "numpy"],
                "license": "Apache-2.0",
                "size": 1073741824,  # 1GB
                "description": "A fine-tuned BERT model for sentiment analysis",
            },
        }

        store.save("model", "complex-artifact", complex_data)
        retrieved = store.get("model", "complex-artifact")

        assert retrieved == complex_data
        assert isinstance(retrieved["data"]["dependencies"], list)
        assert isinstance(retrieved["data"]["metrics"], dict)

    def test_decimal_handling(self):
        """Test handling of Decimal types for DynamoDB compatibility."""
        store = ArtifactStore()

        # Test conversion to Decimal for trust_score
        artifact_data = {
            "metadata": {"id": "test", "name": "test", "type": "model", "version": "1.0.0"},
            "data": {"trust_score": 0.123456789, "metrics": {"score": 0.987654321}},
        }

        with patch("app.db_adapter.dynamodb_table") as mock_table:
            store.use_dynamodb = True
            mock_table.put_item = Mock()

            store.save("model", "test", artifact_data)

            call_args = mock_table.put_item.call_args[1]["Item"]
            assert isinstance(call_args["trust_score"], Decimal)
            assert str(call_args["trust_score"]) == "0.123456789"

    def test_empty_data_handling(self):
        """Test handling of empty or missing data fields."""
        store = ArtifactStore()
        store.use_dynamodb = False

        minimal_data = {
            "metadata": {"id": "minimal", "name": "Minimal", "type": "model", "version": "1.0.0"},
            "data": {},
        }

        store.save("model", "minimal", minimal_data)
        retrieved = store.get("model", "minimal")

        assert retrieved == minimal_data
        assert retrieved["data"] == {}
