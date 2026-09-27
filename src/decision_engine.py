"""
Final claim decision engine for the AssureX Claim Engine.

Combines three independent inputs into the final recommendation required by
SRS xxxiv:

    1. the Python classification model  (Valid Claim / Invalid Claim / Manual Review)
    2. the Google Teachable Machine model, when it is available
    3. the deterministic warranty rule engine

and produces the two outputs the SRS requires:

    a model consistency status   SRS xxiv
    a final decision              SRS xxxiv

        Likely Valid
        Likely Invalid
        Manual Review Required

Design rules that are deliberate, not incidental:

* Every threshold is read from `config/decision_thresholds.json`. SRS 1.8
  item 5 requires the team to be able to change a confidence threshold during
  final evaluation, so no threshold is written into this module.

* The image model can only ever *downgrade* a decision to manual review. It
  can never turn a Likely Invalid into a Likely Valid. Only the rule engine
  and the Python model can do that. Without this asymmetry a noisy image model
  could approve a claim that the rules already rejected.

* The module works with no image model at all. `tm_prediction` is optional, so
  the system degrades to "Uncertain Result" rather than failing. That is also
  what makes the behaviour testable before Teachable Machine is trained.

* Nothing here calls a generative-AI API. SRS Section 15 forbids it.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping

# --- SRS xxiv model consistency statuses ---
STATUS_STRONG_MATCH = "Strong Match"
STATUS_ACCEPTABLE_MATCH = "Acceptable Match"
STATUS_WEAK_MATCH = "Weak Match"
STATUS_DISAGREEMENT = "Model Disagreement"
STATUS_UNCERTAIN = "Uncertain Result"

CONSISTENCY_STATUSES = (
    STATUS_STRONG_MATCH,
    STATUS_ACCEPTABLE_MATCH,
    STATUS_WEAK_MATCH,
    STATUS_DISAGREEMENT,
    STATUS_UNCERTAIN,
)

# --- SRS xxxiv final decisions ---
DECISION_LIKELY_VALID = "Likely Valid"
DECISION_LIKELY_INVALID = "Likely Invalid"
DECISION_MANUAL_REVIEW = "Manual Review Required"

FINAL_DECISIONS = (
    DECISION_LIKELY_VALID,
    DECISION_LIKELY_INVALID,
    DECISION_MANUAL_REVIEW,
)

CLASS_VALID = "Valid Claim"
CLASS_INVALID = "Invalid Claim"
CLASS_REVIEW = "Manual Review"

DEFAULT_CONFIG_PATH = (
    Path(__file__).resolve().parents[1] / "config" / "decision_thresholds.json"
)


class DecisionConfigError(ValueError):
    """Raised when the threshold configuration is missing or inconsistent."""


@dataclass(frozen=True)
class DecisionConfig:
    strong_match_max_difference: float
    acceptable_match_max_difference: float
    weak_match_max_difference: float
    minimum_top_confidence: float
    uncertain_below_confidence: float
    require_image_model: bool
    hard_fail_forces_invalid: bool
    rule_review_forces_manual: bool
    weak_match_forces_manual: bool
    image_model_can_upgrade_decision: bool
    source: str = ""

    @classmethod
    def load(cls, path: str | Path | None = None) -> DecisionConfig:
        config_path = Path(path) if path else DEFAULT_CONFIG_PATH

        if not config_path.is_file():
            raise DecisionConfigError(
                f"Decision thresholds not found: {config_path}"
            )

        payload = json.loads(config_path.read_text(encoding="utf-8"))
        comparison = payload.get("comparison", {})
        decision = payload.get("decision", {})

        try:
            config = cls(
                strong_match_max_difference=float(
                    comparison["strong_match_max_difference"]
                ),
                acceptable_match_max_difference=float(
                    comparison["acceptable_match_max_difference"]
                ),
                weak_match_max_difference=float(
                    comparison["weak_match_max_difference"]
                ),
                minimum_top_confidence=float(comparison["minimum_top_confidence"]),
                uncertain_below_confidence=float(
                    comparison["uncertain_below_confidence"]
                ),
                require_image_model=bool(comparison.get("require_image_model", False)),
                hard_fail_forces_invalid=bool(decision["hard_fail_forces_invalid"]),
                rule_review_forces_manual=bool(decision["rule_review_forces_manual"]),
                weak_match_forces_manual=bool(decision["weak_match_forces_manual"]),
                image_model_can_upgrade_decision=bool(
                    decision["image_model_can_upgrade_decision"]
                ),
                source=str(config_path),
            )
        except KeyError as error:
            raise DecisionConfigError(
                f"Missing threshold in {config_path}: {error}"
            ) from error

        config.validate()
        return config

    def validate(self) -> None:
        ordered = [
            self.strong_match_max_difference,
            self.acceptable_match_max_difference,
            self.weak_match_max_difference,
        ]

        if not ordered[0] <= ordered[1] <= ordered[2]:
            raise DecisionConfigError(
                "Comparison thresholds must be non-decreasing: "
                f"{ordered[0]} <= {ordered[1]} <= {ordered[2]}"
            )

        for name, value in (
            ("minimum_top_confidence", self.minimum_top_confidence),
            ("uncertain_below_confidence", self.uncertain_below_confidence),
        ):
            if not 0.0 <= value <= 1.0:
                raise DecisionConfigError(f"{name} must be between 0 and 1, got {value}")

        if self.uncertain_below_confidence > self.minimum_top_confidence:
            raise DecisionConfigError(
                "uncertain_below_confidence must not exceed minimum_top_confidence"
            )


@dataclass
class ComparisonResult:
    """SRS xxiv: the five-way model consistency status."""

    status: str
    confidence_difference: float | None
    python_top_class: str
    python_top_confidence: float
    image_top_class: str | None
    image_top_confidence: float | None
    classes_match: bool | None
    degraded: bool = False
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "confidence_difference": self.confidence_difference,
            "python_top_class": self.python_top_class,
            "python_top_confidence": self.python_top_confidence,
            "image_top_class": self.image_top_class,
            "image_top_confidence": self.image_top_confidence,
            "classes_match": self.classes_match,
            "degraded": self.degraded,
            "reasons": list(self.reasons),
        }


@dataclass
class DecisionResult:
    """SRS xxxiv final decision plus the SRS xxxv explanation."""

    final_decision: str
    consistency: ComparisonResult
    python_predicted_class: str
    python_confidence: dict[str, float]
    image_predicted_class: str | None
    image_confidence: dict[str, float] | None
    rule_outcome: str

    supporting_factors: list[str] = field(default_factory=list)
    opposing_factors: list[str] = field(default_factory=list)
    rules_passed: list[str] = field(default_factory=list)
    rules_failed: list[str] = field(default_factory=list)
    contradictions: list[str] = field(default_factory=list)
    missing_documents: list[str] = field(default_factory=list)
    duplicate_indicators: list[str] = field(default_factory=list)
    additional_evidence_required: list[str] = field(default_factory=list)
    audit: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "final_decision": self.final_decision,
            "consistency": self.consistency.as_dict(),
            "python_predicted_class": self.python_predicted_class,
            "python_confidence": dict(self.python_confidence),
            "image_predicted_class": self.image_predicted_class,
            "image_confidence": (
                dict(self.image_confidence)
                if self.image_confidence is not None
                else None
            ),
            "rule_outcome": self.rule_outcome,
            "supporting_factors": list(self.supporting_factors),
            "opposing_factors": list(self.opposing_factors),
            "rules_passed": list(self.rules_passed),
            "rules_failed": list(self.rules_failed),
            "contradictions": list(self.contradictions),
            "missing_documents": list(self.missing_documents),
            "duplicate_indicators": list(self.duplicate_indicators),
            "additional_evidence_required": list(
                self.additional_evidence_required
            ),
            "audit": list(self.audit),
        }

    def explanation(self) -> str:
        """One-paragraph human-readable justification, SRS xxxv."""
        parts = [f"Final decision: {self.final_decision}."]

        parts.append(
            f"Python model predicted {self.python_predicted_class} "
            f"at {self._pct(self.consistency.python_top_confidence)}."
        )

        if self.consistency.image_top_class:
            parts.append(
                f"Teachable Machine predicted {self.consistency.image_top_class} "
                f"at {self._pct(self.consistency.image_top_confidence)}."
            )
        else:
            parts.append("Teachable Machine result unavailable.")

        if self.consistency.confidence_difference is not None:
            parts.append(
                "Confidence difference "
                f"{self._pct(self.consistency.confidence_difference)} "
                f"gives {self.consistency.status}."
            )

        if self.supporting_factors:
            parts.append("Supporting: " + "; ".join(self.supporting_factors) + ".")

        if self.opposing_factors:
            parts.append("Opposing: " + "; ".join(self.opposing_factors) + ".")

        if self.additional_evidence_required:
            parts.append(
                "Additional evidence required: "
                + "; ".join(self.additional_evidence_required)
                + "."
            )

        return " ".join(parts)

    @staticmethod
    def _pct(value: float | None) -> str:
        return "n/a" if value is None else f"{value * 100:.1f}%"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def top_class(confidence: Mapping[str, float]) -> tuple[str, float]:
    if not confidence:
        raise ValueError("confidence mapping is empty")

    name = max(confidence, key=lambda key: confidence[key])
    return name, float(confidence[name])


def _rule_field(rule_result: Any, name: str, default: Any) -> Any:
    """Read a field from a RuleEvaluation or a plain dict."""
    if isinstance(rule_result, Mapping):
        return rule_result.get(name, default)
    return getattr(rule_result, name, default)


def _follow_models(
    python_class: str,
    image_class: str | None,
    config: DecisionConfig,
    audit: list[str],
) -> str:
    """
    Turn an agreed model verdict into a final decision.

    The image model may corroborate but never overrule. Only the rule engine
    and the Python model can produce a final verdict, so a noisy image model
    cannot approve a claim the rules already rejected.
    """
    if python_class == CLASS_VALID:
        if image_class and image_class != CLASS_VALID:
            audit.append(
                "Image model did not corroborate Likely Valid and cannot "
                "overrule the Python model on its own."
            )
        else:
            audit.append("Python model predicted Valid Claim and no rule objected.")
        return DECISION_LIKELY_VALID

    if python_class == CLASS_INVALID:
        audit.append("Python model predicted Invalid Claim and no rule objected.")
        return DECISION_LIKELY_INVALID

    audit.append("Python model itself predicted Manual Review.")
    return DECISION_MANUAL_REVIEW


def _outcome_rows(rule_result: Any, group: str) -> list[tuple[str, str]]:
    """Return (label, detail) pairs for one rule group."""
    rows = _rule_field(rule_result, group, []) or []
    pairs: list[tuple[str, str]] = []

    for row in rows:
        if isinstance(row, Mapping):
            pairs.append((str(row.get("label", "")), str(row.get("detail", ""))))
        else:
            pairs.append(
                (str(getattr(row, "label", "")), str(getattr(row, "detail", "")))
            )

    return [(label, detail) for label, detail in pairs if label]


def _outcome_labels(rule_result: Any, group: str) -> list[str]:
    rows = _rule_field(rule_result, group, []) or []
    labels: list[str] = []

    for row in rows:
        if isinstance(row, Mapping):
            labels.append(str(row.get("label", "")))
        else:
            labels.append(str(getattr(row, "label", "")))

    return [label for label in labels if label]


# ---------------------------------------------------------------------------
# SRS xxiv  Model comparison
# ---------------------------------------------------------------------------


def compare_models(
    python_class: str,
    python_confidence: Mapping[str, float],
    image_class: str | None = None,
    image_confidence: Mapping[str, float] | None = None,
    config: DecisionConfig | None = None,
) -> ComparisonResult:
    """
    Classify the two-model comparison into the five SRS xxiv statuses.

    SRS Step 10 defines
        Confidence Difference = |Python top-class confidence - TM top-class confidence|
    """
    config = config or DecisionConfig.load()

    py_class, py_conf = top_class(python_confidence)

    reasons: list[str] = []

    if not image_class or not image_confidence:
        return ComparisonResult(
            status=STATUS_UNCERTAIN,
            confidence_difference=None,
            python_top_class=py_class,
            python_top_confidence=py_conf,
            image_top_class=None,
            image_top_confidence=None,
            classes_match=None,
            degraded=True,
            reasons=[
                "Teachable Machine result unavailable, so no agreement "
                "can be established."
            ],
        )

    im_class, im_conf = top_class(image_confidence)

    if py_conf < config.uncertain_below_confidence:
        reasons.append(
            f"Python confidence {py_conf:.2f} is below the "
            f"{config.uncertain_below_confidence:.2f} floor."
        )
        status = STATUS_UNCERTAIN
        difference = abs(py_conf - im_conf)
        return ComparisonResult(
            status=status,
            confidence_difference=round(difference, 4),
            python_top_class=py_class,
            python_top_confidence=round(py_conf, 4),
            image_top_class=im_class,
            image_top_confidence=round(im_conf, 4),
            classes_match=py_class == im_class,
            reasons=reasons,
        )

    if im_conf < config.uncertain_below_confidence:
        reasons.append(
            f"Teachable Machine confidence {im_conf:.2f} is below the "
            f"{config.uncertain_below_confidence:.2f} floor."
        )

    difference = abs(py_conf - im_conf)
    classes_match = py_class == im_class

    if not classes_match:
        status = STATUS_DISAGREEMENT
        reasons.append(
            f"Models disagree: Python says {py_class}, "
            f"Teachable Machine says {im_class}."
        )
    elif py_conf < config.minimum_top_confidence or im_conf < config.minimum_top_confidence:
        status = STATUS_UNCERTAIN
        reasons.append(
            "At least one model is below the minimum confidence of "
            f"{config.minimum_top_confidence:.2f}."
        )
    elif difference <= config.strong_match_max_difference:
        status = STATUS_STRONG_MATCH
        reasons.append(
            f"Classes agree and confidence differs by only {difference:.2f}."
        )
    elif difference <= config.acceptable_match_max_difference:
        status = STATUS_ACCEPTABLE_MATCH
        reasons.append(
            f"Classes agree with an acceptable confidence gap of {difference:.2f}."
        )
    elif difference <= config.weak_match_max_difference:
        status = STATUS_WEAK_MATCH
        reasons.append(
            f"Classes agree but the confidence gap of {difference:.2f} is weak."
        )
    else:
        status = STATUS_UNCERTAIN
        reasons.append(
            f"Confidence gap of {difference:.2f} exceeds the weak-match limit."
        )

    return ComparisonResult(
        status=status,
        confidence_difference=round(difference, 4),
        python_top_class=py_class,
        python_top_confidence=round(py_conf, 4),
        image_top_class=im_class,
        image_top_confidence=round(im_conf, 4),
        classes_match=classes_match,
        reasons=reasons,
    )


# ---------------------------------------------------------------------------
# SRS xxxiv  Final decision
# ---------------------------------------------------------------------------


def decide(
    python_class: str,
    python_confidence: Mapping[str, float],
    rule_result: Any,
    image_class: str | None = None,
    image_confidence: Mapping[str, float] | None = None,
    config: DecisionConfig | None = None,
) -> DecisionResult:
    """
    Produce the final three-class decision and its explanation.

    Priority order, highest first:

        1. a hard-fail rule            -> Likely Invalid
        2. a manual-review rule        -> Manual Review Required
        3. model disagreement/uncertainty -> Manual Review Required
        4. otherwise                   -> follow the models
    """
    config = config or DecisionConfig.load()

    comparison = compare_models(
        python_class,
        python_confidence,
        image_class,
        image_confidence,
        config,
    )

    hard_fail = _rule_field(rule_result, "hard_fail", []) or []
    manual_review = _rule_field(rule_result, "manual_review", []) or []
    warning = _rule_field(rule_result, "warning", []) or []
    passed = _rule_field(rule_result, "passed", []) or []

    rule_outcome = str(_rule_field(rule_result, "outcome", "unknown"))

    missing_documents = list(_rule_field(rule_result, "missing_documents", []) or [])
    contradictions = list(_rule_field(rule_result, "contradictions", []) or [])
    duplicates = list(_rule_field(rule_result, "duplicate_indicators", []) or [])

    supporting: list[str] = []
    opposing: list[str] = []
    evidence: list[str] = []
    audit: list[str] = []

    audit.append(f"Rule outcome: {rule_outcome}")
    audit.append(f"Model consistency: {comparison.status}")

    for label, detail in _outcome_rows(rule_result, "passed"):
        # Include the detail, because a rule named "Warranty expired" reads as
        # an accusation when it is listed under supporting factors. The detail
        # is what disambiguates "the claim is expired" from "the expiry check
        # passed with 120 days remaining".
        supporting.append(f"{label} (check passed: {detail})" if detail else label)
        audit.append(f"rule passed: {label}")

    for row in hard_fail:
        detail = row.get("detail") if isinstance(row, Mapping) else getattr(row, "detail", "")
        label = row.get("label") if isinstance(row, Mapping) else getattr(row, "label", "")
        opposing.append(f"{label} ({detail})" if detail else str(label))
        audit.append(f"rule failed: {label}")

    for row in manual_review:
        label = row.get("label") if isinstance(row, Mapping) else getattr(row, "label", "")
        opposing.append(str(label))
        audit.append(f"rule requires review: {label}")

    for row in warning:
        label = row.get("label") if isinstance(row, Mapping) else getattr(row, "label", "")
        audit.append(f"warning: {label}")

    for document in missing_documents:
        evidence.append(f"Supply the {document}")

    for issue in contradictions:
        audit.append(f"contradiction: {issue}")

    for indicator in duplicates:
        evidence.append(f"Resolve duplicate indicator: {indicator}")

    # --- 1. hard fail -------------------------------------------------------
    if hard_fail and config.hard_fail_forces_invalid:
        decision = DECISION_LIKELY_INVALID
        audit.append("Decision forced to Likely Invalid by a hard-fail rule.")

    # --- 2. rule-driven review ---------------------------------------------
    elif manual_review and config.rule_review_forces_manual:
        decision = DECISION_MANUAL_REVIEW
        audit.append("Decision forced to Manual Review by a rule trigger.")

    # --- 3. model-driven review --------------------------------------------
    elif comparison.status == STATUS_DISAGREEMENT:
        decision = DECISION_MANUAL_REVIEW
        audit.append("Decision forced to Manual Review by model disagreement.")

    elif (
        comparison.status == STATUS_UNCERTAIN
        and not (comparison.degraded and not config.require_image_model)
    ):
        decision = DECISION_MANUAL_REVIEW
        audit.append("Decision forced to Manual Review by uncertain model result.")

    elif comparison.degraded and not config.require_image_model:
        decision = _follow_models(python_class, image_class, config, audit)
        audit.append(
            "Comparison is degraded: the Teachable Machine model is absent, so "
            "the decision rests on the Python model and the rule engine alone. "
            "Set require_image_model=true once the image model is trained."
        )

    elif (
        comparison.status == STATUS_WEAK_MATCH
        and config.weak_match_forces_manual
    ):
        decision = DECISION_MANUAL_REVIEW
        audit.append("Decision forced to Manual Review by a weak match.")

    # --- 4. follow the models ----------------------------------------------
    else:
        decision = _follow_models(python_class, image_class, config, audit)

    if (
        decision == DECISION_LIKELY_VALID
        and image_class
        and image_class != CLASS_VALID
        and not config.image_model_can_upgrade_decision
    ):
        audit.append(
            "Image model did not corroborate Likely Valid and cannot "
            "downgrade or upgrade on its own."
        )

    return DecisionResult(
        final_decision=decision,
        consistency=comparison,
        python_predicted_class=python_class,
        python_confidence={k: round(float(v), 4) for k, v in python_confidence.items()},
        image_predicted_class=image_class,
        image_confidence=(
            {k: round(float(v), 4) for k, v in image_confidence.items()}
            if image_confidence
            else None
        ),
        rule_outcome=rule_outcome,
        supporting_factors=supporting,
        opposing_factors=opposing,
        rules_passed=_outcome_labels(rule_result, "passed"),
        rules_failed=_outcome_labels(rule_result, "hard_fail"),
        contradictions=contradictions,
        missing_documents=missing_documents,
        duplicate_indicators=duplicates,
        additional_evidence_required=evidence,
        audit=audit,
    )


def decide_from_evaluation(
    prediction: Mapping[str, Any],
    rule_result: Any,
    image_class: str | None = None,
    image_confidence: Mapping[str, float] | None = None,
    config: DecisionConfig | None = None,
) -> DecisionResult:
    """
    Convenience wrapper for the shape produced by the Flask app.

    `prediction` is the dictionary returned by `app.evaluate_submission`.
    """
    return decide(
        python_class=str(prediction["python_predicted_class"]),
        python_confidence=prediction["python_confidence"],
        rule_result=(
            rule_result
            if rule_result is not None
            else prediction.get("rule_result", {})
        ),
        image_class=image_class,
        image_confidence=image_confidence,
        config=config,
    )
