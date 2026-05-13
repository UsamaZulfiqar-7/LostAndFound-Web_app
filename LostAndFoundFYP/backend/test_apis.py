"""
API Test Script for LostAndFound Backend
Tests all endpoints for correct responses and edge cases.
"""
import requests
import json
import sys

BASE = "http://127.0.0.1:5000"
PASS = "[PASS]"
FAIL = "[FAIL]"
SKIP = "[SKIP]"

results = {"pass": 0, "fail": 0, "skip": 0}

def test(name, response, expected_status, expected_field=None, expected_value=None):
    status_ok = response.status_code == expected_status
    field_ok = True

    if expected_field and status_ok:
        try:
            data = response.json()
            if expected_value is not None:
                field_ok = data.get(expected_field) == expected_value
            else:
                field_ok = expected_field in data
        except Exception:
            field_ok = False

    if status_ok and field_ok:
        results["pass"] += 1
        print(f"  {PASS} {name} (HTTP {response.status_code})")
    else:
        results["fail"] += 1
        try:
            body = response.json()
        except Exception:
            body = response.text[:200]
        print(f"  {FAIL} {name} (HTTP {response.status_code}, expected {expected_status})")
        print(f"        Response: {body}")

def skip(name, reason):
    results["skip"] += 1
    print(f"  {SKIP} {name} - {reason}")


print("\n" + "=" * 60)
print("  LOSTANDFOUND BACKEND API TEST SUITE")
print("=" * 60)

# ------------------------------------------------------------------
# 1. HOME
# ------------------------------------------------------------------
print("\n--- HOME ---")
r = requests.get(f"{BASE}/")
test("GET / returns 200", r, 200)

# ------------------------------------------------------------------
# 2. SIGNUP - EDGE CASES
# ------------------------------------------------------------------
print("\n--- SIGNUP ---")

# Missing fields
r = requests.post(f"{BASE}/signup", json={})
test("Signup with empty body -> 400", r, 400)

r = requests.post(f"{BASE}/signup", json={"email": "x@x.com"})
test("Signup with missing fields -> 400", r, 400)

# Valid signup
r = requests.post(f"{BASE}/signup", json={
    "name": "API Test User",
    "email": "apitest@test.com",
    "password": "Secure@123",
    "role": "loser"
})
# Could be 201 (new) or 409 (already exists)
if r.status_code == 201:
    test("Signup valid user -> 201", r, 201)
elif r.status_code == 409:
    test("Signup duplicate user -> 409", r, 409)
else:
    test("Signup valid user -> 201 or 409", r, 201)

# Duplicate signup
r = requests.post(f"{BASE}/signup", json={
    "name": "API Test User",
    "email": "apitest@test.com",
    "password": "Secure@123",
    "role": "loser"
})
test("Signup duplicate email -> 409", r, 409)

# ------------------------------------------------------------------
# 3. LOGIN - EDGE CASES
# ------------------------------------------------------------------
print("\n--- LOGIN ---")

# Missing fields
r = requests.post(f"{BASE}/login", json={})
test("Login with empty body -> 400", r, 400)

# Wrong credentials
r = requests.post(f"{BASE}/login", json={
    "email": "wrong@test.com",
    "password": "wrong"
})
test("Login with bad credentials -> 401", r, 401)

# Valid login
r = requests.post(f"{BASE}/login", json={
    "email": "apitest@test.com",
    "password": "Secure@123"
})
test("Login with valid credentials -> 200", r, 200, "token")

token = None
user_id = None
if r.status_code == 200:
    data = r.json()
    token = data.get("token")
    user_id = data.get("user_id")

# Admin login
r = requests.post(f"{BASE}/login", json={
    "email": "admin@lostfound.com",
    "password": "Admin@1234"
})
test("Admin login -> 200", r, 200, "token")

admin_token = None
if r.status_code == 200:
    admin_token = r.json().get("token")

# ------------------------------------------------------------------
# 4. PROTECTED ROUTES WITHOUT TOKEN
# ------------------------------------------------------------------
print("\n--- AUTH PROTECTION ---")

r = requests.get(f"{BASE}/notifications")
test("Notifications without token -> 401", r, 401)

r = requests.get(f"{BASE}/my-lost-items")
test("My lost items without token -> 401", r, 401)

r = requests.get(f"{BASE}/finder-dashboard")
test("Finder dashboard without token -> 401", r, 401)

r = requests.post(f"{BASE}/lost-item")
test("Post lost item without token -> 401", r, 401)

# Invalid token
headers_bad = {"Authorization": "Bearer invalidtoken123"}
r = requests.get(f"{BASE}/notifications", headers=headers_bad)
test("Notifications with bad token -> 401", r, 401)

# ------------------------------------------------------------------
# 5. PUBLIC ITEM LISTINGS
# ------------------------------------------------------------------
print("\n--- PUBLIC ENDPOINTS ---")

r = requests.get(f"{BASE}/lost-items")
test("GET /lost-items -> 200", r, 200)

r = requests.get(f"{BASE}/found-items")
test("GET /found-items -> 200", r, 200)

# ------------------------------------------------------------------
# 6. AUTHENTICATED ENDPOINTS
# ------------------------------------------------------------------
print("\n--- AUTHENTICATED ENDPOINTS ---")

if token:
    headers = {"Authorization": f"Bearer {token}"}

    r = requests.get(f"{BASE}/notifications", headers=headers)
    test("GET /notifications with token -> 200", r, 200)

    r = requests.get(f"{BASE}/my-lost-items", headers=headers)
    test("GET /my-lost-items with token -> 200", r, 200)

    r = requests.get(f"{BASE}/my-found-items", headers=headers)
    test("GET /my-found-items with token -> 200", r, 200)

    r = requests.get(f"{BASE}/user/{user_id}", headers=headers)
    test("GET /user/<id> own profile -> 200", r, 200, "name")

    # Edge case: access another user's profile
    other_id = 9999
    r = requests.get(f"{BASE}/user/{other_id}", headers=headers)
    test("GET /user/<other_id> -> 403", r, 403)

    # Lost item - missing fields
    r = requests.post(f"{BASE}/lost-item", headers=headers, data={})
    test("POST /lost-item missing fields -> 400", r, 400)

    # Found item - missing fields
    r = requests.post(f"{BASE}/found-item", headers=headers, data={})
    test("POST /found-item missing fields -> 400", r, 400)

    # Request chat - missing item id
    r = requests.post(f"{BASE}/request-chat", headers=headers, json={})
    test("POST /request-chat missing id -> 400", r, 400)

    # Request chat - invalid item id
    r = requests.post(f"{BASE}/request-chat", headers=headers, json={"lost_item_id": 99999})
    test("POST /request-chat invalid id -> 404", r, 404)
else:
    skip("Authenticated endpoints", "No valid token obtained")

# ------------------------------------------------------------------
# 7. ADMIN ENDPOINTS
# ------------------------------------------------------------------
print("\n--- ADMIN ENDPOINTS ---")

if admin_token:
    admin_headers = {"Authorization": f"Bearer {admin_token}"}

    r = requests.get(f"{BASE}/admin/stats", headers=admin_headers)
    test("GET /admin/stats -> 200", r, 200, "total_lost")

    r = requests.get(f"{BASE}/admin/top-finders", headers=admin_headers)
    test("GET /admin/top-finders -> 200", r, 200)

    r = requests.get(f"{BASE}/admin/returned-items", headers=admin_headers)
    test("GET /admin/returned-items -> 200", r, 200)

    r = requests.get(f"{BASE}/admin/chat-requests", headers=admin_headers)
    test("GET /admin/chat-requests -> 200", r, 200)

    # Admin endpoints with non-admin token
    if token:
        user_headers = {"Authorization": f"Bearer {token}"}
        r = requests.get(f"{BASE}/admin/stats", headers=user_headers)
        test("GET /admin/stats with user token -> 403", r, 403)

    # Match item - missing IDs
    r = requests.post(f"{BASE}/match-item", headers=admin_headers, json={})
    test("POST /match-item missing IDs -> 400", r, 400)

    # Match item - invalid IDs
    r = requests.post(f"{BASE}/match-item", headers=admin_headers, json={
        "lost_item_id": 99999, "found_item_id": 99999
    })
    test("POST /match-item invalid IDs -> 404", r, 404)

    # Approve chat - missing ID
    r = requests.post(f"{BASE}/admin/approve-chat", headers=admin_headers, json={})
    test("POST /admin/approve-chat missing ID -> 400", r, 400)

    # Approve chat - invalid ID
    r = requests.post(f"{BASE}/admin/approve-chat", headers=admin_headers, json={"lost_item_id": 99999})
    test("POST /admin/approve-chat invalid ID -> 404", r, 404)

    # Compare images - missing IDs
    r = requests.post(f"{BASE}/admin/compare-images", headers=admin_headers, json={})
    test("POST /admin/compare-images missing IDs -> 400", r, 400)
else:
    skip("Admin endpoints", "No admin token obtained")

# ------------------------------------------------------------------
# 8. QR VIEW - EDGE CASE
# ------------------------------------------------------------------
print("\n--- QR VIEW ---")
r = requests.get(f"{BASE}/qr/99999")
test("GET /qr/<invalid_id> -> 404", r, 404)

# ------------------------------------------------------------------
# SUMMARY
# ------------------------------------------------------------------
print("\n" + "=" * 60)
total = results["pass"] + results["fail"] + results["skip"]
print(f"  RESULTS: {results['pass']}/{total} passed, "
      f"{results['fail']} failed, {results['skip']} skipped")
print("=" * 60 + "\n")

if results["fail"] > 0:
    sys.exit(1)
