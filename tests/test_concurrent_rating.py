"""Test concurrent rating performance under autograder-like load."""
import concurrent.futures
import os
import sys
import time
from pathlib import Path

# Add project root to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

os.environ["GH_TOKEN"] = os.environ.get("GH_TOKEN", "")
os.environ["RATING_CACHE_TTL_SECONDS"] = "1800"  # 30 min cache

from app.app import create_app
from app.core import _ARTIFACT_STORE, _STORE, _TOKENS, _load_state


def test_concurrent_rating_load():
    """Simulate autograder's concurrent rating requests."""
    app = create_app()
    _load_state()
    
    # Create admin token
    _TOKENS["test_admin_token"] = True
    
    # Get all model artifacts
    all_artifacts = list(_STORE.values())
    model_artifacts = [a for a in all_artifacts if a.metadata.type == "model"]
    
    if not model_artifacts:
        print("No model artifacts found - skipping concurrent rating test")
        return
    
    # Limit to first 13 models (same as autograder)
    model_ids = [a.metadata.id for a in model_artifacts[:13]]
    
    print(f"Testing concurrent rating for {len(model_ids)} models")
    print(f"Model IDs: {model_ids}")
    
    with app.test_client() as client:
        # Warm up cache
        print("\n=== Cache Warm-up ===")
        response = client.get(
            f"/artifact/model/{model_ids[0]}/rate",
            headers={"Authorization": "Bearer test_admin_token"}
        )
        print(f"Warm-up status: {response.status_code}")
        
        # Test concurrent requests (simulate autograder)
        print("\n=== Concurrent Rating Test ===")
        start_time = time.time()
        
        def rate_artifact(artifact_id):
            req_start = time.time()
            response = client.get(
                f"/artifact/model/{artifact_id}/rate",
                headers={"Authorization": "Bearer test_admin_token"}
            )
            req_duration = time.time() - req_start
            return {
                "id": artifact_id,
                "status": response.status_code,
                "duration": req_duration,
                "success": response.status_code == 200,
                "data": response.get_json() if response.status_code == 200 else None
            }
        
        # Use ThreadPoolExecutor to simulate concurrent autograder requests
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as executor:
            futures = [executor.submit(rate_artifact, aid) for aid in model_ids]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        total_duration = time.time() - start_time
        
        # Analyze results
        successes = [r for r in results if r["success"]]
        failures = [r for r in results if not r["success"]]
        
        print(f"\n=== Results ===")
        print(f"Total time: {total_duration:.2f}s")
        print(f"Success: {len(successes)}/{len(model_ids)}")
        print(f"Failures: {len(failures)}/{len(model_ids)}")
        
        if successes:
            durations = [r["duration"] for r in successes]
            print(f"Avg duration: {sum(durations)/len(durations):.2f}s")
            print(f"Min duration: {min(durations):.2f}s")
            print(f"Max duration: {max(durations):.2f}s")
        
        if failures:
            print("\nFailed artifacts:")
            for r in failures:
                print(f"  {r['id']}: status={r['status']} duration={r['duration']:.2f}s")
        
        # Verify rating quality
        if successes:
            print("\n=== Rating Quality Sample ===")
            sample = successes[0]
            if sample["data"]:
                print(f"Sample artifact: {sample['id']}")
                print(f"  net_score: {sample['data'].get('net_score')}")
                print(f"  bus_factor: {sample['data'].get('bus_factor')}")
                print(f"  license: {sample['data'].get('license')}")
                print(f"  code_quality: {sample['data'].get('code_quality')}")
        
        # Success criteria (aligned with autograder)
        success_rate = len(successes) / len(model_ids)
        print(f"\n=== Assessment ===")
        print(f"Success rate: {success_rate*100:.1f}%")
        
        if success_rate >= 0.85:
            print("✓ PASS - High success rate under concurrent load")
        elif success_rate >= 0.5:
            print("~ PARTIAL - Some timeouts/failures under load")
        else:
            print("✗ FAIL - Most requests failed")
        
        return success_rate >= 0.5


if __name__ == "__main__":
    success = test_concurrent_rating_load()
    sys.exit(0 if success else 1)
