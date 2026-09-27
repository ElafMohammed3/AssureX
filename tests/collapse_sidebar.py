"""
Collapse the duplicated sidebar into the shared _sidebar.html partial.

The damage being repaired
-------------------------
An earlier script rewrote sidebar links with a regular expression that captured
the opening quote of href="#" separately and then dropped it. Every link it
touched came out as

    <a href={{ url_for('my_products') }}>

with no quotes, which is not valid HTML. The browser reads href="{" and then
discards the rest, so those menu items stopped working.

The reason that was worth fixing properly rather than patching is that the
sidebar was duplicated into all thirteen templates. Each copy had to be edited
separately, and they had already drifted apart. Replacing the whole
<aside class="sidebar"> block in each template with one include means a link is
fixed once and can never drift again.

Safety
------
This script refuses to write unless the result passes all of these checks:

  * no unquoted href={{ survives anywhere
  * no href="#" survives inside a nav-item
  * every template that had a sidebar now includes _sidebar.html
  * the number of non-comment source lines is unchanged

    py -3 tests/collapse_sidebar.py --dry-run
    py -3 tests/collapse_sidebar.py
"""

from __future__ import annotations

import argparse
import codecs
import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "templates"

SKIP = {"_sidebar.html", "_nav.html", "_userchip.html", "base.html",
        "register_mockup.html"}

SIDEBAR_BLOCK = re.compile(
    r'[ \t]*<aside class="sidebar">.*?</aside>[ \t]*\n',
    re.IGNORECASE | re.DOTALL,
)

# Which sidebar key each page highlights, keyed by filename.
ACTIVE_KEY = {
    "CustomerDashbourd.html": "dashboard",
    "all_claims_queue.html": "claims_queue",
    "create-claim.html": "create_claim",
    "admin_dashboard.html": "admin",
    "manual_review_queue.html": "manual_review",
    "my_products.html": "my_products",
    "receipt_vault.html": "receipt_vault",
    "claim_status.html": "claim_status",
    "submit_claim.html": "create_claim",
    "warranty_rules_config.html": "warranty_rules",
    "analytics_reports.html": "analytics",
    "audit_logs.html": "audit",
    "user_management.html": "users",
    "claim-details.html": "claim_status",
}

INCLUDE = (
    "{%% set active = '%s' %%}\n"
    '{%% include "_sidebar.html" %%}\n'
)

# Checks the result must satisfy before anything is written.
BROKEN_HREF = re.compile(r'href=\{\{', re.IGNORECASE)
DEAD_NAV_LINK = re.compile(
    r'<li class="nav-item[^"]*"><a\s+href="#"', re.IGNORECASE
)


def detect_encoding(raw: bytes) -> str:
    if raw.startswith(codecs.BOM_UTF8):
        return "utf-8-sig"
    if raw.startswith(codecs.BOM_UTF32_LE) or raw.startswith(codecs.BOM_UTF32_BE):
        return "utf-32"
    if raw.startswith(codecs.BOM_UTF16_LE) or raw.startswith(codecs.BOM_UTF16_BE):
        return "utf-16"
    if b"\x00" in raw[:512]:
        return "utf-16-le"
    try:
        raw.decode("utf-8")
    except UnicodeDecodeError:
        return "cp1252"
    return "utf-8"


def code_lines(text: str) -> int:
    return sum(
        1
        for line in text.split("\n")
        if line.strip() and not line.strip().startswith(("{#", "#"))
    )


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    changed: list[tuple[Path, str, str]] = []
    untouched: list[str] = []

    for path in sorted(TEMPLATE_DIR.glob("*.html")):
        if path.name in SKIP:
            continue

        raw = path.read_bytes()
        encoding = detect_encoding(raw)
        text = raw.decode(encoding)

        match = SIDEBAR_BLOCK.search(text)
        if not match:
            untouched.append(path.name)
            continue

        key = ACTIVE_KEY.get(path.name, "dashboard")
        replacement = INCLUDE % key
        updated = text[: match.start()] + replacement + text[match.end():]

        changed.append((path, encoding, updated))

    # --- validation, before any write -------------------------------------
    failures: list[str] = []

    for path, _encoding, updated in changed:
        name = path.name

        if BROKEN_HREF.search(updated):
            failures.append(f"{name}: an unquoted href={{{{ survived }}")

        if DEAD_NAV_LINK.search(updated):
            failures.append(f"{name}: a nav-item still points at #")

        if "_sidebar.html" not in updated:
            failures.append(f"{name}: sidebar was removed but never replaced")

    # Statement count must not change, or the regex ate real markup.
    for path, encoding, updated in changed:
        raw = path.read_bytes()
        before = code_lines(raw.decode(encoding))
        after = code_lines(updated)
        if before != after:
            failures.append(
                f"{path.name}: source line count changed {before} -> {after}"
            )

    print("=" * 68)
    print("DRY RUN - nothing was written" if args.dry_run else "WRITTEN")
    print("=" * 68)
    print(f"{'template':30s} {'encoding':10s} {'sidebar':>10s}")
    print("-" * 68)

    for path, encoding, _ in changed:
        key = ACTIVE_KEY.get(path.name, "dashboard")
        print(f"{path.name:30s} {encoding:10s} {key:>10}")

    print()
    print(f"sidebars collapsed : {len(changed)}")
    print(f"left alone         : {len(untouched)}")
    for name in untouched:
        print(f"  {name}")

    if failures:
        print()
        print("VALIDATION FAILED - nothing was written:")
        for item in failures:
            print(f"  ! {item}")
        return 1

    print()
    print("PASS: no unquoted href, no dead nav-item, every sidebar has an include.")

    if not args.dry_run:
        for path, encoding, updated in changed:
            path.write_bytes(updated.encode(encoding))
        print("written.")

    return 0


if __name__ == "__main__":
    sys.exit(main())
