"""
Sample claim seeding for demonstration and for SRS deliverable 8.

Why this exists
---------------
SRS deliverable 8 requires the submission to demonstrate at least:

    one valid claim, one invalid claim, one manual-review claim,
    one expired-warranty claim, one missing-document claim,
    one duplicate claim, one contradictory claim, one serial-number mismatch,
    one unauthorized-repair claim, one tricky boundary-date claim,
    and one case where the two models disagree

SRS deliverable 12 requires sample claim records to be submitted with the
project.

Rather than inventing rows in HTML, this module selects real records from the
project's own dataset, runs each one through the real trained model, the real
warranty rule engine and the real decision engine, and persists the outcome.
So every number visible in the web interface is a genuine system output that can
be traced back to a specific dataset record.

The seeded claims are clearly flagged: their Claim IDs are prefixed SAMPLE- and
their source scenario is recorded in the claim's purchase_details JSON, so
demonstration data can never be mistaken for genuine user submissions.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Mapping

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
if str(PROJECT_ROOT / "src") not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT / "src"))

import pandas as pd  # noqa: E402

from claim_service import derive_numeric_facts, persist_submission  # noqa: E402
from database import Claim, User, db  # noqa: E402

# SRS deliverable 8 wording -> the dataset scenario that demonstrates it.
SRS_DEMO_CASES: dict[str, str] = {
    "one valid claim": "standard_covered",
    "one invalid claim": "excluded_damage",
    "one manual-review claim": "contradictory_information",
    "one expired-warranty claim": "expired_warranty",
    "one missing-document claim": "missing_mandatory_document",
    "one duplicate claim": "duplicate_claim",
    "one contradictory claim": "contradictory_information",
    "one serial-number mismatch": "serial_mismatch",
    "one unauthorized-repair claim": "unauthorized_repair",
    "one tricky boundary-date claim": "borderline_reporting",
    "one near-expiry boundary claim": "near_expiry_boundary",
    "one complex covered claim": "complex_covered",
    "one extended-warranty claim": "extended_warranty",
    "one late-reporting claim": "late_reporting",
    "one invalid-receipt claim": "invalid_receipt",
    "one replacement-not-eligible claim": "replacement_not_eligible",
    "one service-centre-unclear claim": "service_center_unclear",
}

DEMO_EMAIL = "demo@assurex.test"
DEMO_PASSWORD = "demo12345"

# Checkbox fields in the claim form, derived from dataset booleans.
CHECKBOX_FIELDS = (
    "purchase_information_consistent",
    "extended_warranty",
    "physical_damage",
    "liquid_damage",
    "unauthorized_repair",
    "authorized_service_center",
    "previous_replacement",
    "replacement_requested",
    "receipt_available",
    "receipt_valid",
    "warranty_card_available",
    "product_image_available",
    "serial_evidence_available",
    "fault_evidence_available",
    "repair_report_available",
)

# Dataset field -> claim-form field, where the names differ.
FIELD_MAP = {
    "receipt_serial_number": "receipt_serial_number",
    "warranty_card_serial_number": "warranty_card_serial_number",
    "product_image_serial_number": "product_image_serial_number",
    "repair_record_serial_number": "repair_record_serial_number",
    "fault_date": "fault_date",
    "claim_date": "claim_date",
    "purchase_date": "purchase_date",
    "warranty_expiry_date": "warranty_expiry_date",
}


def row_to_form(row: Mapping[str, Any]) -> dict[str, Any]:
    """Convert one dataset record into the shape the claim form submits."""
    form: dict[str, Any] = {
        "claim_id": f"SAMPLE-{row['claim_id']}",
        "product_category": row.get("product_category", ""),
        "brand": row.get("brand", ""),
        "model": row.get("model", ""),
        "product_name": f"{row.get('brand', '')} {row.get('model', '')}".strip(),
        "retailer": row.get("retailer", ""),
        "purchase_date": _text(row.get("purchase_date")),
        "purchase_price": _text(row.get("purchase_price")),
        "warranty_provider": row.get("warranty_provider", ""),
        "warranty_expiry_date": _text(row.get("warranty_expiry_date")),
        "warranty_duration_months": _text(row.get("warranty_duration_months", 12)),
        "fault_date": _text(row.get("fault_date")),
        "claim_date": _text(row.get("claim_date")),
        "last_repair_date": _text(row.get("last_repair_date")),
        "fault_category": row.get("fault_category", ""),
        "fault_description": row.get("fault_description", ""),
        # Left blank when absent so the categorical branch of
        # prepare_features normalises it to "Missing", matching the CSV.
        "damage_type": _text(row.get("damage_type")),
        "serial_number": row.get("serial_number", ""),
        "receipt_serial_number": row.get("receipt_serial_number", ""),
        "warranty_card_serial_number": row.get("warranty_card_serial_number", ""),
        "product_image_serial_number": row.get("product_image_serial_number", ""),
        "repair_record_serial_number": row.get("repair_record_serial_number", ""),
        "previous_repair_count": _text(row.get("previous_repair_count", 0)),
        "previous_replacement_count": _text(row.get("previous_replacement_count", 0)),
    }

    for name in CHECKBOX_FIELDS:
        form[name] = "on" if bool(row.get(name)) else ""

    return form


def _text(value: Any) -> str:
    if value is None:
        return ""
    try:
        if value != value:  # NaN
            return ""
    except TypeError:
        pass
    text = str(value)
    return "" if text in {"nan", "NaT", "None"} else text


def get_demo_user() -> User:
    """Create the demonstration account if it does not exist."""
    user = User.query.filter_by(email=DEMO_EMAIL).first()

    if user is not None:
        return user

    from werkzeug.security import generate_password_hash

    user = User(
        user_id="USR-DEMO-0001",
        full_name="Demo Reviewer",
        email=DEMO_EMAIL,
        password_hash=generate_password_hash(DEMO_PASSWORD),
        role="Administrator",
    )
    db.session.add(user)
    db.session.commit()

    return user


def load_dataset() -> pd.DataFrame:
    """Load the canonical split. Seeding is not model training."""
    parts = [
        pd.read_csv(PROJECT_ROOT / "dataset" / "csv" / f"{split}.csv")
        for split in ("train", "validation", "test")
    ]
    return pd.concat(parts, ignore_index=True)


def select_one_per_scenario(frame: pd.DataFrame) -> pd.DataFrame:
    """
    Choose one representative record per scenario.

    Preference order puts validation and test records first, because SRS
    section 1.2 says those splits exist for evaluation and demonstration. Using
    them for the demo does not contaminate the model, which has already been
    fitted and saved.
    """
    ordered = frame.copy()
    ordered["_rank"] = ordered["split"].map(
        {"validation": 0, "test": 1, "train": 2}
    ).fillna(3)
    ordered = ordered.sort_values(["_rank", "claim_id"])

    return ordered.groupby("scenario", as_index=False).first().drop(columns="_rank")


def seed(evaluator, model_version: str) -> dict[str, Any]:
    """
    Insert one evaluated claim per SRS-required demonstration case.

    `evaluator` is a callable taking a form dict and returning the same
    structure as `app.evaluate_submission`, so the seeder uses the real
    inference path rather than reimplementing it.
    """
    user = get_demo_user()
    frame = select_one_per_scenario(load_dataset())

    report: dict[str, Any] = {
        "created": [],
        "skipped": [],
        "srs_cases": {},
    }

    for _, row in frame.iterrows():
        scenario = str(row["scenario"])
        form = row_to_form(row)
        form["source_scenario"] = scenario

        claim_id = form["claim_id"]

        if Claim.query.filter_by(claim_id=claim_id).first() is not None:
            report["skipped"].append(claim_id)
            continue

        result = evaluator(form)
        decision = _decide(result)

        try:
            claim, evaluation = persist_submission(
                user, form, result, decision, model_version
            )
        except Exception as error:  # noqa: BLE001 - reported, not raised
            report["skipped"].append(f"{claim_id} ({error})")
            continue

        record = {
            "claim_id": claim.claim_id,
            "scenario": scenario,
            "source_claim_id": str(row["claim_id"]),
            "actual_class": str(row["claim_class"]),
            "python_prediction": result.get("python_predicted_class"),
            "rule_outcome": result.get("rule_outcome"),
            "final_decision": decision.final_decision,
            "consistency": decision.consistency.status,
            "status": claim.status,
        }
        report["created"].append(record)

    for srs_requirement, scenario in SRS_DEMO_CASES.items():
        match = [r for r in report["created"] if r["scenario"] == scenario]
        report["srs_cases"][srs_requirement] = (
            match[0]["claim_id"] if match else "NOT SEEDED"
        )

    return report


def _decide(result: Mapping[str, Any]):
    from decision_engine import decide_from_evaluation

    return decide_from_evaluation(result, result.get("rule_result"))
