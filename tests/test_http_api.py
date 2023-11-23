import json

def test_get_records(api_test_client, config_file):
    r = api_test_client.get("/")
    assert r.status_code == 200
    assert r.json() == config_file

def test_add_record(api_test_client):
    r = api_test_client.put(
        "/",
        json={"type": "A", "domain": "*.nashvillenibblers.com", "value": "192.168.69.69"}
    )
    assert r.status_code == 200

    r = api_test_client.get("/")
    assert r.status_code == 200
    assert r.json()["A"]["*.nashvillenibblers.com"] == "192.168.69.69"

def test_delete_record(api_test_client):
    r = api_test_client.request(
        method="DELETE",
        url="/",
        content=json.dumps({"type": "A", "domain": "*.nashvillenibblers.com", "value": "192.168.69.69"}).encode()
    )
    assert r.status_code == 200

    r = api_test_client.get("/")
    assert r.status_code == 200
    assert not r.json()["A"].get("*.nashvillenibblers.com", None)

def test_logs(api_test_client):
    r = api_test_client.get("/logs")
    assert r.status_code == 200

    r = api_test_client.get(
        "/logs",
        params={"type": "A"}
    )
    assert r.status_code == 200
    assert len(r.json())

    r = api_test_client.get(
        "/logs",
        params={"name": "fuck.shit.com"}
    )
    assert r.status_code == 200
    assert len(r.json())

    r = api_test_client.get(
        "/logs",
        params={"name": "fuck.shit.com", "type": "A"}
    )
    assert r.status_code == 200
    assert len(r.json())
