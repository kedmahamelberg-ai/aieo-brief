#!/usr/bin/env python3
"""Confirm that AIEO Brief can read the Observatory's private evidence views."""
from __future__ import annotations

import json
import os
from typing import Any

import requests
from supabase import create_client

OBSERVATORY = os.environ.get(
    "OBSERVATORY_BASE_URL", "https://observatory.hamelberg-ai.com"
).rstrip("/")


def required_env(name: str) -> str:
    value = str(os.environ.get(name) or "").strip()
    if not value:
        raise SystemExit(f"{name} is missing")
    return value


def current_event_ids() -> tuple[str, list[str]]:
    response = requests.get(f"{OBSERVATORY}/data/releases/current.json", timeout=30)
    response.raise_for_status()
    release = response.json()
    event_ids = [
        str(row.get("effective_event_id") or row.get("event_id") or "").strip()
        for row in release.get("evidence") or []
        if isinstance(row, dict)
    ]
    return str(release.get("release_id") or ""), [value for value in event_ids if value]


def chunks(values: list[str], size: int = 100):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def main() -> int:
    release_id, event_ids = current_event_ids()
    client = create_client(required_env("SUPABASE_URL"), required_env("SUPABASE_SECRET_KEY"))
    evidence_rows: list[dict[str, Any]] = []
    readiness_rows: list[dict[str, Any]] = []
    try:
        for batch in chunks(event_ids):
            evidence_rows.extend(
                client.table("brief_event_source_evidence")
                .select("event_id,article_id,evidence_basis,evidence_at,evidence_ref")
                .in_("event_id", batch)
                .execute()
                .data
                or []
            )
            readiness_rows.extend(
                client.table("brief_event_evidence_readiness")
                .select(
                    "event_id,source_count,full_source_count,source_excerpt_count,"
                    "discovery_snippet_count,headline_only_count,editorial_evidence_level"
                )
                .in_("event_id", batch)
                .execute()
                .data
                or []
            )
    except Exception as exc:
        raise SystemExit(
            "The shared Observatory body-evidence views are unavailable. Apply "
            "supabase/migrations/20260902_observatory_body_evidence_contract.sql "
            f"from the Observatory repository. Original error: {type(exc).__name__}: {exc}"
        ) from exc

    evidence_ids = {str(row.get("event_id") or "") for row in evidence_rows}
    missing = sorted(set(event_ids) - evidence_ids)
    invalid_full = [
        str(row.get("article_id") or "")
        for row in evidence_rows
        if row.get("evidence_basis") == "full_source" and not row.get("evidence_ref")
    ]
    full_source_count = sum(row.get("evidence_basis") == "full_source" for row in evidence_rows)
    report = {
        "schema_version": "aieo_brief_shared_evidence_check_v1",
        "release_id": release_id,
        "expected_events": len(event_ids),
        "events_with_evidence": len(evidence_ids),
        "source_rows": len(evidence_rows),
        "full_source_rows": full_source_count,
        "readiness_rows": len(readiness_rows),
        "body_text_logged": False,
    }
    print(json.dumps(report, indent=2))
    if missing:
        raise SystemExit(f"No private evidence rows for {len(missing)} current events")
    if invalid_full:
        raise SystemExit(f"Full-source rows without a versioned evidence reference: {invalid_full[:5]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
