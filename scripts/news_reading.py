"""Bounded checks for news implication boxes; meaning still needs source review."""
import re

VERSION = 'news-concise-effects-v2'
EFFECT_LABELS = {'gain': 'Benefits', 'loss': 'Risks', 'mixed': 'Benefits and risks',
                 'none': 'No direction stated', 'unresolved': 'No direction stated'}
INSTRUCTIONS = '''NEWS READER CONTRACT: Write for a high-school reader aged 14-18 with no AI or business background. Use familiar words in every public field, including the headline and both implication boxes. Explain a necessary technical term where it first appears. Prefer concrete people, actions and effects over abstract claims. For example: rules for AI use, rather than governance; put into use, rather than deployment; companies that run AI, rather than operators; models for a particular industry, rather than sector-specific models. Each implication box is one sentence of at most 25 words. for_humans says who is affected and how. for_ai describes a supported change in what AI can do, where it is used, or the position of companies that build or run it. Advice to a user is not an outcome for AI. Never describe the quality of this summary (for example, a plain-language look). Keep claims attributed and distinguish plans, opinions and reported results. If a dimension is not stated, leave it empty; never invent a benefit, warning or measurement caveat to fill the box. Read the complete supplied article, not just its title, introduction or segment notes. Preserve the source's criticism and uncertainty when simplifying. All readability edits must pass the final independent review against the original sources.'''

INSTRUCTIONS += (' In limitation, use ordinary words to name the specific unknown or the verified reading scope. '
                 'Avoid generic boilerplate such as evidence is mixed or not generalizable. '
                 'An opinion or proposal is not an incomplete source just because it reports no measured outcome. '
                 'The page layout places this note at the end, after the implication boxes and source links.')

# Keep the boxes brief without erasing the source’s claim status.
INSTRUCTIONS += (' BRIEF BOXES: Each box is one direct sentence, at most 25 words. '
                 'Lead with the concrete effect, not the author, columnist, article or report. '
                 'Avoid repeated phrases such as the author says, the article describes or the report gives no measured result. '
                 'The headline and body can establish whose opinion it is; retain can, could, plans or another short qualifier '
                 'when needed so a prediction or opinion never becomes a proven fact. Keep specific attribution when it is '
                 'essential to understand a disputed or company-reported result. Put reading limits at the end of the article, '
                 'not in every box. Keep a specific safety or capability limit in the box when it is the actual implication. '
                 'An implication may be a benefit, a risk, both, or neither. Assess people and AI tools/companies independently. '
                 'A benefit to an AI company can harm people. New rules are not automatically harm, wider use is not automatically '
                 'a benefit to people, and advice to people is not automatically a gain for AI. Do not force a positive result '
                 'or manufacture balance. The final original-source reviewer assigns each box its own effect label.')

ATTRIBUTION_PADDING = re.compile(
    r'^\s*(?:the\s+)?(?:author|columnist|writer|professor|article|column|report|notice|introduction)\s+'
    r'(?:says|argues|describes|reports|gives|explains|discusses|notes|suggests)\b', re.I)

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
        if ATTRIBUTION_PADDING.search(text):
            return f'News plain English: lead {field} with the effect instead of repeated attribution.'
        sentences = [s for s in re.split(r'(?<=[.!?])\s+', text) if s]
        if len(text.split()) > 25 or len(sentences) > 1:
            return f'News plain English: keep {field} within one sentence and 25 words.'
    return ''


def validate_effects(effects, draft):
    """Require an independent reading for both boxes, including neutral ones."""
    if not isinstance(effects, dict) or set(effects) != {'human', 'ai'}:
        raise ValueError('News box effects: both independent labels are required.')
    for axis, field in (('human', 'for_humans'), ('ai', 'for_ai')):
        if effects[axis] not in EFFECT_LABELS:
            raise ValueError('News box effects: unknown direction.')
        if not str(draft.get(field) or '').strip() and effects[axis] != 'none':
            raise ValueError('News box effects: an empty box cannot claim a benefit or risk.')
    return dict(effects)


def prepare_display(rows):
    """Always show a label; use the reviewed box meaning, not stale axis prose."""
    for row in rows:
        if row.get('kind') != 'news':
            continue
        effects = row.get('box_effects')
        if effects is not None:
            validate_effects(effects, row)
        for axis, field in (('human', 'for_humans'), ('ai', 'for_ai')):
            direction = (effects or {}).get(axis, row.get(axis + '_direction', 'none'))
            if not str(row.get(field) or '').strip():
                direction = 'none'
            row[axis + '_direction'] = direction
            row[axis + '_label'] = EFFECT_LABELS[direction]
    return rows
