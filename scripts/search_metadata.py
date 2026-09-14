"""Public identity connections; original paper authors remain separate."""
import json
from pathlib import Path

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
