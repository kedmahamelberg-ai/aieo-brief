#!/usr/bin/env python3
"""Email a private weekly draft and install it only after the owner's GitHub review."""
from __future__ import annotations

import argparse
import base64
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
IMAGE_TYPES = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png"}


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


def section_html(section: dict, kind: str, image_src: str = "") -> str:
    label = "News" if kind == "markets" else "Research"
    title = html.escape(str(section.get("title", "")))
    frame = [
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="margin:0 0 24px;background:#ffffff;border:1px solid #dfe6e5;border-radius:12px">',
        '<tr><td style="padding:0 0 26px">',
    ]
    if image_src:
        frame.append('<img src="' + html.escape(image_src, quote=True) + '" alt="'
                     + html.escape(str(section.get("image_alt", "")), quote=True)
                     + '" width="600" style="display:block;width:100%;height:auto;border:0;'
                     'border-radius:12px 12px 0 0">')
        art_url = str(section.get("image_source_url", ""))
        if not art_url.startswith("https://"):
            raise ValueError("Weekly review artwork source URL is invalid")
        frame.append('<p style="margin:12px 28px 0;color:#60747b;font-size:12px;line-height:1.5">'
                     + '<a style="color:#08727a" href="' + html.escape(art_url, quote=True)
                     + '">' + html.escape(str(section.get("image_caption", ""))) + '</a> · '
                     + html.escape(str(section.get("image_credit", ""))) + ' · '
                     + html.escape(str(section.get("image_rights", ""))) + '</p>')
    frame.append('<div style="padding:18px 28px 0">'
                 '<p style="margin:0 0 8px;color:#1a6971;font-size:12px;font-weight:700;'
                 'letter-spacing:.12em;text-transform:uppercase">' + label + ' · Weekly overview</p>'
                 '<h2 style="margin:0 0 14px;color:#142d39;font:normal 28px/1.2 Georgia,serif">'
                 + title + '</h2>')
    if section.get("status") != "ready":
        reason = html.escape(str(section.get("last_error") or section.get("pending_reason") or "source checks pending"))
        frame.append('<p style="margin:0;color:#6d4f2c;line-height:1.6">This section is awaiting '
                     'editorial checks (' + reason + ').</p>')
        return "".join(frame) + "</div></td></tr></table>"
    frame.append('<p style="margin:0 0 18px;color:#60747b;font-size:13px">By '
                 + html.escape(str(section.get("author", ""))) + '</p>')
    paragraphs = []
    for paragraph in section["prose"]:
        parts = []
        for part in paragraph:
            value = html.escape(part["text"])
            if part["source_key"]:
                target = "https://brief.hamelberg-ai.com/" + html.escape(part["path"], quote=True)
                value = '<a style="color:#08727a;text-decoration:underline" href="' + target + '">' + value + "</a>"
            parts.append(value)
        paragraphs.append('<p style="margin:0 0 16px;color:#243746;font:16px/1.65 Georgia,serif">'
                          + " ".join(parts) + "</p>")
    frame.extend(paragraphs)
    frame.append('<p style="margin:8px 0 0;color:#60747b;font-size:12px;line-height:1.5">'
                 + html.escape(str(section.get("scope_note", ""))) + '</p>')
    return "".join(frame) + "</div></td></tr></table>"


def review_images(overview: dict, root: Path) -> dict:
    """Read the exact rights-cleared artwork selected in the checked draft."""
    result = {}
    root = root.resolve()
    for kind in ("markets", "research"):
        section = overview[kind]
        if section.get("status") != "ready":
            continue
        validate_section(section)
        relative = Path(str(section["image_path"]))
        if (relative.is_absolute() or relative.parts[:2] != ("assets", "culture")
                or ".." in relative.parts or relative.suffix.lower() not in IMAGE_TYPES):
            raise ValueError("Weekly review artwork path is invalid")
        path = (root / relative).resolve()
        if root not in path.parents or not path.is_file():
            raise ValueError("Weekly review artwork is missing")
        content = path.read_bytes()
        if not content or len(content) > 4_000_000:
            raise ValueError("Weekly review artwork size is invalid")
        result[kind] = {"filename": path.name,
                        "content_type": IMAGE_TYPES[relative.suffix.lower()],
                        "content": base64.b64encode(content).decode("ascii")}
    return result


def email_content(draft: dict, run_url: str, *, root: Path = ROOT,
                  image_mode: str = "cid") -> dict:
    if image_mode not in ("cid", "data"):
        raise ValueError("Unknown weekly review image mode")
    overview = draft["overview"]
    ready = overview["editorial_status"] == "ready"
    status_label = "Ready for your approval" if ready else "Checks still pending"
    images = review_images(overview, root)
    attachments = []
    body = [
        '<!doctype html><html lang="en" dir="ltr"><head><meta charset="utf-8">'
        '<meta name="viewport" content="width=device-width,initial-scale=1">'
        '<title>The Brief weekly review ' + html.escape(draft["release_id"]) + '</title></head>'
        '<body style="margin:0;background:#edf2f1;color:#243746">'
        '<div lang="en" dir="ltr" style="padding:24px 12px">'
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" '
        'style="max-width:640px;margin:auto"><tr><td>',
        '<p style="margin:0 0 12px;color:#1a6971;font:700 13px Arial,sans-serif;'
        'letter-spacing:.15em;text-transform:uppercase">The Brief · Owner review</p>',
        '<h1 style="margin:0 0 8px;color:#142d39;font:normal 36px/1.16 Georgia,serif">'
        'Your weekly overview</h1>',
        '<p style="margin:0 0 12px;font:15px/1.5 Arial,sans-serif">'
        + html.escape(draft["release_id"]) + ' · ' + html.escape(draft["period_start"])
        + ' to ' + html.escape(draft["period_end"]) + '</p>',
        '<p style="margin:0 0 24px;color:#1a6971;font:700 13px Arial,sans-serif">'
        + status_label + ' · Unpublished preview</p>',
    ]
    for kind in ("markets", "research"):
        section = overview[kind]
        image = images.get(kind)
        image_src = ""
        if image:
            if image_mode == "cid":
                content_id = "brief-weekly-" + kind
                image_src = "cid:" + content_id
                attachments.append({**image, "content_id": content_id})
            else:
                image_src = "data:" + image["content_type"] + ";base64," + image["content"]
        body.append(section_html(section, kind, image_src))
    safe_url = html.escape(run_url, quote=True)
    if ready:
        body.append('<p style="font:15px/1.6 Arial,sans-serif">Both sections passed the source '
                    'and editorial checks. On GitHub, choose <strong>Approve and deploy</strong> '
                    'to publish this exact draft, or <strong>Reject</strong> and enter correction notes.</p>')
        body.append('<p><a style="display:inline-block;padding:13px 20px;background:#183e50;'
                    'border-radius:6px;color:#fff;font:700 14px Arial,sans-serif;text-decoration:none" '
                    'href="' + safe_url + '">Review and approve on GitHub</a> '
                    '<a style="display:inline-block;padding:13px 20px;color:#183e50;'
                    'font:700 14px Arial,sans-serif" href="' + safe_url
                    + '">Request corrections on GitHub</a></p>')
    else:
        body.append('<p style="font:15px/1.6 Arial,sans-serif">Approval is unavailable while '
                    'a section is pending. The failed check is shown in the card above.</p>')
        body.append('<p><a href="' + safe_url + '">Open the review run</a></p>')
    body.append('<p style="margin:28px 0 0;color:#60747b;font:12px/1.5 Arial,sans-serif">'
                'The artwork, prose, and source links above are the private draft. These buttons '
                'open GitHub; clicking an email link alone cannot publish.</p>'
                '</td></tr></table></div></body></html>')
    return {
        "subject": "The Brief weekly draft " + draft["release_id"] + " — " + status_label,
        "html": "".join(body),
        "attachments": attachments,
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
