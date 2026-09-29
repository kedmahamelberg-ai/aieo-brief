"""Persist readable article URLs while retaining every previously published path."""
import hashlib
import re
import unicodedata

PATH = re.compile(r'(story|research|culture)/[a-zA-Z0-9_-]+/index.html')
STOP = set('a an the and or of to in on at for from with by as is are was were be been being that this these those its it their into yet highlighted noted says said reports reported'.split())


def title_slug(title):
    title = unicodedata.normalize('NFKD', title.replace('‑', '-').replace('–', '-'))
    title = title.encode('ascii', 'ignore').decode().lower()
    words = re.findall(r'[a-z0-9]+(?:-[a-z0-9]+)*', title)
    words = [word for word in words if word not in STOP]
    # Preserve a contrast near the end of a long headline rather than cutting it off.
    if len(words) > 8:
        words = words[:6] + words[-2:]
    selected = []
    for word in words:
        if len('-'.join(selected + [word])) > 90:
            break
        selected.append(word)
    return '-'.join(selected)


def assign_article_urls(items, previous):
    """Mutate public cards; keys (comments/saves) never change. Fail on reused URLs."""
    old = {item['key']: item for item in previous}
    owners = {}

    def reserve(path, key):
        if not PATH.fullmatch(path):
            raise ValueError('Invalid retained article path: ' + path)
        if path in owners and owners[path] != key:
            raise ValueError('Article URL reused: ' + path)
        owners[path] = key

    for item in previous + items:
        for path in [item['path']] + item.get('legacy_paths', []):
            reserve(path, item['key'])
    for item in sorted(items, key=lambda row: row['key']):
        if item['kind'] not in ('news', 'research'):
            continue
        prior = old.get(item['key'], {})
        aliases = set(item.get('legacy_paths', []) + prior.get('legacy_paths', []))
        aliases.add(item['path'])
        if prior.get('path'):
            aliases.add(prior['path'])
        if prior.get('url_slug_version') == 1:
            path = prior['path']
        else:
            # Pending English notices are not article titles. Keep the original
            # address until a real public headline is available.
            slug = title_slug(item.get('headline', '')) if item.get('english_status') != 'pending' else ''
            if not slug:
                continue
            section = 'story' if item['kind'] == 'news' else 'research'
            path = f'{section}/{slug}/index.html'
            if path in owners and owners[path] != item['key']:
                suffix = hashlib.sha256(item['key'].encode()).hexdigest()[:12]
                path = f'{section}/{slug}-{suffix}/index.html'
        reserve(path, item['key'])
        item.update(path=path, slug=path.split('/')[1], url_slug_version=1,
                    legacy_paths=sorted(aliases - {path}))
