"""Recognize model field fragments that must never become article prose."""
import re


DRAFT_MARKER = re.compile(
    r'\b(?:[a-z0-9_]*_placeholder[a-z0-9_]*|placeholder_[a-z0-9_]+'
    r'|limitation_[a-z0-9_]+|(?:for_humans|for_ai|evidence_basis|claim_status)_[a-z0-9_]+)\b',
    re.I,
)

# Older stored drafts sometimes contain an entire malformed JSON field as one
# body paragraph. Remove only these isolated fragments; a marker embedded in
# otherwise usable prose remains visible to the publication gate for review.
FIELD_FRAGMENT = re.compile(
    r'^\s*[\[({"\']*\s*(?:limitation_[a-z0-9_]+|body_paragraphs|'
    r'editorial_[a-z0-9_]+|what_happened|why_it_matters|for_humans|for_ai|claim_status)'
    r'\s*(?:\\?["\'])?\s*:',
    re.I,
)
LEADING_ARTIFACT = re.compile(r'^\s*[a-z0-9_]*limitation[a-z0-9_]*_[a-z0-9_]+', re.I)


def isolated_artifact(value):
    if not isinstance(value, str):
        return False
    value = value.strip()
    return bool(
        DRAFT_MARKER.fullmatch(value)
        or re.fullmatch(r'[a-z0-9_ ,]*_placeholder[a-z0-9_ ,]*', value, re.I)
        or LEADING_ARTIFACT.match(value)
        or FIELD_FRAGMENT.match(value)
    )
