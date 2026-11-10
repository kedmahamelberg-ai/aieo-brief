#!/usr/bin/env python3
"""Publish generated Brief data while preserving concurrent main updates."""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path

FILES = (
    "data/editorial/retry-state.json",
    "data/editorial/status.json",
    "data/research/public.json",
    "data/research/collection-status.json",
    "data/research/generation-status.json",
    "data/research/retry-state.json",
)
ABSENT = object()
EDITORIAL_FIELDS = {
    "has_editorial", "headline", "deck", "what_happened", "why_it_matters",
    "body_paragraphs", "limitation", "claim_status", "summary_status",
    "summary_basis", "prompt_version", "model_revision", "reading_minutes",
    "editorial_engine_version", "research_reading_version", "pdf_reader_version", "html_reader_version",
    "evidence_scope", "full_text_status", "full_text_retry_after",
    "paper_pages", "paper_sections", "paper_source_url", "paper_text_sha256", "pdf_url",
    "paper_pmcid", "paper_doi", "pmc_reader_version",
}


def git(*args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    return subprocess.run(("git", *args), text=True, capture_output=True, check=check)


def from_git(ref: str, path: str):
    result = git("show", f"{ref}:{path}", check=False)
    return json.loads(result.stdout) if result.returncode == 0 else ABSENT


def changed(new, old) -> bool:
    return new != old


def engine_number(record: dict) -> int:
    match = re.search(r"-v(\d+)", str(record.get("editorial_engine_version", "")))
    return int(match.group(1)) if match else 0


def merge_paper(base, local, remote):
    if local is ABSENT or not changed(local, base):
        return remote
    if remote is ABSENT or not changed(remote, base):
        return local
    if local.get("metadata_sha256") != remote.get("metadata_sha256"):
        # A summary about superseded source evidence must not replace current data.
        return remote
    if remote.get("has_editorial") and not local.get("has_editorial"):
        return remote
    use_local_editorial = not remote.get("has_editorial") or engine_number(local) >= engine_number(remote)
    merged = {}
    for field in set(base if isinstance(base, dict) else ()) | set(local) | set(remote):
        old = base.get(field, ABSENT) if isinstance(base, dict) else ABSENT
        ours = local.get(field, ABSENT)
        theirs = remote.get(field, ABSENT)
        if ours == old:
            value = theirs
        elif theirs == old or ours == theirs:
            value = ours
        elif field in EDITORIAL_FIELDS and use_local_editorial:
            value = ours
        else:
            value = theirs
        if value is not ABSENT:
            merged[field] = value
    return merged


def merge_records(base, local, remote, field: str):
    old = {item["key"]: item for item in base.get(field, [])} if isinstance(base, dict) else {}
    ours = {item["key"]: item for item in local.get(field, [])}
    theirs = {item["key"]: item for item in remote.get(field, [])}
    result = dict(theirs)
    for key, item in ours.items():
        merged = merge_paper(old.get(key, ABSENT), item, theirs.get(key, ABSENT))
        if merged is not ABSENT:
            result[key] = merged
    return sorted(result.values(), key=lambda item: (item.get("date", ""), item["key"]), reverse=True)


def reconcile(path: str, base, local, remote):
    if local is ABSENT or local == base:
        return remote
    if remote is ABSENT or remote == base:
        return local
    if path == "data/research/public.json":
        result = dict(remote)
        result["papers"] = merge_records(base, local, remote, "papers")
        result["generated_at"] = local.get("generated_at", remote.get("generated_at"))
        return result
    if path.endswith("retry-state.json") and isinstance(local, dict) and isinstance(remote, dict):
        result = dict(remote)
        old = base if isinstance(base, dict) else {}
        for key in set(old) | set(local):
            if local.get(key, ABSENT) != old.get(key, ABSENT):
                if key not in local:
                    # A completed item should clear its retry marker.
                    result.pop(key, None)
                elif key not in remote or remote.get(key) == old.get(key):
                    result[key] = local[key]
                else:
                    result[key] = max((local[key], remote[key]), key=lambda x: (x.get("attempts", 0), x.get("last_attempt", "")))
        return result
    # Status files describe this run and have no accumulated article records.
    return local


def main():
    base = {path: from_git("HEAD", path) for path in FILES}
    local = {path: json.loads(Path(path).read_text()) if Path(path).exists() else ABSENT for path in FILES}
    if all(local[path] == base[path] for path in FILES):
        print("No generated data changes to publish")
        return
    git("config", "user.name", "github-actions[bot]")
    git("config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com")
    for attempt in range(4):
        git("fetch", "origin", "main")
        remote = {path: from_git("origin/main", path) for path in FILES}
        merged = {path: reconcile(path, base[path], local[path], remote[path]) for path in FILES}
        git("reset", "--hard", "origin/main")
        for path, data in merged.items():
            if data is ABSENT:
                continue
            destination = Path(path)
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
            git("add", path)
        if git("diff", "--cached", "--quiet", check=False).returncode == 0:
            print("Generated data already present on main")
            return
        git("commit", "-m", "Update Brief source summaries and progress")
        pushed = git("push", "origin", "HEAD:main", check=False)
        if pushed.returncode == 0:
            print("Published generated data on main")
            return
        if "non-fast-forward" not in pushed.stderr and "fetch first" not in pushed.stderr:
            raise RuntimeError("Generated-data push rejected: " + pushed.stderr[-1000:])
        print(f"Main moved during generated-data push; reconciling again ({attempt + 1}/4)")
        time.sleep(1)
    raise RuntimeError("Main changed four times during generated-data push")


if __name__ == "__main__":
    main()
