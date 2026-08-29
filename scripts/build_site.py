#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

import requests
from jinja2 import Environment, FileSystemLoader, select_autoescape

ROOT = Path(__file__).resolve().parents[1]
SITE = ROOT / "_site"
OBS = os.environ.get(
    "OBSERVATORY_BASE_URL",
    "https://observatory.hamelberg-ai.com",
).rstrip("/")

REL = {
    "mutualism": ("People ↑","AI ↑","Both gain","Mutualism","mutualism"),
    "ai_benefiting_parasitism": ("People ↓","AI ↑","AI side gains, people are constrained","AI-benefiting parasitism","ai-benefit"),
    "human_benefiting_parasitism": ("People ↑","AI ↓","People gain, AI side is constrained","Human-benefiting parasitism","human-benefit"),
    "competition": ("People ↓","AI ↓","Both are constrained","Competition or co-constraint","competition"),
    "human_enabling_only": ("People ↑","AI ?","People-side gain only","One-sided human signal","human-only"),
    "human_constraining_only": ("People ↓","AI ?","People-side constraint only","One-sided human signal","human-only"),
    "ai_enabling_only": ("People ?","AI ↑","AI-side gain only","One-sided AI signal","ai-only"),
    "ai_constraining_only": ("People ?","AI ↓","AI-side constraint only","One-sided AI signal","ai-only"),
    "no_clear_relational_signal": ("People ↔","AI ↔","No clear relationship signal","No clear relational signal","unclear"),
    "ambiguous_relational_signal": ("People ?","AI ?","Relationship signal is ambiguous","Ambiguous relational signal","unclear"),
    "insufficient_evidence": ("People ?","AI ?","Evidence is still limited","Insufficient evidence","insufficient"),
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def fetch(url):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def slugify(value):
    return (
        re.sub(r"[^a-z0-9]+", "-", str(value or "").casefold())
        .strip("-")[:76]
        or "development"
    )

def safe_url(value):
    try:
        parsed = urlparse(str(value or ""))
        return str(value) if parsed.scheme in {"http","https"} else "#"
    except Exception:
        return "#"

def fmt(value):
    try:
        return datetime.strptime(str(value or "")[:10], "%Y-%m-%d").strftime("%-d %b %Y")
    except Exception:
        return str(value or "")[:10] or "Date unavailable"

def relmeta(row):
    key = str((row or {}).get("configuration") or "insufficient_evidence")
    people, ai, label, technical, cls = REL.get(key, REL["insufficient_evidence"])
    return {
        "configuration": key,
        "people": people,
        "ai": ai,
        "label": label,
        "technical": technical,
        "class": cls,
        "reviewed": bool((row or {}).get("reviewed")),
    }

def novelty(event):
    value = str(event.get("novelty_status") or "")
    if value == "recurring" or event.get("recurring_in_period"):
        return "Seen before"
    if value == "first_time" or event.get("first_time_in_period"):
        return "New to AIEO"
    if value == "follow_on_development" or event.get("follow_on_development"):
        return "New follow-on"
    return "Novelty under review"

def human_copy(value):
    return {
        "enabling": "People gain capability, access, control, or participation.",
        "constraining": "People face reduced capability, access, control, or participation.",
        "neutral": "No directional human effect is established.",
    }.get(value, "The human-side effect is not established.")

def ai_copy(value):
    return {
        "enabling": "The AI or operator side gains capability, data, reach, resources, or operating freedom.",
        "constraining": "The AI or operator side loses capability, reach, resources, or operating freedom.",
        "neutral": "No directional AI-side effect is established.",
    }.get(value, "The AI-side effect is not established.")

def paragraphs(value):
    return [part.strip() for part in re.split(r"\n\s*\n", str(value or "")) if part.strip()]

def paged(client, table, columns, page_size=500):
    start = 0
    while True:
        rows = (
            client.table(table)
            .select(columns)
            .range(start, start + page_size - 1)
            .execute()
            .data or []
        )
        if not rows:
            break
        yield from rows
        if len(rows) < page_size:
            break
        start += page_size

def dbmaps(mock):
    if mock:
        stories = json.loads((ROOT/"data/mock/stories.json").read_text())
        readiness = json.loads((ROOT/"data/mock/readiness.json").read_text())
        editorial = json.loads((ROOT/"data/mock/editorial.json").read_text())
        return stories, readiness, editorial

    from supabase import create_client
    client = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SECRET_KEY"],
    )
    stories = {
        str(row["event_id"]): row
        for row in paged(
            client,
            "brief_stories",
            "story_id,event_id,slug,status,current_headline,current_deck,current_takeaway",
        )
        if row.get("event_id")
    }
    readiness = {
        str(row["event_id"]): row
        for row in paged(
            client,
            "brief_event_evidence_readiness",
            "event_id,source_count,full_source_count,headline_only_count,editorial_evidence_level",
        )
        if row.get("event_id")
    }

    # Prefer the highest preview/published version for each story.
    editorial_by_story = {}
    rows = list(
        paged(
            client,
            "brief_story_versions",
            "story_version_id,story_id,event_id,version_number,editorial_headline,"
            "editorial_deck,body_markdown,what_happened,why_it_matters,for_humans,"
            "for_ai,relationship_configuration,human_direction,ai_direction,"
            "review_status,publication_status,created_at",
        )
    )
    rows.sort(key=lambda row: int(row.get("version_number") or 0), reverse=True)
    for row in rows:
        if row.get("publication_status") not in {"preview","published"}:
            continue
        sid = str(row.get("story_id"))
        if sid not in editorial_by_story:
            editorial_by_story[sid] = row

    editorial = {}
    for event_id, story in stories.items():
        version = editorial_by_story.get(str(story.get("story_id")))
        if version:
            editorial[event_id] = version

    return stories, readiness, editorial

def inputs(mock):
    if mock:
        return (
            json.loads((ROOT/"data/mock/release.json").read_text()),
            json.loads((ROOT/"data/mock/symbiosis.json").read_text()),
        )
    return (
        fetch(f"{OBS}/data/releases/current.json"),
        fetch(f"{OBS}/data/symbiosis/current.json"),
    )

def cards(release, symbiosis, stories, readiness, editorial):
    relationship_map = {
        str(row.get("event_id")): row
        for row in symbiosis.get("evidence", [])
        if row.get("event_id")
    }
    output = []

    for event in release.get("evidence", []):
        event_id = str(event.get("effective_event_id") or event.get("event_id") or "")
        if not event_id:
            continue

        registry = stories.get(event_id, {})
        evidence_readiness = readiness.get(event_id, {})
        level = str(
            evidence_readiness.get("editorial_evidence_level")
            or "headline_only"
        )
        relationship = relationship_map.get(event_id, {})
        rel = relmeta(relationship)
        title = str(event.get("event_title") or "Untitled AI development").strip()
        summary = str(event.get("event_summary") or "").strip()
        version = editorial.get(event_id)

        if level == "headline_only":
            # Headline-only cases stay conservative even if an old generated version exists.
            version = None

        headline = (
            version.get("editorial_headline")
            if version
            else ("Early signal: " + title if level == "headline_only" else title)
        )
        deck = (
            version.get("editorial_deck")
            if version
            else (
                "AIEO has detected this development, but retained source evidence is still limited."
                if level == "headline_only"
                else summary
            )
        )
        happened = (
            version.get("what_happened")
            if version
            else (
                summary
                or (
                    "AIEO detected this development, but retained source evidence is still limited. Open the source links below."
                    if level == "headline_only"
                    else "AIEO grouped the supporting coverage into one development. Open the source links below."
                )
            )
        )
        why = (
            version.get("why_it_matters")
            if version
            else (
                "AIEO is keeping the interpretation conservative until stronger source evidence is available."
                if level == "headline_only"
                else (
                    str(relationship.get("reasoning") or "").strip()
                    or "The relationship lens separates what changes for people from what changes for the AI or operator side."
                )
            )
        )
        for_humans = (
            version.get("for_humans")
            if version
            else human_copy(str(relationship.get("human_direction") or "unclear"))
        )
        for_ai = (
            version.get("for_ai")
            if version
            else ai_copy(str(relationship.get("ai_direction") or "unclear"))
        )
        body = (
            paragraphs(version.get("body_markdown"))
            if version
            else []
        )

        sources = [
            {
                "publisher": source.get("publisher") or source.get("name") or "Publication",
                "headline": source.get("headline") or "Open source",
                "url": safe_url(source.get("url")),
                "published_date": source.get("published_date") or "",
            }
            for source in (event.get("sources") or [])
        ]

        slug = (
            registry.get("slug")
            or f"{slugify(title)}-{event_id.replace('-','')[:8]}"
        )

        output.append(
            {
                "event_id": event_id,
                "story_id": registry.get("story_id"),
                "slug": slug,
                "url": f"/story/{slug}/",
                "headline": headline,
                "deck": deck,
                "what_happened": happened,
                "why_it_matters": why,
                "for_humans": for_humans,
                "for_ai": for_ai,
                "body_paragraphs": body,
                "event_date": fmt(event.get("event_date")),
                "event_date_raw": str(event.get("event_date") or ""),
                "source_count": int(evidence_readiness.get("source_count") or len(sources)),
                "full_source_count": int(evidence_readiness.get("full_source_count") or 0),
                "evidence_level": level,
                "novelty": novelty(event),
                "sources": sources,
                "relationship": rel,
                "editorial_version": int((version or {}).get("version_number") or 0),
                "has_editorial": bool(version),
            }
        )

    order = {
        "strong_multi_source": 0,
        "mixed_with_full_source": 1,
        "single_full_source": 2,
        "snippet_or_excerpt_only": 3,
        "headline_only": 4,
    }
    output.sort(
        key=lambda item: (
            order.get(item["evidence_level"], 9),
            -item["source_count"],
            item["event_date_raw"],
        )
    )
    return output

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--mock", action="store_true")
    args = parser.parse_args()

    release, symbiosis = inputs(args.mock)
    stories, readiness, editorial = dbmaps(args.mock)
    story_cards = cards(release, symbiosis, stories, readiness, editorial)
    if not story_cards:
        raise SystemExit("No current stories could be built.")

    if SITE.exists():
        shutil.rmtree(SITE)
    SITE.mkdir()
    shutil.copytree(ROOT/"assets", SITE/"assets")

    env = Environment(
        loader=FileSystemLoader(str(ROOT/"templates")),
        autoescape=select_autoescape(["html"]),
    )

    complete = int(
        (symbiosis.get("event") or {}).get("complete_configuration_count")
        or 0
    )
    configuration_counts = (
        (symbiosis.get("event") or {}).get("configuration_counts")
        or {}
    )
    ticker = []
    for key in [
        "mutualism",
        "ai_benefiting_parasitism",
        "human_benefiting_parasitism",
        "competition",
    ]:
        item = relmeta({"configuration": key, "reviewed": True})
        item["key"] = key
        item["count"] = int(configuration_counts.get(key) or 0)
        item["share"] = round(item["count"] / complete * 100) if complete else 0
        ticker.append(item)

    lead = next(
        (
            card
            for card in story_cards
            if card["evidence_level"] != "headline_only" and card["has_editorial"]
        ),
        next(
            (
                card
                for card in story_cards
                if card["evidence_level"] != "headline_only"
            ),
            story_cards[0],
        ),
    )
    rest = [
        card for card in story_cards
        if card["event_id"] != lead["event_id"]
    ]

    by_relationship = {}
    for card in story_cards:
        by_relationship.setdefault(
            card["relationship"]["configuration"], []
        ).append(card)

    context = {
        "release": release,
        "symbiosis": symbiosis,
        "cards": story_cards,
        "lead": lead,
        "main_cards": rest,
        "ticker": ticker,
        "by_relationship": by_relationship,
        "generated_at": utc_now(),
    }

    (SITE/"index.html").write_text(
        env.get_template("index.html").render(**context),
        encoding="utf-8",
    )

    story_template = env.get_template("story.html")
    for card in story_cards:
        path = SITE/"story"/card["slug"]
        path.mkdir(parents=True)
        (path/"index.html").write_text(
            story_template.render(
                story=card,
                release=release,
                generated_at=utc_now(),
            ),
            encoding="utf-8",
        )

    data = SITE/"data"
    data.mkdir()
    public_payload = {
        "schema_version": "aieo_brief_public_v2a1",
        "release_id": release.get("release_id"),
        "period_start": release.get("period_start"),
        "period_end": release.get("period_end"),
        "generated_at": utc_now(),
        "story_count": len(story_cards),
        "stories": [
            {
                "event_id": card["event_id"],
                "slug": card["slug"],
                "headline": card["headline"],
                "deck": card["deck"],
                "relationship": card["relationship"],
                "evidence_level": card["evidence_level"],
                "source_count": card["source_count"],
                "full_source_count": card["full_source_count"],
                "novelty": card["novelty"],
                "editorial_version": card["editorial_version"],
            }
            for card in story_cards
        ],
    }
    (data/"current.json").write_text(
        json.dumps(public_payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    summary = {
        "release_id": release.get("release_id"),
        "stories_built": len(story_cards),
        "editorial_versions_used": sum(card["has_editorial"] for card in story_cards),
        "with_full_source": sum(card["full_source_count"] > 0 for card in story_cards),
        "headline_only": sum(card["evidence_level"] == "headline_only" for card in story_cards),
    }
    print(json.dumps(summary, indent=2))

    step_summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if step_summary:
        with open(step_summary, "a", encoding="utf-8") as handle:
            handle.write("## AIEO Brief Phase 2A.1 preview\n\n")
            handle.write(f"- Release: **{summary['release_id']}**\n")
            handle.write(f"- Stories built: **{summary['stories_built']}**\n")
            handle.write(f"- Editorial versions used: **{summary['editorial_versions_used']}**\n")
            handle.write(f"- Stories with full-source support: **{summary['with_full_source']}**\n")
            handle.write(f"- Headline-only early signals: **{summary['headline_only']}**\n")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
