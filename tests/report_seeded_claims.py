"""Report the seeded claims with their scenarios, decisions and indicators."""

import os
import sys
from pathlib import Path

os.environ.setdefault("ASSUREX_DATABASE_URL", "sqlite:///assurex_dev.db")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))
sys.path.insert(0, str(PROJECT_ROOT / "src"))

import app as application  # noqa: E402

application.bootstrap()

with application.app.app_context():
    from database import Claim, Evaluation, Product, Warranty

    claims = Claim.query.order_by(Claim.id).all()

    print("=" * 104)
    print(
        f"{'claim_id':22s} {'scenario':28s} {'final_decision':22s} "
        f"{'rule':14s} indicators"
    )
    print("=" * 104)

    for claim in claims:
        details = claim.purchase_details or {}

        # A claim submitted through the form has no source_scenario key, and a
        # None value must not be formatted as a padded string.
        scenario = details.get("source_scenario") or "form submission"

        evaluation = Evaluation.query.filter_by(claim_id=claim.id).first()

        if evaluation is None:
            print(f"{claim.claim_id:22s} {scenario:28s} {'NO EVALUATION':22s} {'-':14s} -")
            continue

        indicators = details.get("duplicate_indicators") or []
        note = "; ".join(indicators) if indicators else (evaluation.rule_result or "-")

        decision = evaluation.final_decision or "not yet decided"
        rule = evaluation.rule_result or "-"

        print(
            f"{claim.claim_id:22s} {scenario:28s} "
            f"{decision:22s} {rule:14s} {note[:44]}"
        )

    print()
    print(f"claims: {len(claims)}  products: {Product.query.count()}  "
          f"warranties: {Warranty.query.count()}  "
          f"evaluations: {Evaluation.query.count()}")
