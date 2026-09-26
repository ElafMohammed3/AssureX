"""Smoke test: every route, as a signed-in Administrator."""

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("ASSUREX_DATABASE_URL", "sqlite:///assurex_dev.db")
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app as application  # noqa: E402

application.bootstrap()
client = application.app.test_client()

# A unique email each run, so the test is repeatable against a persistent
# SQLite file instead of failing on "email already registered".
ADMIN_EMAIL = f"admin-{uuid.uuid4().hex[:8]}@assurex.test"

register_response = client.post(
    "/register",
    data={
        "full_name": "Admin",
        "email": ADMIN_EMAIL,
        "password": "admin12345",
        "role": "Administrator",
    },
)
print(f"  register -> {register_response.status_code} "
      f"{register_response.headers.get('Location')}")

with client.session_transaction() as sess:
    print(f"  session  -> {dict(sess)}")
print()

ROUTES = [
    "/dashboard",
    "/claims",
    "/claims/new",
    "/products",
    "/documents",
    "/claims/status",
    "/manual-review",
    "/analytics",
    "/audit",
    "/users",
    "/warranty-rules",
    "/admin/dashboard",
    "/profile",
]

failures = []

for path in ROUTES:
    response = client.get(path)
    status = "OK  " if response.status_code == 200 else "FAIL"
    print(f"  {status} {response.status_code}  {path}")
    if response.status_code != 200:
        failures.append((path, response.status_code, response.headers.get("Location")))

print()
print(f"FAILING ROUTES: {len(failures)}")
for path, code, location in failures:
    print(f"  {path} -> {code} {location}")
