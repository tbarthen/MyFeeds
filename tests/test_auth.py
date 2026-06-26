import pytest

from src.app import create_app


@pytest.fixture
def auth_client(tmp_path):
    app = create_app({
        "TESTING": True,
        "DATABASE": str(tmp_path / "test.db"),
        "APP_PASSWORD": "test-password",
        "SECRET_KEY": "test-secret-key",
    })
    return app.test_client()


def test_unauthenticated_request_redirects_to_login(auth_client):
    resp = auth_client.get("/")
    assert resp.status_code == 302
    assert "/login" in resp.headers["Location"]


def test_health_is_exempt_from_auth(auth_client):
    resp = auth_client.get("/health")
    assert resp.status_code == 200


def test_correct_password_grants_access(auth_client):
    resp = auth_client.post("/login", data={"password": "test-password"})
    assert resp.status_code == 302
    assert auth_client.get("/").status_code == 200


def test_wrong_password_is_rejected_and_stays_locked(auth_client):
    resp = auth_client.post("/login", data={"password": "wrong"})
    assert resp.status_code == 200
    assert b"Incorrect password" in resp.data
    assert auth_client.get("/").status_code == 302


def test_open_redirect_is_blocked(auth_client):
    resp = auth_client.post("/login?next=https://evil.example/", data={"password": "test-password"})
    assert resp.status_code == 302
    assert "evil.example" not in resp.headers["Location"]


def test_no_password_configured_leaves_app_open(client):
    assert client.get("/").status_code == 200


def test_unknown_path_404s_instead_of_redirecting(auth_client):
    assert auth_client.get("/vendor/phpunit/eval-stdin.php").status_code == 404
    assert auth_client.get("/.env").status_code == 404
    assert auth_client.get("/wp-admin").status_code == 404


def test_wrong_method_on_real_route_does_not_redirect(auth_client):
    # / accepts GET only; POST should 405, not redirect to /login (which would
    # cost a kilobyte of login HTML to whatever scanner sent the POST).
    resp = auth_client.post("/")
    assert resp.status_code != 302
