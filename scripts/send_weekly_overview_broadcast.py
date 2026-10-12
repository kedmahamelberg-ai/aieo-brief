#!/usr/bin/env python3
"""Send one explicitly human-approved weekly overview through Resend.

The program only accepts an approved archive edition.  It sends a Resend
Broadcast to the configured Audience, so subscriber addresses are never read
or stored by the Brief repository.
"""
from __future__ import annotations

import argparse
import html
import json
import os
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]


def approved_overview(release_id: str) -> dict:
    history = json.loads((ROOT / "data/weekly-overviews/history.json").read_text())
    overview = next((item for item in history.get("overviews", [])
                     if item.get("release_id") == release_id), None)
    if not overview or overview.get("editorial_status") != "ready":
        raise ValueError("The requested edition is not ready")
    for kind in ("markets", "research"):
        section = overview.get(kind, {})
        if not section.get("human_approved"):
            raise ValueError("The requested edition has not been human-approved")
    return overview


def section_html(section: dict) -> str:
    paragraphs = []
    for paragraph in section.get("prose", []):
        parts = []
        for part in paragraph:
            text = html.escape(str(part.get("text", "")))
            path = str(part.get("path", ""))
            if part.get("source_key") and path:
                text = '<a href="https://brief.hamelberg-ai.com/' + html.escape(path) + '">' + text + "</a>"
            parts.append(text)
        paragraphs.append("<p>" + " ".join(parts) + "</p>")
    image = html.escape(str(section.get("image_path", "")))
    title = html.escape(str(section.get("title", "")))
    return "<section><h2>" + title + "</h2>" + ("<img src=\"https://brief.hamelberg-ai.com/" + image + "\" alt=\"\">" if image else "") + "".join(paragraphs) + "</section>"


def payload(overview: dict) -> dict:
    content = (
        "<main><h1>The Brief: week from above</h1>"
        + section_html(overview["markets"])
        + section_html(overview["research"])
        + "<p><a href=\"https://brief.hamelberg-ai.com/week-from-above/"
          + html.escape(str(overview["release_id"]).lower())
          + "/\">Read the full weekly overview</a></p>"
        + "<p><a href=\"{{{RESEND_UNSUBSCRIBE_URL}}}\">Unsubscribe</a></p></main>"
    )
    return {
        "audience_id": os.environ["RESEND_AUDIENCE_ID"],
        "from": os.environ["RESEND_FROM_EMAIL"],
        "subject": "The Brief: week from above — " + str(overview["period_end"]),
        "html": content,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_id")
    parser.add_argument("--send", action="store_true", help="Create and send the Resend Broadcast")
    args = parser.parse_args()
    overview = approved_overview(args.release_id)
    message = payload(overview)
    if not args.send:
        print(json.dumps({"dry_run": True, "release_id": args.release_id,
                          "subject": message["subject"], "recipient": "configured Resend Audience"}, indent=2))
        return
    response = requests.post(
        "https://api.resend.com/broadcasts",
        headers={"Authorization": "Bearer " + os.environ["RESEND_API_KEY"]},
        json={**message, "send": True}, timeout=30,
    )
    response.raise_for_status()
    print(json.dumps(response.json(), indent=2))


if __name__ == "__main__":
    main()
