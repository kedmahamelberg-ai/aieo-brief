"""Private, version-bound reading of complete extractable paper text."""
import hashlib
import io
import re
import unicodedata
from datetime import date
from urllib.parse import urlparse
import requests

READING_VERSION = 'paper-practitioner-v1'


def needs_upgrade(row):
    return (not row.get('has_editorial') or row.get('research_reading_version') != READING_VERSION
            or (row.get('evidence_scope') != 'paper_text' and row.get('full_text_retry_after', '9999') <= date.today().isoformat()))


def allowed_pdf(url):
    host = (urlparse(url).hostname or '').lower()
    return url.startswith('https://') and any(host == d or host.endswith('.' + d) for d in ('arxiv.org', 'pnas.org', 'ssrn.com'))


def extract_paper(content, title):
    from pypdf import PdfReader
    if not content.startswith(b'%PDF-'):
        raise ValueError('not_pdf')
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted or not 2 <= len(reader.pages) <= 120:
        raise ValueError('unsupported_pdf')
    pages = [unicodedata.normalize('NFKC', p.extract_text() or '') for p in reader.pages]
    normal = lambda s: re.sub(r'\W+', '', s).casefold()
    if normal(title) not in normal(pages[0]):
        raise ValueError('paper_identity_mismatch')
    # Do not call a partial or image-only extraction a paper reading.
    if any(len(re.sub(r'\s+', '', p)) < 80 for p in pages):
        raise ValueError('incomplete_text_extraction')
    text = '\n\n'.join('[PDF page %d]\n%s' % (i + 1, p) for i, p in enumerate(pages))
    if len(text) < 2500 or len(text) > 210000:
        raise ValueError('paper_reading_size')
    return {'text': text, 'pages': len(pages), 'pdf_sha256': hashlib.sha256(content).hexdigest(),
            'text_sha256': hashlib.sha256(text.encode()).hexdigest()}


def read_paper(paper):
    url = paper.get('pdf_url', '')
    if not url and paper.get('arxiv_id'):
        url = 'https://arxiv.org/pdf/' + paper['arxiv_id']
    if not allowed_pdf(url):
        return {'status': 'no_supported_pdf'}
    try:
        # Follow only redirects within the original-source allowlist.
        for _ in range(5):
            with requests.get(url, stream=True, allow_redirects=False, timeout=45,
                              headers={'User-Agent': 'AIEO-Brief (paper reading; https://brief.hamelberg-ai.com)'}) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = urljoin(url, response.headers.get('Location', ''))
                    if not allowed_pdf(url):
                        return {'status': 'unsupported_pdf_redirect'}
                    continue
                response.raise_for_status()
                parts = []; size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > 32 * 1024 * 1024:
                        return {'status': 'pdf_size_limit'}
                    parts.append(chunk)
                return {**extract_paper(b''.join(parts), paper['original_headline']), 'status': 'read', 'url': url}
        return {'status': 'pdf_redirect_limit'}
    except requests.RequestException:
        return {'status': 'pdf_unavailable'}
    except Exception:
        return {'status': 'pdf_text_unreadable'}
