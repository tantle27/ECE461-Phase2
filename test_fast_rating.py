#!/usr/bin/env python3
"""Test fast rating mode functionality."""
import os
import sys
from unittest.mock import MagicMock
from datetime import datetime

# Mock secrets loader BEFORE any other imports
sys.modules['app.secrets_loader'] = MagicMock()

# Set fast rating mode (can be overridden by environment)
if "FAST_RATING_MODE" not in os.environ:
    os.environ["FAST_RATING_MODE"] = "true"

from app.scoring import _score_artifact_with_metrics

# Create a mock artifact
class MockMetadata:
    id = "test-123"
    name = "Test Model"
    type = "model"

class MockArtifact:
    def __init__(self):
        self.metadata = MockMetadata()
        self.data = {
            "model_link": "https://huggingface.co/test/model",
            "code_link": "https://github.com/test/repo",
            "dataset_link": "https://huggingface.co/datasets/test/data",
        }

def test_fast_rating():
    artifact = MockArtifact()
    
    print("Testing FAST_RATING_MODE...")
    print(f"FAST_RATING_MODE env: {os.environ.get('FAST_RATING_MODE')}")
    print()
    
    try:
        rating = _score_artifact_with_metrics(artifact)
        
        print("✅ Rating generated successfully!")
        print(f"   ID: {rating.id}")
        print(f"   Generated at: {rating.generated_at}")
        print()
        print("Scores:")
        for key, value in sorted(rating.scores.items()):
            print(f"   {key}: {value}")
        print()
        print("Latencies:")
        for key, value in sorted(rating.latencies.items()):
            print(f"   {key}: {value}")
        print()
        
        # Verify all required attributes are present
        required_attrs = [
            "net_score", "bus_factor", "code_quality", "dataset_quality",
            "dataset_and_code_score", "license", "performance_claims",
            "ramp_up_time", "reproducibility", "reviewedness", "tree_score"
        ]
        
        missing = [attr for attr in required_attrs if attr not in rating.scores]
        if missing:
            print(f"❌ Missing attributes: {missing}")
            return False
        
        # Verify non-zero scores
        zero_scores = [k for k, v in rating.scores.items() 
                      if k != "tree_score" and v == 0.0]
        if zero_scores:
            print(f"⚠️  Zero scores found: {zero_scores}")
        else:
            print("✅ All scores are non-zero (except tree_score)")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = test_fast_rating()
    sys.exit(0 if success else 1)
