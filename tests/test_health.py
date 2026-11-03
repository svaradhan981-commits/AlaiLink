def test_health_is_fast_and_ok(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok", "app": "AlaiLink", "environment": "test"}


def test_hello_is_ok(client):
    r = client.get("/hello")
    assert r.status_code == 200
    assert r.json() == {"message": "Hello  AlaiLink in test!"}

