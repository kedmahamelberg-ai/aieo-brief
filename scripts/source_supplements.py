"""Fetch hash-bound public copies when a publisher URL exposes only a template."""
import hashlib
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SELECTORS = {
    'www.ecnu.edu.cn': '.v_news_content',
    'finance.eastmoney.com': '#ContentBody',
}


def verified_text(supplement, get=requests.get):
    if supplement.get('evidence_text'):
        return supplement['evidence_text']
    url = supplement.get('source_url', '')
    host = urlparse(url).hostname
    if not url.startswith('https://') or host not in SELECTORS:
        return ''
    try:
        response = get(url, timeout=30)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, 'html.parser')
        article = soup.select_one(SELECTORS[host])
        if article is None:
            return ''
        for node in article.select('style,script,nav,aside'):
            node.decompose()
        text = '\n'.join(' '.join(line.split()) for line in article.get_text('\n').splitlines() if line.strip())
        if hashlib.sha256(text.encode()).hexdigest() != supplement.get('evidence_sha256'):
            return ''
        return text
    except requests.RequestException:
        return ''
