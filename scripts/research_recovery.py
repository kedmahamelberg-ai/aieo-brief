"""Re-fetch evidence for unfinished published papers, beyond discovery's top six.

Abstracts remain private. Recovery uses the exact published arXiv version or DOI,
never a title search, and does not silently substitute a different paper.
"""
import hashlib
import json
import re
import time
from html.parser import HTMLParser
from urllib.parse import quote

import requests
from research_pdf import read_pdf_abstract


class AbstractPage(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.depth = 0
        self.parts = []
        self.title = ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'meta' and attrs.get('name') == 'citation_title':
            self.title = attrs.get('content', '')
        if tag == 'blockquote' and 'abstract' in attrs.get('class', '').split():
            self.depth = 1
        elif self.depth and tag not in ('br', 'meta', 'img', 'hr', 'input', 'link'):
            self.depth += 1

    def handle_endtag(self, tag):
        if self.depth and tag not in ('br', 'meta', 'img', 'hr', 'input', 'link'):
            self.depth -= 1

    def handle_data(self, data):
        if self.depth:
            self.parts.append(data)

    @property
    def abstract(self):
        return re.sub(r'^Abstract:\s*', '', ' '.join(' '.join(self.parts).split()))


def unfinished(root):
    records = {}
    for path, field in [('data/archive/stories.json', 'stories'), ('data/research/public.json', 'papers')]:
        file = root / path
        if file.exists():
            for row in json.loads(file.read_text()).get(field, []):
                if row.get('kind') == 'research' or row.get('key', '').startswith('paper:'):
                    records[row['key']] = row
    return [r for r in records.values() if not r.get('has_editorial')]


def recover(paper, get):
    aid = paper.get('arxiv_id', '')
    doi = paper.get('doi', '')
    pdf_urls=[]
    if re.fullmatch(r'\d{4}\.\d{4,5}(?:v\d+)?', aid):
        pdf_urls=['https://arxiv.org/pdf/' + aid]
        page = AbstractPage()
        try:page.feed(get('https://arxiv.org/abs/' + aid).text)
        except requests.RequestException:pass
        title, abstract = page.title, page.abstract
    elif doi.startswith('10.'):
        row = get('https://api.crossref.org/works/' + quote(doi, safe='')).json()['message']
        title = (row.get('title') or [''])[0]
        abstract = re.sub('<[^>]+>', ' ', row.get('abstract') or '')
        pdf_urls=[link.get('URL','') for link in row.get('link',[]) if link.get('content-type')=='application/pdf']
    else:
        return None
    pdf_source=''
    if len(' '.join(abstract.split())) < 80:
        for pdf_url in pdf_urls[:2]:
            abstract=read_pdf_abstract(pdf_url,paper['original_headline'])
            if abstract:
                title=paper['original_headline'];pdf_source=pdf_url;break
    normalize = lambda s: re.sub(r'\W+', '', s).casefold()
    if not title or normalize(title) != normalize(paper['original_headline']):
        return None
    abstract = ' '.join(abstract.split())
    if len(abstract) < 80:
        return None
    result = {**paper, 'abstract': abstract, 'evidence_scope': 'abstract',
              'abstract_format': 'html' if aid else 'metadata', 'abstract_source_url': paper.get('url',''),
              'metadata_sha256': hashlib.sha256((paper['original_headline'] + '\n' + abstract).encode()).hexdigest()}
    if pdf_source:
        result.update(pdf_url=pdf_source,abstract_source_url=pdf_source,abstract_format='pdf')
    if aid:
        result['pdf_url'] = 'https://arxiv.org/pdf/' + aid
    return result


def recover_unfinished(root, rows, get):
    selected = {row['key']: row for row in rows}
    status = {'recovered': 0, 'unavailable': 0}
    backlog={paper['key']:paper for paper in unfinished(root)}
    backlog.update({paper['key']:paper for paper in rows if not paper.get('abstract')})
    for paper in sorted(backlog.values(), key=lambda p: (p.get('date', ''), p['key']), reverse=True):
        if selected.get(paper['key'], {}).get('abstract'):
            continue
        try:
            result = recover(paper, get)
        except (requests.RequestException, ValueError, KeyError, TypeError):
            result = None
        if result:
            selected[paper['key']] = result
            status['recovered'] += 1
        else:
            # Keep the record visible, but never infer findings from its title.
            selected.setdefault(paper['key'], paper)
            status['unavailable'] += 1
        time.sleep(3)
    return list(selected.values()), status
