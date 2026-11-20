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


def main() -> None:
    release_id = current_release_id(os.environ.get(
        "OBSERVATORY_BASE_URL", "https://observatory.hamelberg-ai.com"))
    prepare = reopen_requested() or not approved_for_release(ROOT, release_id)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with Path(output).open("a", encoding="utf-8") as handle:
            handle.write(f"release_id={release_id}\nprepare={str(prepare).lower()}\n")
    if prepare:
        print(f"Weekly review is due for {release_id}.")
    else:
        print(f"Skipping {release_id}: the owner-approved edition is already published.")


if __name__ == "__main__":
    main()
