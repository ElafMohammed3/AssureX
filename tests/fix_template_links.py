"""
Replace hardcoded .html file paths with Flask url_for() routes.

A link such as href="create-claim.html" asks the browser for a static file at
/templates/create-claim.html. That returns 404 because the page is served by a
route, not served as a file. url_for() emits the correct URL and survives route
changes.

templates/register_mockup.html is deliberately left alone. It is an archived
design draft, is not routed, and is kept only so the original design work is not
lost.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEMPLATE_DIR = PROJECT_ROOT / "templates"

SKIP = {"register_mockup.html"}

# href value -> url_for() expression
REPLACEMENTS = {
    "create-claim.html": "{{ url_for('create_claim') }}",
    "register.html": "{{ url_for('register') }}",
    "login.html": "{{ url_for('login') }}",
    "logout.html": "{{ url_for('logout') }}",
    "index.html": "{{ url_for('index') }}",
    "my-products.html": "{{ url_for('my_products') }}",
    "all-claims-queue.html": "{{ url_for('claims_queue') }}",
    # There is no single claim-details URL without an ID, so send the user to
    # the queue and let them pick a claim.
    "claim-details.html": "{{ url_for('claims_queue') }}",
}

HREF = re.compile(r'href="([^"]+\.html)"')


def main() -> int:
    total = 0
    touched: list[tuple[str, str, str]] = []

    for path in sorted(TEMPLATE_DIR.glob("*.html")):
        if path.name in SKIP:
            continue

        text = original = path.read_text(encoding="utf-8")

        def substitute(match: re.Match) -> str:
            value = match.group(1)
            replacement = REPLACEMENTS.get(value)
            if not replacement:
                return match.group(0)
            touched.append((path.name, value, replacement))
            return f'href="{replacement}"'

        text = HREF.sub(substitute, text)

        if text != original:
            path.write_text(text, encoding="utf-8")
            total += 1

    print(f"templates modified: {total}")
    for name, old, new in touched:
        print(f"  {name}: {old}  ->  {new}")

    # Verify nothing live still points at a bare .html path.
    remaining = []
    for path in sorted(TEMPLATE_DIR.glob("*.html")):
        if path.name in SKIP:
            continue
        for match in HREF.finditer(path.read_text(encoding="utf-8")):
            remaining.append(f"{path.name}: {match.group(1)}")

    print()
    if remaining:
        print("STILL POINTING AT .html FILES:")
        for item in remaining:
            print(f"  {item}")
        return 1

    print("PASS: no live template links to a bare .html file path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
