#!/usr/bin/env python3
"""Email a private weekly draft and install it only after the owner's GitHub review."""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

import requests

from build_site import ROOT, cards, inputs, papers
from brief_database import dbmaps
from weekly_editorials import eligible, ready_valid, validate_section

REPOSITORY = "kedmahamelberg-ai/aieo-brief"
OWNER_LOGIN = "kedmahamelberg-ai"
OWNER_ID = 209744145
ENVIRONMENT = "weekly-editorial"
RELEASE_ID = re.compile(r"202\d-W\d{2}\Z")


def load_draft(path: Path, expected_sha256: str) -> dict:
    data = path.read_bytes()
    if not re.fullmatch(r"[0-9a-f]{64}", expected_sha256):
        raise ValueError("Invalid expected draft digest")
    if hashlib.sha256(data).hexdigest() != expected_sha256:
        raise ValueError("Weekly draft changed after preparation")
    draft = json.loads(data)
    if draft.get("schema_version") != "aieo_weekly_review_draft_v1":
        raise ValueError("Unknown weekly draft schema")
    release_id = draft.get("release_id", "")
    overview = draft.get("overview", {})
    if (not isinstance(release_id, str) or not RELEASE_ID.fullmatch(release_id)
            or overview.get("release_id") != release_id
            or draft.get("publication_blocked") is not True
            or draft.get("email_blocked") is not True):
        raise ValueError("Weekly draft identity or publication boundary is invalid")
    ready = overview.get("editorial_status") == "ready"
    if ready != (draft.get("requires_human_approval") is True):
        raise ValueError("Weekly review readiness is inconsistent")
    if ready:
        for kind in ("markets", "research"):
            validate_section(overview[kind])
    return draft


def section_html(section: dict) -> str:
    if section.get("status") != "ready":
        reason = html.escape(str(section.get("last_error") or section.get("pending_reason") or "source checks pending"))
        return "<p>This section is awaiting editorial checks (" + reason + ").</p>"
    paragraphs = []
    for paragraph in section["prose"]:
        parts = []
        for part in paragraph:
            value = html.escape(part["text"])
            if part["source_key"]:
                target = "https://brief.hamelberg-ai.com/" + html.escape(part["path"], quote=True)
                value = '<a href="' + target + '">' + value + "</a>"
            parts.append(value)
        paragraphs.append("<p>" + " ".join(parts) + "</p>")
    return "".join(paragraphs)


def email_content(draft: dict, run_url: str) -> dict:
    overview = draft["overview"]
    ready = overview["editorial_status"] == "ready"
    status_label = "Ready for your approval" if ready else "Checks still pending"
    body = [
        '<main style="max-width:650px;margin:auto;font:16px/1.6 Arial,sans-serif;color:#243746">',
        "<h1>The Brief weekly review</h1>",
        "<p><strong>" + html.escape(draft["release_id"]) + " · " + status_label + "</strong></p>",
        "<p>This unpublished draft covers " + html.escape(draft["period_start"])
        + " through " + html.escape(draft["period_end"]) + ".</p>",
    ]
    for kind, heading in (("markets", "News"), ("research", "Research")):
        section = overview[kind]
        body.append("<h2>" + heading + ": " + html.escape(section["title"]) + "</h2>")
        body.append(section_html(section))
    safe_url = html.escape(run_url, quote=True)
    if ready:
        body.append("<p>Both sections passed the source and editorial checks. GitHub will ask you to approve or reject the protected publication job. A rejection lets you leave correction notes.</p>")
        for button_label in ("Review and approve on GitHub", "Request corrections on GitHub"):
            body.append('<p><a style="display:inline-block;padding:12px 18px;background:#183e50;color:white;text-decoration:none" href="'
                        + safe_url + '">' + button_label + "</a></p>")
    else:
        body.append("<p>Approval is unavailable while a section is pending. The failed check is shown above and in the workflow run.</p>")
        body.append('<p><a href="' + safe_url + '">Open the review run</a></p>')
    body.append("<p>These links open GitHub; clicking an email link alone cannot publish.</p></main>")
    return {
        "subject": "The Brief weekly draft " + draft["release_id"] + " — " + status_label,
        "html": "".join(body),
    }


def send_email(draft: dict, run_id: str) -> None:
    recipient = os.environ["WEEKLY_REVIEW_TO_EMAIL"]
    if recipient != "kedma@hamelberg-ai.com":
        raise ValueError("Weekly review recipient is not the confirmed owner address")
    if not re.fullmatch(r"\d+", run_id):
        raise ValueError("Invalid workflow run ID")
    run_url = "https://github.com/" + REPOSITORY + "/actions/runs/" + run_id
    message = email_content(draft, run_url)
    response = requests.post(
        "https://api.resend.com/emails",
        headers={
            "Authorization": "Bearer " + os.environ["RESEND_API_KEY"],
            "Idempotency-Key": "brief-weekly-review-" + draft["release_id"] + "-" + run_id,
        },
        json={"from": os.environ["RESEND_FROM_EMAIL"], "to": [recipient], **message},
        timeout=30,
    )
    response.raise_for_status()
    print("Weekly private review email accepted by Resend for " + draft["release_id"] + ".")


def owner_approved(reviews: list[dict]) -> bool:
    return any(
        review.get("state") == "approved"
        and review.get("user", {}).get("login") == OWNER_LOGIN
        and review.get("user", {}).get("id") == OWNER_ID
        and any(env.get("name") == ENVIRONMENT for env in review.get("environments", []))
        for review in reviews
    )


def review_history(run_id: str) -> list[dict]:
    if not re.fullmatch(r"\d+", run_id):
        raise ValueError("Invalid workflow run ID")
    response = requests.get(
        "https://api.github.com/repos/" + REPOSITORY + "/actions/runs/" + run_id + "/approvals",
        headers={"Authorization": "Bearer " + os.environ["GITHUB_TOKEN"],
                 "Accept": "application/vnd.github+json"},
        timeout=30,
    )
    response.raise_for_status()
    value = response.json()
    if not isinstance(value, list):
        raise ValueError("GitHub did not return workflow review history")
    return value


def validate_live_sources(draft: dict) -> None:
    release, symbiosis = inputs()
    if (release["release_id"] != draft["release_id"]
            or release["period_start"] != draft["period_start"]
            or release["period_end"] != draft["period_end"]):
        raise ValueError("The source edition changed before approval")
    registry, readiness, editorial = dbmaps(False)
    news = cards(release, symbiosis, registry, readiness, editorial)
    for kind, rows in (("markets", news), ("research", papers())):
        available = {row["key"]: row for row in eligible(rows, release)}
        if not ready_valid(draft["overview"][kind], available):
            raise ValueError("Weekly " + kind + " sources changed before approval")


def approved_file(draft: dict, reviews: list[dict], now: datetime) -> dict:
    if draft["overview"].get("editorial_status") != "ready" or not owner_approved(reviews):
        raise ValueError("Only a complete draft approved by the owner can be published")
    result = {"release_id": draft["release_id"],
              "human_approved_at": now.astimezone(timezone.utc).isoformat(),
              "approved_by": OWNER_LOGIN}
    for kind in ("markets", "research"):
        section = dict(draft["overview"][kind])
        validate_section(section)
        section["human_approved"] = True
        result[kind] = section
    return result


def install_approval(draft: dict, run_id: str) -> Path:
    reviews = review_history(run_id)
    result = approved_file(draft, reviews, datetime.now(timezone.utc))
    validate_live_sources(draft)
    path = ROOT / "data/weekly-overviews/approved" / (draft["release_id"] + ".json")
    if path.exists():
        raise ValueError("This weekly edition already has an approval file")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print("Installed owner-approved weekly draft " + draft["release_id"] + ".")
    return path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("email", "approve"))
    parser.add_argument("--draft", type=Path, default=Path("weekly-review-draft.json"))
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args()
    draft = load_draft(args.draft, args.sha256)
    if args.command == "email":
        send_email(draft, args.run_id)
    else:
        install_approval(draft, args.run_id)


if __name__ == "__main__":
    main()
