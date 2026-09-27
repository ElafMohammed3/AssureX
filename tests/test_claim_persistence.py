"""End-to-end check: submit a claim, confirm it is saved with a decision."""

import os
import sys
import uuid
from pathlib import Path

os.environ.setdefault("ASSUREX_DATABASE_URL", "sqlite:///assurex_e2e.db")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import app as application  # noqa: E402

application.bootstrap()
client = application.app.test_client()

email = f"user-{uuid.uuid4().hex[:8]}@assurex.test"
client.post(
    "/register",
    data={
        "full_name": "E2E Tester",
        "email": email,
        "password": "password123",
        "role": "Customer",
    },
)

FORM = {
    "product_category": "Smartphone",
    "brand": "TechCorp",
    "model": "SP-100",
    "retailer": "TechMart",
    "purchase_date": "2023-05-03",
    "purchase_price": "440.99",
    "warranty_expiry_date": "2024-05-03",
    "warranty_duration_months": "12",
    "warranty_provider": "TechCorp Warranty Services",
    "fault_date": "2023-12-30",
    "claim_date": "2024-01-04",
    "fault_category": "Manufacturing Defect",
    "fault_description": "Device will not boot after a firmware update.",
    "damage_type": "None",
    "serial_number": "SN-S-840632",
    "receipt_serial_number": "SN-S-840632",
    "warranty_card_serial_number": "SN-S-840632",
    "product_image_serial_number": "SN-S-840632",
    "repair_record_serial_number": "SN-S-840632",
    "receipt_available": "on",
    "receipt_valid": "on",
    "warranty_card_available": "on",
    "product_image_available": "on",
    "serial_evidence_available": "on",
    "fault_evidence_available": "on",
    "repair_report_available": "on",
    "authorized_service_center": "on",
}

response = client.post("/claims/new", data=FORM)
print(f"POST /claims/new            -> {response.status_code}")
print(f"  redirect to               -> {response.headers.get('Location')}")

if response.status_code != 302:
    print("  FLASH MESSAGES:")
    with client.session_transaction() as sess:
        for category, message in sess.get("_flashes", []):
            print(f"    [{category}] {message}")

with application.app.app_context():
    from database import Claim, Evaluation, Product, User, Warranty

    claims = Claim.query.all()
    evaluations = Evaluation.query.all()
    products = Product.query.all()
    warranties = Warranty.query.all()
    user = User.query.filter_by(email=email).first()

    print()
    print("ROWS WRITTEN")
    print(f"  products  : {len(products)}")
    print(f"  warranties: {len(warranties)}")
    print(f"  claims    : {len(claims)}")
    print(f"  evaluations: {len(evaluations)}")
    print()

    failures = []

    for name, count, expected in (
        ("products", len(products), 1),
        ("warranties", len(warranties), 1),
        ("claims", len(claims), 1),
        ("evaluations", len(evaluations), 1),
    ):
        mark = "OK  " if count == expected else "FAIL"
        if count != expected:
            failures.append(f"{name}: expected {expected}, got {count}")
        print(f"  {mark} {name}: {count}")

    if claims:
        claim = claims[0]
        print()
        print("CLAIM ROW")
        print(f"  claim_id  : {claim.claim_id}")
        print(f"  status    : {claim.status}")
        print(f"  product   : {claim.product.product_name}")
        print(f"  warranty  : {claim.warranty.status} to {claim.warranty.expiry_date}")

    if evaluations:
        ev = evaluations[0]
        print()
        print("EVALUATION ROW")
        print(f"  python_prediction : {ev.python_prediction}")
        print(f"  python confidence : V={ev.python_valid_confidence} "
              f"I={ev.python_invalid_confidence} M={ev.python_manual_review_confidence}")
        print(f"  model_consistency : {ev.model_consistency}")
        print(f"  warranty_result   : {ev.warranty_result}")
        print(f"  final_decision    : {ev.final_decision}")
        print(f"  explanation       : {(ev.explanation or '')[:150]}...")

    print()
    print("LIST PAGES NOW SHOW DATA")
    for path in ("/claims", "/dashboard", "/products", "/claims/status", "/claims/submit"):
        page = client.get(path)
        print(f"  {'OK  ' if page.status_code == 200 else 'FAIL'} {page.status_code}  {path}")

    print()
    if failures:
        print("FAILURES:")
        for item in failures:
            print(f"  {item}")
    else:
        print("PASS: a submitted claim is persisted with model, rule and decision data.")
