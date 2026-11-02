"""Private, version-bound reading of complete extractable paper text."""
import hashlib
import io
import re
import unicodedata
from datetime import date
from urllib.parse import unquote, urlparse
import requests

READING_VERSION = 'paper-practitioner-v1'
PDF_READER_VERSION = 2
HTML_READER_VERSION = 1
MAX_PDF_BYTES = 64 * 1024 * 1024
MAX_HTML_BYTES = 8 * 1024 * 1024
MAX_PAPER_CHARS = 600000


def verified_paper_reading(row):
    """A stored full-paper label needs the completed reading's source proof."""
    return (row.get('summary_basis') == 'Summary of the paper'
            and row.get('full_text_status') == 'read'
            and ((type(row.get('paper_pages')) is int and row['paper_pages'] >= 1)
                 or (type(row.get('paper_sections')) is int and row['paper_sections'] >= 2
                     and row.get('paper_source_url') == 'https://arxiv.org/html/' + str(row.get('arxiv_id', ''))
                     and bool(re.fullmatch(r'\d{4}\.\d{4,5}(?:v\d+)?', str(row.get('arxiv_id', ''))))))
            and bool(re.fullmatch(r'[0-9a-f]{64}', row.get('paper_text_sha256', ''))))


def restore_reading_scope(row):
    """Repair a collector-scope overwrite only when full-paper proof survives."""
    if row.get('evidence_scope') != 'paper_text' and verified_paper_reading(row):
        return {**row, 'evidence_scope': 'paper_text'}
    return row


def withhold_abstract_summary(row):
    """Remove editorial copy unless a complete paper reading is cryptographically proven."""
    if row.get('has_editorial') and row.get('evidence_scope') != 'paper_text':
        return {**row,
                'has_editorial': False,
                'headline': row.get('original_headline') or row.get('headline', ''),
                'deck': 'A checked summary requires reading the full paper. Open the paper for its source and access options.',
                'what_happened': '',
                'why_it_matters': '',
                'body_paragraphs': [],
                'limitation': '',
                'summary_basis': 'Original paper title',
                'reading_minutes': 1,
                'summary_status': 'full_text_required'}
    return row


def needs_upgrade(row):
    return (not row.get('has_editorial') or bool(style_problem(row)) or row.get('research_reading_version') != READING_VERSION
            or (row.get('evidence_scope') != 'paper_text' and row.get('pdf_reader_version', 1) < PDF_READER_VERSION
                and row.get('full_text_status') in ('pdf_size_limit', 'pdf_text_unreadable'))
            or (row.get('evidence_scope') != 'paper_text' and row.get('arxiv_id')
                and row.get('html_reader_version', 0) < HTML_READER_VERSION
                and row.get('full_text_status') in ('pdf_size_limit', 'pdf_text_unreadable', 'pdf_unavailable', 'incomplete_text_extraction', 'paper_reading_size'))
            or (row.get('evidence_scope') != 'paper_text' and row.get('full_text_retry_after', '9999') <= date.today().isoformat()))


def allowed_pdf(url):
    host = (urlparse(url).hostname or '').lower()
    return url.startswith('https://') and any(host == d or host.endswith('.' + d) for d in ('arxiv.org', 'pnas.org', 'ssrn.com'))


def publisher_pdf_urls(doi, links):
    """Accept Crossref's publisher PDF even when it labels its type unspecified."""
    urls = []
    for link in links or []:
        url = link.get('URL', '')
        if not allowed_pdf(url):
            continue
        path = unquote(urlparse(url).path).lower()
        official_pnas = (doi.lower().startswith('10.1073/pnas.') and
                         (urlparse(url).hostname or '').lower() in ('pnas.org', 'www.pnas.org') and
                         path == '/doi/pdf/' + doi.lower())
        if link.get('content-type') == 'application/pdf' or official_pnas:
            if url not in urls:
                urls.append(url)
    return urls


def extract_paper(content, title):
    from pypdf import PdfReader
    if not content.startswith(b'%PDF-'):
        raise ValueError('not_pdf')
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted or not 2 <= len(reader.pages) <= 200:
        raise ValueError('unsupported_pdf')
    pages = [re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', unicodedata.normalize('NFKC', p.extract_text() or '')) for p in reader.pages]
    def title_words(value):
        value = value.replace(r'\ell', 'ℓ').replace(r'\infty', '∞').replace('_', '')
        return re.findall(r'\w+|∞', unicodedata.normalize('NFKC', value).casefold())

    expected = title_words(title)
    actual = title_words(pages[0][:500])
    exact = ''.join(expected) in ''.join(actual)
    # Publisher metadata sometimes omits a year or article in the PDF title.
    # Permit only a few inserted words, never substitutions or missing title words.
    near = False
    if not exact and len(expected) >= 8:
        for start in range(min(len(actual), 30)):
            if actual[start] != expected[0]:
                continue
            pos = start; extras = 0
            for word in expected[1:]:
                pos += 1
                while pos < len(actual) and actual[pos] != word and extras < 3:
                    pos += 1; extras += 1
                if pos >= len(actual) or actual[pos] != word:
                    break
            else:
                near = True
                break
    if not (exact or near):
        raise ValueError('paper_identity_mismatch')
    # A figure or formula page can have little selectable text without making
    # the surrounding, fully extracted paper an abstract-only reading.
    sparse_pages = sum(len(re.sub(r'\s+', '', p)) < 80 for p in pages)
    if sparse_pages > (1 if len(pages) >= 10 else 0):
        raise ValueError('incomplete_text_extraction')
    text = '\n\n'.join('[PDF page %d]\n%s' % (i + 1, p) for i, p in enumerate(pages))
    if len(text) < 2500 or len(text) > MAX_PAPER_CHARS:
        raise ValueError('paper_reading_size')
    return {'text': text, 'pages': len(pages), 'pdf_sha256': hashlib.sha256(content).hexdigest(),
            'text_sha256': hashlib.sha256(text.encode()).hexdigest()}


def extract_arxiv_html(content, title):
    """Read the complete arXiv article, excluding the site's surrounding UI."""
    from bs4 import BeautifulSoup
    if b'</article>' not in content.lower():
        raise ValueError('incomplete_html_article')
    soup = BeautifulSoup(content, 'html.parser')
    article = soup.select_one('article.ltx_document')
    heading = article.select_one('h1.ltx_title_document') if article else None
    if not heading:
        raise ValueError('html_article_missing')
    words = lambda value: re.findall(r'\w+', unicodedata.normalize('NFKC', value).casefold())
    if words(heading.get_text(' ', strip=True)) != words(title):
        raise ValueError('paper_identity_mismatch')
    sections = article.find_all('section', recursive=False)
    if len(sections) < 2 or not article.select_one('.ltx_abstract'):
        raise ValueError('incomplete_html_article')
    for element in article.select('script, style'):
        element.decompose()
    text = '\n\n'.join(element.get_text(' ', strip=True) for element in article.children
                       if getattr(element, 'name', None) and element.get_text(' ', strip=True))
    text = unicodedata.normalize('NFKC', text)
    if not 2500 <= len(text) <= MAX_PAPER_CHARS:
        raise ValueError('paper_reading_size')
    return {'text': text, 'sections': len(sections), 'html_sha256': hashlib.sha256(content).hexdigest(),
            'text_sha256': hashlib.sha256(text.encode()).hexdigest()}


def read_arxiv_html(paper):
    arxiv_id = str(paper.get('arxiv_id') or '')
    if not re.fullmatch(r'\d{4}\.\d{4,5}(?:v\d+)?', arxiv_id):
        return {'status': 'html_unavailable'}
    url = 'https://arxiv.org/html/' + arxiv_id
    try:
        with requests.get(url, stream=True, allow_redirects=False, timeout=45,
                          headers={'User-Agent': 'AIEO-Brief (paper reading; https://brief.hamelberg-ai.com)'}) as response:
            if response.status_code != 200 or 'text/html' not in response.headers.get('Content-Type', '').lower():
                return {'status': 'html_unavailable'}
            parts = []; size = 0
            for chunk in response.iter_content(65536):
                size += len(chunk)
                if size > MAX_HTML_BYTES:
                    return {'status': 'html_size_limit'}
                parts.append(chunk)
        return {**extract_arxiv_html(b''.join(parts), paper['original_headline']),
                'status': 'read', 'url': url, 'format': 'arxiv_html'}
    except requests.RequestException:
        return {'status': 'html_unavailable'}
    except ValueError as error:
        return {'status': str(error) if str(error) in ('html_article_missing', 'incomplete_html_article',
                                                     'paper_identity_mismatch', 'paper_reading_size') else 'html_text_unreadable'}


def read_paper(paper):
    url = paper.get('pdf_url', '')
    if not url and paper.get('arxiv_id'):
        url = 'https://arxiv.org/pdf/' + paper['arxiv_id']
    if not allowed_pdf(url):
        return read_arxiv_html(paper) if paper.get('arxiv_id') else {'status': 'no_supported_pdf'}
    try:
        # Follow only redirects within the original-source allowlist.
        for _ in range(5):
            with requests.get(url, stream=True, allow_redirects=False, timeout=45,
                              headers={'User-Agent': 'AIEO-Brief (paper reading; https://brief.hamelberg-ai.com)'}) as response:
                if response.is_redirect:
                    from urllib.parse import urljoin
                    url = urljoin(url, response.headers.get('Location', ''))
                    if not allowed_pdf(url):
                        return read_arxiv_html(paper) if paper.get('arxiv_id') else {'status': 'unsupported_pdf_redirect'}
                    continue
                response.raise_for_status()
                parts = []; size = 0
                for chunk in response.iter_content(65536):
                    size += len(chunk)
                    if size > MAX_PDF_BYTES:
                        return read_arxiv_html(paper) if paper.get('arxiv_id') else {'status': 'pdf_size_limit'}
                    parts.append(chunk)
                try:
                    return {**extract_paper(b''.join(parts), paper['original_headline']), 'status': 'read', 'url': url, 'format': 'pdf'}
                except Exception:
                    if paper.get('arxiv_id'):
                        return read_arxiv_html(paper)
                    raise
        return read_arxiv_html(paper) if paper.get('arxiv_id') else {'status': 'pdf_redirect_limit'}
    except requests.RequestException:
        return read_arxiv_html(paper) if paper.get('arxiv_id') else {'status': 'pdf_unavailable'}
    except ValueError as error:
        return {'status': str(error) if str(error) in ('not_pdf', 'unsupported_pdf', 'paper_identity_mismatch',
                                                       'incomplete_text_extraction', 'paper_reading_size') else 'pdf_text_unreadable'}
    except Exception:
        return {'status': 'pdf_text_unreadable'}


def style_problem(row):
    """Reader-facing research must not require an unexplained acronym glossary."""
    title=row.get('editorial_headline',row.get('headline',''))
    public=' '.join(str(row.get(k,'')) for k in ('editorial_headline','headline','editorial_deck','deck','what_happened','why_it_matters','limitation'))+' '+' '.join(row.get('body_paragraphs',[]))
    acronyms=set(re.findall(r'\b[A-Z][A-Z0-9-]{1,}\b',public))-{'AI','IT','API','GPU','CPU','PDF','EU','UK','US','USA','UN','NASA'}
    if public.count('?')>1:return 'Use at most one reflective question across the entire brief.'
    if acronyms:return 'Replace unexplained acronyms with everyday words throughout: '+', '.join(sorted(acronyms))
    if re.search(r'\b(native|unified|readiness|benchmark|paradigm|latent|quantization|distillation)\b|with (?:limits|caveats)|abstract.only',title,re.I):
        return 'Rewrite the title around the concrete finding in ordinary words, without method jargon or boilerplate about limits.'
    return ''
