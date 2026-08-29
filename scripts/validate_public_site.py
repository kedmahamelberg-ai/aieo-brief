#!/usr/bin/env python3
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"

def main():
    if not SITE.exists():
        raise SystemExit("_site does not exist.")

    files = [p for p in SITE.rglob("*") if p.is_file()]
    text_files = [
        p for p in files
        if p.suffix.lower() in {".html",".js",".css",".json",".txt"}
    ]
    combined = "\n".join(
        p.read_text(encoding="utf-8", errors="ignore")
        for p in text_files
    )

    forbidden = [
        "SUPABASE_SECRET_KEY",
        "OPENAI_API_KEY",
        "sb_secret_",
        '"body_text"',
    ]
    found = [token for token in forbidden if token in combined]
    if found:
        raise SystemExit(f"Forbidden private material found in public build: {found}")

    if "—" in combined:
        raise SystemExit("Public build contains an em dash.")

    payload = json.loads((SITE/"data/current.json").read_text(encoding="utf-8"))
    expected = int(payload.get("story_count") or 0)
    story_pages = list((SITE/"story").glob("*/index.html"))
    if len(story_pages) != expected:
        raise SystemExit(
            f"Story page count mismatch: JSON={expected}, pages={len(story_pages)}"
        )

    homepage = (SITE/"index.html").read_text(encoding="utf-8")
    requirements = [
        'id="relationships"',
        'id="subscribe"',
        'data-ad-placement="top-banner"',
        'data-action="share"',
        'data-story-filter="all"',
        'class="share-dialog"',
    ]
    missing = [item for item in requirements if item not in homepage]
    if missing:
        raise SystemExit(f"Homepage acceptance checks failed: {missing}")

    sample_story = story_pages[0].read_text(encoding="utf-8")
    story_requirements = [
        'data-action="share"',
        'data-action="follow"',
        'data-ad-placement="story-rail"',
        'href="/#relationships"',
        'class="share-dialog"',
    ]
    missing = [item for item in story_requirements if item not in sample_story]
    if missing:
        raise SystemExit(f"Story acceptance checks failed: {missing}")

    print(
        json.dumps(
            {
                "files": len(files),
                "stories": expected,
                "private_material_found": False,
                "em_dash_found": False,
                "ux_acceptance_checks": "passed",
            },
            indent=2,
        )
    )
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
