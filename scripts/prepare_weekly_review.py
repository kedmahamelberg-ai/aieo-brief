#!/usr/bin/env python3
"""Create a private review artifact for a weekly Brief edition.

This is deliberately separate from the public site build. It prepares a
source-linked draft artifact without writing the archive or deploying the site.
"""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from build_site import ROOT, cards, inputs, papers
from brief_database import dbmaps
from weekly_overviews import prepare_weekly_overviews
from weekly_editorials import validate_section
from weekly_review_delivery import REPOSITORY, email_content


def main() -> None:
    release, symbiosis = inputs()
    registry, readiness, editorial = dbmaps(False)
    news = cards(release, symbiosis, registry, readiness, editorial)
    research = papers()
    # This returns a candidate in memory only.  write_archive=False is the
    # non-negotiable boundary between a review and a public release.
    overview, _ = prepare_weekly_overviews(
        news, research, release, ROOT, write_archive=False, allow_model=True
    )
    ready = overview.get("editorial_status") == "ready"
    if ready:
        for kind in ("markets", "research"):
            validate_section(overview[kind])
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
    path = Path("weekly-review-draft.json")
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )
    run_id = os.environ.get("GITHUB_RUN_ID", "")
    run_url = ("https://github.com/" + REPOSITORY + "/actions/runs/" + run_id
               if run_id.isdigit() else "https://github.com/" + REPOSITORY + "/actions")
    Path("weekly-review-preview.html").write_text(
        email_content(payload, run_url, image_mode="data")["html"], encoding="utf-8"
    )
    already_approved = (ROOT / "data/weekly-overviews/approved" / (str(payload["release_id"]) + ".json")).exists()
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a") as handle:
            handle.write("release_id=" + str(payload["release_id"]) + "\n")
            handle.write("ready=" + str(ready).lower() + "\n")
            handle.write("needs_review=" + str(not already_approved).lower() + "\n")
            handle.write("draft_sha256=" + hashlib.sha256(path.read_bytes()).hexdigest() + "\n")
    print("Prepared review artifact for " + str(payload["release_id"]))
    print("Publication remains blocked pending human approval.")


if __name__ == "__main__":
    main()
