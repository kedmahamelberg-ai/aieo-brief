"""Free, deterministic article aliases generated with the static site."""
import hashlib
import re
from urllib.parse import urlencode


def article_alias(path):
    if not re.fullmatch(r'(story|research|culture)/[a-zA-Z0-9_-]+/index.html', path):
        raise ValueError('Invalid article path')
    return 's/' + hashlib.sha256(path.encode()).hexdigest()[:12] + '/index.html'


def short_link_routes(items, campaigns, baseurl):
    by_path = {item['path']: item for item in items}
    routes = {}
    for path in sorted(by_path):
        alias = article_alias(path)
        if alias in routes:
            raise ValueError('Short address collision; preserve existing aliases before resolving')
        routes[alias] = {'article_path': path, 'destination': baseurl + '/' + path}
    for entry in campaigns:
        slug = entry['slug']
        path = entry['article_path']
        if not re.fullmatch(r'[a-z0-9][a-z0-9-]{0,40}', slug):
            raise ValueError('Invalid campaign short address')
        if path not in by_path:
            raise ValueError('Campaign article missing: ' + path)
        tracking = entry['tracking']
        if set(tracking) != {'utm_source', 'utm_medium', 'utm_campaign', 'utm_content'}:
            raise ValueError('Incomplete campaign tracking')
        if tracking['utm_source'] not in ('facebook', 'linkedin', 'instagram'):
            raise ValueError('Invalid social platform')
        alias = 's/' + slug + '/index.html'
        if alias in routes:
            raise ValueError('Duplicate short address: ' + slug)
        routes[alias] = {'article_path': path, 'destination': baseurl + '/' + path + '?' + urlencode(tracking)}
    return routes
