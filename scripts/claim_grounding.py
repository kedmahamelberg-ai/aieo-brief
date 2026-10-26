"""Fail-closed publication gate for every public prose field.

The verifier receives original evidence, never writer-selected excerpts or
lossy segment notes. Exact citations are checked locally. Semantic entailment
still requires model judgement; this gate is a risk reduction, not a proof.
"""
import hashlib
import json
import re

VERSION = 'all-public-fields-grounding-v1'
FIELDS = ('editorial_headline', 'editorial_deck', 'what_happened',
          'why_it_matters', 'for_humans', 'for_ai', 'limitation')
CHECKS = ('source_is_substantive', 'entities_and_roles_preserved',
          'dates_and_event_status_preserved', 'comparators_and_metrics_preserved',
          'provenance_preserved', 'limitations_and_examples_supported')


def units(draft):
    result = {key: draft[key] for key in FIELDS if draft.get(key)}
    result.update({f'body_paragraphs[{i}]': text for i, text in enumerate(draft.get('body_paragraphs', [])) if text})
    return result


def normalized(text):
    return re.sub(r'\s+', ' ', text).strip()


def extend_schema(schema, draft):
    import copy
    result = copy.deepcopy(schema)
    result['properties'].update({key: {'type': 'boolean'} for key in CHECKS})
    result['required'].extend(CHECKS)
    result['properties']['field_reviews'] = {
        'type': 'array', 'minItems': len(units(draft)), 'maxItems': len(units(draft)),
        'items': {'type': 'object', 'additionalProperties': False,
                  'properties': {
                      'field': {'type': 'string', 'enum': list(units(draft))},
                      'verdict': {'type': 'string', 'enum': ['supported', 'unsupported', 'uncertain']},
                      'reason': {'type': 'string', 'maxLength': 250},
                      'citations': {'type': 'array', 'maxItems': 6,
                                    'items': {'type': 'object', 'additionalProperties': False,
                                              'properties': {'source_number': {'type': 'integer'},
                                                             'quote': {'type': 'string', 'maxLength': 600}},
                                              'required': ['source_number', 'quote']}}},
                  'required': ['field', 'verdict', 'reason', 'citations']}}
    result['required'].append('field_reviews')
    return result


INSTRUCTIONS = '''\nADVERSARIAL GROUNDING REVIEW:
Review EVERY factual clause of EVERY listed field, including every sentence in each body paragraph, all caveats, implications and examples. Do not rely on the writer's support quotes. Select exact quotes from ORIGINAL SOURCES yourself. A quote merely on the same topic is not support. A field is supported only if ALL its claims are entailed by the cited source context; a plausible inference is not enough. Use uncertain whenever the evidence cannot settle a claim. Reject unsupported negative claims as well as positive claims. Empty optional fields are allowed.
Set each boolean check to true when the draft satisfies that rule, including when that dimension is not mentioned. Review factual content only in non-empty public fields. Empty fields are not unsupported claims and must not cause a failed check. Completeness and required-field checks happen separately before this review. A concise summary may omit unrelated details; reject an omission only when it changes the meaning of a claim that the draft actually makes. Do not require every source date or every comparison in each field. Preserve qualifiers needed for the stated claim.
source_is_substantive: original text contains the relevant article or research, not only navigation, a video caption, login text or a newsletter teaser. Abstracts are allowed only with the matching scope.
entities_and_roles_preserved: keep exact organization, campus, person, title, model versus family, trained classifier versus rules, and singular/plural distinctions.
dates_and_event_status_preserved: preserve scheduled versus completed events and estimates versus deadlines; roughly twenty years is not up to twenty years.
comparators_and_metrics_preserved: check each number WITH its denominator, subgroup, metric, baseline, direction and qualifier. Training error is not generalization error. Same trajectory is not equal speed. A worse score than one competitor is not a failure to improve over the base model.
provenance_preserved: published or obtained does not mean leaked, stolen, confidential or unauthorized. Preserve who made each claim.
limitations_and_examples_supported: do not invent critics, warnings, cautions, mixed results, targets, independent confirmation, lab data, hypothetical studies, or practical applications. Do not turn real observations into hypothetical examples. A missing detail may be described only as absent from the supplied material, not absent from the underlying research. A scope statement can cite supplied evidence metadata; a substantive claim cannot be supported by metadata alone.
Return one field_reviews entry for EACH field ID. Each entry must cover ALL clauses, give a verdict, and cite exact original-language passages with source_number. Supported entries require citations. False/uncertain, omitted or duplicate fields prevent publication. Never repair text inside the review.\n'''


def validate(result, draft, sources):
    expected = units(draft)
    failed = [key for key in CHECKS if result.get(key) is not True]
    rows = result.get('field_reviews')
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise ValueError('Every public field needs a complete grounding review.')
    seen = set()
    source_map = {}
    for source in sources:
        source_map.setdefault(source['source_number'], []).append(normalized(source['evidence']))
    for row in rows:
        if not isinstance(row, dict) or row.get('field') not in expected or row['field'] in seen:
            raise ValueError('Grounding review has an unknown or duplicate field.')
        field = row['field']; seen.add(field)
        if row.get('verdict') != 'supported':
            failed.append(field + ': ' + str(row.get('reason', 'unsupported or uncertain'))[:250])
        citations = row.get('citations')
        if not isinstance(citations, list) or not 1 <= len(citations) <= 6:
            raise ValueError('Grounding review has missing citations.')
        for citation in citations:
            if not isinstance(citation, dict):
                raise ValueError('Grounding citation is malformed.')
            number = citation.get('source_number'); quote = citation.get('quote')
            if type(number) is not int or not isinstance(quote, str) or not 12 <= len(quote) <= 600 or not any(normalized(quote) in text for text in source_map.get(number, [])):
                raise ValueError('Grounding citation is not an exact passage in its original source.')
    if failed:
        raise ValueError('Grounding review rejected: ' + '; '.join(failed))
    return {'version': VERSION, 'public_sha256': hashlib.sha256(json.dumps(expected, sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            'field_reviews': rows, 'checks': {key: True for key in CHECKS}}
