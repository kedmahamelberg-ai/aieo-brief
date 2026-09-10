#!/usr/bin/env python3
"""Build concise, source-linked weekly editorial overviews for The Brief.

The country section summarizes *reporting discovered in each market*. It never
claims that the selected coverage represents a country, its population, or its
national direction. The research section only attaches an institution to a
paper when the metadata provider supplied a verified affiliation.
"""
from __future__ import annotations

import collections
import copy
import hashlib
import json
import re
from datetime import date
from pathlib import Path
from urllib.parse import urlparse

MARKETS = (
    ("CN", "China"),
    ("US", "United States"),
    ("GB", "United Kingdom"),
    ("FR", "France"),
    ("CA", "Canada"),
)
MARKET_ORDER = {code: position for position, (code, _) in enumerate(MARKETS)}
TOPIC_LABELS = {
    "work": "work and skills",
    "creativity": "culture and creativity",
    "everyday": "everyday use",
    "policy": "rules and rights",
    "technology": "models, agents and infrastructure",
    "research": "research and evidence",
    "business": "business and investment",
}
RESEARCH_THEMES = (
    ("agents and coordination", re.compile(r"\bagent|multi-agent|coordination|collective|tool use|workflow", re.I)),
    ("robotics and embodied AI", re.compile(r"robot|humanoid|navigation|embodied|vision-language-action", re.I)),
    ("reliability and evaluation", re.compile(r"reliab|benchmark|reward|citation|faithful|robust|fragil|evaluation", re.I)),
    ("reasoning and memory", re.compile(r"reason|memory|context|recurrent|long-context|inference", re.I)),
    ("training and efficiency", re.compile(r"gradient|training|optimization|efficien|compute|acceleration", re.I)),
    ("human interaction and creativity", re.compile(r"human|interaction|creative|music|art|interface|tangible", re.I)),
)
NATURE_IMAGES = {
    "markets": {
        "image_path": "assets/weekly-overviews/east-fork-toklat.jpg",
        "image_alt": "The East Fork of the Toklat River flowing through a wide mountain valley in Denali National Park and Preserve",
        "image_caption": "East Fork of the Toklat River, Denali National Park and Preserve",
        "image_credit": "NPS Photo / Tim Rains",
        "image_source_url": "https://npgallery.nps.gov/AssetDetail/e6ee57ae-3522-4861-8d29-db16ab53d0bb",
        "image_rights": "Public domain · Full Granting Rights",
    },
    "research": {
        "image_path": "assets/weekly-overviews/milky-way-yellowstone.jpg",
        "image_alt": "The Milky Way and stars reflected on a backcountry lake in Yellowstone National Park",
        "image_caption": "Milky Way reflected over a backcountry lake, Yellowstone National Park",
        "image_credit": "Neal Herbert / NPS",
        "image_source_url": "https://npgallery.nps.gov/AssetDetail/2ef91b9f-ad6d-4c60-9a57-d2386724aeb7",
        "image_rights": "Public domain · Full Granting Rights",
    },
}
SCHEMA = "aieo_weekly_overview_archive_v1"


def _plain(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _words(value: str) -> int:
    return len(re.findall(r"\b[\w’'-]+\b", value, flags=re.UNICODE))


def _clip(value: str, limit: int) -> str:
    value = _plain(value)
    tokens = value.split()
    if len(tokens) <= limit:
        return value
    return " ".join(tokens[:limit]).rstrip(" ,;:.-") + "…"


def _https(value: object) -> str:
    value = _plain(value)
    try:
        parsed = urlparse(value)
    except ValueError:
        return ""
    return value if parsed.scheme == "https" and parsed.hostname else ""


def _stable_choice(seed: str, options: tuple[str, ...]) -> str:
    digest = hashlib.sha256(seed.encode("utf-8")).digest()
    return options[int.from_bytes(digest[:2], "big") % len(options)]


def _representative(items: list[dict]) -> dict | None:
    if not items:
        return None
    return sorted(
        items,
        key=lambda item: (
            not bool(item.get("has_editorial")),
            int(item.get("daily_rank", 99999)),
            -len(_plain(item.get("deck"))),
            _plain(item.get("key")),
        ),
    )[0]


def _market_entry(code: str, name: str, news: list[dict], release_id: str) -> dict:
    items = [item for item in news if code in (item.get("markets") or [])]
    counts = collections.Counter(_plain(item.get("topic")) for item in items)
    topic = counts.most_common(1)[0][0] if counts else ""
    topic_text = TOPIC_LABELS.get(topic, "several AI questions")
    representative = _representative(items)
    if not representative:
        return {
            "code": code,
            "name": name,
            "count": 0,
            "topic": "No complete-content signal",
            "sentence": f"{name}: no eligible development entered this week’s complete-content edition.",
            "story": None,
        }

    title = _clip(representative.get("headline") or representative.get("original_headline"), 11)
    patterns = (
        f"{name}: selected reporting leaned toward {topic_text}, with “{title}” as one visible signal.",
        f"{name}: {topic_text} stood out in the selected coverage; one example was “{title}.”",
        f"{name}: the discovery stream centred most often on {topic_text}, including “{title}.”",
    )
    sentence = _stable_choice(f"{release_id}:{code}", patterns)
    source = (representative.get("sources") or [{}])[0]
    source_url = _https(source.get("url"))
    return {
        "code": code,
        "name": name,
        "count": len(items),
        "topic": TOPIC_LABELS.get(topic, "AI developments").title(),
        "sentence": sentence,
        "story": {
            "headline": _plain(representative.get("headline")),
            "path": _plain(representative.get("path")),
            "publisher": _plain(representative.get("publisher") or source.get("publisher")),
            "source_url": source_url,
        },
    }


def _market_overview(news: list[dict], release: dict) -> dict:
    release_id = _plain(release.get("release_id"))
    entries = [_market_entry(code, name, news, release_id) for code, name in MARKETS]
    active = [entry for entry in entries if entry["count"]]
    dominant = collections.Counter(
        _plain(item.get("topic")) for item in news if _plain(item.get("topic"))
    ).most_common(2)
    themes = [TOPIC_LABELS.get(topic, topic) for topic, _ in dominant]
    if len(themes) >= 2:
        deck = f"Across the five discovery markets, {themes[0]} met {themes[1]}. The balance differed by reporting stream."
    elif themes:
        deck = f"Across the five discovery markets, {themes[0]} supplied the strongest common current."
    else:
        deck = "Five discovery streams, read side by side, show where this week’s reporting placed its attention."

    summary = " ".join(entry["sentence"] for entry in entries)
    scope_note = (
        "This is a map of selected reporting discovered in each market, not a forecast of national policy, "
        "public opinion or all AI activity in that country."
    )
    # Five compact market sentences plus the scope note should remain a true sub-minute read.
    if _words(summary + " " + scope_note) > 145:
        summary = " ".join(_clip(entry["sentence"], 20) for entry in entries)
    return {
        "kind": "markets",
        "eyebrow": "THE WEEK FROM ABOVE",
        "title": "Five currents in this week’s AI reporting",
        "deck": deck,
        "summary": summary,
        "scope_note": scope_note,
        "word_count": _words(summary + " " + scope_note),
        "reading_minutes": 1,
        **copy.deepcopy(NATURE_IMAGES["markets"]),
        "entries": entries,
        "active_market_count": len(active),
    }


def _paper_theme(paper: dict) -> str:
    material = " ".join(
        _plain(paper.get(key))
        for key in ("headline", "original_headline", "deck", "what_happened", "why_it_matters")
    )
    for label, pattern in RESEARCH_THEMES:
        if pattern.search(material):
            return label
    return "new methods and evidence"


def _paper_institutions(paper: dict) -> list[str]:
    raw = paper.get("institutions") or paper.get("affiliations") or []
    values: list[str] = []
    for item in raw:
        name = _plain(item.get("name") if isinstance(item, dict) else item)
        if name and name.casefold() not in {value.casefold() for value in values}:
            values.append(name)
    return values[:4]


def _research_overview(research: list[dict], release: dict) -> dict:
    start = _plain(release.get("period_start"))
    end = _plain(release.get("period_end"))
    current = [paper for paper in research if start <= _plain(paper.get("date")) <= end]
    current = sorted(
        current,
        key=lambda paper: (
            not bool(paper.get("has_editorial")),
            -len(_paper_institutions(paper)),
            _plain(paper.get("key")),
        ),
    )
    sourced: list[dict] = []
    for paper in current:
        url = _https(paper.get("url"))
        if not url:
            continue
        institutions = _paper_institutions(paper)
        sourced.append(
            {
                "key": _plain(paper.get("key")),
                "headline": _plain(paper.get("headline") or paper.get("original_headline")),
                "original_headline": _plain(paper.get("original_headline")),
                "deck": _plain(paper.get("deck")),
                "authors": [_plain(author) for author in (paper.get("authors") or []) if _plain(author)],
                "institutions": institutions,
                "institution_status": "verified" if institutions else "not supplied in verified metadata",
                "url": url,
                "path": _plain(paper.get("path")),
                "publisher": _plain(paper.get("publisher")),
                "label": _plain(paper.get("research_label")),
                "date": _plain(paper.get("date")),
                "theme": _paper_theme(paper),
                "source_verified_at": _plain(paper.get("source_verified_at")),
                "affiliation_source_url": _https(paper.get("affiliation_source_url")),
            }
        )

    theme_counts = collections.Counter(item["theme"] for item in sourced)
    top_themes = [theme for theme, _ in theme_counts.most_common(2)]
    qualified = [item for item in sourced if item["institutions"]]
    featured = (qualified or sourced)[:4]
    if len(top_themes) >= 2:
        title = f"Research turns toward {top_themes[0]} and {top_themes[1]}"
        deck = f"The selected papers point in two directions: {top_themes[0]} and {top_themes[1]}."
    elif top_themes:
        title = f"Research turns toward {top_themes[0]}"
        deck = f"The strongest thread in the selected papers was {top_themes[0]}."
    else:
        title = "Where AI research is heading"
        deck = "The research compass will appear when this week’s source records are complete."

    sentences: list[str] = []
    for paper in featured[:3]:
        institution = ", ".join(paper["institutions"]) if paper["institutions"] else "Affiliation not yet verified"
        signal = _clip(paper["deck"] or paper["headline"], 20)
        sentences.append(f"{institution}: {signal}")
    summary = " ".join(sentences)
    if not summary:
        summary = "No institution-linked paper met the publication rule for this edition. The research feed keeps the verified source records available."
    note = (
        "Institution names come from source or OpenAlex metadata and are shown only as affiliations, not as endorsements. "
        "Preprints and abstract-only evidence remain labelled."
    )
    if _words(summary + " " + note) > 145:
        summary = " ".join(_clip(sentence, 28) for sentence in sentences[:3])
    return {
        "kind": "research",
        "eyebrow": "THE RESEARCH COMPASS",
        "title": title,
        "deck": deck,
        "summary": summary,
        "scope_note": note,
        "word_count": _words(summary + " " + note),
        "reading_minutes": 1,
        **copy.deepcopy(NATURE_IMAGES["research"]),
        "papers": featured,
        "paper_count": len(sourced),
        "affiliation_verified_count": len(qualified),
    }


def _overview_path(release_id: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", release_id.casefold()).strip("-") or "current"
    return f"week-from-above/{slug}/index.html"


def _load_history(path: Path) -> dict:
    if not path.exists():
        return {"schema_version": SCHEMA, "overviews": []}
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schema_version") != SCHEMA or not isinstance(value.get("overviews"), list):
        raise ValueError("The weekly overview archive has an unsupported structure.")
    return value


def prepare_weekly_overviews(
    news: list[dict],
    research: list[dict],
    release: dict,
    root: Path,
    *,
    write_archive: bool = False,
) -> tuple[dict, list[dict]]:
    """Return the current overview and newest-first archive.

    Rebuilding the same release is deterministic. A new release replaces only
    its own archive record and leaves earlier weeks untouched.
    """
    release_id = _plain(release.get("release_id"))
    if not release_id:
        raise ValueError("A release ID is required for the weekly overview.")
    current = {
        "schema_version": "aieo_weekly_overview_v1",
        "release_id": release_id,
        "period_start": _plain(release.get("period_start")),
        "period_end": _plain(release.get("period_end")),
        "display_date": _plain(release.get("period_end")),
        "path": _overview_path(release_id),
        "markets": _market_overview(news, release),
        "research": _research_overview(research, release),
    }
    current["content_sha256"] = hashlib.sha256(
        json.dumps(current, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    ).hexdigest()

    archive_path = Path(root) / "data/weekly-overviews/history.json"
    history = _load_history(archive_path)
    records = {
        _plain(item.get("release_id")): copy.deepcopy(item)
        for item in history["overviews"]
        if isinstance(item, dict) and _plain(item.get("release_id"))
    }
    # Replace the retired generated illustrations in every archived week too.
    for archived in records.values():
        for section in ("markets", "research"):
            if isinstance(archived.get(section), dict):
                archived[section].update(copy.deepcopy(NATURE_IMAGES[section]))
        archived.pop("content_sha256", None)
        archived["content_sha256"] = hashlib.sha256(
            json.dumps(archived, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
    records[release_id] = current
    ordered = sorted(
        records.values(),
        key=lambda item: (_plain(item.get("period_end")), _plain(item.get("release_id"))),
        reverse=True,
    )
    if write_archive:
        archive_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"schema_version": SCHEMA, "overviews": ordered}
        archive_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return current, copy.deepcopy(ordered)


def social_queue(current: dict, base_url: str) -> dict:
    base_url = _plain(base_url).rstrip("/")
    destination = base_url + "/" + (current["path"][:-10] if current["path"].endswith("index.html") else current["path"]) if base_url else ""
    market = current["markets"]
    research = current["research"]
    return {
        "schema_version": "aieo_social_queue_v1",
        "release_id": current["release_id"],
        "items": [
            {
                "kind": "weekly_markets",
                "destination": destination + "#five-markets",
                "linkedin": f"Five markets, five different AI currents. {market['deck']} Read the one-minute, source-linked view: {destination}#five-markets",
                "facebook": f"What did this week’s selected AI reporting emphasize in China, the US, the UK, France and Canada? {market['deck']} {destination}#five-markets",
            },
            {
                "kind": "weekly_research",
                "destination": destination + "#research-compass",
                "linkedin": f"Where is AI research moving this week? {research['deck']} Universities and research institutions are named only when the affiliation is verified. {destination}#research-compass",
                "facebook": f"This week’s AI research compass: {research['deck']} Open the papers, authors, institutions and source links: {destination}#research-compass",
            },
        ],
    }
