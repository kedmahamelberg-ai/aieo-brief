#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import time
import uuid
from datetime import datetime, timezone

import requests
from supabase import create_client

OBSERVATORY = os.environ.get(
    "OBSERVATORY_BASE_URL",
    "https://observatory.hamelberg-ai.com",
).rstrip("/")
MODEL = os.environ.get("BRIEF_EDITORIAL_MODEL", "Qwen3-4B-Q4_K_M")
MODEL_REVISION = os.environ.get("BRIEF_EDITORIAL_MODEL_REVISION", "ggml-org/Qwen3-4B-GGUF:Q4_K_M")
LLM_BASE_URL = os.environ.get("BRIEF_LOCAL_LLM_URL", "http://127.0.0.1:8080").rstrip("/")
LLAMA_CPP_VERSION = os.environ.get("BRIEF_LLAMA_CPP_VERSION", "b10516")
PROMPT_VERSION = "aieo-brief-editorial-local-v2a3-quality"
MAX_SOURCE_CHARS = 5200
MAX_TOTAL_EVIDENCE_CHARS = 14000
MAX_GENERATION_ATTEMPTS = 4

ELIGIBLE_LEVELS = {
    "strong_multi_source",
    "mixed_with_full_source",
    "single_full_source",
}

RELATIONSHIP_LABELS = {
    "mutualism": "Both gain",
    "ai_benefiting_parasitism": "AI side gains, people are constrained",
    "human_benefiting_parasitism": "People gain, AI side is constrained",
    "competition": "Both are constrained",
    "human_enabling_only": "People-side gain only",
    "human_constraining_only": "People-side constraint only",
    "ai_enabling_only": "AI-side gain only",
    "ai_constraining_only": "AI-side constraint only",
    "no_clear_relational_signal": "No clear relationship signal",
    "ambiguous_relational_signal": "Relationship signal is ambiguous",
    "insufficient_evidence": "Evidence is still limited",
}

def utc_now():
    return datetime.now(timezone.utc).isoformat()

def sha256(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()

def fetch_json(url: str):
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.json()

def normalize(value) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()

def sanitise(value: str) -> str:
    # Keep public prose free of em dashes and accidental markdown headings.
    text = str(value or "").replace("—", ",").replace("–", "-")
    text = re.sub(r"^\s*#+\s*", "", text, flags=re.MULTILINE)
    return text.strip()

def parse_json_output(text: str) -> dict:
    raw = str(text or "").strip()
    raw = re.sub(r"^```(?:json)?\s*", "", raw, flags=re.I)
    raw = re.sub(r"\s*```$", "", raw)
    start, end = raw.find("{"), raw.rfind("}")
    if start < 0 or end < start:
        raise ValueError("Model did not return a JSON object.")
    return json.loads(raw[start:end+1])

def paged(client, table, columns, page_size=500):
    start = 0
    while True:
        response = client.table(table).select(columns).range(start, start + page_size - 1).execute()
        rows = response.data or []
        if not rows:
            break
        yield from rows
        if len(rows) < page_size:
            break
        start += page_size

def current_inputs():
    return (
        fetch_json(f"{OBSERVATORY}/data/releases/current.json"),
        fetch_json(f"{OBSERVATORY}/data/symbiosis/current.json"),
    )

def current_maps(client, event_ids):
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
            "event_id,source_count,full_source_count,source_excerpt_count,"
            "discovery_snippet_count,headline_only_count,editorial_evidence_level",
        )
        if row.get("event_id")
    }

    evidence = {eid: [] for eid in event_ids}
    event_id_list = list(event_ids)
    for i in range(0, len(event_id_list), 25):
        batch = event_id_list[i:i+25]
        rows = (
            client.table("brief_event_source_evidence")
            .select(
                "event_id,event_title,event_summary,event_date,article_id,is_canonical_source,"
                "source_headline,publisher,source_url,published_at,evidence_basis,evidence_text,"
                "evidence_at,evidence_ref,extraction_quality"
            )
            .in_("event_id", batch)
            .execute()
            .data or []
        )
        for row in rows:
            evidence.setdefault(str(row["event_id"]), []).append(row)

    latest_versions = {}
    for i in range(0, len(list(stories.values())), 25):
        batch_story_ids = [str(row["story_id"]) for row in list(stories.values())[i:i+25]]
        if not batch_story_ids:
            continue
        rows = (
            client.table("brief_story_versions")
            .select(
                "story_version_id,story_id,event_id,version_number,review_status,"
                "publication_status,evidence_basis_summary,created_at"
            )
            .in_("story_id", batch_story_ids)
            .order("version_number", desc=True)
            .execute()
            .data or []
        )
        for row in rows:
            sid = str(row["story_id"])
            if sid not in latest_versions:
                latest_versions[sid] = row

    return stories, readiness, evidence, latest_versions

def symbiosis_map(symbiosis):
    return {
        str(row.get("event_id")): row
        for row in (symbiosis.get("evidence") or [])
        if row.get("event_id")
    }

def source_payload(rows):
    # Prefer retained full source evidence. Supporting headlines stay visible as context.
    full = [r for r in rows if r.get("evidence_basis") == "full_source" and r.get("evidence_text")]
    others = [r for r in rows if r not in full]
    selected = full[:3] + others[:5]
    payload = []
    remaining = MAX_TOTAL_EVIDENCE_CHARS
    for index, row in enumerate(selected, start=1):
        evidence = normalize(row.get("evidence_text"))
        if not evidence:
            evidence = normalize(row.get("source_headline"))
        evidence = evidence[: min(MAX_SOURCE_CHARS, remaining)]
        remaining -= len(evidence)
        payload.append({
            "source_number": index,
            "publisher": normalize(row.get("publisher")) or "Unknown publication",
            "headline": normalize(row.get("source_headline")),
            "published_at": str(row.get("published_at") or ""),
            "evidence_basis": row.get("evidence_basis") or "headline_only",
            "evidence": evidence,
            "evidence_ref": row.get("evidence_ref"),
        })
        if remaining <= 300:
            break
    return payload

def input_fingerprint(event, relationship, readiness, sources) -> str:
    stable = {
        "event_id": event.get("event_id"),
        "event_title": event.get("event_title"),
        "event_summary": event.get("event_summary"),
        "relationship": {
            "configuration": relationship.get("configuration"),
            "human_direction": relationship.get("human_direction"),
            "ai_direction": relationship.get("ai_direction"),
            "reasoning": relationship.get("reasoning"),
            "evidence_summary": relationship.get("evidence_summary"),
        },
        "readiness": readiness,
        "sources": [
            {
                "publisher": s["publisher"],
                "headline": s["headline"],
                "evidence_basis": s["evidence_basis"],
                "evidence_hash": sha256(s["evidence"]),
            }
            for s in sources
        ],
        "prompt_version": PROMPT_VERSION,
    }
    return sha256(json.dumps(stable, ensure_ascii=False, sort_keys=True))

def event_kind_hint(event: dict) -> str:
    title = normalize(event.get("event_title")).casefold()
    if title.startswith("opinion:") or title.startswith("commentary:"):
        return "opinion"
    if title.startswith("prediction:") or title.startswith("forecast:"):
        return "prediction"
    if title.startswith("analysis:"):
        return "analysis"
    if (
        title.startswith("study:")
        or title.startswith("research:")
        or " new study " in f" {title} "
        or title.startswith("new study ")
    ):
        return "research"
    return "news"


def shared_ten_word_phrase(output_text: str, source_texts: list[str]) -> str | None:
    output_words = re.findall(r"\b[\w'-]+\b", output_text.casefold())
    if len(output_words) < 10:
        return None
    source_blobs = [
        " ".join(re.findall(r"\b[\w'-]+\b", text.casefold()))
        for text in source_texts
    ]
    for i in range(len(output_words) - 9):
        phrase = " ".join(output_words[i:i+10])
        if any(phrase and phrase in blob for blob in source_blobs):
            return phrase
    return None

def validate_output(data: dict, relationship: dict, source_texts: list[str], event_kind: str):
    required = [
        "editorial_headline",
        "editorial_deck",
        "what_happened",
        "why_it_matters",
        "for_humans",
        "for_ai",
        "body_paragraphs",
    ]
    for key in required:
        if key not in data:
            raise ValueError(f"Missing editorial field: {key}")

    cleaned = {}
    for key in required[:-1]:
        cleaned[key] = sanitise(data[key])
        if not cleaned[key]:
            raise ValueError(f"Empty editorial field: {key}")

    paragraphs = data["body_paragraphs"]
    if not isinstance(paragraphs, list) or not 1 <= len(paragraphs) <= 4:
        raise ValueError("body_paragraphs must contain 1 to 4 paragraphs.")
    cleaned["body_paragraphs"] = [sanitise(p) for p in paragraphs if sanitise(p)]

    if len(cleaned["editorial_headline"]) > 130:
        raise ValueError("Headline is too long.")
    if len(cleaned["what_happened"]) > 900:
        raise ValueError("What happened is too long.")
    if len(cleaned["why_it_matters"]) > 650:
        raise ValueError("Why it matters is too long.")

    headline_lower = cleaned["editorial_headline"].casefold()
    if event_kind == "opinion" and not headline_lower.startswith("opinion:"):
        raise ValueError(
            "This development is opinion/commentary. The editorial headline must begin with 'Opinion:' so commentary is not presented as established fact."
        )
    if event_kind == "prediction" and not headline_lower.startswith("prediction:"):
        raise ValueError(
            "This development is a prediction/forecast. The editorial headline must begin with 'Prediction:' so a forecast is not presented as an established outcome."
        )
    if event_kind == "analysis" and not (
        headline_lower.startswith("analysis:")
        or "analysis" in cleaned["editorial_deck"].casefold()
    ):
        raise ValueError(
            "This development is analysis. Label it as analysis in the headline or deck."
        )

    combined = " ".join(
        [
            cleaned["editorial_headline"],
            cleaned["editorial_deck"],
            cleaned["what_happened"],
            cleaned["why_it_matters"],
            cleaned["for_humans"],
            cleaned["for_ai"],
            *cleaned["body_paragraphs"],
        ]
    )
    if "—" in combined:
        raise ValueError("Public copy contains an em dash.")
    phrase = shared_ten_word_phrase(combined, source_texts)
    if phrase:
        raise ValueError(f"Output copied a 10-word source phrase: {phrase}")

    # Relationship directions are fixed by the reviewed AIEO artifact.
    cleaned["relationship_configuration"] = relationship.get("configuration")
    cleaned["human_direction"] = relationship.get("human_direction")
    cleaned["ai_direction"] = relationship.get("ai_direction")
    return cleaned

def prompt_for(event, relationship, readiness, sources, retry_note=""):
    fixed_label = RELATIONSHIP_LABELS.get(
        str(relationship.get("configuration") or ""),
        relationship.get("plain_label") or "Evidence is still limited",
    )
    source_blocks = []
    for source in sources:
        source_blocks.append(
            "\n".join(
                [
                    f"SOURCE {source['source_number']}",
                    f"Publisher: {source['publisher']}",
                    f"Source headline: {source['headline']}",
                    f"Evidence basis: {source['evidence_basis']}",
                    f"Evidence:\n{source['evidence']}",
                ]
            )
        )

    return f"""
You are the evidence-bounded editorial writer for AIEO Brief. /no_think

AIEO Brief turns fragmented AI coverage into one living development. Write for an intelligent general reader who wants clarity quickly. The public interface is deliberately easy to scan and uses progressive disclosure.

NON-NEGOTIABLE RULES
1. Use only the evidence supplied below. Do not use outside facts.
2. Do not change, reinterpret, or strengthen the fixed reviewed AIEO relationship classification.
3. Do not invent causality, motives, numbers, dates, people, countries, or consequences.
4. Paraphrase. Do not reproduce any phrase of 10 or more consecutive words from a source.
5. Do not use an em dash.
6. Avoid jargon, hype, clickbait, rhetorical questions, and generic phrases such as "in today's rapidly evolving landscape".
7. The headline must state the substantive development or key finding, not merely repeat a publisher headline.
8. Write in English.
9. Keep the distinction between people and the AI or operator side explicit.
10. If the evidence does not support a detail, leave it out.

STYLE
- Headline: 8 to 18 words, concrete and easy to understand.
- Deck: 1 sentence, maximum about 35 words.
- What happened: 2 or 3 short sentences.
- Why it matters: 1 or 2 short sentences.
- For humans: 1 short sentence.
- For AI: 1 short sentence.
- Body: 2 concise paragraphs. Add a third only if genuinely necessary.
- Short paragraphs. One idea per paragraph.
- The first screen should make sense without opening anything else.

FIXED AIEO RELATIONSHIP
Configuration: {relationship.get('configuration')}
Plain-language label: {fixed_label}
Human direction: {relationship.get('human_direction')}
AI direction: {relationship.get('ai_direction')}
Reviewed evidence summary: {relationship.get('evidence_summary') or ''}
Reviewed reasoning: {relationship.get('reasoning') or ''}

SOURCE GENRE / CLAIM STATUS
Event kind hint: {event_kind_hint(event)}
If the event kind is opinion, the headline must begin "Opinion:" and describe what the author/commentator argues rather than presenting the argument as established fact.
If the event kind is prediction, the headline must begin "Prediction:" and describe the forecast rather than presenting it as an achieved outcome.
If the event kind is analysis, make that analytical status clear in the headline or deck.

EVENT
AIEO resolved title: {event.get('event_title') or ''}
AIEO event summary: {event.get('event_summary') or ''}
Event date: {event.get('event_date') or ''}
Editorial evidence level: {readiness.get('editorial_evidence_level')}
Full-source count: {readiness.get('full_source_count')}
Total source count: {readiness.get('source_count')}

SOURCE EVIDENCE
{chr(10).join(source_blocks)}

{retry_note}

Return ONLY valid JSON with this exact structure:
{{
  "editorial_headline": "...",
  "editorial_deck": "...",
  "what_happened": "...",
  "why_it_matters": "...",
  "for_humans": "...",
  "for_ai": "...",
  "body_paragraphs": ["...", "..."]
}}
""".strip()

def local_completion(prompt: str, attempt: int = 0) -> str:
    response = requests.post(
        f"{LLM_BASE_URL}/v1/chat/completions",
        json={
            "model": "aieo-editorial",
            "messages": [
                {"role": "user", "content": prompt},
            ],
            # Slightly more variation on retries helps the local model escape
            # a source phrase it reproduced in the previous draft.
            "temperature": min(0.42, 0.20 + (attempt * 0.07)),
            "top_p": 0.88,
            "max_tokens": 1100,
            "seed": 42 + attempt,
        },
        timeout=900,
    )
    response.raise_for_status()
    payload = response.json()
    choices = payload.get("choices") or []
    if not choices:
        raise RuntimeError("Local model returned no choices.")
    content = (choices[0].get("message") or {}).get("content")
    if not content:
        raise RuntimeError("Local model returned an empty response.")
    return str(content)


def retry_instruction(exc: Exception) -> str:
    message = str(exc)
    copied = re.search(
        r"Output copied a 10-word source phrase:\\s*(.+)$",
        message,
        flags=re.I,
    )
    if copied:
        phrase = copied.group(1).strip()
        return (
            "\\nREVISION REQUIRED\\n"
            "The draft reproduced source wording too closely. Rewrite from scratch. "
            "Preserve factual quantities only when needed, but change the grammar, "
            "word order, and sentence structure. The exact sequence below is banned "
            "from every output field, and no other 10-word source sequence may appear.\\n"
            f"BANNED EXACT PHRASE: {phrase}\\n"
            "/no_think"
        )

    return (
        "\\nREVISION REQUIRED\\n"
        f"The previous draft failed validation: {message}. "
        "Rewrite from scratch and obey every rule. /no_think"
    )


def generate_one(event, relationship, readiness, sources):
    prompt = prompt_for(event, relationship, readiness, sources)
    source_texts = [s["evidence"] for s in sources if s.get("evidence")]
    event_kind = event_kind_hint(event)

    last_error = None
    errors = []
    for attempt in range(MAX_GENERATION_ATTEMPTS):
        raw_output = local_completion(prompt, attempt=attempt)
        try:
            data = parse_json_output(raw_output)
            return (
                validate_output(
                    data,
                    relationship,
                    source_texts,
                    event_kind,
                ),
                raw_output,
            )
        except Exception as exc:
            last_error = exc
            errors.append(str(exc))
            prompt = prompt_for(
                event,
                relationship,
                readiness,
                sources,
                retry_note=retry_instruction(exc),
            )

    raise RuntimeError(
        "Editorial output failed validation after "
        f"{MAX_GENERATION_ATTEMPTS} attempts: {last_error}"
    )

def existing_same_input(latest_version, fingerprint):
    if not latest_version:
        return False
    summary = latest_version.get("evidence_basis_summary")
    return isinstance(summary, dict) and summary.get("input_fingerprint") == fingerprint

def valid_uuid(value):
    try:
        return str(uuid.UUID(str(value)))
    except Exception:
        return None

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=5, help="0 means all eligible current stories")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--max-runtime-minutes", type=int, default=105)
    parser.add_argument(
        "--strict",
        action="store_true",
        help="Fail the whole workflow if any selected story fails. Default is resilient batch mode.",
    )
    args = parser.parse_args()

    supabase = create_client(os.environ["SUPABASE_URL"], os.environ["SUPABASE_SECRET_KEY"])
    if not args.dry_run:
        health = requests.get(f"{LLM_BASE_URL}/health", timeout=30)
        health.raise_for_status()

    started_at = time.monotonic()

    release, symbiosis = current_inputs()
    current_events = {
        str(row.get("effective_event_id") or row.get("event_id")): row
        for row in (release.get("evidence") or [])
        if row.get("effective_event_id") or row.get("event_id")
    }
    relationship_map = symbiosis_map(symbiosis)
    stories, readiness_map, evidence_map, latest_versions = current_maps(
        supabase,
        current_events.keys(),
    )

    failed_items = []

    counters = {
        "eligible": 0,
        "generated": 0,
        "skipped_headline_only": 0,
        "skipped_no_story_registry": 0,
        "skipped_missing_reviewed_relationship": 0,
        "skipped_unchanged": 0,
        "failed": 0,
    }

    eligible = []
    for event_id, event in current_events.items():
        readiness = readiness_map.get(event_id) or {}
        if readiness.get("editorial_evidence_level") not in ELIGIBLE_LEVELS:
            counters["skipped_headline_only"] += 1
            continue
        story = stories.get(event_id)
        if not story:
            counters["skipped_no_story_registry"] += 1
            continue
        relationship = relationship_map.get(event_id)
        if not relationship or not relationship.get("reviewed"):
            counters["skipped_missing_reviewed_relationship"] += 1
            continue

        sources = source_payload(evidence_map.get(event_id) or [])
        if not any(s.get("evidence_basis") == "full_source" for s in sources):
            counters["skipped_headline_only"] += 1
            continue

        fingerprint = input_fingerprint(event, relationship, readiness, sources)
        latest = latest_versions.get(str(story["story_id"]))
        if not args.force and existing_same_input(latest, fingerprint):
            counters["skipped_unchanged"] += 1
            continue

        eligible.append((event_id, event, story, relationship, readiness, sources, fingerprint, latest))

    counters["eligible"] = len(eligible)
    if args.limit:
        eligible = eligible[:args.limit]

    print(
        json.dumps(
            {
                "model": MODEL,
                "model_revision": MODEL_REVISION,
                "llama_cpp_version": LLAMA_CPP_VERSION,
                "prompt_version": PROMPT_VERSION,
                "eligible_before_limit": counters["eligible"],
                "selected_for_run": len(eligible),
                "dry_run": args.dry_run,
            },
            indent=2,
        )
    )

    for index, item in enumerate(eligible, start=1):
        event_id, event, story, relationship, readiness, sources, fingerprint, latest = item
        print(f"[{index}/{len(eligible)}] {event_id} {event.get('event_title')}", flush=True)

        if args.dry_run:
            print(
                f"  would generate with {readiness.get('editorial_evidence_level')} "
                f"and {len(sources)} evidence source(s)",
                flush=True,
            )
            continue

        try:
            if (time.monotonic() - started_at) / 60 >= args.max_runtime_minutes:
                print("Soft stop before workflow timeout; rerun with the same settings to continue.", flush=True)
                break
            output, raw_output = generate_one(
                event,
                relationship,
                readiness,
                sources,
            )
            output_json = {
                **output,
                "body_markdown": "\n\n".join(output["body_paragraphs"]),
            }
            output_hash = sha256(json.dumps(output_json, ensure_ascii=False, sort_keys=True))

            evidence_snapshot_ids = []
            for source in sources:
                ref = valid_uuid(source.get("evidence_ref"))
                if ref:
                    evidence_snapshot_ids.append(ref)

            generated_row = {
                "entity_type": "brief_story",
                "entity_id": str(story["story_id"]),
                "task": "editorial_story",
                "run_id": os.environ.get("GITHUB_RUN_ID"),
                "provider": "local_llama_cpp",
                "model_name": MODEL,
                "model_revision": MODEL_REVISION,
                "prompt_version": PROMPT_VERSION,
                "classifier_version": "reviewed-symbiosis",
                "input_sha256": fingerprint,
                "output_sha256": output_hash,
                "output_text": json.dumps(output_json, ensure_ascii=False),
                "output_json": output_json,
                "evidence_snapshot_ids": evidence_snapshot_ids,
                "human_review_status": "governed_preview",
            }
            generated = (
                supabase.table("brief_generated_artifacts")
                .insert(generated_row)
                .select("generated_id")
                .execute()
                .data or []
            )
            generated_id = generated[0]["generated_id"]

            prior_version = int((latest or {}).get("version_number") or 0)
            version_number = prior_version + 1

            version_row = {
                "story_id": story["story_id"],
                "version_number": version_number,
                "event_id": event_id,
                "editorial_headline": output["editorial_headline"],
                "editorial_deck": output["editorial_deck"],
                "body_markdown": "\n\n".join(output["body_paragraphs"]),
                "what_happened": output["what_happened"],
                "why_it_matters": output["why_it_matters"],
                "for_humans": output["for_humans"],
                "for_ai": output["for_ai"],
                "relationship_configuration": relationship.get("configuration"),
                "human_direction": relationship.get("human_direction"),
                "ai_direction": relationship.get("ai_direction"),
                "evidence_basis_summary": {
                    "input_fingerprint": fingerprint,
                    "editorial_evidence_level": readiness.get("editorial_evidence_level"),
                    "full_source_count": readiness.get("full_source_count"),
                    "source_count": readiness.get("source_count"),
                    "prompt_version": PROMPT_VERSION,
                    "model": MODEL,
                    "model_revision": MODEL_REVISION,
                    "llama_cpp_version": LLAMA_CPP_VERSION,
                },
                "generated_artifact_id": generated_id,
                "review_status": "model_generated_governed",
                "publication_status": "preview",
                "supersedes_story_version_id": (latest or {}).get("story_version_id"),
            }
            (
                supabase.table("brief_story_versions")
                .insert(version_row)
                .execute()
            )
            (
                supabase.table("brief_stories")
                .update(
                    {
                        "current_headline": output["editorial_headline"],
                        "current_deck": output["editorial_deck"],
                        "current_takeaway": output["why_it_matters"],
                        "last_updated_at": utc_now(),
                    }
                )
                .eq("story_id", story["story_id"])
                .execute()
            )

            counters["generated"] += 1
            latest_versions[str(story["story_id"])] = {
                "story_version_id": None,
                "version_number": version_number,
                "evidence_basis_summary": {
                    "input_fingerprint": fingerprint,
                },
            }
            print(f"  generated v{version_number}: {output['editorial_headline']}", flush=True)
            time.sleep(0.2)
        except Exception as exc:
            counters["failed"] += 1
            failed_items.append(
                {
                    "event_id": event_id,
                    "event_title": event.get("event_title"),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
            )
            print(f"  ERROR: {type(exc).__name__}: {exc}", flush=True)

    if failed_items:
        with open(
            "editorial-generation-failures.json",
            "w",
            encoding="utf-8",
        ) as handle:
            json.dump(
                {
                    "prompt_version": PROMPT_VERSION,
                    "model": MODEL,
                    "failed": failed_items,
                },
                handle,
                ensure_ascii=False,
                indent=2,
            )
            handle.write("\n")

    print(json.dumps(counters, indent=2))

    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write("## AIEO Brief editorial generation\n\n")
            handle.write(f"- Model: **{MODEL}** (local llama.cpp, no paid model API)\n")
            handle.write(f"- Prompt version: **{PROMPT_VERSION}**\n")
            handle.write(f"- Generated: **{counters['generated']}**\n")
            handle.write(f"- Failed: **{counters['failed']}**\n")
            handle.write(f"- Unchanged: **{counters['skipped_unchanged']}**\n")
            handle.write(f"- Headline-only skipped: **{counters['skipped_headline_only']}**\n")

    if counters["failed"] and summary:
        with open(summary, "a", encoding="utf-8") as handle:
            handle.write(
                "\n> Some drafts were quarantined because they failed validation. "
                "Previously generated valid stories were kept.\n"
            )

    # Resilient batch behavior:
    # - a minority failure does not discard a successful batch;
    # - if every attempted generation failed, the workflow remains red;
    # - --strict restores fail-on-any-error behavior for audits.
    if counters["failed"] and (
        args.strict or counters["generated"] == 0
    ):
        raise SystemExit(
            f"{counters['failed']} editorial story/stories failed generation."
        )

    return 0

if __name__ == "__main__":
    raise SystemExit(main())
