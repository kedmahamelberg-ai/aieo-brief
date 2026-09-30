"""Recover an explicitly delimited abstract from an original-source PDF."""
import io
import re
import unicodedata
from urllib.parse import urlparse

import requests


def abstract_from_text(text, title):
    text = unicodedata.normalize('NFKC', text)
    normal = lambda value: re.sub(r'\W+', '', unicodedata.normalize('NFKC', value)).casefold()
    start = re.search(r'(?im)^\s*abstract\s*[:.\-–—]?\s*', text)
    if not start or normal(title) not in normal(text[:start.start()]):
        return ''
    rest = text[start.end():]
    end = re.search(r'(?im)^\s*(?:(?:1|I)\s*[.)]?\s*)?(?:introduction|background)\b|^\s*(?:keywords|key words|index terms)\s*[:\-–—]', rest)
    if not end:
        return ''  # Never substitute arbitrary first-page text for an abstract.
    abstract = ' '.join(rest[:end.start()].split())
    return abstract if 80 <= len(abstract) <= 8000 else ''


def read_pdf_abstract(url, title):
    host = (urlparse(url).hostname or '').lower()
    if not url.startswith('https://') or not any(host == domain or host.endswith('.' + domain) for domain in ('arxiv.org', 'pnas.org', 'ssrn.com')):
        return ''
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    try:
        with requests.get(url, stream=True, timeout=45, headers={'User-Agent': 'AIEO-Brief/3.2 (abstract recovery; https://brief.hamelberg-ai.com)'}) as response:
            response.raise_for_status()
            chunks=[];size=0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > 32 * 1024 * 1024:
                    return ''
                chunks.append(chunk)
        content=b''.join(chunks)
        if not content.startswith(b'%PDF-'):
            return ''
        reader=PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            return ''
        text='\n'.join(page.extract_text() or '' for page in reader.pages[:3])
        return abstract_from_text(text, title)
    except (requests.RequestException, PdfReadError, ValueError, OSError):
        return ''
