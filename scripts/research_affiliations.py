#!/usr/bin/env python3
"""Add source-checked institutional metadata to research records at no added service fee.

The script uses bibliographic metadata from OpenAlex. A missing match or network
failure is non-fatal: the Brief keeps the original paper link and never invents
an affiliation.
"""
from __future__ import annotations

import os
import re
import time
from datetime import datetime, timezone
from difflib import SequenceMatcher
from html.parser import HTMLParser
from urllib.parse import quote

import requests

OPENALEX = "https://api.openalex.org/works"


def _plain(value):
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _normal(value):
    return re.sub(r"[^a-z0-9]+", " ", _plain(value).casefold()).strip()


def _request(url, *, params=None, contact=""):
    params = dict(params or {})
    key = _plain(os.environ.get("OPENALEX_API_KEY"))
    if key:
        params.setdefault("api_key", key)
    # The parameter is harmless for deployments where OpenAlex ignores it and
    # still identifies the project on older-compatible endpoints.
    if contact:
        params.setdefault("mailto", contact)
    headers = {
        "User-Agent": "AIEO-Brief/3.2 (research metadata; https://brief.hamelberg-ai.com)"
    }
    response = requests.get(url, params=params, headers=headers, timeout=30)
    response.raise_for_status()
    return response.json()


def _verify_source(url):
    """Return True only after the original HTTPS paper URL responds."""
    url = _plain(url)
    if not url.startswith("https://"):
        return False
    headers = {"User-Agent": "AIEO-Brief/3.2 (source-link check; https://brief.hamelberg-ai.com)"}
    try:
        response = requests.head(url, headers=headers, allow_redirects=True, timeout=15)
        if response.status_code in (403, 405) or response.status_code >= 500:
            response = requests.get(url, headers=headers, allow_redirects=True, timeout=20, stream=True)
        return 200 <= response.status_code < 400 and response.url.startswith("https://")
    except requests.RequestException:
        return False


def _candidate_score(paper, work):
    expected = _normal(paper.get("original_headline"))
    actual = _normal(work.get("display_name") or work.get("title"))
    if not expected or not actual:
        return 0.0
    score = SequenceMatcher(None, expected, actual).ratio()
    ids = work.get("ids") or {}
    arxiv = re.sub(r"v\d+$", "", _plain(paper.get("arxiv_id")), flags=re.I)
    if arxiv and any(arxiv in _plain(value) for value in ids.values()):
        score += 1.0
    doi = _plain(paper.get("doi")).casefold()
    if doi and doi in _plain(ids.get("doi")).casefold():
        score += 1.0
    if _plain(paper.get("date")) == _plain(work.get("publication_date")):
        score += 0.1
    return score


def _lookup(paper, contact=""):
    doi = _plain(paper.get("doi"))
    if doi:
        try:
            work = _request(
                f"{OPENALEX}/https://doi.org/{quote(doi, safe='/')}",
                contact=contact,
            )
            return work if _candidate_score(paper, work) >= 0.8 else None
        except requests.RequestException:
            pass
    data = _request(
        OPENALEX,
        params={
            "search": _plain(paper.get("original_headline")),
            "per_page": 5,
            "select": "id,display_name,publication_date,ids,authorships",
        },
        contact=contact,
    )
    candidates = data.get("results") or []
    if not candidates:
        return None
    best = max(candidates, key=lambda work: _candidate_score(paper, work))
    return best if _candidate_score(paper, best) >= 0.88 else None


def _institutions(work):
    names = []
    for authorship in work.get("authorships") or []:
        for institution in authorship.get("institutions") or []:
            name = _plain(institution.get("display_name"))
            if name and name.casefold() not in {item.casefold() for item in names}:
                names.append(name)
    return names[:8]


class _ArxivAuthorInstitutions(HTMLParser):
    """Read affiliation cells in arXiv's author block, never the repository name."""
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []

    def handle_starttag(self, tag, attrs):
        classes = dict(attrs).get("class", "").split()
        if tag == "div" and "ltx_authors" in classes and not self.depth:
            self.depth = 1
        elif self.depth:
            if tag == "div":
                self.depth += 1

    def handle_endtag(self, tag):
        if self.depth and tag == "div":
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            value = _plain(data)
            if value:
                self.parts.append(value)


def _arxiv_institutions(paper):
    aid = _plain(paper.get("arxiv_id"))
    if not re.fullmatch(r"\d{4}\.\d{4,5}(?:v\d+)?", aid):
        return [], ""
    url = f"https://arxiv.org/html/{aid}"
    response = requests.get(url, timeout=30, headers={"User-Agent": "AIEO-Brief/3.2 (author affiliation check; https://brief.hamelberg-ai.com)"})
    response.raise_for_status()
    parser = _ArxivAuthorInstitutions()
    parser.feed(response.text)
    author_block = _normal(" ".join(parser.parts))
    if not any(_normal(author) in author_block for author in paper.get("authors") or [] if _normal(author)):
        return [], ""
    names = []
    for part in parser.parts:
        if (re.search(r"\b(university|université|universidad|institute|college|academy)\b", part, re.I)
                and len(part) < 140 and "@" not in part
                and _normal(part) not in {_normal(name) for name in names}):
            names.append(part)
    return names[:8], url if names else ""


def _age_days(value, now):
    value = _plain(value)
    if not value:
        return None
    try:
        return (now - datetime.fromisoformat(value.replace("Z", "+00:00"))).days
    except ValueError:
        return None


def enrich_affiliations(papers, *, contact="", refresh_days=30):
    """Mutate paper records with checked source and institutional metadata."""
    now = datetime.now(timezone.utc)
    verified_at = now.isoformat()
    status = []
    for paper in papers:
        paper.setdefault("institutions", [])
        source_age = _age_days(paper.get("source_verified_at"), now)
        source_ok = source_age is not None and source_age < refresh_days
        if not source_ok and _verify_source(paper.get("url")):
            paper["source_verified_at"] = verified_at
            source_ok = True

        affiliation_age = _age_days(paper.get("affiliation_checked_at"), now)
        fallback_age = _age_days(paper.get("affiliation_fallback_checked_at"), now)
        if (affiliation_age is not None and affiliation_age < refresh_days
                and (paper["institutions"] or not paper.get("arxiv_id")
                     or (fallback_age is not None and fallback_age < refresh_days))):
            status.append({
                "key": paper.get("key"),
                "status": "cached",
                "source_verified": source_ok,
                "institutions": len(paper["institutions"]),
            })
            continue
        try:
            work = _lookup(paper, contact=contact)
            paper["affiliation_checked_at"] = verified_at
            if work:
                names = _institutions(work)
                if names:
                    paper["institutions"] = names
                work_id = _plain(work.get("id"))
                if work_id and names:
                    paper["affiliation_source_url"] = "https://openalex.org/" + work_id.rsplit("/", 1)[-1]
                result = "matched"
            else:
                result = "not_matched"
            if (not paper["institutions"] or paper.get("affiliation_source_url", "").startswith("https://arxiv.org/html/")) and paper.get("arxiv_id"):
                names, url = _arxiv_institutions(paper)
                paper["affiliation_fallback_checked_at"] = verified_at
                if names:
                    paper["institutions"] = names
                    paper["affiliation_source_url"] = url
                    result = "arxiv_authors"
            status.append({
                "key": paper.get("key"),
                "status": result,
                "source_verified": source_ok,
                "institutions": len(paper["institutions"]),
            })
        except (requests.RequestException, ValueError, TypeError):
            try:
                names, url = _arxiv_institutions(paper)
                paper["affiliation_fallback_checked_at"] = verified_at
                if names:
                    paper["institutions"] = names
                    paper["affiliation_source_url"] = url
                    paper["affiliation_checked_at"] = verified_at
                    status.append({
                        "key": paper.get("key"), "status": "arxiv_authors",
                        "source_verified": source_ok, "institutions": len(names),
                    })
                    continue
            except requests.RequestException:
                pass
            status.append({
                "key": paper.get("key"),
                "status": "unavailable",
                "source_verified": source_ok,
                "institutions": len(paper["institutions"]),
            })
        time.sleep(0.12)
    return status
