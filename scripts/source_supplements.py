"""Fetch hash-bound public copies when a publisher URL exposes only a template."""
import hashlib
import json
import re
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

SELECTORS = {
    'www.ecnu.edu.cn': '.v_news_content',
    'finance.eastmoney.com': '#ContentBody',
    'm.sohu.com': '.article-content',
}


def verified_text(supplement, get=requests.get):
    if supplement.get('evidence_text'):
        return supplement['evidence_text']
    url = supplement.get('source_url', '')
    host = urlparse(url).hostname
    public_chart=host=='flo.uri.sh' and re.fullmatch(r'/story/\d+/embed',urlparse(url).path)
    if not url.startswith('https://') or (host not in SELECTORS and not public_chart):
        return ''
    try:
        response = get(url, timeout=30)
        response.raise_for_status()
        if public_chart:
            # Read only published slide captions; never execute page scripts
            # or obtain private project data. Keep all captions in order.
            captions=[json.loads(match) for match in re.findall(r'"caption_text"\s*:\s*("(?:[^"\\]|\\.)*")',response.text)]
            soup=BeautifulSoup('\n'.join(captions),'html.parser')
            text='\n'.join(' '.join(line.split()) for line in soup.get_text('\n').splitlines() if line.strip())
            return text if hashlib.sha256(text.encode()).hexdigest()==supplement.get('evidence_sha256') else ''
        soup = BeautifulSoup(response.content, 'html.parser')
        article = soup.select_one(SELECTORS[host])
        if article is None:
            return ''
        for node in article.select('style,script,nav,aside,.surplus-btn'):
            node.decompose()
        text = '\n'.join(' '.join(line.split()) for line in article.get_text('\n').splitlines() if line.strip())
        if hashlib.sha256(text.encode()).hexdigest() != supplement.get('evidence_sha256'):
            return ''
        return text
    except (requests.RequestException, ValueError):
        return ''
