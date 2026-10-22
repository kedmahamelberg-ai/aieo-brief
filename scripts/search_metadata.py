"""Public identity connections; original paper authors remain separate."""
import json
import re
import copy
from pathlib import Path

def canonical_local(value, prefix=''):
    """Link directly to directory canonicals, retaining queries and fragments."""
    return (prefix + re.sub(r'(^|/)index\.html(?=$|[?#])', r'\1', value)) or './'


def weekly_overview_with_canonical_links(overview, items):
    """Render saved weekly sources at their current article addresses.

    Historical overview snapshots retain the paths used when they were
    approved. Those paths may later become redirect aliases after a headline
    URL change, so rewrite only the copy used for public HTML and schema.
    """
    canonical = {path: item['path'] for item in items
                 for path in [item['path'], *item.get('legacy_paths', [])]}
    rendered = copy.deepcopy(overview)
    for entry in rendered['markets'].get('entries', []):
        story = entry.get('story')
        if story and story.get('path'):
            story['path'] = canonical[story['path']]
    for paper in rendered['research'].get('papers', []):
        if paper.get('path'):
            paper['path'] = canonical[paper['path']]
    return rendered

def identity_graph(root, canonical, page):
    nodes = json.loads((Path(root)/'config/search-identity.json').read_text())
    nodes.append({'@type': 'AboutPage' if page == 'about' else 'WebPage',
        '@id': canonical+'#webpage', 'url': canonical,
        'isPartOf': {'@id': 'https://brief.hamelberg-ai.com/#website'},
        'publisher': {'@id': 'https://brief.hamelberg-ai.com/#organization'}})
    if page == 'about':
        nodes[-1].update(about=[{'@id':'https://brief.hamelberg-ai.com/#organization'},
            {'@id':'https://kedmahamelberg.com/#person'}],
            primaryImageOfPage={'@id':'https://kedmahamelberg.com/#portrait'})
    return {'@context':'https://schema.org','@graph':nodes}
