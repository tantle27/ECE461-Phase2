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



# Step 2: Upload a model artifact using multipart/form-data
import io
i = 2
model_url = f"https://huggingface.co/google-bert/bert-base-uncased{i}"
filename = "bert-base-uncased.txt"
file_content = f"Model URL: {model_url}".encode()

upload_headers = {"Authorization": f"Bearer {token[7::]}"}
files = {
    "file": (filename, io.BytesIO(file_content), "text/plain"),
}
data = {
    "name": "bert-base-uncased",
    "artifact_type": "model",
    "id": f"id-{i}",
}
upload_resp = requests.post(f"{BASE_URL}/upload", files=files, data=data, headers=upload_headers)
assert upload_resp.status_code == 201, f"Model upload failed: {upload_resp.text}"
print("[green]Model upload succeeded.[/green]")


# Step 3: Query models using backend convention
headers = {"Authorization": f"Bearer {token[7::]}"}
all_models = []
page = 1
page_size = 10

while True:
    query_payload = [{
        "artifact_type": "model",
        "name": "",
        "page": page,
        "page_size": page_size
    }]
    resp = requests.post(f"{BASE_URL}/artifacts", json=query_payload, headers=headers)
    assert resp.status_code == 200, f"Model query failed: {resp.text}"
    models = resp.json()
    if not models:
        break
    all_models.extend(models)
    page += 1

models = all_models

print("[magenta]Retrieved models:[/magenta]", models)
print("Number of models retrieved:", len(models))
