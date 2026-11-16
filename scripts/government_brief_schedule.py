"""Decide whether the daily government import is due in Europe/Amsterdam."""
from __future__ import annotations
import argparse
import json
import os
from datetime import datetime, time
from pathlib import Path
from zoneinfo import ZoneInfo

AMSTERDAM = ZoneInfo("Europe/Amsterdam")

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

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--state", type=Path, default=Path("data/governments/public.json"))
    parser.add_argument("--force", action="store_true", help="Recheck a corrected Monitor feed after today's import")
    args = parser.parse_args()
    state = json.loads(args.state.read_text()) if args.state.exists() else {}
    due = args.force or is_due(state, datetime.now(AMSTERDAM))
    print("Daily government import " + ("is due" if due else "is not due or already checked"))
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            output.write("due=" + str(due).lower() + "\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
