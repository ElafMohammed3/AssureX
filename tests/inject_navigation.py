"""
Inject the shared navigation partial into the standalone dashboard templates.

Why this exists
---------------
The dashboard templates written earlier are complete HTML documents, each with
its own <!DOCTYPE>, <head> and <style> block. Converting them to Jinja
`{% extends %}` layouts would mean deleting their stylesheets, which would
discard work that is not ours to discard.

Instead this script inserts a single `{% include "_nav.html" %}` line directly
after each file's opening <body> tag. That is purely additive: their markup,
styling and layout are untouched, and every page gains working navigation built
from url_for() so the links cannot break when routes change.

It is idempotent. Running it twice does nothing the second time.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "templates"

INCLUDE_LINE = '{% include "_nav.html" %}'

# Templates that already extend base.html, and so already have navigation.
SKIP = {
    "base.html",
    "_nav.html",
    "login.html",
    "register.html",
    "profile.html",
    "claim_result.html",
    "error.html",
    "register_mockup.html",
}

BODY_PATTERN = re.compile(r"(<body\b[^>]*>)", re.IGNORECASE)


def main() -> int:
    changed: list[str] = []
    skipped: list[str] = []
    already: list[str] = []
    failed: list[str] = []

    for path in sorted(TEMPLATE_DIR.glob("*.html")):
        if path.name in SKIP:
            skipped.append(path.name)
            continue

        text = path.read_text(encoding="utf-8")

        if INCLUDE_LINE in text:
            already.append(path.name)
            continue

        match = BODY_PATTERN.search(text)
        if not match:
            failed.append(path.name)
            continue

        insert_at = match.end()
        # Keep the nav on its own line, with a blank line after for spacing.
        patched = (
            text[:insert_at]
            + "\n\n"
            + INCLUDE_LINE
            + "\n"
            + text[insert_at:]
        )

        path.write_text(patched, encoding="utf-8")
        changed.append(path.name)

    print(f"nav injected into : {len(changed)}")
    for name in changed:
        print(f"  + {name}")

    if already:
        print(f"\nalready connected : {len(already)}")
        for name in already:
            print(f"  = {name}")

    if skipped:
        print(f"\nskipped (extend base.html or are partials): {len(skipped)}")
        for name in skipped:
            print(f"  - {name}")

    if failed:
        print(f"\nNO <body> TAG FOUND: {len(failed)}")
        for name in failed:
            print(f"  ! {name}")
        return 1

    print("\nPASS: every dashboard template now renders shared navigation.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
