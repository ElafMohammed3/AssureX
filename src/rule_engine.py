"""
Deterministic warranty rule engine for the AssureX Claim Engine.

This module is the runtime counterpart to the dataset generator. The generator
creates labelled training data offline; this module evaluates live submissions
inside the Flask application. The two are deliberately independent
implementations of the same published warranty policies, so agreement between
them is evidence that the policies are correctly specified rather than merely
copied.

The engine never imports generator code and never reads the dataset's audit
columns (`hard_fail_detected`, `warning_detected`, `manual_review_trigger`,
`contradiction_detected`, `missing_documents`, `serial_number_status`,
`warranty_status`, `replacement_eligible`). Every one of those is recomputed
here from primary claim facts, which is what prevents the rule engine from
merely echoing the answer key.

SRS coverage:
    xxv  Warranty Rule Validation
    xxvi Configurable Warranty Policies
    xxvii Serial-Number Verification
    xxviii Contradiction Detection
    xxix Missing Document Detection
    xxx   Duplicate Claim Detection
    xxxi  Document Duplicate Detection
    xxxv  Decision Explanation inputs
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

# Maps a policy document name to the claim column that records its presence.
# This is part of the policy file contract, not generator logic.
DOCUMENT_FLAGS: dict[str, str] = {
    "Purchase Receipt": "receipt_available",
    "Warranty Card": "warranty_card_available",
    "Product ID Tag Photo": "product_image_available",
    "Product Image": "product_image_available",
    "Serial Number Photo": "serial_evidence_available",
    "Fault Evidence": "fault_evidence_available",
    "Technical Diagnostic Report": "repair_report_available",
    "Repair Report": "repair_report_available",
}

SERIAL_COLUMNS: tuple[str, ...] = (
    "serial_number",
    "receipt_serial_number",
    "warranty_card_serial_number",
    "product_image_serial_number",
    "repair_record_serial_number",
)

MODEL_COLUMNS: tuple[str, ...] = (
    "model",
    "receipt_model",
    "warranty_card_model",
    "product_image_model",
    "repair_record_model",
)

# Fields the rule engine is allowed to read. Everything else in a claim row is
# either an identifier or a generator-produced audit value.
PRIMARY_FIELDS: frozenset[str] = frozenset(
    {
        "claim_id",
        "claimant_id",
        "product_id",
        "invoice_number",
        "product_category",
        "brand",
        "model",
        "retailer",
        "purchase_date",
        "purchase_price",
        "purchase_information_consistent",
        "serial_number",
        "receipt_serial_number",
        "warranty_card_serial_number",
        "product_image_serial_number",
        "repair_record_serial_number",
        "receipt_model",
        "warranty_card_model",
        "product_image_model",
        "repair_record_model",
        "warranty_provider",
        "warranty_start_date",
        "warranty_expiry_date",
        "warranty_duration_months",
        "extended_warranty",
        "fault_date",
        "claim_date",
        "last_repair_date",
        "fault_category",
        "fault_description",
        "damage_type",
        "physical_damage",
        "liquid_damage",
        "unauthorized_repair",
        "authorized_service_center",
        "previous_repair_count",
        "previous_replacement",
        "previous_replacement_count",
        "replacement_requested",
        "receipt_available",
        "receipt_valid",
        "warranty_card_available",
        "product_image_available",
        "serial_evidence_available",
        "fault_evidence_available",
        "repair_report_available",
    }
)


# ---------------------------------------------------------------------------
# Result types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RuleOutcome:
    """One evaluated rule."""

    rule_id: str
    label: str
    status: str
    detail: str

    def as_dict(self) -> dict[str, str]:
        return {
            "rule_id": self.rule_id,
            "label": self.label,
            "status": self.status,
            "detail": self.detail,
        }


@dataclass
class DuplicateIndex:
    """
    Cross-claim lookup used by SRS xxx and xxxi.

    Built once from the claims table. A live application would build this from
    MySQL queries rather than holding every claim in memory.
    """

    invoice_numbers: dict[str, list[str]] = field(default_factory=dict)
    serial_numbers: dict[str, list[str]] = field(default_factory=dict)
    product_ids: dict[str, list[str]] = field(default_factory=dict)
    document_hashes: dict[str, list[str]] = field(default_factory=dict)
    groups: dict[str, list[str]] = field(default_factory=dict)

    @classmethod
    def build(cls, claims: Iterable[dict[str, Any]]) -> DuplicateIndex:
        index = cls()

        for claim in claims:
            claim_id = str(claim.get("claim_id", ""))
            index._add(index.invoice_numbers, claim.get("invoice_number"), claim_id)
            index._add(index.serial_numbers, claim.get("serial_number"), claim_id)
            index._add(index.product_ids, claim.get("product_id"), claim_id)
            index._add(index.groups, claim.get("duplicate_group_id"), claim_id)

            for digest in claim.get("document_hashes", []) or []:
                index._add(index.document_hashes, digest, claim_id)

        return index

    @staticmethod
    def _add(store: dict[str, list[str]], key: Any, claim_id: str) -> None:
        if _is_missing(key):
            return
        store.setdefault(str(key), []).append(claim_id)


@dataclass
class RuleEvaluation:
    """Everything the decision engine and the explanation need."""

    claim_id: str
    product_category: str
    policy_source: str

    hard_fail: list[RuleOutcome] = field(default_factory=list)
    warning: list[RuleOutcome] = field(default_factory=list)
    manual_review: list[RuleOutcome] = field(default_factory=list)
    passed: list[RuleOutcome] = field(default_factory=list)

    missing_documents: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    duplicate_indicators: list[str] = field(default_factory=list)

    warranty_status: str = ""
    warranty_status_at_fault: str = ""
    claim_reporting_within_period: bool = True
    serial_number_status: str = "Matched"
    replacement_eligible: bool = False
    reporting_days: int = 0
    warranty_remaining_days: int = 0

    @property
    def hard_fail_detected(self) -> bool:
        return bool(self.hard_fail)

    @property
    def warning_detected(self) -> bool:
        return bool(self.warning)

    @property
    def manual_review_trigger(self) -> bool:
        return bool(self.manual_review)

    @property
    def outcome(self) -> str:
        """Coarse rule verdict, independent of any model prediction."""
        if self.hard_fail:
            return "hard_fail"
        if self.manual_review:
            return "manual_review"
        return "pass"

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim_id,
            "product_category": self.product_category,
            "policy_source": self.policy_source,
            "outcome": self.outcome,
            "hard_fail_detected": self.hard_fail_detected,
            "warning_detected": self.warning_detected,
            "manual_review_trigger": self.manual_review_trigger,
            "missing_documents": list(self.missing_documents),
            "contradictions": list(self.contradictions),
            "duplicate_indicators": list(self.duplicate_indicators),
            "warranty_status": self.warranty_status,
            "warranty_status_at_fault": self.warranty_status_at_fault,
            "claim_reporting_within_period": self.claim_reporting_within_period,
            "serial_number_status": self.serial_number_status,
            "replacement_eligible": self.replacement_eligible,
            "reporting_days": self.reporting_days,
            "warranty_remaining_days": self.warranty_remaining_days,
            "hard_fail": [item.as_dict() for item in self.hard_fail],
            "warning": [item.as_dict() for item in self.warning],
            "manual_review": [item.as_dict() for item in self.manual_review],
            "passed": [item.as_dict() for item in self.passed],
        }


# ---------------------------------------------------------------------------
# Policy loading (SRS xxvi)
# ---------------------------------------------------------------------------


def load_policies(policy_dir: str | Path) -> dict[str, dict[str, Any]]:
    """
    Load every warranty policy file from a configurable directory.

    Policies are data, never code. Adding a fourth category means dropping a
    fourth JSON file into the directory, with no change to this module.
    """
    directory = Path(policy_dir)

    if not directory.is_dir():
        raise FileNotFoundError(f"Policy directory not found: {directory}")

    policies: dict[str, dict[str, Any]] = {}

    for path in sorted(directory.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        category = payload.get("product_category")

        if not category:
            raise ValueError(f"{path.name} has no product_category")

        missing = _missing_policy_keys(payload)
        if missing:
            raise ValueError(f"{path.name} is missing keys: {missing}")

        policies[str(category)] = payload

    if not policies:
        raise ValueError(f"No policy files found in {directory}")

    return policies


REQUIRED_POLICY_KEYS: tuple[str, ...] = (
    "product_category",
    "coverage_duration_months",
    "warranty_start_conditions",
    "covered_faults",
    "exclusions",
    "claim_reporting_period_days",
    "repair_conditions",
    "authorized_service_centre_required",
    "replacement_conditions",
    "grace_period_days",
    "mandatory_documents",
    "hard_fail_rules",
    "warning_rules",
    "manual_review_rules",
)


def _missing_policy_keys(policy: dict[str, Any]) -> list[str]:
    return [key for key in REQUIRED_POLICY_KEYS if key not in policy]


def get_policy(
    policies: dict[str, dict[str, Any]],
    product_category: str,
) -> dict[str, Any]:
    try:
        return policies[product_category]
    except KeyError as error:
        available = ", ".join(sorted(policies))
        raise KeyError(
            f"No warranty policy for category {product_category!r}. "
            f"Available categories: {available}"
        ) from error


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------


def _as_date(value: Any) -> date | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "nat"}:
        return None
    try:
        return date.fromisoformat(text[:10])
    except ValueError:
        return None


def _as_bool(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "y", "t"}
    if value is None:
        return False
    try:
        if value != value:  # NaN
            return False
    except TypeError:
        pass
    return bool(value)


def _as_int(value: Any, default: int = 0) -> int:
    try:
        if value is None or value != value:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _is_missing(value: Any) -> bool:
    """
    Treat NaN, NaT, None and blank strings as absent.

    This matters more than it looks. Reading a CSV with pandas turns a blank
    cell into float('nan'), and `nan == ""` is False while `nan is None` is
    also False. Without this guard every blank identifier collapses into one
    shared key, and the duplicate detector reports the entire dataset as a
    single duplicate group.
    """
    if value is None:
        return True
    if isinstance(value, str):
        text = value.strip().lower()
        return text == "" or text in {"nan", "none", "nat", "null"}
    try:
        return bool(value != value)
    except (TypeError, ValueError):
        return False


def document_sha256(payload: bytes) -> str:
    """SRS xxxi. Hash an uploaded document so reuse can be detected."""
    return hashlib.sha256(payload).hexdigest()


# ---------------------------------------------------------------------------
# Derived facts
# ---------------------------------------------------------------------------


def _derive_dates(claim: dict[str, Any]) -> dict[str, Any]:
    purchase = _as_date(claim.get("purchase_date"))
    fault = _as_date(claim.get("fault_date"))
    claimed = _as_date(claim.get("claim_date"))
    expiry = _as_date(claim.get("warranty_expiry_date"))
    last_repair = _as_date(claim.get("last_repair_date"))

    return {
        "purchase_date": purchase,
        "fault_date": fault,
        "claim_date": claimed,
        "warranty_expiry_date": expiry,
        "last_repair_date": last_repair,
        "product_age_days": (claimed - purchase).days if purchase and claimed else 0,
        "reporting_days": (claimed - fault).days if fault and claimed else 0,
        "warranty_remaining_days": (
            (expiry - claimed).days if expiry and claimed else 0
        ),
        "days_since_last_repair": (
            (claimed - last_repair).days if last_repair and claimed else None
        ),
    }


# ---------------------------------------------------------------------------
# SRS xxvii  Serial-number verification
# ---------------------------------------------------------------------------


def verify_serial_numbers(claim: dict[str, Any]) -> str:
    """
    Compare the entered serial number with every serial extracted from the
    uploaded documents. Returns Matched, Mismatch, or Unavailable.
    """
    observed = {
        str(claim[column]).strip()
        for column in SERIAL_COLUMNS
        if claim.get(column) not in (None, "")
    }

    if not observed:
        return "Unavailable"

    return "Matched" if len(observed) == 1 else "Mismatch"


# ---------------------------------------------------------------------------
# SRS xxviii  Contradiction detection
# ---------------------------------------------------------------------------


def detect_contradictions(claim: dict[str, Any]) -> list[str]:
    """Find conflicting information within a single claim."""
    issues: list[str] = []
    dates = _derive_dates(claim)

    purchase = dates["purchase_date"]
    fault = dates["fault_date"]
    claimed = dates["claim_date"]
    last_repair = dates["last_repair_date"]

    if purchase and fault and fault < purchase:
        issues.append("Fault date before purchase date")
    if purchase and claimed and claimed < purchase:
        issues.append("Claim date before purchase date")
    if fault and claimed and claimed < fault:
        issues.append("Claim date before fault date")
    if purchase and last_repair and last_repair < purchase:
        issues.append("Repair date before purchase date")
    if fault and last_repair and last_repair > fault:
        issues.append("Repair date after fault date")

    if len({str(claim[c]).strip() for c in SERIAL_COLUMNS if claim.get(c)}) > 1:
        issues.append("Conflicting serial numbers")

    if len({str(claim[c]).strip() for c in MODEL_COLUMNS if claim.get(c)}) > 1:
        issues.append("Inconsistent product model")

    return issues


# ---------------------------------------------------------------------------
# SRS xxix  Missing document detection
# ---------------------------------------------------------------------------


def detect_missing_documents(
    claim: dict[str, Any],
    policy: dict[str, Any],
) -> list[str]:
    """Return the mandatory documents the claimant did not supply."""
    missing: list[str] = []

    for document in policy.get("mandatory_documents", []):
        column = DOCUMENT_FLAGS.get(document)
        if column is None:
            continue
        if not _as_bool(claim.get(column)):
            missing.append(document)

    return missing


# ---------------------------------------------------------------------------
# SRS xxx / xxxi  Duplicate detection
# ---------------------------------------------------------------------------


def detect_duplicates(
    claim: dict[str, Any],
    index: DuplicateIndex | None,
) -> list[str]:
    """Report indicators that this claim may already have been submitted."""
    if index is None:
        return []

    claim_id = str(claim.get("claim_id", ""))
    indicators: list[str] = []

    checks = (
        ("invoice_number", index.invoice_numbers, "Same invoice number"),
        ("serial_number", index.serial_numbers, "Same product serial number"),
        ("product_id", index.product_ids, "Same registered product"),
        ("duplicate_group_id", index.groups, "Same duplicate group"),
    )

    for field_name, store, label in checks:
        key = claim.get(field_name)
        if _is_missing(key):
            continue
        others = [c for c in store.get(str(key), []) if c != claim_id]
        if others:
            indicators.append(f"{label} ({len(others)} existing claim(s))")

    for digest in claim.get("document_hashes", []) or []:
        if _is_missing(digest):
            continue
        others = [c for c in index.document_hashes.get(str(digest), []) if c != claim_id]
        if others:
            indicators.append(
                f"Reused document file ({len(others)} existing claim(s))"
            )

    return indicators


# ---------------------------------------------------------------------------
# SRS xxv  Rule groups
# ---------------------------------------------------------------------------


def _evaluate_hard_fail(
    claim: dict[str, Any],
    policy: dict[str, Any],
    dates: dict[str, Any],
    contradictions: list[str],
    warranty_status: str,
    within_period: bool,
) -> list[RuleOutcome]:
    results: list[RuleOutcome] = []

    if warranty_status == "Expired":
        results.append(
            RuleOutcome(
                "warranty_expired",
                "Warranty expired",
                "fail",
                f"Claim submitted after expiry on {dates['warranty_expiry_date']}",
            )
        )
    else:
        results.append(
            RuleOutcome(
                "warranty_expired",
                "Warranty expired",
                "pass",
                f"{dates['warranty_remaining_days']} day(s) of cover remaining",
            )
        )

    fault_category = str(claim.get("fault_category") or "")
    exclusions = policy.get("exclusions", {})

    if fault_category in exclusions:
        results.append(
            RuleOutcome(
                "fault_excluded",
                "Fault excluded by policy",
                "fail",
                exclusions[fault_category],
            )
        )
    elif fault_category in policy.get("covered_faults", {}):
        results.append(
            RuleOutcome(
                "fault_covered",
                "Fault covered by policy",
                "pass",
                policy["covered_faults"][fault_category],
            )
        )

    damage_reasons = []
    if _as_bool(claim.get("physical_damage")):
        damage_reasons.append("physical damage")
    if _as_bool(claim.get("liquid_damage")):
        damage_reasons.append("liquid damage")
    if _as_bool(claim.get("unauthorized_repair")):
        damage_reasons.append("unauthorized repair")

    if damage_reasons:
        results.append(
            RuleOutcome(
                "excluded_damage",
                "Excluded damage or unauthorized repair",
                "fail",
                "Detected " + ", ".join(damage_reasons),
            )
        )

    if _as_bool(claim.get("receipt_available")) and not _as_bool(
        claim.get("receipt_valid")
    ):
        results.append(
            RuleOutcome(
                "invalid_receipt",
                "Invalid purchase receipt",
                "fail",
                "Receipt is present but the purchase details do not validate",
            )
        )
    elif _as_bool(claim.get("receipt_available")):
        results.append(
            RuleOutcome(
                "proof_of_purchase",
                "Proof of purchase",
                "pass",
                "Valid purchase receipt supplied",
            )
        )

    if not within_period and not contradictions:
        results.append(
            RuleOutcome(
                "reporting_period",
                "Claim reported after policy deadline",
                "fail",
                f"Reported {dates['reporting_days']} day(s) after the fault, "
                f"policy allows {policy.get('claim_reporting_period_days')}",
            )
        )
    elif within_period:
        results.append(
            RuleOutcome(
                "reporting_period",
                "Claim reported within policy period",
                "pass",
                f"Reported {dates['reporting_days']} day(s) after the fault",
            )
        )

    # A replacement request that does not meet the policy repair threshold is
    # a hard fail, not a warning: the claimant asked for a replacement the
    # policy does not allow.
    conditions = policy.get("replacement_conditions", {})
    threshold = _as_int(conditions.get("eligible_after_repairs"), default=99)

    if _as_bool(claim.get("replacement_requested")):
        eligible = (
            warranty_status == "Active"
            and _as_int(claim.get("previous_repair_count")) >= threshold
            and not any(r.status == "fail" for r in results)
        )

        if eligible:
            results.append(
                RuleOutcome(
                    "replacement_eligible",
                    "Replacement is eligible under policy",
                    "pass",
                    f"{_as_int(claim.get('previous_repair_count'))} previous "
                    f"repair(s) meets the threshold of {threshold}",
                )
            )
        else:
            reasons = []
            if warranty_status != "Active":
                reasons.append("warranty is not active")
            if _as_int(claim.get("previous_repair_count")) < threshold:
                reasons.append(
                    f"only {_as_int(claim.get('previous_repair_count'))} previous "
                    f"repair(s) against a threshold of {threshold}"
                )
            if any(r.status == "fail" for r in results):
                reasons.append("another hard-fail rule already applies")

            results.append(
                RuleOutcome(
                    "replacement_not_eligible",
                    "Replacement is not eligible under policy",
                    "fail",
                    "Replacement requested but " + "; ".join(reasons),
                )
            )

    return results


def _evaluate_warning(
    claim: dict[str, Any],
    policy: dict[str, Any],
    dates: dict[str, Any],
) -> list[RuleOutcome]:
    results: list[RuleOutcome] = []

    grace = _as_int(policy.get("grace_period_days"))
    remaining = dates["warranty_remaining_days"]

    if 0 <= remaining <= grace:
        results.append(
            RuleOutcome(
                "near_expiry",
                "Claim is near warranty expiry",
                "warn",
                f"{remaining} day(s) remaining, grace period is {grace} day(s)",
            )
        )

    period = _as_int(policy.get("claim_reporting_period_days"))
    reporting = dates["reporting_days"]

    if reporting == period:
        results.append(
            RuleOutcome(
                "at_reporting_deadline",
                "Claim is at the reporting deadline",
                "warn",
                f"Reported exactly {period} day(s) after the fault",
            )
        )

    if _as_bool(claim.get("extended_warranty")):
        results.append(
            RuleOutcome(
                "extended_warranty",
                "Extended warranty applies",
                "warn",
                "Claim is being assessed against an extended warranty",
            )
        )

    return results


def _evaluate_manual_review(
    claim: dict[str, Any],
    policy: dict[str, Any],
    dates: dict[str, Any],
    missing_documents: list[str],
    contradictions: list[str],
    duplicate_indicators: list[str],
    serial_status: str,
) -> list[RuleOutcome]:
    results: list[RuleOutcome] = []

    if missing_documents:
        results.append(
            RuleOutcome(
                "missing_mandatory_document",
                "Missing mandatory document",
                "review",
                "Not supplied: " + ", ".join(missing_documents),
            )
        )

    if serial_status == "Mismatch":
        results.append(
            RuleOutcome(
                "serial_mismatch",
                "Serial-number mismatch",
                "review",
                "Serial numbers differ between the claim and its documents",
            )
        )

    if duplicate_indicators:
        results.append(
            RuleOutcome(
                "duplicate_claim",
                "Duplicate claim group",
                "review",
                "; ".join(duplicate_indicators),
            )
        )

    if contradictions:
        results.append(
            RuleOutcome(
                "contradictory_information",
                "Contradictory information",
                "review",
                "; ".join(contradictions),
            )
        )

    if policy.get("authorized_service_centre_required") and not _as_bool(
        claim.get("authorized_service_center")
    ):
        results.append(
            RuleOutcome(
                "service_centre_authorization",
                "Service-center authorization unclear",
                "review",
                "Policy requires an authorized service centre",
            )
        )

    # A claim filed right on the expiry boundary is a business rule in its own
    # right, derived from dates rather than from any dataset label.
    if (
        dates["warranty_remaining_days"] == 0
        and dates["claim_date"] is not None
        and dates["claim_date"] == dates["warranty_expiry_date"]
    ):
        results.append(
            RuleOutcome(
                "expiry_boundary",
                "Claim submitted on warranty expiry boundary",
                "review",
                "Claim date equals the warranty expiry date",
            )
        )

    period = _as_int(policy.get("claim_reporting_period_days"))
    reporting = dates["reporting_days"]

    if reporting > 0 and reporting >= period - 1:
        results.append(
            RuleOutcome(
                "borderline_reporting",
                "Borderline warranty/reporting date",
                "review",
                f"Reported {reporting} day(s) after the fault against a "
                f"{period} day policy window",
            )
        )

    return results


def _evaluate_replacement(
    claim: dict[str, Any],
    policy: dict[str, Any],
    hard_fail: Sequence[RuleOutcome],
    warranty_status: str,
) -> bool:
    conditions = policy.get("replacement_conditions", {})
    threshold = _as_int(conditions.get("eligible_after_repairs"), default=99)

    if not _as_bool(claim.get("replacement_requested")):
        return False

    eligible = (
        warranty_status == "Active"
        and _as_int(claim.get("previous_repair_count")) >= threshold
        and not hard_fail
    )

    return bool(eligible)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def evaluate_claim(
    claim: dict[str, Any],
    policies: dict[str, dict[str, Any]],
    index: DuplicateIndex | None = None,
) -> RuleEvaluation:
    """
    Evaluate one claim against its category policy.

    `claim` must contain primary claim facts only. Audit columns are ignored
    even if present, so this function cannot be used to read the answer key.
    """
    category = str(claim.get("product_category") or "")
    policy = get_policy(policies, category)

    evaluation = RuleEvaluation(
        claim_id=str(claim.get("claim_id") or ""),
        product_category=category,
        policy_source=f"{category} policy",
    )

    dates = _derive_dates(claim)
    expiry = dates["warranty_expiry_date"]
    claimed = dates["claim_date"]
    fault = dates["fault_date"]

    evaluation.warranty_remaining_days = dates["warranty_remaining_days"]
    evaluation.reporting_days = dates["reporting_days"]
    evaluation.warranty_status = (
        "Active" if claimed and expiry and claimed <= expiry else "Expired"
    )
    evaluation.warranty_status_at_fault = (
        "Active" if fault and expiry and fault <= expiry else "Expired"
    )

    period = _as_int(policy.get("claim_reporting_period_days"))
    evaluation.claim_reporting_within_period = dates["reporting_days"] <= period

    evaluation.serial_number_status = verify_serial_numbers(claim)
    evaluation.contradictions = detect_contradictions(claim)
    evaluation.missing_documents = detect_missing_documents(claim, policy)
    evaluation.duplicate_indicators = detect_duplicates(claim, index)

    hard_fail = _evaluate_hard_fail(
        claim,
        policy,
        dates,
        evaluation.contradictions,
        evaluation.warranty_status,
        evaluation.claim_reporting_within_period,
    )
    evaluation.hard_fail = [r for r in hard_fail if r.status == "fail"]
    evaluation.passed = [r for r in hard_fail if r.status == "pass"]

    evaluation.warning = _evaluate_warning(claim, policy, dates)
    evaluation.manual_review = _evaluate_manual_review(
        claim,
        policy,
        dates,
        evaluation.missing_documents,
        evaluation.contradictions,
        evaluation.duplicate_indicators,
        evaluation.serial_number_status,
    )

    evaluation.replacement_eligible = _evaluate_replacement(
        claim,
        policy,
        evaluation.hard_fail,
        evaluation.warranty_status,
    )

    return evaluation


def evaluate_claims(
    claims: Sequence[dict[str, Any]],
    policies: dict[str, dict[str, Any]],
    index: DuplicateIndex | None = None,
) -> list[RuleEvaluation]:
    return [evaluate_claim(claim, policies, index) for claim in claims]
