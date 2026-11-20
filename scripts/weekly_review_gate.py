#!/usr/bin/env python3
"""Skip automatic weekly review work for an edition already approved by its owner."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
RELEASE_ID = re.compile(r"202\d-W\d{2}\Z")
REPOSITORY = "kedmahamelberg-ai/aieo-brief"
ACTIVE_RUN_STATUSES = ("waiting", "in_progress", "queued")


def approved_for_release(root: Path, release_id: str) -> bool:
    if not RELEASE_ID.fullmatch(release_id):
        raise ValueError("Invalid weekly release ID")
    path = root / "data/weekly-overviews/approved" / f"{release_id}.json"
    if not path.exists():
        return False
    approved = json.loads(path.read_text(encoding="utf-8"))
    if (approved.get("release_id") != release_id
            or not approved.get("human_approved_at")
            or any(approved.get(kind, {}).get("status") != "ready"
                   or approved[kind].get("human_approved") is not True
                   for kind in ("markets", "research"))):
        raise ValueError(f"Invalid owner approval for {release_id}")
    return True


def current_release_id(base_url: str) -> str:
    if not base_url.startswith("https://"):
        raise ValueError("Observatory URL must use HTTPS")
    request = Request(base_url.rstrip("/") + "/data/brief/current.json",
                      headers={"Accept": "application/json", "User-Agent": "AIEO-Brief-Weekly-Review/1.0"})
    with urlopen(request, timeout=25) as response:
        export = json.load(response)
    release_id = export.get("release_id")
    if (not isinstance(release_id, str) or not RELEASE_ID.fullmatch(release_id)
            or export.get("release", {}).get("release_id") != release_id):
        raise ValueError("Observatory current release identity is invalid")
    return release_id


def reopen_requested() -> bool:
    value = os.environ.get("REOPEN_APPROVED", "false").lower()
    if value not in ("true", "false"):
        raise ValueError("Invalid weekly re-review input")
    return value == "true"


def github_json(path: str, token: str) -> dict:
    request = Request("https://api.github.com/repos/" + REPOSITORY + path,
                      headers={"Accept": "application/vnd.github+json",
                               "X-GitHub-Api-Version": "2022-11-28",
                               "Authorization": "Bearer " + token,
                               "User-Agent": "AIEO-Brief-Weekly-Review/1.0"})
    with urlopen(request, timeout=25) as response:
        value = json.load(response)
    if not isinstance(value, dict):
        raise ValueError("GitHub weekly review response is invalid")
    return value


def active_review_exists(release_id: str, current_run_id: str, token: str) -> bool:
    """Find an unfinished draft for this exact week before starting another."""
    if (not RELEASE_ID.fullmatch(release_id) or not current_run_id.isdigit()
            or not token):
        raise ValueError("Weekly review run identity or GitHub token is missing")
    for status in ACTIVE_RUN_STATUSES:
        runs = github_json(
            f"/actions/workflows/prepare-weekly-review.yml/runs?status={status}&per_page=100",
            token,
        )
        rows = runs.get("workflow_runs")
        if (not isinstance(rows, list) or not isinstance(runs.get("total_count"), int)
                or runs["total_count"] > len(rows)):
            raise ValueError("GitHub did not return the complete active weekly review list")
        for run in rows:
            run_id = run.get("id")
            if (not isinstance(run_id, int) or run.get("status") != status
                    or str(run_id) == current_run_id):
                continue
            artifacts = github_json(f"/actions/runs/{run_id}/artifacts?per_page=100", token)
            matches = artifacts.get("artifacts")
            if (not isinstance(matches, list) or not isinstance(artifacts.get("total_count"), int)
                    or artifacts["total_count"] > len(matches)):
                raise ValueError("GitHub did not return the complete weekly review artifacts")
            if any(artifact.get("name") == f"weekly-review-{release_id}-{run_id}"
                   and artifact.get("expired") is False for artifact in matches):
                return True
    return False


def main() -> None:
    release_id = current_release_id(os.environ.get(
        "OBSERVATORY_BASE_URL", "https://observatory.hamelberg-ai.com"))
    already_approved = approved_for_release(ROOT, release_id)
    if already_approved and not reopen_requested():
        prepare = False
        reason = "the owner-approved edition is already published"
    elif active_review_exists(release_id, os.environ.get("GITHUB_RUN_ID", ""),
                              os.environ.get("GITHUB_TOKEN", "")):
        prepare = False
        reason = "a review draft for this edition is already awaiting completion"
    else:
        prepare = True
        reason = ""
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"release_id={release_id}\nprepare={str(prepare).lower()}\n")
    if prepare:
        print(f"Weekly review is due for {release_id}.")
    else:
        print(f"Skipping {release_id}: {reason}.")


if __name__ == "__main__":
    main()
