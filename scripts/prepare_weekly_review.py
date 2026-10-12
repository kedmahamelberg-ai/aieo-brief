#!/usr/bin/env python3
"""Create a private review artifact for a weekly Brief edition.

This is deliberately separate from the public site build.  It may prepare a
source-linked draft, but it never writes the archive, deploys a site, or sends
mail.  A human-approved edition is added to the archive in a later release.
"""
from __future__ import annotations

import json
from pathlib import Path

from build_site import ROOT, cards, culture_items, inputs, papers
from brief_database import dbmaps
from weekly_overviews import prepare_weekly_overviews


def main() -> None:
    release, symbiosis = inputs()
    registry, readiness, editorial = dbmaps()
    news = cards(release, symbiosis, registry, readiness, editorial)
    research = papers()
    # This returns a candidate in memory only.  write_archive=False is the
    # non-negotiable boundary between a review and a public release.
    overview, _ = prepare_weekly_overviews(
        news, research, release, ROOT, write_archive=False, allow_model=True
    )
    ready = overview.get("editorial_status") == "ready"
    payload = {
        "schema_version": "aieo_weekly_review_draft_v1",
        "release_id": overview.get("release_id"),
        "period_start": overview.get("period_start"),
        "period_end": overview.get("period_end"),
        "requires_human_approval": ready,
        "publication_blocked": True,
        "email_blocked": True,
        "overview": overview,
    }
    Path("weekly-review-draft.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    print("Prepared review artifact for " + str(payload["release_id"]))
    print("Publication and email remain blocked pending human approval.")


if __name__ == "__main__":
    main()
