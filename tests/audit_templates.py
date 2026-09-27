"""Report which templates are rendered by a route and which are orphaned."""

import re
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]

RENDER_CALL = re.compile(
    r"""render_template\(\s*["']([^"']+\.html)["']""", re.S
)


def main() -> int:
    app_source = (PROJECT_ROOT / "app.py").read_text(encoding="utf-8")

    rendered = sorted(set(RENDER_CALL.findall(app_source)))
    on_disk = sorted(p.name for p in (PROJECT_ROOT / "templates").glob("*.html"))

    print(f"templates on disk : {len(on_disk)}")
    print(f"rendered by route : {len(rendered)}")
    for name in rendered:
        print(f"   {name}")

    # A partial or a base layout is included by Jinja, not rendered directly.
    structural = {"base.html", "_nav.html"}
    # Kept only as an archived design draft.
    archived = {"register_mockup.html"}

    orphans = [
        name
        for name in on_disk
        if name not in rendered and name not in structural and name not in archived
    ]

    print()
    print(f"orphaned templates : {len(orphans)}")
    for name in orphans:
        print(f"   {name}")

    if orphans:
        print()
        print("Each of these exists on disk but no route can reach it.")
        print("Either add a route that renders it, or delete it.")

    return 1 if orphans else 0


if __name__ == "__main__":
    sys.exit(main())
