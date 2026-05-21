def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_root(client):
    r = client.get("/")
    assert r.status_code == 200
    assert r.json()["name"] == "bc-api"


def test_docs_available(client):
    r = client.get("/docs")
    assert r.status_code == 200
