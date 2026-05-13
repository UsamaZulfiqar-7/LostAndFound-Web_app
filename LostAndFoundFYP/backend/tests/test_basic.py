import json
import pytest

def test_home_page(client):
    """Test the home page works and returns expected text."""
    response = client.get("/")
    assert response.status_code == 200
    assert b"Backend is running successfully!" in response.data

def test_signup_missing_fields(client):
    """Test signup fails when fields are missing."""
    response = client.post("/signup", json={})
    assert response.status_code == 400
    data = response.get_json()
    assert "msg" in data

def test_login_wrong_credentials(client):
    """Test login fails with incorrect credentials."""
    response = client.post("/login", json={
        "email": "nonexistent@test.com",
        "password": "wrong"
    })
    assert response.status_code == 401
    data = response.get_json()
    assert data["msg"] == "Invalid credentials"

def test_ai_feature_extraction_lazy_load(app):
    """Test that the AI model can be lazy-loaded without crashing."""
    from app import get_ai_model
    with app.app_context():
        model = get_ai_model()
        assert model is not None
        # Subsequent calls should return the same instance
        model2 = get_ai_model()
        assert model is model2

def test_lost_items_public(client):
    """Test that public lost items list is accessible."""
    response = client.get("/lost-items")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)

def test_found_items_public(client):
    """Test that public found items list is accessible."""
    response = client.get("/found-items")
    assert response.status_code == 200
    assert isinstance(response.get_json(), list)

def test_notifications_unauthorized(client):
    """Test that notifications require authentication."""
    response = client.get("/notifications")
    assert response.status_code == 401

def test_admin_stats_unauthorized(client):
    """Test that admin stats require authentication and admin role."""
    response = client.get("/admin/stats")
    assert response.status_code == 401
