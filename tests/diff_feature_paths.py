"""Find which feature differs between the CSV path and the web/seed path."""

import os
import sys
from pathlib import Path

os.environ.setdefault("ASSUREX_DATABASE_URL", "sqlite:///dbg_diff.db")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

import app as application  # noqa: E402
import claim_service  # noqa: E402
from preprocessing import prepare_features  # noqa: E402
from rule_engine import load_policies  # noqa: E402
from sample_data import load_dataset, row_to_form, select_one_per_scenario  # noqa: E402

application.bootstrap()
policies = load_policies(PROJECT_ROOT / "dataset" / "policies")
application.get_pipeline()  # populate the cache
features = application._pipeline_cache["features"]

frame = select_one_per_scenario(load_dataset())
row = frame[frame.scenario == "standard_covered"].iloc[0]
form = row_to_form(row)

from_csv = prepare_features(pd.DataFrame([row.to_dict()]), list(features))

claim = {
    "claim_id": form["claim_id"],
    "product_category": form["product_category"],
    "brand": form["brand"],
    "model": form["model"],
    "retailer": form["retailer"],
    "purchase_date": form["purchase_date"],
    "purchase_price": float(form["purchase_price"] or 0),
    "purchase_information_consistent": form["purchase_information_consistent"] == "on",
    "serial_number": form["serial_number"],
    "receipt_serial_number": form["receipt_serial_number"],
    "warranty_card_serial_number": form["warranty_card_serial_number"],
    "product_image_serial_number": form["product_image_serial_number"],
    "repair_record_serial_number": form["repair_record_serial_number"],
    "receipt_model": form["model"],
    "warranty_card_model": form["model"],
    "product_image_model": form["model"],
    "repair_record_model": form["model"],
    "warranty_provider": form["warranty_provider"],
    "warranty_start_date": form["purchase_date"],
    "warranty_expiry_date": form["warranty_expiry_date"],
    "warranty_duration_months": int(form["warranty_duration_months"] or 12),
    "extended_warranty": form["extended_warranty"] == "on",
    "fault_date": form["fault_date"],
    "claim_date": form["claim_date"],
    "last_repair_date": form["last_repair_date"] or None,
    "fault_category": form["fault_category"],
    "fault_description": form["fault_description"],
    "damage_type": form["damage_type"],
    "physical_damage": form["physical_damage"] == "on",
    "liquid_damage": form["liquid_damage"] == "on",
    "unauthorized_repair": form["unauthorized_repair"] == "on",
    "authorized_service_center": form["authorized_service_center"] == "on",
    "previous_repair_count": int(form["previous_repair_count"] or 0),
    "previous_replacement": form["previous_replacement"] == "on",
    "previous_replacement_count": int(form["previous_replacement_count"] or 0),
    "replacement_requested": form["replacement_requested"] == "on",
    "receipt_available": form["receipt_available"] == "on",
    "receipt_valid": form["receipt_valid"] == "on",
    "warranty_card_available": form["warranty_card_available"] == "on",
    "product_image_available": form["product_image_available"] == "on",
    "serial_evidence_available": form["serial_evidence_available"] == "on",
    "fault_evidence_available": form["fault_evidence_available"] == "on",
    "repair_report_available": form["repair_report_available"] == "on",
}
claim.update(claim_service.derive_numeric_facts(claim, policies["Laptop"]))

from_form = prepare_features(
    pd.DataFrame([{name: claim.get(name, "") for name in features}]),
    list(features),
)

print(f"{'column':36s} {'CSV path':28s} {'form path':28s}")
print("-" * 96)
diffs = 0
for name in features:
    if name not in from_csv.columns:
        continue
    left = str(from_csv[name].iloc[0])[:27]
    right = str(from_form[name].iloc[0])[:27]
    if left != right:
        diffs += 1
        print(f"{name:36s} {left:28s} {right:28s}  DIFFERS")

print()
print(f"differing columns: {diffs} of {len(features)}")
