#!/usr/bin/env python3
"""Quick test of lambda_handler to verify awsgi integration."""

import json
from app.lambda_handler import handler

# Simulate a Lambda Function URL event
test_event = {
    "rawPath": "/health",
    "requestContext": {
        "http": {
            "method": "GET",
            "path": "/health"
        }
    },
    "headers": {},
    "queryStringParameters": None,
    "body": None,
    "isBase64Encoded": False
}

class FakeContext:
    request_id = "test-request-123"

try:
    response = handler(test_event, FakeContext())
    print("✓ Lambda handler executed successfully")
    print(f"Status: {response.get('statusCode')}")
    print(f"Body preview: {response.get('body', '')[:100]}")
    
    if response.get('statusCode') == 200:
        print("\n✓ Handler returned 200 OK")
    else:
        print(f"\n✗ Handler returned {response.get('statusCode')}")
        
except Exception as e:
    print(f"✗ Lambda handler failed: {e}")
    import traceback
    traceback.print_exc()
