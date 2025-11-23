import requests
from rich import print

# BASE_URL = "https://ot47z7sef6wrgsvcw3bmrh752e0hzclv.lambda-url.us-east-2.on.aws/"
BASE_URL = "http://localhost:5000"

# Step 0: Health check

print(f"[magenta]Testing health at {BASE_URL}/health[/magenta]")

auth_resp = requests.get(f"{BASE_URL}/health")
assert auth_resp.status_code == 200, f"Health check failed: {auth_resp.text}"

print("[green]Health check passed.[/green]")


# Step 1: Authenticate
print(f"[magenta]Authenticating at {BASE_URL}/authenticate[/magenta]")


# Use frontend convention: user and secret objects
auth_payload = {
    "user": {"name": "ece30861defaultadminuser"},
    "secret": {"password": '''correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;'''}
}

auth_resp = requests.put(f"{BASE_URL}/authenticate", json=auth_payload)
assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
token = auth_resp.json()

print(f"[green]Authentication succeeded. Token: '{token[7::]}'[/green]")


# Step 2: Reset registry
headers = {"Authorization": f"Bearer {token[7::]}"}
print(f"[magenta]Resetting registry at {BASE_URL}/reset[/magenta]")
reset_resp = requests.delete(f"{BASE_URL}/reset", headers=headers)
if reset_resp.status_code == 200:
    print("[yellow]Registry reset successfully.[/yellow]")
else:
    print(f"[red]Registry reset failed: {reset_resp.status_code} {reset_resp.text}[/red]")

