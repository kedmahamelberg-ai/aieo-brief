"""Decide whether the daily government import is due in Europe/Amsterdam."""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo
from government_briefs import FEED, candidate, fingerprint

AMSTERDAM = ZoneInfo("Europe/Amsterdam")
MAX_SNAPSHOT_BYTES = 25_000_000


def feed_has_changes(state, snapshot):
    """Check exact Monitor eligibility and input hashes without a second AI judgment."""
    if not isinstance(snapshot, dict) or not isinstance(snapshot.get("items"), list) or not snapshot.get("as_of"):
        raise ValueError("Monitor government snapshot is invalid")
    checked = state.get("checked") or {}
    records = state.get("records") or {}
    seen = set()
    for item in snapshot["items"]:
        ident = str(item.get("id") or "")
        if not ident or ident in seen:
            continue
        seen.add(ident)
        if candidate(item):
            if checked.get(ident) != fingerprint(item):
                return True
        elif ident in records or ident in checked:
            return True
    return False


def changed_live_feed(state):
    request = Request(FEED, headers={"Cache-Control": "no-cache", "User-Agent": "AIEO-Brief-daily-government-sync/1.0"})
    with urlopen(request, timeout=45) as response:
        payload = response.read(MAX_SNAPSHOT_BYTES + 1)
    if len(payload) > MAX_SNAPSHOT_BYTES:
        raise ValueError("Monitor government snapshot exceeds 25 MB")
    return feed_has_changes(state, json.loads(payload))

def is_due(state, now):
    local = now.astimezone(AMSTERDAM)
    due_at = datetime.combine(local.date(), time(16, 5), AMSTERDAM)
    if local < due_at:
        return False
    # A changed import policy needs one catch-up even after an earlier same-day check.
    if state.get("policy") != "government-ai-brief-v4":
        return True
    checked = state.get("last_checked_at")
    if not checked:
        return True
    checked_at = datetime.fromisoformat(checked.replace("Z", "+00:00"))
    if checked_at.tzinfo is None:
        raise ValueError("last_checked_at must include a timezone")
    return checked_at.astimezone(AMSTERDAM) < due_at


def import_due(state, now, check_feed=False):
    if is_due(state, now):
        return True
    return check_feed and changed_live_feed(state)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("data/governments/public.json"))
    parser.add_argument("--force", action="store_true", help="Recheck a corrected Monitor feed after today's import")
    parser.add_argument("--check-feed", action="store_true", help="Import later same-day Monitor corrections on scheduled wake-ups")
    args = parser.parse_args()
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    # A late Monitor collection can add yesterday's eligible records after the
    # preceding daily import. Check exact fingerprints on every wake-up; the
    # 16:05 daily check remains independently due.
    due = args.force or import_due(state, datetime.now(AMSTERDAM), args.check_feed)
    print("Daily government import " + ("is due" if due else "is not due or already checked"))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("due=" + str(due).lower() + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
