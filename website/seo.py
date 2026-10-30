"""Deterministic public search metadata; no network or application dependencies."""
from __future__ import annotations

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from releases import REPOSITORY

ORIGIN = 'https://ratiolab.dev'
HOME_TITLE = 'RatioLab — Open-source gear and reducer design software'
HOME_DESCRIPTION = 'Open-source desktop software for parametric gears and reducers. Set dimensions, inspect 3D geometry and motion, and export designs for CAD or 3D printing.'
IMAGE = ORIGIN + '/assets/workspace.png'
IMAGE_ALT = 'RatioLab desktop workspace with model parameters, a planetary reducer preview and geometric results.'


def canonical(route):
    if not route.endswith('index.html') or route.startswith('/') or '..' in route.split('/'):
        raise ValueError('Canonical pages must have a relative index.html route')
    return ORIGIN + '/' + route.removesuffix('index.html')


def json_script(data):
    serialized = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
    for character, escaped in (('<', '\\u003c'), ('>', '\\u003e'), ('&', '\\u0026'), ('\u2028', '\\u2028'), ('\u2029', '\\u2029')):
        serialized = serialized.replace(character, escaped)
    return '<script type="application/ld+json">' + serialized + '</script>'


def home_schema(release):
    return {'@context': 'https://schema.org', '@graph': [
        {'@type': 'WebSite', '@id': ORIGIN + '/#website', 'url': ORIGIN + '/',
         'name': 'RatioLab', 'description': HOME_DESCRIPTION, 'inLanguage': 'en'},
        {'@type': 'SoftwareApplication', '@id': ORIGIN + '/#software', 'name': 'RatioLab',
         'url': ORIGIN + '/', 'description': HOME_DESCRIPTION, 'applicationCategory': 'DesignApplication',
         'operatingSystem': ['Windows 11', 'macOS 15 or later', 'Linux with glibc 2.39 or later'],
         'license': REPOSITORY + '/blob/main/LICENSE', 'isAccessibleForFree': True,
         'offers': {'@type': 'Offer', 'price': '0'}, 'softwareVersion': release.version,
         'downloadUrl': [url for key, url in release.downloads.items() if key != 'checksums'],
         'screenshot': IMAGE, 'softwareHelp': ORIGIN + '/docs/'}]}


def documentation_schema(route, title):
    if route == 'docs/index.html':
        return {'@context': 'https://schema.org', '@type': 'CollectionPage',
                'name': title, 'url': canonical(route), 'isPartOf': {'@id': ORIGIN + '/#website'}}
    items = [{'@type': 'ListItem', 'position': 1, 'name': 'Documentation', 'item': ORIGIN + '/docs/'}]
    items.append({'@type': 'ListItem', 'position': 2, 'name': title, 'item': canonical(route)})
    return {'@context': 'https://schema.org', '@type': 'BreadcrumbList', 'itemListElement': items}


def metadata(route, title, description, *, schema=None, noindex=False):
    escape = lambda value: html.escape(value, quote=True)
    lines = ['<title>' + escape(title) + '</title>',
             '<meta name="description" content="' + escape(description) + '">']
    if noindex:
        lines.append('<meta name="robots" content="noindex, follow">')
    else:
        url = canonical(route)
        lines.extend(['<link rel="canonical" href="' + url + '">',
                      '<meta property="og:type" content="website">',
                      '<meta property="og:site_name" content="RatioLab">',
                      '<meta property="og:locale" content="en_US">',
                      '<meta property="og:url" content="' + url + '">'])
        for prefix, attr in (('og:', 'property'), ('twitter:', 'name')):
            for key, value in (('title', title), ('description', description), ('image', IMAGE), ('image:alt', IMAGE_ALT)):
                lines.append(f'<meta {attr}="{prefix}{key}" content="{escape(value)}">')
        lines.extend(['<meta property="og:image:width" content="1280">',
                      '<meta property="og:image:height" content="800">',
                      '<meta name="twitter:card" content="summary_large_image">'])
    if schema is not None:
        lines.append(json_script(schema))
    return '\n  '.join(lines)


def discovery_files(output, routes):
    namespace = 'http://www.sitemaps.org/schemas/sitemap/0.9'
    ET.register_namespace('', namespace)
    root = ET.Element('{' + namespace + '}urlset')
    for route in routes:
        item = ET.SubElement(root, '{' + namespace + '}url')
        ET.SubElement(item, '{' + namespace + '}loc').text = canonical(route)
    (output / 'sitemap.xml').write_bytes(ET.tostring(root, encoding='utf-8', xml_declaration=True) + b'\n')
    (output / 'robots.txt').write_text('User-agent: *\nAllow: /\n\nSitemap: ' + ORIGIN + '/sitemap.xml\n', encoding='utf-8')
    head = metadata(None, 'Page not found — RatioLab', 'The requested RatioLab page could not be found.', noindex=True)
    page = '''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><meta name="color-scheme" content="dark">
  ''' + head + '''
  <link rel="icon" href="/assets/ratiolab-icon.png"><link rel="stylesheet" href="/assets/site.css">
</head><body><header class="site-header shell"><a class="brand" href="/" aria-label="RatioLab home"><img src="/assets/ratiolab-logo-dark.png" alt="RatioLab"></a></header>
<main class="shell docs-main prose" id="content"><h1>Page not found</h1><p>The requested page may have moved or the address may be incorrect.</p><p><a href="/">RatioLab home</a> · <a href="/docs/">Documentation</a></p></main></body></html>
'''
    (output / '404.html').write_text(page, encoding='utf-8')


def directory_links(output, routes):
    """Rewrite actual internal anchor hrefs only; preserve examples and fragments."""
    output = output.resolve()
    targets = {(output / route).resolve() for route in routes}
    attributes = re.compile(r'([\w:-]+)\s*=\s*([\"\'])(.*?)\2', re.S)

    class Links(HTMLParser):
        def __init__(self, source, path):
            super().__init__(convert_charrefs=False)
            self.path, self.edits = path, []
            self.lines = source.splitlines(keepends=True)
            self.feed(source)

        def handle_starttag(self, tag, attrs):
            if tag != 'a':
                return
            line, column = self.getpos()
            start = sum(map(len, self.lines[:line - 1])) + column
            for match in attributes.finditer(self.get_starttag_text()):
                if match[1].lower() != 'href':
                    continue
                parsed = urlsplit(html.unescape(match[3]))
                if parsed.scheme or parsed.netloc or not parsed.path.endswith('index.html'):
                    continue
                decoded = unquote(parsed.path)
                target = (output / decoded.lstrip('/') if decoded.startswith('/') else self.path.parent / decoded).resolve()
                if target not in targets:
                    continue
                url = parsed.path.removesuffix('index.html') or './'
                if parsed.query:
                    url += '?' + parsed.query
                if parsed.fragment:
                    url += '#' + parsed.fragment
                self.edits.append((start + match.start(3), start + match.end(3), html.escape(url, quote=True)))

    for path in output.rglob('*.html'):
        source = path.read_text(encoding='utf-8')
        links = Links(source, path)
        for start, end, value in reversed(links.edits):
            source = source[:start] + value + source[end:]
        path.write_text(source, encoding='utf-8')
