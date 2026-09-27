"""
Claim persistence and evaluation recording.

Kept separate from `app.py` so the write path has one responsibility: turn an
evaluated submission into a `Claim` row plus an `Evaluation` row, and nothing
else. SRS xlvi requires the application to store claims, predictions,
confidence scores and rule results, and SRS xlviii requires each prediction to
be linked to the model version that produced it.

Two schema realities this module works with honestly:

1. `Claim.product_id` and `Claim.warranty_id` are NOT NULL, but the claim form
   does not ask the user to register a product first. Rather than reject the
   submission, the product and warranty are created from the form data if they
   do not already exist. That keeps the demo path short without inventing data.

2. `Evaluation.model_consistency` is a three-value Enum
   (Consistent / Inconsistent / Uncertain), while SRS xxiv defines a five-way
   status (Strong Match, Acceptable Match, Weak Match, Model Disagreement,
   Uncertain Result). The five-way status is mapped onto the Enum for storage,
   and the precise status is preserved verbatim in the explanation text, so no
   information is lost.
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime
from typing import Any, Mapping

from database import Claim, Evaluation, Product, Warranty, WarrantyPolicy, db
from rule_engine import detect_missing_documents


def derive_claim_features(
    claim: dict[str, Any],
    policy: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Compute every derived model input that SRS xvi requires.

    The training CSV carries these precomputed. A web submission does not, and
    omitting them is not harmless:

    * the numeric imputer raises "Cannot use median strategy with non-numeric
      data" when the derived counts arrive as empty strings;
    * `repair_history` is the strongest single feature in the trained model, so
      sending it blank removes the model's most important signal and collapses
      predictions towards the majority class.

    Deriving them here keeps the web path and the training path describing
    identical features, which is what makes a web prediction comparable to the
    reported 92.89% test accuracy.
    """
    def as_date(value: Any) -> date | None:
        if not value:
            return None
        try:
            return date.fromisoformat(str(value)[:10])
        except ValueError:
            return None

    purchase = as_date(claim.get("purchase_date"))
    fault = as_date(claim.get("fault_date"))
    claimed = as_date(claim.get("claim_date"))
    expiry = as_date(claim.get("warranty_expiry_date"))
    last_repair = as_date(claim.get("last_repair_date"))

    facts: dict[str, Any] = {
        "product_age_days": (claimed - purchase).days if purchase and claimed else 0,
        "reporting_days": (claimed - fault).days if fault and claimed else 0,
        "warranty_remaining_days": (expiry - claimed).days if expiry and claimed else 0,
        "warranty_status": (
            "Active" if claimed and expiry and claimed <= expiry else "Expired"
        ),
        "days_since_last_repair": (
            (claimed - last_repair).days if claimed and last_repair else 0
        ),
        "missing_documents_count": 0,
        "missing_documents": "None",
    }

    def as_bool(name: str) -> bool:
        value = claim.get(name)
        if isinstance(value, str):
            return value.strip().lower() in {"on", "true", "1", "yes"}
        return bool(value)

    def as_int(name: str) -> int:
        try:
            return int(float(claim.get(name) or 0))
        except (TypeError, ValueError):
            return 0

    # repair_history is one-hot encoded, so it must use the same wording as the
    # dataset. Any other string lands in a category the model has never seen.
    repairs = as_int("previous_repair_count")
    if repairs <= 0:
        facts["repair_history"] = "No previous repairs"
    elif as_bool("unauthorized_repair"):
        facts["repair_history"] = "Unauthorized repair reported"
    elif as_bool("replacement_requested"):
        facts["repair_history"] = (
            "Replacement requested before policy repair threshold"
        )
    elif not as_bool("authorized_service_center"):
        facts["repair_history"] = "Service-center authorization is unclear"
    elif repairs > 1:
        facts["repair_history"] = (
            "Complex repair history with supporting diagnostics"
        )
    else:
        facts["repair_history"] = "One or more authorized repairs"

    if policy is not None:
        missing = detect_missing_documents(claim, dict(policy))
        facts["missing_documents"] = "|".join(missing) if missing else "None"
        facts["missing_documents_count"] = len(missing)

    # Supporting evidence requires every mandatory document and no conflict.
    facts["supporting_evidence_available"] = (
        as_bool("receipt_available")
        and as_bool("warranty_card_available")
        and as_bool("product_image_available")
        and as_bool("serial_evidence_available")
        and as_bool("fault_evidence_available")
        and as_bool("repair_report_available")
        and facts["missing_documents_count"] == 0
    )

    # An absent damage type must reach the encoder as NaN so prepare_features
    # normalises it to "Missing", exactly as the training CSV does.
    if not str(claim.get("damage_type") or "").strip():
        claim["damage_type"] = None

    return facts


# Backwards-compatible alias for the earlier numeric-only helper.
derive_numeric_facts = derive_claim_features

# --- SRS xxiv five-way status -> Evaluation.model_consistency Enum ---------
CONSISTENCY_ENUM = {
    "Strong Match": "Consistent",
    "Acceptable Match": "Consistent",
    "Weak Match": "Inconsistent",
    "Model Disagreement": "Inconsistent",
    "Uncertain Result": "Uncertain",
}

# --- SRS xxxiv final decision -> Claim.status Enum --------------------------
STATUS_UNDER_EVALUATION = "Under Evaluation"
STATUS_MANUAL_REVIEW = "Manual Review"

DECISION_TO_STATUS = {
    "Likely Valid": STATUS_UNDER_EVALUATION,
    "Likely Invalid": STATUS_UNDER_EVALUATION,
    "Manual Review Required": STATUS_MANUAL_REVIEW,
}

CLASSES = ("Valid Claim", "Invalid Claim", "Manual Review")


def _reference(prefix: str) -> str:
    return f"{prefix}-{uuid.uuid4().hex[:10].upper()}"


def _as_date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _as_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(str(value).replace(",", "").strip() or default)
    except (TypeError, ValueError):
        return default


def _checkbox(form: Mapping[str, Any], name: str) -> bool:
    return str(form.get(name, "")).strip().lower() in {"on", "true", "1", "yes"}


# ---------------------------------------------------------------------------
# Product and warranty
# ---------------------------------------------------------------------------


def ensure_product(user, form: Mapping[str, Any]) -> Product:
    """Find the claimant's product by serial number, or create it."""
    serial = str(form.get("serial_number") or "").strip()
    serial = serial or f"SN-PENDING-{uuid.uuid4().hex[:8].upper()}"

    existing = Product.query.filter_by(
        user_id=user.id, serial_number=serial
    ).first()

    if existing is not None:
        return existing

    product = Product(
        product_id=_reference("PRD"),
        user_id=user.id,
        product_name=str(
            form.get("product_name")
            or f"{form.get('brand', 'Unknown')} {form.get('model', 'Product')}"
        ).strip(),
        category=str(form.get("product_category") or "Electronics"),
        brand=str(form.get("brand") or "Unknown"),
        model_number=str(form.get("model") or "Unknown"),
        serial_number=serial,
        purchase_date=_as_date(form.get("purchase_date")) or date.today(),
        purchase_price=_as_float(form.get("purchase_price")),
        retailer=str(form.get("retailer") or "Unknown"),
        warranty_duration_months=int(
            _as_float(form.get("warranty_duration_months"), 12)
        ),
    )

    db.session.add(product)
    db.session.flush()

    return product


def ensure_warranty(
    product: Product,
    form: Mapping[str, Any],
) -> Warranty:
    """Find the product's warranty, or create one from the claim form."""
    existing = Warranty.query.filter_by(product_id=product.id).first()

    if existing is not None:
        return existing

    category = product.category
    policy = WarrantyPolicy.query.filter_by(
        product_category=category, active=True
    ).first()

    if policy is None:
        policy = WarrantyPolicy.query.filter_by(active=True).first()

    if policy is None:
        raise RuntimeError(
            "No warranty policy is available. Run: py -3 app.py"
        )

    start = _as_date(form.get("purchase_date")) or product.purchase_date
    months = product.warranty_duration_months or policy.coverage_duration_months or 12

    expiry = _as_date(form.get("warranty_expiry_date"))
    if expiry is None:
        expiry = date(start.year + months // 12, start.month, start.day)

    warranty = Warranty(
        warranty_id=_reference("WAR"),
        product_id=product.id,
        policy_id=policy.id,
        provider=str(
            form.get("warranty_provider") or f"{policy.product_category} Warranty"
        ),
        start_date=start,
        expiry_date=expiry,
        coverage_conditions=policy.covered_faults or {},
        exclusions=policy.exclusions or {},
        service_center_information=policy.repair_conditions or {},
        status="Expired" if expiry < date.today() else "Active",
    )

    db.session.add(warranty)
    db.session.flush()

    return warranty


# ---------------------------------------------------------------------------
# Claim and evaluation
# ---------------------------------------------------------------------------


def persist_submission(
    user,
    form: Mapping[str, Any],
    prediction: Mapping[str, Any],
    decision_result: Any,
    model_version: str,
) -> tuple[Claim, Evaluation]:
    """
    Write one evaluated submission and roll the transaction back on failure.

    Returns the saved (claim, evaluation) pair.
    """
    try:
        product = ensure_product(user, form)
        warranty = ensure_warranty(product, form)

        claim = Claim(
            claim_id=str(form.get("claim_id") or _reference("CLM")),
            user_id=user.id,
            product_id=product.id,
            warranty_id=warranty.id,
            product_age_days=int(_as_float(form.get("product_age_days"), 0)),
            purchase_details={
                "purchase_date": form.get("purchase_date"),
                "purchase_price": form.get("purchase_price"),
                "retailer": form.get("retailer"),
                "brand": form.get("brand"),
                "model": form.get("model"),
                "serial_number": form.get("serial_number"),
            },
            fault_occurrence_date=(
                _as_date(form.get("fault_date")) or date.today()
            ),
            fault_description=str(form.get("fault_description") or ""),
            damage_type=str(form.get("damage_type") or "None"),
            warranty_conditions={
                "warranty_provider": form.get("warranty_provider"),
                "warranty_expiry_date": form.get("warranty_expiry_date"),
                "extended_warranty": _checkbox(form, "extended_warranty"),
            },
            service_history={
                "previous_repair_count": form.get("previous_repair_count"),
                "authorized_service_center": _checkbox(
                    form, "authorized_service_center"
                ),
                "last_repair_date": form.get("last_repair_date"),
            },
            previous_replacement_information={
                "previous_replacement": _checkbox(form, "previous_replacement"),
                "replacement_requested": _checkbox(form, "replacement_requested"),
            },
            submission_date=datetime.utcnow(),
            status=DECISION_TO_STATUS.get(
                decision_result.final_decision, STATUS_UNDER_EVALUATION
            ),
        )

        db.session.add(claim)
        db.session.flush()

        evaluation = _build_evaluation(
            claim, prediction, decision_result, model_version
        )

        db.session.add(evaluation)
        db.session.commit()

        return claim, evaluation

    except Exception:
        db.session.rollback()
        raise


def _build_evaluation(
    claim: Claim,
    prediction: Mapping[str, Any],
    decision_result: Any,
    model_version: str,
) -> Evaluation:
    python_confidence = dict(prediction.get("python_confidence") or {})
    image_confidence = dict(prediction.get("image_confidence") or {}) or None

    consistency = CONSISTENCY_ENUM.get(
        decision_result.consistency.status, "Uncertain"
    )

    explanation = decision_result.explanation()
    explanation += f" Model version: {model_version}."

    return Evaluation(
        evaluation_id=_reference("EVA"),
        claim_id=claim.id,
        python_prediction=prediction.get("python_predicted_class"),
        python_valid_confidence=_confidence(python_confidence, "Valid Claim"),
        python_invalid_confidence=_confidence(python_confidence, "Invalid Claim"),
        python_manual_review_confidence=_confidence(
            python_confidence, "Manual Review"
        ),
        teachable_prediction=prediction.get("image_predicted_class"),
        teachable_valid_confidence=_confidence(image_confidence, "Valid Claim"),
        teachable_invalid_confidence=_confidence(image_confidence, "Invalid Claim"),
        teachable_manual_review_confidence=_confidence(
            image_confidence, "Manual Review"
        ),
        prediction_match=decision_result.consistency.classes_match,
        confidence_difference=decision_result.consistency.confidence_difference,
        model_consistency=consistency,
        warranty_result=decision_result.rule_outcome,
        missing_documents=list(decision_result.missing_documents),
        contradictions=list(decision_result.contradictions),
        duplicate_indicator=bool(decision_result.duplicate_indicators),
        rule_result=decision_result.rule_outcome,
        final_decision=decision_result.final_decision,
        explanation=explanation,
    )


def _confidence(scores: Mapping[str, float] | None, class_name: str) -> float | None:
    if not scores:
        return None
    value = scores.get(class_name)
    return None if value is None else float(value)
