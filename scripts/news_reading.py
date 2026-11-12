"""Bounded checks for news implication boxes; meaning still needs source review."""
import re

VERSION = 'news-plain-english-v1'
INSTRUCTIONS = '''NEWS READER CONTRACT: Write for a high-school reader aged 14-18 with no AI or business background. Use familiar words in every public field, including the headline and both implication boxes. Explain a necessary technical term where it first appears. Prefer concrete people, actions and effects over abstract claims. For example: rules for AI use, rather than governance; put into use, rather than deployment; companies that run AI, rather than operators; models for a particular industry, rather than sector-specific models. Each implication box should have one or two short sentences, at most 50 words total and at most 26 words per sentence. for_humans says who is affected and how. for_ai describes a supported change in what AI can do, where it is used, or the position of companies that build or run it. Advice to a user is not an outcome for AI. Never describe the quality of this summary (for example, a plain-language look). Keep claims attributed and distinguish plans, opinions and reported results. If a dimension is not stated, leave it empty; never invent a benefit, warning or measurement caveat to fill the box. Read the complete supplied article, not just its title, introduction or segment notes. Preserve the source's criticism and uncertainty when simplifying. All readability edits must pass the final independent review against the original sources.'''

INSTRUCTIONS += (' In limitation, use ordinary words to name the specific unknown or the verified reading scope. '
                 'Avoid generic boilerplate such as evidence is mixed or not generalizable. '
                 'An opinion or proposal is not an incomplete source just because it reports no measured outcome. '
                 'The page layout places this note at the end, after the implication boxes and source links.')

BOX_JARGON = re.compile(
    r'\b(?:governance|deploy(?:ment|ments)|ecosystems?|augment(?:s|ed|ation)?|'
    r'operators?|multimodal|inference|workflows?|sector-specific|full-stack|'
    r'operational capabilities|system performance|at scale|EIOS|FOD-Diffusion)\b', re.I)
META_COPY = re.compile(
    r'\b(?:plain-language look|this explains|this reads as|the evidence describes|'
    r'no explicit (?:human|AI)[- ]side outcome)\b', re.I)


def style_problem(draft):
    for field in ('for_humans', 'for_ai'):
        text = str(draft.get(field) or '').strip()
        if not text:
            continue
        if BOX_JARGON.search(text):
            return f'News plain English: explain or replace specialist wording in {field}: {BOX_JARGON.search(text).group()}'
        if META_COPY.search(text):
            return f'News plain English: {field} must describe a source-supported effect, not the summary.'
        sentences = [s for s in re.split(r'(?<=[.!?])\s+', text) if s]
        if len(text.split()) > 50 or len(sentences) > 2 or any(len(s.split()) > 26 for s in sentences):
            return f'News plain English: keep {field} within two sentences, 26 words per sentence and 50 words total.'
    return ''


def prepare_display(rows):
    """Keep private reading status out of public effect badges, including archives."""
    for row in rows:
        if row.get('kind') != 'news':
            continue
        for axis, field in (('human', 'for_humans'), ('ai', 'for_ai')):
            label = axis + '_label'
            if (row.get(axis + '_direction') == 'unresolved'
                    or row.get(label) == 'Evidence incomplete'
                    or not str(row.get(field) or '').strip()):
                row[label] = ''
    return rows
