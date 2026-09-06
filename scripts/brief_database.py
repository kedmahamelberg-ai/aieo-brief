import json,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
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
            "review_status,publication_status,evidence_basis_summary,created_at",
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
                "story_version_id,story_id,event_id,version_number,review_status,editorial_headline,editorial_deck,body_markdown,what_happened,why_it_matters,for_humans,for_ai,relationship_configuration,human_direction,ai_direction,generated_artifact_id,"
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
