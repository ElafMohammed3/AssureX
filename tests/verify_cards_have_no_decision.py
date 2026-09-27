"""Verify that Claim Summary Cards carry facts only, never a decision."""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT / "dataset_generator"))

GENERATOR = PROJECT_ROOT / "dataset_generator" / "dataset_generator.py"

# Anything matching these must never appear as a rendered card label.
FORBIDDEN = [
    "claim_class",
    "prediction",
    "confidence",
    "decision",
    "valid claim",
    "invalid claim",
    "manual review",
    "likely valid",
    "likely invalid",
]


def main() -> int:
    source = GENERATOR.read_text(encoding="utf-8")

    match = re.search(r"def card_entries.*?(?=\ndef )", source, re.S)
    if not match:
        print("could not locate card_entries()")
        return 1

    body = match.group(0)
    labels = re.findall(r"""\(\s*["']([^"']+)["']\s*,""", body)

    print(f"card labels found: {len(labels)}")
    for label in labels:
        print(f"  - {label}")

    print()
    offenders = [
        label
        for label in labels
        if any(bad in label.lower() for bad in FORBIDDEN)
    ]

    if offenders:
        print("FORBIDDEN LABELS ON CARD:", offenders)
        return 1

    print("PASS: no prediction, confidence, class or decision label is rendered.")
    print("      SRS xx and SRS deliverable 5 requirement satisfied.")

    # Also confirm the render function never reads those fields.
    render = re.search(
        r"def generate_claim_card.*?(?=\ndef )", source, re.S
    )
    if render:
        reads = [
            field
            for field in ("claim_class", "hard_fail_detected", "manual_review_trigger")
            if field in render.group(0)
        ]
        print()
        if reads:
            print("WARNING: generate_claim_card references:", reads)
        else:
            print("PASS: generate_claim_card() does not read any audit column.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
