"""
Measure the decision engine against the Python model alone.

This answers a specific question: does adding the rule engine to the classifier
improve accuracy on unseen test claims, and by how much?

The Teachable Machine model does not exist yet, so it is simulated. Every
simulated figure below is a PROJECTION, not a measurement, and is labelled as
such. The measured figures are the "no image model" columns, which use only
real components.
"""

from __future__ import annotations

import sys
from pathlib import Path

import joblib
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

from data_loader import load_datasets  # noqa: E402
from decision_engine import (  # noqa: E402
    DECISION_LIKELY_INVALID,
    DECISION_LIKELY_VALID,
    DECISION_MANUAL_REVIEW,
    DecisionConfig,
    decide,
    top_class,
)
from preprocessing import prepare_features  # noqa: E402
from rule_engine import DuplicateIndex, evaluate_claims, load_policies  # noqa: E402

ARTIFACT_DIR = PROJECT_ROOT / "models" / "tabular"

# Ground truth -> the final decision that counts as correct.
CORRECT_DECISION = {
    "Valid Claim": DECISION_LIKELY_VALID,
    "Invalid Claim": DECISION_LIKELY_INVALID,
    "Manual Review": DECISION_MANUAL_REVIEW,
}


def simulate_image_model(actual: str, confidence: float, rate: float, seed: int):
    """
    Return a projected Teachable Machine result.

    With probability `rate` it agrees with the truth, otherwise it picks one of
    the other two classes. This is a projection used for planning only.
    """
    import random

    rng = random.Random(f"{seed}-{actual}")

    if rng.random() < rate:
        predicted = actual
    else:
        others = [c for c in CORRECT_DECISION if c != actual]
        predicted = rng.choice(others)

    scores = {c: (1.0 - confidence) / 2 for c in CORRECT_DECISION}
    scores[predicted] = confidence

    return predicted, scores


def main() -> None:
    config = DecisionConfig.load()
    print(f"thresholds loaded from : {Path(config.source).name}")

    train_df, validation_df, test_df, features = load_datasets(
        PROJECT_ROOT / "dataset"
    )
    policies = load_policies(PROJECT_ROOT / "dataset" / "policies")

    all_claims = pd.concat([train_df, validation_df, test_df], ignore_index=True)
    index = DuplicateIndex.build(all_claims.to_dict(orient="records"))

    pipeline = joblib.load(ARTIFACT_DIR / "final_pipeline.joblib")
    test_rows = test_df.to_dict(orient="records")

    print(f"test claims            : {len(test_rows)}")
    print()

    prepared = prepare_features(test_df, features)
    probabilities = pipeline.predict_proba(prepared)
    classes = list(pipeline.named_steps["model"].classes_)

    rules = evaluate_claims(test_rows, policies, index)
    rule_lookup = {r.claim_id: r for r in rules}

    # --- measured: Python model only ---------------------------------------
    model_correct = 0
    model_wrong = []

    # --- measured: model + rule engine, no image model ---------------------
    combined_correct = 0
    combined_wrong = []
    decisions = []

    for position, row in enumerate(test_rows):
        confidence = {
            name: float(p) for name, p in zip(classes, probabilities[position])
        }
        predicted = max(confidence, key=lambda key: confidence[key])
        actual = row["claim_class"]

        if predicted == actual:
            model_correct += 1
        else:
            model_wrong.append((row["claim_id"], actual, predicted))

        result = decide(
            python_class=predicted,
            python_confidence=confidence,
            rule_result=rule_lookup[row["claim_id"]],
            config=config,
        )
        decisions.append(result.final_decision)

        if result.final_decision == CORRECT_DECISION[actual]:
            combined_correct += 1
        else:
            combined_wrong.append(
                (row["claim_id"], actual, predicted, result.final_decision)
            )

    total = len(test_rows)
    print("=" * 68)
    print("MEASURED  (real model + real rule engine, no image model)")
    print("=" * 68)
    print(f"  Python model alone        : {model_correct}/{total} = {model_correct/total:.2%}")
    print(f"  Model + rule engine       : {combined_correct}/{total} = {combined_correct/total:.2%}")
    print(f"  Net change                : {(combined_correct - model_correct)/total:+.2%}")
    print()

    print("  final decision distribution:")
    for value, count in pd.Series(decisions).value_counts().items():
        print(f"    {value:24s} {count:>4}  ({count/total:.1%})")
    print()

    if combined_wrong:
        print("  remaining errors:")
        for claim_id, actual, predicted, final in combined_wrong:
            print(f"    {claim_id}  truth={actual:<14} model={predicted:<14} final={final}")
    else:
        print("  no remaining errors")

    print()
    print("=" * 68)
    print("PROJECTED  (simulated Teachable Machine, NOT a measurement)")
    print("=" * 68)
    print(f"  {'TM accuracy':>14}  {'model+TM+rules':>16}")
    for rate in (0.70, 0.80, 0.85, 0.90, 0.95):
        correct = 0
        for position, row in enumerate(test_rows):
            confidence = {
                name: float(p) for name, p in zip(classes, probabilities[position])
            }
            predicted = max(confidence, key=lambda key: confidence[key])
            actual = row["claim_class"]

            image_class, image_confidence = simulate_image_model(
                actual, confidence[predicted], rate, position
            )

            result = decide(
                python_class=predicted,
                python_confidence=confidence,
                rule_result=rule_lookup[row["claim_id"]],
                image_class=image_class,
                image_confidence=image_confidence,
                config=config,
            )

            if result.final_decision == CORRECT_DECISION[actual]:
                correct += 1

        print(f"  {rate:>13.0%}  {correct/total:>15.2%}")

    print()
    print("  These rows are projections for planning. Replace them with real")
    print("  figures once the Teachable Machine model is trained.")


if __name__ == "__main__":
    main()
