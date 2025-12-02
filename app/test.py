import requests
from rich import print

BASE_URL = "https://ot47z7sef6wrgsvcw3bmrh752e0hzclv.lambda-url.us-east-2.on.aws/"
# BASE_URL = "http://localhost:5000"

print(f"[blue]Testing health at {BASE_URL}/health[/blue]")
auth_resp = requests.get(f"{BASE_URL}/health")
assert auth_resp.status_code == 200, f"Health check failed: {auth_resp.text}"
print("[green]Health check passed.[/green]")

# Step 1: Authenticate
print(f"[blue]Authenticating at {BASE_URL}/authenticate[/blue]")

auth_payload = {
    "username": "ece30861defaultadminuser",
    "password": '''correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;''',
    "role": "admin",
}

auth_resp = requests.put(f"{BASE_URL}/authenticate", json=auth_payload)
print("Auth response:", auth_payload)
assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
token = auth_resp.json()["token"]
print(f"[green]Authentication succeeded. Token: {token}[/green]")

# Step 2: Query models
headers = {"Authorization": f"Bearer {token}"}
query_payload = [{"Name": "", "Version": ""}]  # Empty to get all models

resp = requests.post(f"{BASE_URL}/artifacts?limit=10", json=query_payload, headers=headers)
assert resp.status_code == 200, f"Model query failed: {resp.text}"
models = resp.json()

print("Retrieved models:", models)