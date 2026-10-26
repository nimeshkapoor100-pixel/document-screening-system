import pytest
from app import app
from database import verify_user, create_user

@pytest.fixture
def client():
    app.config["TESTING"] = True
    app.config["SECRET_KEY"] = "test-secret-key-12345"
    with app.test_client() as client:
        yield client

def test_login_page_renders(client):
    """GET /login should return 200 and render the Shadcn login interface."""
    res = client.get("/login")
    assert res.status_code == 200
    html = res.data.decode("utf-8")
    assert "Officer Login" in html
    assert "SSB-88429-DEL" in html
    assert "Secure Terminal Authentication" in html
    assert "Satark Sarthi" in html
    assert "tailwind.config" in html

def test_unauthenticated_redirect_to_login(client):
    """GET / without session should redirect to /login."""
    res = client.get("/")
    assert res.status_code == 302
    assert "/login" in res.headers["Location"]

def test_login_missing_fields(client):
    """POST /login with missing credentials should return 400."""
    res = client.post("/login", json={"officerId": ""})
    assert res.status_code == 400
    data = res.get_json()
    assert data["status"] == "error"

def test_login_invalid_credentials(client):
    """POST /login with incorrect password should return 401."""
    res = client.post("/login", json={
        "officerId": "SSB-88429-DEL",
        "password": "wrongpassword999"
    })
    assert res.status_code == 401
    data = res.get_json()
    assert data["status"] == "error"
    assert "Invalid password" in data["message"] or "credentials" in data["message"]

def test_login_success_and_session(client):
    """POST /login with valid officer credentials (only ID and password) should succeed and establish session."""
    res = client.post("/login", json={
        "officerId": "SSB-88429-DEL",
        "password": "password123"
    })
    assert res.status_code == 200
    data = res.get_json()
    assert data["status"] == "success"
    assert data["redirect"] == "/"

    # Now verify /api/me has authenticated officer
    me_res = client.get("/api/me")
    assert me_res.status_code == 200
    me_data = me_res.get_json()
    assert me_data["authenticated"] is True
    assert me_data["user"]["officer_id"] == "SSB-88429-DEL"

    # Now verify GET / loads dashboard without redirect
    dash_res = client.get("/")
    assert dash_res.status_code == 200
    html = dash_res.data.decode("utf-8")
    assert "Identity & Document Screening" in html
    assert "Satark Sarthi" in html
    assert "/logout" in html
    assert "Logout" in html

def test_logout_flow(client):
    """GET /logout should clear session and redirect to /login."""
    # First login with only ID and password
    client.post("/login", json={
        "officerId": "SSB-88429-DEL",
        "password": "password123"
    })

    # Call logout
    logout_res = client.get("/logout")
    assert logout_res.status_code == 302
    assert "/login" in logout_res.headers["Location"]

    # Verify session is cleared
    me_res = client.get("/api/me")
    assert me_res.status_code == 401
