"""
AssureX Claim Engine - final dataset generator.

SRS source:
  AssureX Claim Engine - NextWave AI and ML SRS, section 1.2, pages 8-9.

The SRS requires the team to create its own common warranty-claim dataset.
It must contain 500 Valid Claim, 500 Invalid Claim and 500 Manual Review
records. The same records are written to CSV and rendered as Claim Summary
Cards. Records are split 70/15/15 before cards are generated.

This version is intentionally designed for competition evaluation:

- IDs are assigned after scenario generation and shuffling.
- Duplicate claims are real groups and never cross data splits.
- Warranty expiry uses calendar months.
- Every record is checked for date and policy invariants.
- Model inputs are explicitly separated from audit/rule outputs.
- The Claim Summary Card contains facts only, never a prediction or label.
- Policies are written as configurable JSON files.
- Data dictionary, feature manifest, statistics and validation report are written.
- A fixed seed makes the dataset reproducible.
- Card variations change presentation only, not claim facts.

Run from any directory:

    py -3 dataset_generator_final.py

Test in an isolated output folder first:

    py -3 dataset_generator_final.py --root dataset_test --keep-existing
"""

from __future__ import annotations

import argparse
import calendar
import csv
import hashlib
import json
import random
import shutil
from collections import Counter, defaultdict
from datetime import date, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

from PIL import Image, ImageDraw, ImageFont


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

CLASS_NAMES = ("Valid Claim", "Invalid Claim", "Manual Review")
CLASS_FOLDERS = {
    "Valid Claim": "valid",
    "Invalid Claim": "invalid",
    "Manual Review": "manual_review",
}
SPLIT_TARGETS = {"train": 350, "validation": 75, "test": 75}
SPLIT_NAMES = ("train", "validation", "test")
TOTAL_CLAIMS = 1500
DEFAULT_SEED = 42


# ---------------------------------------------------------------------------
# Configurable warranty policies
# ---------------------------------------------------------------------------

POLICIES: dict[str, dict[str, Any]] = {
    "Smartphone": {
        "product_category": "Smartphone",
        "coverage_duration_months": 12,
        "warranty_start_conditions": [
            "Valid purchase receipt from authorized seller",
            "Original serial number intact",
        ],
        "covered_faults": {
            "Manufacturing Defect": "Internal motherboard defect causing bootloop.",
            "Screen Defect (Non-Impact)": "Touch failure or dead pixels with no physical drop.",
            "Battery Manufacturing Defect": "Battery swelling or sudden degradation.",
            "Charging Port Failure": "Charging connector failure under normal usage.",
        },
        "exclusions": {
            "Physical Damage": "Cracked screen or casing from impact.",
            "Liquid Damage": "Liquid contact indicator triggered.",
            "Unauthorized Repair": "Device opened by third-party technician.",
        },
        "claim_reporting_period_days": 30,
        "repair_conditions": ["Authorized service centre inspection mandatory"],
        "authorized_service_centre_required": True,
        "replacement_conditions": {
            "eligible_after_repairs": 2,
            "unrepairable_covered_fault": True,
        },
        "grace_period_days": 7,
        "mandatory_documents": [
            "Purchase Receipt",
            "Warranty Card",
            "Serial Number Photo",
        ],
        "hard_fail_rules": [
            "Warranty expired",
            "Liquid damage present",
            "Unauthorized repair detected",
        ],
        "warning_rules": [
            "Claim submitted within grace period",
            "Minor cosmetic wear",
        ],
        "manual_review_rules": [
            "Receipt serial mismatch",
            "Inconsistent claim date",
            "Duplicate claim detected",
        ],
        "brands": ["TechCorp", "MobileX", "ApexPhone"],
        "models": ["SP-100", "SP-200", "SP-X"],
        "retailers": ["TechMart", "City Electronics", "Mobile Hub"],
    },
    "Laptop": {
        "product_category": "Laptop",
        "coverage_duration_months": 24,
        "warranty_start_conditions": ["Valid purchase receipt from authorized seller"],
        "covered_faults": {
            "Motherboard Defect": "Component failure on main board.",
            "Keyboard Failure": "Multiple keys non-functional.",
            "Display Failure": "Backlight failure without screen crack.",
            "Factory SSD Failure": "Primary storage failure.",
        },
        "exclusions": {
            "Physical Damage": "Hinge broken or chassis damage.",
            "Liquid Damage": "Liquid spill marks internal.",
            "Unauthorized Modification": "RAM/SSD force modification damage.",
        },
        "claim_reporting_period_days": 45,
        "repair_conditions": ["Manufacturer original parts required"],
        "authorized_service_centre_required": True,
        "replacement_conditions": {
            "eligible_after_repairs": 3,
            "unrepairable_covered_fault": True,
        },
        "grace_period_days": 14,
        "mandatory_documents": [
            "Purchase Receipt",
            "Serial Number Photo",
            "Technical Diagnostic Report",
        ],
        "hard_fail_rules": [
            "Warranty expired",
            "Liquid damage",
            "Unauthorized modification",
        ],
        "warning_rules": ["Battery health degradation under 80%"],
        "manual_review_rules": [
            "Hardware modification status unclear",
            "Conflicting repair records",
        ],
        "brands": ["ProBook", "UltraTech", "OmniLap"],
        "models": ["LP-500", "LP-900", "LP-Pro"],
        "retailers": ["OfficeDirect", "PC World", "Digital Bazaar"],
    },
    "Television": {
        "product_category": "Television",
        "coverage_duration_months": 18,
        "warranty_start_conditions": ["Authorized retailer purchase receipt"],
        "covered_faults": {
            "Display Panel Defect": "Internal panel line defect.",
            "Power Supply Failure": "Internal power board failure.",
            "Main Board Defect": "Smart hub system failure.",
        },
        "exclusions": {
            "Cracked Screen": "External screen crack from impact.",
            "Electrical Surge": "High voltage power surge damage.",
            "Liquid Damage": "Liquid intrusion.",
        },
        "claim_reporting_period_days": 30,
        "repair_conditions": ["On-site inspection by authorized technician"],
        "authorized_service_centre_required": True,
        "replacement_conditions": {
            "eligible_after_repairs": 2,
            "unrepairable_covered_fault": True,
        },
        "grace_period_days": 10,
        "mandatory_documents": ["Purchase Receipt", "Product ID Tag Photo"],
        "hard_fail_rules": ["Warranty expired", "Cracked screen", "Electrical surge"],
        "warning_rules": ["Claim reported near expiry date"],
        "manual_review_rules": ["Surge evidence inconclusive", "Serial mismatch"],
        "brands": ["VisionMax", "ViewOptics", "CineDisplay"],
        "models": ["TV-43U", "TV-55OLED", "TV-65Q"],
        "retailers": ["Home Screen", "Vision Retail", "Electro Store"],
    },
}


# Exact per-class scenario counts. Every count is deterministic and auditable.
SCENARIO_COUNTS: dict[str, dict[str, int]] = {
    "Valid Claim": {
        "standard_covered": 200,
        "near_expiry_boundary": 100,
        "previous_authorized_repair": 80,
        "extended_warranty": 60,
        "complex_covered": 60,
    },
    "Invalid Claim": {
        "expired_warranty": 120,
        "excluded_damage": 110,
        "unauthorized_repair": 100,
        "invalid_receipt": 90,
        "late_reporting": 50,
        "replacement_not_eligible": 30,
    },
    "Manual Review": {
        "missing_mandatory_document": 110,
        "serial_mismatch": 90,
        "duplicate_claim": 100,
        "contradictory_information": 90,
        "borderline_reporting": 60,
        "service_center_unclear": 50,
    },
}


# model_input=False means the column is retained for traceability/audit but
# must not be given to the Python classifier.
FIELD_DEFINITIONS: dict[str, tuple[str, str, bool]] = {
    "claim_id": ("string", "Unique random claim identifier.", False),
    "claimant_id": ("string", "Synthetic claimant identifier.", False),
    "product_id": ("string", "Random product identifier; duplicate claims share it.", False),
    "invoice_number": ("string", "Synthetic invoice number for duplicate checks.", False),
    "duplicate_group_id": ("string", "Links real duplicate records; blank otherwise.", False),
    "scenario": ("string", "Audit-only scenario definition name.", False),
    "split": ("string", "train, validation or test.", False),
    "claim_class": ("string", "Ground truth target.", False),
    "product_category": ("category", "Smartphone, Laptop or Television.", True),
    "brand": ("category", "Product brand.", True),
    "model": ("category", "Product model number.", True),
    "retailer": ("category", "Purchase retailer.", True),
    "purchase_date": ("date", "Product purchase date.", True),
    "purchase_price": ("number", "Synthetic purchase amount.", True),
    "purchase_information_consistent": ("boolean", "Whether purchase information is consistent.", True),
    "serial_number": ("string", "Serial stored on the product record.", False),
    "receipt_serial_number": ("string", "Serial extracted from receipt.", False),
    "warranty_card_serial_number": ("string", "Serial extracted from warranty card.", False),
    "product_image_serial_number": ("string", "Serial extracted from product evidence.", False),
    "repair_record_serial_number": ("string", "Serial extracted from repair records.", False),
    "serial_number_status": ("category", "Derived serial comparison result.", False),
    "receipt_model": ("category", "Model found on receipt.", False),
    "warranty_card_model": ("category", "Model found on warranty card.", False),
    "product_image_model": ("category", "Model found in product evidence.", False),
    "repair_record_model": ("category", "Model found in repair records.", False),
    "warranty_provider": ("string", "Warranty provider.", True),
    "warranty_start_date": ("date", "Warranty start date.", True),
    "warranty_expiry_date": ("date", "Warranty expiry date.", True),
    "warranty_duration_months": ("number", "Configured duration in calendar months.", True),
    "warranty_remaining_days": ("number", "Expiry minus claim date; negative when expired.", True),
    "warranty_status": ("category", "Derived warranty status at claim date.", False),
    "warranty_status_at_fault": ("category", "Derived warranty status at fault date.", False),
    "extended_warranty": ("boolean", "Whether extended warranty is recorded.", True),
    "fault_date": ("date", "Reported fault date.", True),
    "claim_date": ("date", "Claim submission date.", True),
    "last_repair_date": ("date", "Most recent repair date, if any.", True),
    "previous_replacement_date": ("date", "Most recent replacement date, if any.", True),
    "product_age_days": ("number", "Claim date minus purchase date.", True),
    "reporting_days": ("number", "Claim date minus fault date.", True),
    "fault_category": ("category", "Reported fault type.", True),
    "fault_description": ("text", "Fault description.", True),
    "damage_type": ("category", "Type of damage reported.", True),
    "physical_damage": ("boolean", "Physical damage flag.", True),
    "liquid_damage": ("boolean", "Liquid damage flag.", True),
    "unauthorized_repair": ("boolean", "Unauthorized repair flag.", True),
    "authorized_service_center": ("boolean", "Whether service center was authorized.", True),
    "repair_history": ("text", "Previous repair history.", True),
    "previous_repair_count": ("number", "Number of previous repairs.", True),
    "previous_replacement": ("boolean", "Previous replacement flag.", True),
    "previous_replacement_count": ("number", "Number of previous replacements.", True),
    "replacement_requested": ("boolean", "Whether replacement is requested.", True),
    "receipt_available": ("boolean", "Whether purchase receipt is available.", True),
    "receipt_valid": ("boolean", "Whether purchase receipt is valid.", True),
    "warranty_card_available": ("boolean", "Whether warranty card is available.", True),
    "product_image_available": ("boolean", "Whether product image is available.", True),
    "serial_evidence_available": ("boolean", "Whether serial evidence is available.", True),
    "fault_evidence_available": ("boolean", "Whether fault evidence is available.", True),
    "repair_report_available": ("boolean", "Whether repair report is available.", True),
    "missing_documents": ("text", "Pipe-separated missing mandatory documents.", True),
    "missing_documents_count": ("number", "Number of missing mandatory documents.", True),
    "supporting_evidence_available": ("boolean", "Whether supporting evidence is usable.", True),
    "evidence_consistency": ("boolean", "Whether evidence agrees with entered data.", False),
    "claim_reporting_within_period": ("boolean", "Derived reporting-period result.", False),
    "duplicate_claim": ("boolean", "Whether record belongs to a real duplicate group.", False),
    "contradiction_detected": ("boolean", "Deterministic contradiction result.", False),
    "contradiction_details": ("text", "Contradiction descriptions.", False),
    "replacement_eligible": ("boolean", "Derived replacement result; audit only.", False),
    "hard_fail_detected": ("boolean", "Derived hard-fail result; audit only.", False),
    "warning_detected": ("boolean", "Derived warning result; audit only.", False),
    "manual_review_trigger": ("boolean", "Derived manual-review result; audit only.", False),
}


DOCUMENT_FLAGS = {
    "Purchase Receipt": "receipt_available",
    "Warranty Card": "warranty_card_available",
    "Product ID Tag Photo": "product_image_available",
    "Product Image": "product_image_available",
    "Serial Number Photo": "serial_evidence_available",
    "Fault Evidence": "fault_evidence_available",
    "Technical Diagnostic Report": "repair_report_available",
    "Repair Report": "repair_report_available",
}


# ---------------------------------------------------------------------------
# Date and record helpers
# ---------------------------------------------------------------------------


def add_months(value: date, months: int) -> date:
    """Add calendar months and clamp the day to the target month."""
    month_index = value.month - 1 + months
    year = value.year + month_index // 12
    month = month_index % 12 + 1
    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def iso(value: date | None) -> str:
    return value.isoformat() if value else ""


def new_serial(category: str, rng: random.Random, used: set[str]) -> str:
    prefix = {"Smartphone": "S", "Laptop": "L", "Television": "T"}[category]
    while True:
        value = f"SN-{prefix}-{rng.randint(100000, 999999)}"
        if value not in used:
            used.add(value)
            return value


def new_invoice(rng: random.Random) -> str:
    return f"INV-{rng.randint(10_000_000, 99_999_999)}"


def set_document(record: dict[str, Any], document_name: str, available: bool) -> None:
    field = DOCUMENT_FLAGS.get(document_name)
    if field:
        record[field] = available
    if document_name == "Purchase Receipt" and not available:
        # Absence of a receipt is a manual-review condition. A present but
        # invalid receipt is handled as a hard failure by the policy evaluator.
        record["receipt_valid"] = True


def random_covered_fault(
    policy: dict[str, Any], purchase: date, expiry: date, rng: random.Random
) -> tuple[str, str, date]:
    fault_name, description = rng.choice(list(policy["covered_faults"].items()))
    max_offset = max(30, min(300, (expiry - purchase).days - 10))
    return (
        fault_name,
        description,
        purchase + timedelta(days=rng.randint(20, max_offset)),
    )


def claim_date_for_fault(
    fault_date: date, expiry: date, reporting_period: int, rng: random.Random
) -> date:
    # Ordinary covered claims are submitted before the expiry date. The
    # explicit borderline scenario is the only one allowed to land exactly on
    # the expiry boundary, where deterministic policy evaluation routes it to
    # manual review.
    boundary = expiry - timedelta(days=1)
    latest = min(fault_date + timedelta(days=reporting_period), boundary)
    if latest <= fault_date:
        latest = min(boundary, fault_date + timedelta(days=1))
    days = max(1, (latest - fault_date).days)
    return fault_date + timedelta(days=rng.randint(1, days))


def make_base_record(
    claim_class: str,
    scenario: str,
    category: str,
    rng: random.Random,
    used_serials: set[str],
    group_id: str,
    duplicate_group_id: str = "",
) -> dict[str, Any]:
    policy = POLICIES[category]
    brand = rng.choice(policy["brands"])
    model = rng.choice(policy["models"])
    retailer = rng.choice(policy["retailers"])
    serial = new_serial(category, rng, used_serials)
    purchase = date(2023, 1, 1) + timedelta(days=rng.randint(0, 700))
    duration = policy["coverage_duration_months"] + (12 if scenario == "extended_warranty" else 0)
    expiry = add_months(purchase, duration)
    reporting_period = policy["claim_reporting_period_days"]
    threshold = policy["replacement_conditions"]["eligible_after_repairs"]
    fault_name, description, fault_date = random_covered_fault(policy, purchase, expiry, rng)

    record: dict[str, Any] = {
        "claim_id": "",
        "claimant_id": f"CUST-{rng.randint(1000, 9999)}",
        "product_id": "",
        "invoice_number": new_invoice(rng),
        "duplicate_group_id": duplicate_group_id,
        "scenario": scenario,
        "split": "",
        "claim_class": claim_class,
        "product_category": category,
        "brand": brand,
        "model": model,
        "retailer": retailer,
        "purchase_date": purchase,
        "purchase_price": round(rng.uniform(150, 3500), 2),
        "purchase_information_consistent": True,
        "serial_number": serial,
        "receipt_serial_number": serial,
        "warranty_card_serial_number": serial,
        "product_image_serial_number": serial,
        "repair_record_serial_number": serial,
        "serial_number_status": "Matched",
        "receipt_model": model,
        "warranty_card_model": model,
        "product_image_model": model,
        "repair_record_model": model,
        "warranty_provider": f"{brand} Warranty Services",
        "warranty_start_date": purchase,
        "warranty_expiry_date": expiry,
        "warranty_duration_months": duration,
        "warranty_remaining_days": 0,
        "warranty_status": "",
        "warranty_status_at_fault": "",
        "extended_warranty": scenario == "extended_warranty",
        "fault_date": fault_date,
        "claim_date": claim_date_for_fault(fault_date, expiry, reporting_period, rng),
        "last_repair_date": None,
        "previous_replacement_date": None,
        "product_age_days": 0,
        "reporting_days": 0,
        "fault_category": fault_name,
        "fault_description": description,
        "damage_type": "None",
        "physical_damage": False,
        "liquid_damage": False,
        "unauthorized_repair": False,
        "authorized_service_center": True,
        "repair_history": "No previous repairs",
        "previous_repair_count": 0,
        "previous_replacement": False,
        "previous_replacement_count": 0,
        "replacement_requested": False,
        "receipt_available": True,
        "receipt_valid": True,
        "warranty_card_available": True,
        "product_image_available": True,
        "serial_evidence_available": True,
        "fault_evidence_available": True,
        "repair_report_available": True,
        "missing_documents": "",
        "missing_documents_count": 0,
        "supporting_evidence_available": True,
        "evidence_consistency": True,
        "claim_reporting_within_period": True,
        "duplicate_claim": scenario == "duplicate_claim",
        "contradiction_detected": False,
        "contradiction_details": "",
        "replacement_eligible": False,
        "hard_fail_detected": False,
        "warning_detected": False,
        "manual_review_trigger": False,
        "_group_id": group_id,
    }

    if scenario in {
        "standard_covered",
        "near_expiry_boundary",
        "previous_authorized_repair",
        "extended_warranty",
        "complex_covered",
    }:
        if scenario == "near_expiry_boundary":
            record["fault_date"] = expiry - timedelta(days=rng.randint(3, 25))
            record["claim_date"] = claim_date_for_fault(
                record["fault_date"], expiry, reporting_period, rng
            )
        elif scenario == "previous_authorized_repair":
            record["previous_repair_count"] = rng.randint(1, max(1, threshold - 1))
            repair_date = record["fault_date"] - timedelta(days=rng.randint(5, 25))
            record["last_repair_date"] = max(purchase + timedelta(days=1), repair_date)
            record["repair_history"] = "One or more authorized repairs"
        elif scenario == "complex_covered":
            record["previous_repair_count"] = rng.randint(0, threshold)
            if record["previous_repair_count"]:
                repair_date = record["fault_date"] - timedelta(days=rng.randint(10, 30))
                record["last_repair_date"] = max(purchase + timedelta(days=1), repair_date)
            record["repair_history"] = "Complex repair history with supporting diagnostics"
            record["fault_description"] = f"{description} Additional diagnostic evidence supplied."

    elif scenario == "expired_warranty":
        record["fault_date"] = expiry + timedelta(days=rng.randint(5, 150))
        record["claim_date"] = record["fault_date"] + timedelta(
            days=rng.randint(1, reporting_period)
        )

    elif scenario == "excluded_damage":
        exclusion, exclusion_description = rng.choice(list(policy["exclusions"].items()))
        record["fault_category"] = exclusion
        record["fault_description"] = exclusion_description
        record["fault_date"] = purchase + timedelta(days=rng.randint(20, 150))
        record["claim_date"] = claim_date_for_fault(
            record["fault_date"], expiry, reporting_period, rng
        )
        if "Physical" in exclusion or "Cracked" in exclusion:
            record["physical_damage"] = True
            record["damage_type"] = "Physical Impact"
        elif "Liquid" in exclusion:
            record["liquid_damage"] = True
            record["damage_type"] = "Liquid Contact"
        elif "Surge" in exclusion:
            record["damage_type"] = "Electrical Surge"
        elif "Unauthorized" in exclusion:
            record["unauthorized_repair"] = True
            record["damage_type"] = "Unauthorized Modification"

    elif scenario == "unauthorized_repair":
        record["fault_date"] = purchase + timedelta(days=rng.randint(20, 180))
        record["claim_date"] = claim_date_for_fault(
            record["fault_date"], expiry, reporting_period, rng
        )
        record["unauthorized_repair"] = True
        record["authorized_service_center"] = False
        record["damage_type"] = "Unauthorized Modification"
        record["repair_history"] = "Unauthorized repair reported"

    elif scenario == "invalid_receipt":
        record["fault_date"] = purchase + timedelta(days=rng.randint(20, 150))
        record["claim_date"] = claim_date_for_fault(
            record["fault_date"], expiry, reporting_period, rng
        )
        record["receipt_valid"] = False
        record["purchase_information_consistent"] = False
        record["evidence_consistency"] = False

    elif scenario == "late_reporting":
        record["fault_date"] = purchase + timedelta(days=20)
        record["claim_date"] = record["fault_date"] + timedelta(
            days=reporting_period + rng.randint(3, 20)
        )

    elif scenario == "replacement_not_eligible":
        record["fault_date"] = purchase + timedelta(days=rng.randint(30, 150))
        record["claim_date"] = claim_date_for_fault(
            record["fault_date"], expiry, reporting_period, rng
        )
        record["replacement_requested"] = True
        record["previous_repair_count"] = max(0, threshold - 1)
        record["last_repair_date"] = max(
            purchase + timedelta(days=1), record["fault_date"] - timedelta(days=10)
        )
        record["repair_history"] = "Replacement requested before policy repair threshold"

    elif scenario == "missing_mandatory_document":
        mandatory = policy["mandatory_documents"]
        missing_name = rng.choice(mandatory)
        set_document(record, missing_name, False)
        if rng.random() < 0.25:
            second = rng.choice([item for item in mandatory if item != missing_name])
            set_document(record, second, False)
        record["evidence_consistency"] = False

    elif scenario == "serial_mismatch":
        record["receipt_serial_number"] = new_serial(category, rng, used_serials)
        record["evidence_consistency"] = False

    elif scenario == "duplicate_claim":
        # The caller clones this record to create a real duplicate pair.
        pass

    elif scenario == "contradictory_information":
        if rng.random() < 0.5:
            record["fault_date"] = purchase - timedelta(days=rng.randint(5, 40))
            record["claim_date"] = purchase + timedelta(days=rng.randint(1, 20))
            record["fault_description"] = "Reported fault date predates the purchase date."
        else:
            record["fault_date"] = purchase + timedelta(days=rng.randint(40, 150))
            record["claim_date"] = claim_date_for_fault(
                record["fault_date"], expiry, reporting_period, rng
            )
            record["previous_repair_count"] = 1
            record["last_repair_date"] = purchase - timedelta(days=rng.randint(5, 30))
            record["repair_history"] = "Conflicting repair record predates purchase"
        record["evidence_consistency"] = False

    elif scenario == "borderline_reporting":
        record["fault_date"] = expiry - timedelta(days=rng.randint(2, 12))
        record["claim_date"] = expiry
        record["repair_history"] = "Claim submitted on warranty expiry boundary"

    elif scenario == "service_center_unclear":
        record["fault_date"] = purchase + timedelta(days=rng.randint(30, 150))
        record["claim_date"] = claim_date_for_fault(
            record["fault_date"], expiry, reporting_period, rng
        )
        record["previous_repair_count"] = 1
        record["last_repair_date"] = max(
            purchase + timedelta(days=1), record["fault_date"] - timedelta(days=20)
        )
        record["authorized_service_center"] = False
        record["repair_history"] = "Service-center authorization is unclear"

    return record


# ---------------------------------------------------------------------------
# Deterministic checks and policy indicators
# ---------------------------------------------------------------------------


def detect_contradictions(record: dict[str, Any]) -> list[str]:
    issues: list[str] = []
    purchase = record["purchase_date"]
    fault = record["fault_date"]
    claim = record["claim_date"]
    if fault < purchase:
        issues.append("Fault date before purchase date")
    if claim < purchase:
        issues.append("Claim date before purchase date")
    if claim < fault:
        issues.append("Claim date before fault date")
    if record["last_repair_date"] and record["last_repair_date"] < purchase:
        issues.append("Repair date before purchase date")
    if record["last_repair_date"] and record["last_repair_date"] > fault:
        issues.append("Repair date after fault date")
    serials = {
        record["serial_number"],
        record["receipt_serial_number"],
        record["warranty_card_serial_number"],
        record["product_image_serial_number"],
        record["repair_record_serial_number"],
    }
    if len(serials) > 1:
        issues.append("Conflicting serial numbers")
    models = {
        record["model"],
        record["receipt_model"],
        record["warranty_card_model"],
        record["product_image_model"],
        record["repair_record_model"],
    }
    if len(models) > 1:
        issues.append("Inconsistent product model")
    return issues


def apply_policy_indicators(record: dict[str, Any], policy: dict[str, Any]) -> None:
    claim_date = record["claim_date"]
    fault_date = record["fault_date"]
    expiry = record["warranty_expiry_date"]
    reporting_period = policy["claim_reporting_period_days"]
    reporting_days = (claim_date - fault_date).days

    record["product_age_days"] = (claim_date - record["purchase_date"]).days
    record["reporting_days"] = reporting_days
    record["warranty_remaining_days"] = (expiry - claim_date).days
    record["warranty_status"] = "Active" if claim_date <= expiry else "Expired"
    record["warranty_status_at_fault"] = "Active" if fault_date <= expiry else "Expired"
    record["claim_reporting_within_period"] = 0 <= reporting_days <= reporting_period

    serials = {
        record["serial_number"],
        record["receipt_serial_number"],
        record["warranty_card_serial_number"],
        record["product_image_serial_number"],
        record["repair_record_serial_number"],
    }
    record["serial_number_status"] = "Matched" if len(serials) == 1 else "Mismatch"

    missing = [
        document
        for document in policy["mandatory_documents"]
        if DOCUMENT_FLAGS.get(document) and not record[DOCUMENT_FLAGS[document]]
    ]
    record["missing_documents"] = "|".join(missing)
    record["missing_documents_count"] = len(missing)
    record["supporting_evidence_available"] = not missing and record["evidence_consistency"]

    contradictions = detect_contradictions(record)
    record["contradiction_detected"] = bool(contradictions)
    record["contradiction_details"] = "|".join(contradictions)

    hard_fail: list[str] = []
    if record["warranty_status"] == "Expired":
        hard_fail.append("Warranty expired")
    if record["fault_category"] in policy["exclusions"]:
        hard_fail.append("Fault is excluded by policy")
    if record["physical_damage"] or record["liquid_damage"] or record["unauthorized_repair"]:
        hard_fail.append("Excluded damage or unauthorized repair")
    if record["receipt_available"] and not record["receipt_valid"]:
        hard_fail.append("Invalid purchase receipt")
    if not record["claim_reporting_within_period"] and not contradictions:
        hard_fail.append("Claim reported after policy deadline")

    threshold = policy["replacement_conditions"]["eligible_after_repairs"]
    base_eligible = (
        record["replacement_requested"]
        and record["warranty_status"] == "Active"
        and record["previous_repair_count"] >= threshold
        and not hard_fail
    )
    record["replacement_eligible"] = base_eligible
    if record["replacement_requested"] and not base_eligible:
        hard_fail.append("Replacement is not eligible under policy")

    manual: list[str] = []
    if missing:
        manual.append("Missing mandatory document")
    if record["serial_number_status"] == "Mismatch":
        manual.append("Serial-number mismatch")
    if record["duplicate_claim"]:
        manual.append("Duplicate claim group")
    if contradictions:
        manual.append("Contradictory information")
    if not record["authorized_service_center"]:
        manual.append("Service-center authorization unclear")
    if record["scenario"] == "borderline_reporting":
        manual.append("Borderline warranty/reporting date")
    if record["warranty_remaining_days"] == 0 and record["claim_date"] == expiry:
        manual.append("Claim submitted on warranty expiry boundary")

    warning: list[str] = []
    if 0 <= record["warranty_remaining_days"] <= policy["grace_period_days"]:
        warning.append("Claim is near warranty expiry")
    if reporting_days == reporting_period:
        warning.append("Claim is at the reporting deadline")

    record["hard_fail_detected"] = bool(hard_fail)
    record["manual_review_trigger"] = bool(manual)
    record["warning_detected"] = bool(warning)
    record["_hard_fail_reasons"] = "|".join(hard_fail)
    record["_manual_review_reasons"] = "|".join(manual)
    record["_warning_reasons"] = "|".join(warning)


# ---------------------------------------------------------------------------
# Splitting, IDs and record generation
# ---------------------------------------------------------------------------


def assign_splits(records: list[dict[str, Any]], rng: random.Random) -> None:
    """Assign exact per-class splits without separating duplicate groups."""
    by_class: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        by_class[record["claim_class"]].append(record)

    for claim_class in CLASS_NAMES:
        groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for record in by_class[claim_class]:
            groups[record["_group_id"]].append(record)
        group_list = list(groups.values())
        rng.shuffle(group_list)
        group_list.sort(key=len, reverse=True)
        remaining = SPLIT_TARGETS.copy()
        assigned = {name: 0 for name in SPLIT_NAMES}

        for group in group_list:
            size = len(group)
            possible = [name for name in SPLIT_NAMES if remaining[name] >= size]
            if not possible:
                raise ValueError(f"Cannot place group of size {size} in {claim_class}")
            # Relative fill keeps pairs distributed across all three splits.
            split = min(
                possible,
                key=lambda name: (assigned[name] / SPLIT_TARGETS[name], rng.random()),
            )
            for record in group:
                record["split"] = split
            remaining[split] -= size
            assigned[split] += size

        if any(remaining.values()):
            raise ValueError(f"Split allocation failed for {claim_class}: {remaining}")


def assign_random_ids(records: list[dict[str, Any]], rng: random.Random) -> None:
    """Assign IDs after shuffling so numeric ranges do not encode classes."""
    group_ids = list(dict.fromkeys(record["_group_id"] for record in records))
    rng.shuffle(group_ids)
    product_numbers = rng.sample(range(100000, 999999), len(group_ids))
    product_map = {
        group_id: f"PRD-{number:06d}"
        for group_id, number in zip(group_ids, product_numbers)
    }

    rng.shuffle(records)
    claim_numbers = rng.sample(range(100000, 999999), len(records))
    for record, number in zip(records, claim_numbers):
        record["claim_id"] = f"CLM-{number:06d}"
        record["product_id"] = product_map[record["_group_id"]]


def generate_records(rng: random.Random) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    used_serials: set[str] = set()
    group_number = 1
    categories = list(POLICIES)

    for class_index, claim_class in enumerate(CLASS_NAMES):
        for scenario, count in SCENARIO_COUNTS[claim_class].items():
            if scenario == "duplicate_claim":
                for _ in range(count // 2):
                    category = categories[(group_number - 1 + class_index) % len(categories)]
                    group_id = f"group-{group_number:05d}"
                    duplicate_id = f"DUP-{rng.randint(100000, 999999)}"
                    first = make_base_record(
                        claim_class, scenario, category, rng, used_serials, group_id, duplicate_id
                    )
                    second = dict(first)
                    records.extend([first, second])
                    group_number += 1
            else:
                for _ in range(count):
                    category = categories[(group_number - 1 + class_index) % len(categories)]
                    group_id = f"group-{group_number:05d}"
                    records.append(
                        make_base_record(claim_class, scenario, category, rng, used_serials, group_id)
                    )
                    group_number += 1

    for record in records:
        apply_policy_indicators(record, POLICIES[record["product_category"]])
    assign_splits(records, rng)
    assign_random_ids(records, rng)
    return records


# ---------------------------------------------------------------------------
# Output writers
# ---------------------------------------------------------------------------


def serialise(value: Any) -> Any:
    if isinstance(value, date):
        return value.isoformat()
    if value is None:
        return ""
    return value


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: serialise(value)
        for key, value in record.items()
        if not key.startswith("_")
    }


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def write_policies(root: Path) -> None:
    policy_dir = root / "policies"
    policy_dir.mkdir(parents=True, exist_ok=True)
    for category, policy in POLICIES.items():
        write_json(policy_dir / f"{category.lower()}_warranty_policy.json", policy)


def write_csvs(root: Path, records: list[dict[str, Any]]) -> None:
    csv_dir = root / "csv"
    csv_dir.mkdir(parents=True, exist_ok=True)
    fields = list(FIELD_DEFINITIONS)
    for split in SPLIT_NAMES:
        rows = [public_record(record) for record in records if record["split"] == split]
        rows.sort(key=lambda row: row["claim_id"])
        with (csv_dir / f"{split}.csv").open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
            writer.writeheader()
            writer.writerows(rows)


def build_document_manifest(root: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    document_types = [
        ("Purchase Receipt", "receipt_available"),
        ("Warranty Card", "warranty_card_available"),
        ("Product Image", "product_image_available"),
        ("Serial Number Evidence", "serial_evidence_available"),
        ("Fault Evidence", "fault_evidence_available"),
        ("Repair Report", "repair_report_available"),
    ]
    for record in records:
        for document_name, field in document_types:
            available = bool(record[field])
            digest = ""
            filename = ""
            if available:
                seed = (record["duplicate_group_id"] or record["_group_id"]) + document_name
                digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()
                extension = "pdf" if document_name == "Purchase Receipt" else "png"
                filename = (
                    f"{document_name.lower().replace(' ', '_')}_{record['claim_id']}.{extension}"
                )
            rows.append(
                {
                    "document_id": f"DOC-{record['claim_id']}-{document_name.replace(' ', '_')}",
                    "claim_id": record["claim_id"],
                    "split": record["split"],
                    "document_type": document_name,
                    "available": available,
                    "filename": filename,
                    "sha256": digest,
                    "source": "synthetic-manifest",
                }
            )

    hash_counts = Counter(row["sha256"] for row in rows if row["sha256"])
    for row in rows:
        row["is_duplicate_hash"] = bool(row["sha256"] and hash_counts[row["sha256"]] > 1)

    with (root / "documents.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def write_data_dictionary(root: Path) -> None:
    lines = [
        "# AssureX Dataset Data Dictionary",
        "",
        "Generated according to SRS section 1.2.",
        "",
        "| Column | Type | Description | Python model input |",
        "|---|---|---|---|",
    ]
    for name, (kind, description, allowed) in FIELD_DEFINITIONS.items():
        lines.append(f"| `{name}` | {kind} | {description} | {'Yes' if allowed else 'No'} |")
    lines += [
        "",
        "`claim_class`, policy/rule outputs, identifiers and duplicate audit fields",
        "are retained for traceability but are not classifier inputs.",
    ]
    (root / "data_dictionary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_feature_manifest(root: Path) -> None:
    features = [name for name, (_, _, allowed) in FIELD_DEFINITIONS.items() if allowed]
    write_json(
        root / "feature_manifest.json",
        {
            "target": "claim_class",
            "features": features,
            "excluded_audit_or_target_columns": [
                name for name, (_, _, allowed) in FIELD_DEFINITIONS.items() if not allowed
            ],
        },
    )


def write_statistics(
    root: Path, records: list[dict[str, Any]], mapping: list[dict[str, Any]], documents: list[dict[str, Any]]
) -> None:
    stats = {
        "total_claims": len(records),
        "class_counts": dict(Counter(record["claim_class"] for record in records)),
        "split_counts": dict(Counter(record["split"] for record in records)),
        "category_counts": dict(Counter(record["product_category"] for record in records)),
        "scenario_counts": dict(Counter(record["scenario"] for record in records)),
        "card_counts": dict(Counter(row["split"] for row in mapping)),
        "document_rows": len(documents),
        "duplicate_document_hashes": len(
            {row["sha256"] for row in documents if row["is_duplicate_hash"]}
        ),
        "missing_document_claims": sum(1 for record in records if record["missing_documents_count"]),
        "contradiction_claims": sum(1 for record in records if record["contradiction_detected"]),
        "expired_claims": sum(1 for record in records if record["warranty_status"] == "Expired"),
    }
    write_json(root / "statistics.json", stats)


# ---------------------------------------------------------------------------
# Claim Summary Cards
# ---------------------------------------------------------------------------


@lru_cache(maxsize=32)
def load_font(size: int, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        Path(r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf"),
        Path(r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf"),
        Path("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size)
    return ImageFont.load_default()


def yes_no(value: Any) -> str:
    return "Yes" if bool(value) else "No"


def display_date(value: date | str | None, variant: int) -> str:
    if not value:
        return "Not recorded"
    parsed = value if isinstance(value, date) else date.fromisoformat(value)
    return parsed.strftime("%d/%m/%Y") if variant == 2 else parsed.isoformat()


def card_entries(record: dict[str, Any], variant: int) -> list[tuple[str, str]]:
    missing = record["missing_documents"] or "None"
    return [
            ("PRODUCT", f"{record['brand']} {record['model']} | {record['product_category']}"),
        ("PRODUCT AGE", f"{record['product_age_days']} days"),
        ("WARRANTY", f"{record['warranty_status']} | {record['warranty_remaining_days']} days remaining"),
        ("RECEIPT", f"Available: {yes_no(record['receipt_available'])} | Valid: {yes_no(record['receipt_valid'])}"),
        (
            "DATES",
            f"Purchased {display_date(record['purchase_date'], variant)} | "
            f"Fault {display_date(record['fault_date'], variant)} | "
            f"Claim {display_date(record['claim_date'], variant)}",
        ),
        ("FAULT", str(record["fault_category"])),
        ("SERIAL STATUS", str(record["serial_number_status"])),
        ("REPAIR HISTORY", f"{record['repair_history']} | Previous repairs: {record['previous_repair_count']}"),
        ("DOCUMENTS", f"Missing: {missing}"),
        (
            "EVIDENCE",
            f"Supporting evidence: {yes_no(record['supporting_evidence_available'])} | "
            f"Authorized centre: {yes_no(record['authorized_service_center'])}",
        ),
        (
            "DAMAGE FLAGS",
            f"Physical: {yes_no(record['physical_damage'])} | "
            f"Liquid: {yes_no(record['liquid_damage'])} | "
            f"Unauthorized repair: {yes_no(record['unauthorized_repair'])}",
        ),
    ]


def wrap_lines(draw: ImageDraw.ImageDraw, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    words = str(text).split()
    if not words:
        return [""]
    lines: list[str] = []
    current = words[0]
    for word in words[1:]:
        trial = f"{current} {word}"
        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            current = trial
        else:
            lines.append(current)
            current = word
    lines.append(current)
    return lines


def draw_field(
    draw: ImageDraw.ImageDraw,
    x: int,
    y: int,
    label: str,
    value: str,
    width: int,
    label_font: ImageFont.ImageFont,
    value_font: ImageFont.ImageFont,
    accent: tuple[int, int, int],
    text_color: tuple[int, int, int],
) -> int:
    draw.text((x, y), label, font=label_font, fill=accent)
    lines = wrap_lines(draw, value, value_font, width)
    draw.multiline_text((x, y + 20), "\n".join(lines), font=value_font, fill=text_color, spacing=3)
    return 24 + len(lines) * 19


def generate_claim_card(record: dict[str, Any], output_path: Path, variant: int = 1) -> None:
    """Render facts only. Never render class, prediction, confidence or decision."""
    width, height = 900, 700
    if variant == 1:
        background, header, accent, text_color = (248, 250, 252), (22, 55, 92), (22, 55, 92), (28, 32, 38)
    else:
        background, header, accent, text_color = (240, 244, 248), (46, 92, 122), (46, 92, 122), (30, 30, 30)

    image = Image.new("RGB", (width, height), background)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width, 78), fill=header)
    draw.text((28, 18), "ASSUREX CLAIM SUMMARY CARD", font=load_font(26, True), fill=(255, 255, 255))
    draw.text(
        (30, 50),
        f"Claim ID: {record['claim_id']} | {record['product_category']}",
        font=load_font(16),
        fill=(225, 235, 245),
    )

    entries = card_entries(record, variant)
    if variant == 1:
        y = 100
        for label, value in entries:
            y += draw_field(draw, 30, y, label, value, width - 60, load_font(14, True), load_font(16), accent, text_color)
    else:
        left_x, right_x, column_width = 30, 465, 390
        y_left = y_right = 105
        for index, (label, value) in enumerate(entries):
            if index < 5:
                y_left += draw_field(draw, left_x, y_left, label, value, column_width, load_font(14, True), load_font(16), accent, text_color)
            else:
                y_right += draw_field(draw, right_x, y_right, label, value, column_width, load_font(14, True), load_font(16), accent, text_color)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    image.save(output_path)


def generate_cards(root: Path, records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    mapping: list[dict[str, Any]] = []
    for record in records:
        split = record["split"]
        class_folder = CLASS_FOLDERS[record["claim_class"]]
        variations = 2 if split == "train" else 1
        for variant in range(1, variations + 1):
            filename = f"{record['claim_id']}_v{variant}.png" if split == "train" else f"{record['claim_id']}.png"
            path = root / "cards" / split / class_folder / filename
            generate_claim_card(record, path, variant)
            mapping.append(
                {
                    "claim_id": record["claim_id"],
                    "split": split,
                    "claim_class": record["claim_class"],
                    "image_filename": filename,
                    "image_path": path.relative_to(root).as_posix(),
                    "variant": variant,
                }
            )
    mapping.sort(key=lambda row: (row["split"], row["claim_id"], row["variant"]))
    with (root / "claim_image_mapping.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(mapping[0]))
        writer.writeheader()
        writer.writerows(mapping)
    return mapping


# ---------------------------------------------------------------------------
# Verification
# ---------------------------------------------------------------------------


def validate_dataset(
    root: Path,
    records: list[dict[str, Any]],
    mapping: list[dict[str, Any]],
    documents: list[dict[str, Any]],
) -> dict[str, Any]:
    errors: list[str] = []
    checks: list[dict[str, Any]] = []

    def check(name: str, condition: bool, detail: str) -> None:
        checks.append({"name": name, "status": "PASS" if condition else "FAIL", "detail": detail})
        if not condition:
            errors.append(f"{name}: {detail}")

    class_counts = Counter(record["claim_class"] for record in records)
    check("total_claims", len(records) == TOTAL_CLAIMS, f"Found {len(records)}; expected {TOTAL_CLAIMS}")
    for claim_class in CLASS_NAMES:
        check(
            f"class_count_{claim_class.replace(' ', '_').lower()}",
            class_counts[claim_class] == 500,
            f"Found {class_counts[claim_class]}; expected 500",
        )
    for split, expected_records in {"train": 1050, "validation": 225, "test": 225}.items():
        actual = sum(1 for record in records if record["split"] == split)
        check(f"split_count_{split}", actual == expected_records, f"Found {actual}; expected {expected_records}")

    check("unique_claim_ids", len({record["claim_id"] for record in records}) == len(records), "Claim IDs are not unique")
    split_by_group: dict[str, set[str]] = defaultdict(set)
    for record in records:
        split_by_group[record["_group_id"]].add(record["split"])
    check(
        "no_group_crosses_splits",
        all(len(value) == 1 for value in split_by_group.values()),
        "A duplicate group crosses a split boundary",
    )

    card_counts = Counter(row["split"] for row in mapping)
    check("train_card_count", card_counts["train"] == 2100, f"Found {card_counts['train']}; expected 2100")
    check("validation_card_count", card_counts["validation"] == 225, f"Found {card_counts['validation']}; expected 225")
    check("test_card_count", card_counts["test"] == 225, f"Found {card_counts['test']}; expected 225")
    check(
        "all_card_files_exist",
        all((root / row["image_path"]).exists() for row in mapping),
        "One or more card files are missing",
    )

    # Semantic checks: these are the checks most likely to catch bad synthetic data.
    for record in records:
        policy = POLICIES[record["product_category"]]
        if record["claim_class"] == "Valid Claim" and (record["hard_fail_detected"] or record["manual_review_trigger"]):
            errors.append(f"Valid claim has audit failure: {record['claim_id']}")
        if record["claim_class"] == "Invalid Claim" and not record["hard_fail_detected"]:
            errors.append(f"Invalid claim has no hard failure: {record['claim_id']}")
        if record["claim_class"] == "Manual Review" and not record["manual_review_trigger"]:
            errors.append(f"Manual Review claim has no trigger: {record['claim_id']}")
        if record["fault_date"] < record["purchase_date"] and not record["contradiction_detected"]:
            errors.append(f"Unflagged fault-before-purchase: {record['claim_id']}")
        if record["last_repair_date"] and record["last_repair_date"] < record["purchase_date"] and not record["contradiction_detected"]:
            errors.append(f"Unflagged repair-before-purchase: {record['claim_id']}")
        expected_status = "Active" if record["claim_date"] <= record["warranty_expiry_date"] else "Expired"
        if record["warranty_status"] != expected_status:
            errors.append(f"Warranty status mismatch: {record['claim_id']}")
        if record["receipt_available"] and not record["receipt_valid"] and record["claim_class"] != "Invalid Claim":
            errors.append(f"Invalid receipt outside Invalid class: {record['claim_id']}")
        # All mandatory-document flags must agree with the stored missing list.
        expected_missing = [
            document
            for document in policy["mandatory_documents"]
            if DOCUMENT_FLAGS.get(document) and not record[DOCUMENT_FLAGS[document]]
        ]
        if record["missing_documents"] != "|".join(expected_missing):
            errors.append(f"Missing-document mismatch: {record['claim_id']}")
        if record["serial_number_status"] != ("Matched" if len({
            record["serial_number"], record["receipt_serial_number"],
            record["warranty_card_serial_number"], record["product_image_serial_number"],
            record["repair_record_serial_number"]
        }) == 1 else "Mismatch"):
            errors.append(f"Serial status mismatch: {record['claim_id']}")

    check(
        "real_duplicate_document_hash",
        any(row["is_duplicate_hash"] for row in documents),
        "No real duplicate document hash was generated",
    )

    stats = {
        "total_claims": len(records),
        "class_counts": dict(class_counts),
        "split_counts": dict(Counter(record["split"] for record in records)),
        "card_counts": dict(card_counts),
        "category_counts": dict(Counter(record["product_category"] for record in records)),
        "scenario_counts": dict(Counter(record["scenario"] for record in records)),
        "duplicate_groups": len({record["duplicate_group_id"] for record in records if record["duplicate_group_id"]}),
        "missing_document_claims": sum(1 for record in records if record["missing_documents_count"]),
        "contradiction_claims": sum(1 for record in records if record["contradiction_detected"]),
        "expired_claims": sum(1 for record in records if record["warranty_status"] == "Expired"),
    }
    report = {"status": "FAIL" if errors else "PASS", "errors": errors, "checks": checks, "statistics": stats}
    write_json(root / "validation_report.json", report)
    if errors:
        raise ValueError("Dataset validation failed. See validation_report.json.")
    return report


def clean_generated_output(root: Path) -> None:
    for directory in (root / "csv", root / "cards"):
        if directory.exists():
            shutil.rmtree(directory)
    for filename in (
        "documents.csv", "claim_image_mapping.csv", "statistics.json",
        "validation_report.json", "data_dictionary.md", "feature_manifest.json",
    ):
        path = root / filename
        if path.exists():
            path.unlink()


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate the final AssureX SRS dataset.")
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parent, help="Output dataset root")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED)
    parser.add_argument("--keep-existing", action="store_true", help="Do not clean generated outputs first")
    args = parser.parse_args()
    root = args.root.resolve()
    root.mkdir(parents=True, exist_ok=True)
    rng = random.Random(args.seed)

    if not args.keep_existing:
        clean_generated_output(root)
    write_policies(root)
    records = generate_records(rng)
    write_csvs(root, records)
    mapping = generate_cards(root, records)
    documents = build_document_manifest(root, records)
    write_data_dictionary(root)
    write_feature_manifest(root)
    write_statistics(root, records, mapping, documents)
    report = validate_dataset(root, records, mapping, documents)

    print("AssureX final dataset generated successfully.")
    print(f"Root: {root}")
    print(f"Claims: {len(records)}")
    print(f"Training cards: {card_count(mapping, 'train')}")
    print(f"Validation cards: {card_count(mapping, 'validation')}")
    print(f"Test cards: {card_count(mapping, 'test')}")
    print(f"Validation: {report['status']}")


def card_count(mapping: list[dict[str, Any]], split: str) -> int:
    return sum(1 for row in mapping if row["split"] == split)


if __name__ == "__main__":
    main()
