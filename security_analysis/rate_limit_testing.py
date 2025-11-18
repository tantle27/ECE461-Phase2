
import requests  # type: ignore
import io
import threading
import time
from rich import print  # type: ignore

def endpoint_to_use(i, agent_id, headers):
    upload_endpoint(i, agent_id, headers)

# BASE_URL = "https://ot47z7sef6wrgsvcw3bmrh752e0hzclv.lambda-url.us-east-2.on.aws/"
BASE_URL = "http://localhost:5000"

NUM_AGENTS = 1
UPLOADS_PER_AGENT = 20
WAIT_BETWEEN_UPLOADS = 0.0  # seconds

RESET_REGISTRY_BEFORE_TEST = True
RESET_REGISTRY_AFTER_TEST = False

# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
# DO NOT BYPASS THESE WARNINGS <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

if BASE_URL != "http://localhost:5000":
    print("\n\n[red bold]Warning: BASE_URL is not localhost. Ensure this is intended before running the rate limit test against a production server.[/red bold]")
    print(f">>> You are going to rate limit test: [yellow] {BASE_URL} [/yellow]")
    if RESET_REGISTRY_BEFORE_TEST or RESET_REGISTRY_AFTER_TEST: 
        print(f">>> [magenta]WARNING: RESET_REGISTRY_BEFORE_TEST = {RESET_REGISTRY_BEFORE_TEST} or RESET_REGISTRY_BEFORE_TEST = {RESET_REGISTRY_AFTER_TEST} is set to True! This will DELETE ALL DATA on the target server AFTER the test![/magenta]")
    print(f">>> You are going to send {NUM_AGENTS * UPLOADS_PER_AGENT} requests in total.\n")
    if input("Type 'yes' to continue: ") != 'yes':
        exit("Aborted by user.")
    if input(f"Are you really, really sure you want to hit  >> {BASE_URL} <<  with  >> {NUM_AGENTS * UPLOADS_PER_AGENT} <<  requests, type '{NUM_AGENTS * UPLOADS_PER_AGENT} requests': ") != f'{NUM_AGENTS * UPLOADS_PER_AGENT} requests':
        exit("Aborted by user.")
    if RESET_REGISTRY_BEFORE_TEST or RESET_REGISTRY_AFTER_TEST:
        if input("You have set RESET_REGISTRY_AFTER_TEST to True! This will DELETE ALL DATA on the target server AFTER the test! Type 'delete entire registry': ") != 'delete entire registry':
            exit("Aborted by user.")

# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
# DO NOT BYPASS THESE WARNINGS <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<
# <<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<<

def agent(token, agent_id):
    headers = {"Authorization": f"Bearer {token}"}
    start_i = agent_id * UPLOADS_PER_AGENT
    end_i = start_i + UPLOADS_PER_AGENT
    for i in range(start_i, end_i):
        endpoint_to_use(i, agent_id, headers)
        time.sleep(WAIT_BETWEEN_UPLOADS)
    
def upload_endpoint(i, agent_id, headers):
    model_url = f"https://huggingface.co/google-bert/bert-base-uncased{i}"
    filename = f"rate-limit-test-agent-{agent_id}-num-{i}.txt"
    file_content = f"Model URL: {model_url}".encode()
    files = {
        "file": (filename, io.BytesIO(file_content), "text/plain"),
    }
    data = {
        "name": f"rate-limit-test-agent-{agent_id}-num-{i}",
        "artifact_type": "model",
        "id": f"{i}",
    }
    try:
        upload_resp = requests.post(f"{BASE_URL}/upload", files=files, data=data, headers=headers)
        if upload_resp.status_code == 201:
            if agent_id == 0:
                print(f"Agent {agent_id}: Model upload {round(i / UPLOADS_PER_AGENT * 100, 2)}% succeeded.\r", end="\r")
        else:
            print(f"[red]Agent {agent_id}: Model upload {i} failed: {upload_resp.text}[/red]")
    except Exception as e:
        print(f"[red]Agent {agent_id}: Exception during upload {i}: {e}[/red]")


def main():
    auth_resp = requests.get(f"{BASE_URL}/health")
    assert auth_resp.status_code == 200, f"Health check failed: {auth_resp.text}"
    print("Health check passed.")

    auth_payload = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": '''correcthorsebatterystaple123(!__+@**(A'\"`;DROP TABLE packages;'''}
    }
    auth_resp = requests.put(f"{BASE_URL}/authenticate", json=auth_payload)
    assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
    token = auth_resp.json()
    token_str = token[7::] if isinstance(token, str) else token

    start = time.time()

    threads = []
    for agent_id in range(NUM_AGENTS):
        t = threading.Thread(target=agent, args=(token_str, agent_id))
        t.start()
        threads.append(t)

    for t in threads:
        t.join()
        
    end = time.time()

    print("\n\n[green]Rate limit test complete.[/green]")
    print(f" > [cyan]Total time for uploads: {end - start} seconds[/cyan]")
    print(f" > [cyan]Average time per upload: {(end - start) / (NUM_AGENTS * UPLOADS_PER_AGENT)} seconds[/cyan]\n")

if __name__ == "__main__":
    
    if RESET_REGISTRY_BEFORE_TEST:
        # Use frontend convention: user and secret objects
        auth_payload = {
            "user": {"name": "ece30861defaultadminuser"},
            "secret": {"password": '''correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;'''}
        }

        auth_resp = requests.put(f"{BASE_URL}/authenticate", json=auth_payload)
        assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
        token = auth_resp.json()
        
        headers = {"Authorization": f"Bearer {token[7::]}"}
        reset_resp = requests.delete(f"{BASE_URL}/reset", headers=headers)
        if reset_resp.status_code == 200:
            print("[yellow]Registry reset successfully.[/yellow]")
        else:
            print(f"[red]Registry reset failed: {reset_resp.status_code} {reset_resp.text}[/red]")
    
    main()  # rate limit test
    
    # Step 1: Authenticate
    # Use frontend convention: user and secret objects
    auth_payload = {
        "user": {"name": "ece30861defaultadminuser"},
        "secret": {"password": '''correcthorsebatterystaple123(!__+@**(A'"`;DROP TABLE packages;'''}
    }

    auth_resp = requests.put(f"{BASE_URL}/authenticate", json=auth_payload)
    assert auth_resp.status_code == 200, f"Auth failed: {auth_resp.text}"
    token = auth_resp.json()

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

    print(f"[magenta]Number of models retrieved:[/magenta] {len(models)} / {(NUM_AGENTS * UPLOADS_PER_AGENT)}")
    
    if RESET_REGISTRY_AFTER_TEST:
        # Step 4: Reset registry
        headers = {"Authorization": f"Bearer {token[7::]}"}
        reset_resp = requests.delete(f"{BASE_URL}/reset", headers=headers)
        if reset_resp.status_code == 200:
            print("[yellow]Registry reset successfully.[/yellow]")
        else:
            print(f"[red]Registry reset failed: {reset_resp.status_code} {reset_resp.text}[/red]")

    # Verify all uploaded model IDs are present
    collected_ids = []
    for model in models:
        if int(model['id']) >= 0 and int(model['id']) < (NUM_AGENTS * UPLOADS_PER_AGENT):
            collected_ids.append(int(model['id']))
        
    collected_ids.sort()
    
    if collected_ids == list(range(NUM_AGENTS * UPLOADS_PER_AGENT)):
        print("[green]All uploaded model IDs are present.[/green]\n")
    else:
        print("[red]Some uploaded model IDs are missing.[/red]\n")
    