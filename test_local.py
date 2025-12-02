#!/usr/bin/env python3
"""
Local test script to verify reset and authentication work correctly.
Run this before deploying to AWS to catch issues early.
"""

import json
import requests
import sys

# Adjust this if your local Flask app runs on a different port
BASE_URL = "http://localhost:5000"

def test_health():
    """Test health endpoint"""
    print("\n=== Testing Health Endpoint ===")
    response = requests.get(f"{BASE_URL}/health")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200 and response.json().get("ok") == True

def test_tracks():
    """Test tracks endpoint"""
    print("\n=== Testing Tracks Endpoint ===")
    response = requests.get(f"{BASE_URL}/tracks")
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    # Try both camelCase and snake_case
    tracks = response.json().get("planned_tracks", []) or response.json().get("plannedTracks", [])
    has_access_control = "Access control track" in tracks
    print(f"Has 'Access control track': {has_access_control}")
    return has_access_control

def test_authenticate():
    """Test authentication"""
    print("\n=== Testing Authentication ===")
    payload = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": """correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;"""}
    }
    response = requests.put(f"{BASE_URL}/authenticate", json=payload)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    
    if response.status_code == 200:
        token = response.json().strip('"')
        print(f"Received token: {token}")
        return token
    return None

def test_reset(token):
    """Test reset endpoint"""
    print("\n=== Testing Reset ===")
    headers = {"X-Authorization": token}
    response = requests.delete(f"{BASE_URL}/reset", headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")
    return response.status_code == 200

def test_list_artifacts_after_reset(token):
    """Test that no artifacts exist after reset"""
    print("\n=== Testing Artifact List After Reset ===")
    headers = {"X-Authorization": token}
    payload = [{"name": "*"}]
    response = requests.post(f"{BASE_URL}/artifacts", json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    artifacts = response.json()
    print(f"Response: {artifacts}")
    print(f"Number of artifacts: {len(artifacts)}")
    return len(artifacts) == 0

def test_create_artifact(token):
    """Test creating an artifact after reset; return id if successful"""
    print("\n=== Testing Artifact Creation ===")
    headers = {"X-Authorization": token}
    payload = {"url": "https://huggingface.co/bert-base-uncased"}
    response = requests.post(f"{BASE_URL}/artifact/model", json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    try:
        body = response.json()
    except Exception:
        body = {}
    print(f"Response: {body}")
    if response.status_code == 201:
        # Body may be the created artifact dict
        created_id = None
        if isinstance(body, dict):
            created_id = body.get("id") or (body.get("metadata", {}) or {}).get("id")
        print(f"Created artifact id: {created_id}")
        return created_id
    return None

def test_rate_endpoint(token, artifact_id=None):
    """Create a model artifact and test the rating endpoint."""
    print("\n=== Testing Rating Endpoint ===")
    headers = {"X-Authorization": token}
    # Create artifact if id not provided
    if not artifact_id:
        artifact_id = test_create_artifact(token)
    if not artifact_id:
        print("Failed to create artifact; cannot test rating.")
        return False
    # Call rate endpoint
    url = f"{BASE_URL}/artifact/model/{artifact_id}/rate"
    response = requests.get(url, headers=headers)
    print(f"Rate Status: {response.status_code}")
    try:
        rating = response.json()
    except Exception:
        rating = {}
    print(f"Rating Response: {json.dumps(rating, indent=2)}")
    # Basic validations
    if response.status_code != 200:
        return False
    required_keys = [
        "net_score",
        "bus_factor",
        "code_quality",
        "dataset_quality",
        "dataset_and_code_score",
        "license",
        "performance_claims",
        "ramp_up_time",
    ]
    has_keys = all(k in rating for k in required_keys)
    print(f"Rating has required keys: {has_keys}")
    return has_keys

def test_reset_clears_artifacts(token):
    """Test that reset actually clears artifacts"""
    print("\n=== Testing Reset Clears Artifacts ===")
    
    # Create an artifact
    headers = {"X-Authorization": token}
    payload = {"url": "https://github.com/test/artifact1"}
    response = requests.post(f"{BASE_URL}/artifact/model", json=payload, headers=headers)
    print(f"Created artifact: {response.status_code}")
    
    # Verify it exists
    payload = [{"name": "*"}]
    response = requests.post(f"{BASE_URL}/artifacts", json=payload, headers=headers)
    artifacts_before = response.json()
    print(f"Artifacts before reset: {len(artifacts_before)}")
    
    # Reset
    response = requests.delete(f"{BASE_URL}/reset", headers=headers)
    print(f"Reset status: {response.status_code}")
    
    # Verify cleared
    response = requests.post(f"{BASE_URL}/artifacts", json=payload, headers=headers)
    artifacts_after = response.json()
    print(f"Artifacts after reset: {len(artifacts_after)}")
    
    return len(artifacts_after) == 0

def test_auth_persists_after_reset(token):
    """Test that authentication still works after reset"""
    print("\n=== Testing Auth Persists After Reset ===")
    
    # Reset
    headers = {"X-Authorization": token}
    response = requests.delete(f"{BASE_URL}/reset", headers=headers)
    print(f"Reset status: {response.status_code}")
    
    # Try to use same token
    payload = [{"name": "*"}]
    response = requests.post(f"{BASE_URL}/artifacts", json=payload, headers=headers)
    print(f"Post-reset auth status: {response.status_code}")
    
    return response.status_code in [200, 201]

def main():
    """Run all tests"""
    print("=" * 60)
    print("ECE 461 Phase 2 - Local Testing")
    print("=" * 60)
    print(f"\nTesting against: {BASE_URL}")
    print("\nMake sure your Flask app is running:")
    print("  python -m app.app")
    print("\nor")
    print("  flask --app app.app run")
    print("=" * 60)
    
    results = {}
    
    # Test health
    results["Health"] = test_health()
    
    # Test tracks
    results["Tracks (Access Control)"] = test_tracks()
    
    # Test authentication
    token = test_authenticate()
    results["Authentication"] = token is not None
    
    if token:
        # Test reset
        results["Reset"] = test_reset(token)
        
        # Test artifacts cleared after reset
        results["Artifacts Cleared After Reset"] = test_list_artifacts_after_reset(token)
        
        # Test can create artifact
        created_id = test_create_artifact(token)
        results["Create Artifact"] = created_id is not None

        # Test rating endpoint
        results["Rate Endpoint"] = test_rate_endpoint(token, created_id)
        
        # Test reset actually clears
        results["Reset Clears Artifacts"] = test_reset_clears_artifacts(token)
        
        # Test auth persists
        results["Auth Persists After Reset"] = test_auth_persists_after_reset(token)
    
    # Print summary
    print("\n" + "=" * 60)
    print("TEST SUMMARY")
    print("=" * 60)
    passed = 0
    total = 0
    for test_name, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
        total += 1
    
    print("=" * 60)
    print(f"Total: {passed}/{total} tests passed")
    print("=" * 60)
    
    if passed == total:
        print("\n🎉 All tests passed! Ready to deploy.")
        return 0
    else:
        print("\n❌ Some tests failed. Check the output above.")
        return 1

if __name__ == "__main__":
    try:
        sys.exit(main())
    except requests.exceptions.ConnectionError:
        print("\n❌ Error: Could not connect to the Flask app.")
        print("Make sure the app is running on", BASE_URL)
        print("\nStart it with:")
        print("  python -m app.app")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user.")
        sys.exit(1)
