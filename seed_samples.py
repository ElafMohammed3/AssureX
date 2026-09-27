"""
Seed the demonstration claims required by SRS deliverable 8.

Run it from the project root:

    py -3 seed_samples.py

Then start the app and sign in with:

    email     demo@assurex.test
    password  demo12345

Every seeded claim is a real dataset record pushed through the real trained
model, the real warranty rule engine and the real decision engine. Nothing is
hard-coded and nothing is invented.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

os.environ.setdefault("ASSUREX_DATABASE_URL", "sqlite:///assurex_dev.db")

import app as application  # noqa: E402
from sample_data import DEMO_EMAIL, DEMO_PASSWORD, seed  # noqa: E402


def main() -> int:
    application.bootstrap()

    with application.app.app_context():
        report = seed(
            application.evaluate_submission,
            application.MODEL_VERSION,
        )

    print("=" * 70)
    print(f"SEEDED {len(report['created'])} SAMPLE CLAIMS")
    print("=" * 70)
    for record in report["created"]:
        print()
        print(f"  {record['claim_id']}")
        print(f"    scenario        : {record['scenario']}")
        print(f"    from dataset id : {record['source_claim_id']}")
        print(f"    actual class    : {record['actual_class']}")
        print(f"    python predicted: {record['python_prediction']}")
        print(f"    rule outcome    : {record['rule_outcome']}")
        print(f"    consistency     : {record['consistency']}")
        print(f"    FINAL DECISION  : {record['final_decision']}")
        print(f"    claim status    : {record['status']}")

    if report["skipped"]:
        print()
        print("SKIPPED")
        for item in report["skipped"]:
            print(f"  {item}")

    print()
    print("=" * 70)
    print("SRS DELIVERABLE 8 REQUIRED DEMONSTRATION CASES")
    print("=" * 70)
    missing = 0
    for requirement, claim_id in report["srs_cases"].items():
        ok = claim_id != "NOT SEEDED"
        if not ok:
            missing += 1
        print(f"  {'OK  ' if ok else 'MISS'} {requirement:38s} {claim_id}")

    print()
    print(f"demonstration login : {DEMO_EMAIL} / {DEMO_PASSWORD}")
    print()
    if missing:
        print(f"{missing} required case(s) NOT seeded. See the list above.")
        return 1

    print("PASS: every SRS deliverable 8 demonstration case is present, and each")
    print("      one is a real dataset record evaluated by the real system.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
