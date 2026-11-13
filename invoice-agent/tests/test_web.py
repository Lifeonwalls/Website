from fastapi.testclient import TestClient

from app import invoices
from tests.test_core import add_email, inv


def client():
    from app.web import app
    return TestClient(app)


def test_login_and_pages():
    with client() as c:
        assert c.get("/", follow_redirects=False).status_code == 303
        assert c.post("/login", data={"username": "admin", "password": "nope"}).status_code == 401
        r = c.post("/login", data={"username": "admin", "password": "pw", "next": "/"}, follow_redirects=False)
        assert r.status_code == 303
        e = add_email()
        iid = invoices.upsert_extracted(e, None, inv(), 0)
        for path in ["/", "/invoices", "/invoices?status=any&review=1", "/emails", "/reports", "/chat", "/improve"]:
            assert c.get(path).status_code == 200, path
        r = c.post(f"/api/invoices/{iid}", json={"changes": {"amount_due": "10"}, "comment": "test"})
        assert r.status_code == 200 and r.json()["amount_due"] == 10
        assert c.post(f"/api/invoices/{iid}", json={"changes": {"status": "bogus"}}).status_code == 400
        rep = c.post("/api/reports", json={"notify": False}).json()
        assert c.get(f"/reports/{rep['id']}").status_code == 200
    with client() as anon:
        assert anon.get(f"/r/{rep['share_token']}").status_code == 200
        assert anon.get("/r/wrong").status_code == 404
        assert anon.post("/api/chat", json={"message": "hi"}).status_code == 401
