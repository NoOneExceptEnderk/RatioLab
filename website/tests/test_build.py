"""Portable website integration checks: canonical sources, privacy and release failure safety."""
import copy
import hashlib
import io
import json
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.error import URLError
from urllib.parse import unquote, urlsplit
from xml.etree import ElementTree as ET

from markdown_it import MarkdownIt

WEBSITE = Path(__file__).resolve().parents[1]
REPO = WEBSITE.parent
sys.path.insert(0, str(WEBSITE))
import build
from seo import HOME_DESCRIPTION, HOME_TITLE, IMAGE, IMAGE_ALT, ORIGIN, canonical, json_script, metadata
from releases import REPOSITORY, asset_names, cache_document, fetch_latest, load_cache, validate_release
from render_docs import DOCUMENTS, render_markdown, rewrite_url

FIXTURE = json.loads((WEBSITE / 'tests/fixtures/github-release.json').read_text())


class Content(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.tags, self.pre, self.tables = [], [], 0
        self.current = None
        self.feed(source)
    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))
        if tag == 'pre':
            self.current = []
        if tag == 'table':
            self.tables += 1
    def handle_data(self, value):
        if self.current is not None:
            self.current.append(value)
    def handle_endtag(self, tag):
        if tag == 'pre':
            self.pre.append(''.join(self.current))
            self.current = None


def hashes(directory):
    return {p.relative_to(directory).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in directory.rglob('*') if p.is_file()}


def asset_versions(directory):
    """Assert every native local CSS/JS URL matches its actual output bytes."""
    references = {}
    for path in directory.rglob('*.html'):
        for tag, attrs in Content(path.read_text()).tags:
            url = attrs.get('src') if tag == 'script' else attrs.get('href') if tag == 'link' else None
            if not url:
                continue
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or Path(parsed.path).suffix not in ('.css', '.js'):
                continue
            target = (directory / unquote(parsed.path).lstrip('/') if parsed.path.startswith('/') else path.parent / unquote(parsed.path)).resolve()
            expected = 'v=' + hashlib.sha256(target.read_bytes()).hexdigest()[:16]
            if parsed.query != expected:
                raise AssertionError(f'{path}: {url} does not match {expected}')
            references[(path.relative_to(directory).as_posix(), parsed.path)] = parsed.query
    return references


class RenderingTests(unittest.TestCase):
    def test_only_strict_standalone_alias_before_heading_is_rendered_as_html(self):
        markdown = ('<a id="vecchio-titolo"></a>\n\n# New title\n\n'
                    '<script>alert(1)</script>\n\n<a id="bad" onclick="alert(1)"></a>\n\n'
                    '<a id="not-before-heading"></a>\n\nA paragraph.\n\n'
                    '[bad](javascript:alert%281%29)\n\n'
                    '```html\n<a id="inside-code"></a>\n```\n')
        body, headings = render_markdown(markdown, 'user-guide.md', 'docs/user-guide/index.html')
        page = Content(body)
        self.assertIn(('span', {'class': 'anchor-alias', 'aria-hidden': 'true', 'id': 'vecchio-titolo'}), page.tags)
        self.assertFalse(any(tag == 'script' or 'onclick' in attrs for tag, attrs in page.tags))
        ids = [attrs['id'] for _, attrs in page.tags if 'id' in attrs]
        self.assertNotIn('bad', ids)
        self.assertNotIn('not-before-heading', ids)
        self.assertNotIn('inside-code', ids)
        self.assertEqual(page.pre, ['<a id="inside-code"></a>\n'])
        self.assertIn('&lt;script&gt;', body)
        self.assertEqual(headings[0][2], 'new-title')
        for bad in ('javascript:alert(1)', 'JaVaScRiPt%3aalert(1)', 'data:text/html,evil', '//evil.example', '\\evil.example'):
            self.assertEqual(rewrite_url(bad, 'mcp.md', 'docs/mcp/index.html'), '#')

    def test_duplicate_ids_and_copy_targets_remain_unique(self):
        source = '<a id="same"></a>\n\n# Same\n\n## Same\n\n## ratiolab-code-1\n\n```sh\necho hello\n```\n'
        body, _ = render_markdown(source, 'mcp.md', 'docs/mcp/index.html')
        page = Content(body)
        ids = [attrs['id'] for _, attrs in page.tags if 'id' in attrs]
        self.assertEqual(len(ids), len(set(ids)))
        self.assertIn('same-1', ids)
        self.assertIn('same-2', ids)
        for _, attrs in page.tags:
            if 'data-copy-target' in attrs:
                self.assertIn(attrs['data-copy-target'], ids)
        with self.assertRaises(ValueError):
            render_markdown('<a id="same"></a>\n\n# A\n\n<a id="same"></a>\n\n# B', 'mcp.md', 'docs/mcp/index.html')

    def test_all_canonical_code_tables_and_legacy_anchors_survive(self):
        parser = MarkdownIt('commonmark', {'html': False}).enable('table')
        aliases = 0
        for document in DOCUMENTS:
            source = (REPO / 'docs' / document.source).read_text()
            body, _ = render_markdown(source, document.source, document.route)
            tokens, page = parser.parse(source), Content(body)
            self.assertEqual(page.pre, [t.content for t in tokens if t.type in ('fence', 'code_block')], document.source)
            self.assertEqual(page.tables, sum(t.type == 'table_open' for t in tokens), document.source)
            for anchor in re.findall(r'^<a id="([\w-]+)"></a>$', source, re.M):
                self.assertTrue(any(attrs.get('id') == anchor for _, attrs in page.tags), anchor)
                self.assertNotIn('&lt;a id=', body)
                aliases += 1
        self.assertGreaterEqual(aliases, 28)
        self.assertEqual(len(DOCUMENTS), 15)

    def test_source_links_follow_verified_revision_and_docs_stay_relative(self):
        revision = 'a' * 40
        self.assertEqual(rewrite_url('../../examples/example.config.json', 'technical/worm.md', 'docs/technical/worm/index.html', revision), REPOSITORY + '/blob/' + revision + '/examples/example.config.json')
        self.assertEqual(rewrite_url('../mcp.md#start-the-server', 'technical/worm.md', 'docs/technical/worm/index.html'), '../../mcp/index.html#start-the-server')
        self.assertEqual(rewrite_url(REPOSITORY + '/blob/main/docs/technical/strain-wave.md', 'user-guide.md', 'docs/user-guide/index.html'), '../technical/strain-wave/index.html')


class ReleaseTests(unittest.TestCase):
    def test_public_stable_assets_are_taken_from_api_not_inferred_links(self):
        payload = copy.deepcopy(FIXTURE)
        payload['assets'].append({'name': 'build-evidence.json'})
        release = validate_release(payload)
        self.assertEqual(release.version, '0.1.3')
        self.assertEqual(set(release.downloads), set(asset_names(release.version)))
        self.assertEqual(set(release.downloads.values()), {a['browser_download_url'] for a in FIXTURE['assets']})
        self.assertEqual(len(release.payload['assets']), 7)
        self.assertNotIn('build-evidence.json', json.dumps(release.payload))

    def test_partial_wrong_repository_and_unpublished_assets_are_rejected(self):
        mutations = [lambda p: p.update(draft=True), lambda p: p.update(prerelease=True),
                     lambda p: p.update(tag_name='v0.1.3-preview.1'), lambda p: p.update(published_at=None),
                     lambda p: p.update(html_url='https://github.com/elsewhere/RatioLab/releases/tag/v0.1.3'),
                     lambda p: p['assets'].pop(), lambda p: p['assets'][0].update(state='new'),
                     lambda p: p['assets'][0].update(size=0), lambda p: p['assets'][0].update(size=True),
                     lambda p: p['assets'][0].update(browser_download_url='https://evil.example/installer.exe'),
                     lambda p: p['assets'].append(copy.deepcopy(p['assets'][0]))]
        for mutate in mutations:
            payload = copy.deepcopy(FIXTURE)
            mutate(payload)
            with self.assertRaises(ValueError):
                validate_release(payload)

    def test_offline_requires_validated_cache_envelope_and_rechecks_assets(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'release.json'
            path.write_text(json.dumps(FIXTURE))
            with self.assertRaises(ValueError):
                load_cache(path)
            cached = cache_document(validate_release(FIXTURE))
            path.write_text(json.dumps(cached))
            self.assertEqual(load_cache(path).tag, 'v0.1.3')
            cached['release']['assets'][0]['size'] = -1
            path.write_text(json.dumps(cached))
            with self.assertRaises(ValueError):
                load_cache(path)

    def test_api_client_is_public_bounded_and_injectable(self):
        class Response(io.BytesIO):
            status = 200
        def opener(request, timeout):
            self.assertEqual(request.full_url, 'https://api.github.com/repos/NoOneExceptEnderk/RatioLab/releases/latest')
            self.assertNotIn('Authorization', request.headers)
            self.assertEqual(timeout, 30)
            return Response(json.dumps(FIXTURE).encode())
        self.assertEqual(fetch_latest(opener), FIXTURE)
        with self.assertRaises(ValueError):
            fetch_latest(lambda *_args, **_kwargs: Response(b' ' * 2_000_001))


class BuildTests(unittest.TestCase):
    def test_offline_site_allowlist_links_search_and_static_asset_integrity(self):
        before = hashes(WEBSITE / 'assets')
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'site'
            result = build.build(offline=True, output=output)
            self.assertEqual(result['files'], 36)
            self.assertEqual(result['pages'], 18)
            self.assertEqual(set(hashes(output)), set(build.public_files()))
            build.validate_output(output)
            for name in build.STATIC_ASSETS:
                self.assertEqual((output / 'assets' / name).read_bytes(), (WEBSITE / 'assets' / name).read_bytes())
            forbidden = ('.py', '.md', '.zip')
            self.assertFalse(any(p.endswith(forbidden) or '/work/' in p or 'docs-source' in p for p in hashes(output)))
            index = json.loads((output / 'assets/search-index.js').read_text().removeprefix('window.RATIOLAB_SEARCH_INDEX=').removesuffix(';\n'))
            self.assertEqual({e['page'] for e in index}, {'Documentation', *(d.title for d in DOCUMENTS)})
            self.assertTrue(any('budget_exceeded' in e['text'] for e in index))
            self.assertTrue(any('two independent' in e['text'].lower() for e in index))
            for entry in index:
                route, _, fragment = entry['url'].partition('#')
                page = build.Page((output / route / 'index.html').read_text())
                if fragment:
                    self.assertIn(fragment, page.ids)
            home = Content((output / 'index.html').read_text())
            downloads = {attrs['href'] for tag, attrs in home.tags if tag == 'a' and 'data-download' in attrs}
            release = load_cache(WEBSITE / 'release.json')
            self.assertEqual(downloads, {url for key, url in release.downloads.items() if key != 'checksums'})
        self.assertEqual(before, hashes(WEBSITE / 'assets'))

    def test_canonical_metadata_sitemap_and_schema_match_published_pages_and_release(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'site'
            build.build(offline=True, output=output)
            routes = ['index.html', 'docs/index.html', *(d.route for d in DOCUMENTS)]
            namespace = {'s': 'http://www.sitemaps.org/schemas/sitemap/0.9'}
            sitemap = ET.parse(output / 'sitemap.xml')
            self.assertEqual([item.text for item in sitemap.findall('s:url/s:loc', namespace)], [canonical(r) for r in routes])
            self.assertEqual({node.tag.rsplit('}', 1)[-1] for node in sitemap.iter()}, {'urlset', 'url', 'loc'})
            self.assertEqual((output / 'robots.txt').read_text(), 'User-agent: *\nAllow: /\n\nSitemap: https://ratiolab.dev/sitemap.xml\n')
            titles, descriptions = [], []
            for route in routes:
                source = (output / route).read_text()
                page = Content(source)
                metas = {attrs.get('name', attrs.get('property')): attrs.get('content') for tag, attrs in page.tags if tag == 'meta'}
                canonicals = [attrs['href'] for tag, attrs in page.tags if tag == 'link' and attrs.get('rel') == 'canonical']
                self.assertEqual(canonicals, [canonical(route)])
                self.assertTrue(canonicals[0].startswith(ORIGIN + '/'))
                self.assertTrue(canonicals[0].endswith('/'))
                self.assertNotIn('robots', metas)
                title = re.search(r'<title>(.*?)</title>', source).group(1)
                titles.append(title)
                descriptions.append(metas['description'])
                for prefix in ('og:', 'twitter:'):
                    self.assertEqual(metas[prefix + 'image'], IMAGE)
                    self.assertEqual(metas[prefix + 'image:alt'], IMAGE_ALT)
                    self.assertEqual(metas[prefix + 'description'], metas['description'])
                self.assertEqual(metas['og:url'], canonical(route))
                self.assertEqual(metas['twitter:card'], 'summary_large_image')
                self.assertNotIn('twitter:site', metas)
                for tag, attrs in page.tags:
                    href = attrs.get('href', '')
                    if tag == 'a' and not urlsplit(href).scheme:
                        self.assertFalse(urlsplit(href).path.endswith('index.html'), href)
                structured = json.loads(re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.S).group(1))
                if route == 'index.html':
                    self.assertEqual(title, HOME_TITLE)
                    self.assertEqual(metas['description'], HOME_DESCRIPTION)
                    graph = {node['@type']: node for node in structured['@graph']}
                    self.assertEqual(set(graph), {'WebSite', 'SoftwareApplication'})
                    software = graph['SoftwareApplication']
                    release = load_cache(WEBSITE / 'release.json')
                    self.assertEqual(software['softwareVersion'], release.version)
                    self.assertEqual(set(software['downloadUrl']), {url for key, url in release.downloads.items() if key != 'checksums'})
                    self.assertEqual(software['offers']['price'], '0')
                    self.assertTrue(software['isAccessibleForFree'])
                    self.assertTrue(software['license'].endswith('/LICENSE'))
                    self.assertNotIn('aggregateRating', software)
                    self.assertNotIn('review', software)
                elif route == 'docs/index.html':
                    self.assertEqual(structured['@type'], 'CollectionPage')
                    self.assertEqual(structured['name'], 'Documentation')
                    self.assertEqual(structured['url'], canonical(route))
                    self.assertEqual(structured['isPartOf'], {'@id': ORIGIN + '/#website'})
                else:
                    self.assertEqual(structured['@type'], 'BreadcrumbList')
                    crumbs = structured['itemListElement']
                    self.assertEqual(len(crumbs), 2)
                    self.assertEqual(crumbs[0]['item'], ORIGIN + '/docs/')
                    self.assertEqual(crumbs[-1]['item'], canonical(route))
                    self.assertEqual([c['position'] for c in crumbs], list(range(1, len(crumbs) + 1)))
            self.assertEqual(len(set(titles)), 17)
            self.assertEqual(len(set(descriptions)), 17)

    def test_404_is_noindex_uses_root_assets_and_upgrades_old_output_safely(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'site'
            build.build(offline=True, output=output)
            for relative in ('404.html', 'sitemap.xml', 'robots.txt'):
                (output / relative).unlink()
            self.assertEqual(len(hashes(output)), 33)
            build.build(offline=True, output=output)
            page = Content((output / '404.html').read_text())
            metas = {a.get('name'): a.get('content') for tag, a in page.tags if tag == 'meta'}
            self.assertEqual(metas['robots'], 'noindex, follow')
            self.assertFalse(any(tag == 'link' and a.get('rel') == 'canonical' for tag, a in page.tags))
            for tag, attrs in page.tags:
                for key in ('src', 'href'):
                    if key in attrs:
                        self.assertTrue(attrs[key].startswith('/'), (tag, attrs[key]))
            self.assertEqual(len(hashes(output)), 36)
            asset_versions(output)
            previous = hashes(output)
            build.build(offline=True, output=output)
            self.assertEqual(previous, hashes(output))
            (output / 'private.txt').write_text('keep')
            with self.assertRaises(ValueError):
                build.build(offline=True, output=output)
            self.assertEqual((output / 'private.txt').read_text(), 'keep')

    def test_metadata_escapes_attributes_and_structured_data_script_boundaries(self):
        unsafe = '</script><script>alert("x")</script> & \"quoted\" \u2028'
        source = metadata('index.html', unsafe, unsafe, schema={'name': unsafe})
        page = Content(source)
        scripts = [(tag, attrs) for tag, attrs in page.tags if tag == 'script']
        self.assertEqual(scripts, [('script', {'type': 'application/ld+json'})])
        self.assertNotIn('<title></script>', source)
        self.assertIn('&lt;/script&gt;', source)
        encoded = re.search(r'<script type="application/ld\+json">(.*?)</script>', source, re.S).group(1)
        self.assertEqual(json.loads(encoded), {'name': unsafe})
        self.assertNotIn('<', encoded)
        self.assertNotIn('\u2028', encoded)
        self.assertEqual(json.loads(json_script({'x': unsafe}).split('>', 1)[1].rsplit('</script>', 1)[0]), {'x': unsafe})

    def test_asset_urls_are_deterministic_and_only_changed_content_is_invalidated(self):
        with tempfile.TemporaryDirectory() as directory:
            website = Path(directory) / 'website'
            shutil.copytree(WEBSITE, website)
            output = Path(directory) / 'site'
            with patch('build.WEBSITE', website):
                build.build(offline=True, output=output)
                before = hashes(output)
                versions = asset_versions(output)
                self.assertTrue(versions)
                css_pages = {route for route, url in versions if Path(url).name == 'site.css'}
                self.assertEqual(css_pages, {'index.html', '404.html', 'docs/index.html', *(d.route for d in DOCUMENTS)})
                build.version_assets(output)
                self.assertEqual(before, hashes(output), 'Finalization must be idempotent')
                build.build(offline=True, output=output)
                self.assertEqual(before, hashes(output), 'Identical offline builds must be deterministic')
                source = website / 'assets/site.css'
                source.write_text(source.read_text() + '\n/* cache freshness probe */\n')
                build.build(offline=True, output=output)
                changed = asset_versions(output)
                self.assertEqual(versions.keys(), changed.keys())
                for key, previous in versions.items():
                    if key[1].endswith('/site.css'):
                        self.assertNotEqual(previous, changed[key], key)
                    else:
                        self.assertEqual(previous, changed[key], key)
                self.assertEqual(set(hashes(output)), set(build.public_files()))
                for name in build.STATIC_ASSETS:
                    self.assertEqual((output / 'assets' / name).read_bytes(), (website / 'assets' / name).read_bytes())

    def test_asset_finalization_leaves_external_urls_and_non_asset_content_unchanged(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'site'
            build.build(offline=True, output=output)
            page = output / 'docs/index.html'
            untouched = ('<a href="../assets/site.js">Source link</a>'
                         '<script src="https://example.com/assets/site.js"></script>'
                         '<script src="//example.com/assets/site.js"></script>'
                         '<script>const sample = \'<script src="assets/site.js">\';</script>'
                         '<pre>&lt;script src="assets/site.js"&gt;</pre>'
                         '<link rel="icon" href="../assets/site.css">'
                         '<script src="../assets/not-allowlisted.js"></script>')
            page.write_text(page.read_text() + untouched +
                            '<script src="../assets/site.js?old=1#probe"></script>')
            build.version_assets(output)
            rewritten = page.read_text()
            self.assertIn(untouched, rewritten)
            digest = hashlib.sha256((output / 'assets/site.js').read_bytes()).hexdigest()[:16]
            self.assertIn(f'<script src="../assets/site.js?v={digest}#probe"></script>', rewritten)
            build.version_assets(output)
            self.assertEqual(rewritten, page.read_text())

    def test_canonical_edit_refreshes_html_and_search_on_every_build(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'repository'
            shutil.copytree(REPO / 'docs', repo / 'docs')
            doc = repo / 'docs/user-guide.md'
            first = 'Canonical freshness firstmarker'
            second = 'Canonical freshness secondmarker'
            doc.write_text(doc.read_text() + '\n## Freshness probe\n\n' + first + '\n')
            output = repo / '_site'
            build.build(offline=True, repository_root=repo)
            for relative in ('docs/user-guide/index.html', 'assets/search-index.js'):
                self.assertIn(first, (output / relative).read_text())
            before_versions = asset_versions(output)
            doc.write_text(doc.read_text().replace(first, second))
            build.build(offline=True, repository_root=repo)
            for relative in ('docs/user-guide/index.html', 'assets/search-index.js'):
                self.assertIn(second, (output / relative).read_text())
                self.assertNotIn(first, (output / relative).read_text())
            after_versions = asset_versions(output)
            for key, previous in before_versions.items():
                if key[1].endswith('/search-index.js'):
                    self.assertNotEqual(previous, after_versions[key], key)
                else:
                    self.assertEqual(previous, after_versions[key], key)

    def test_api_failure_or_missing_canonical_source_preserves_prior_output(self):
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory) / 'repository'
            shutil.copytree(REPO / 'docs', repo / 'docs')
            output = repo / '_site'
            build.build(offline=True, repository_root=repo)
            previous, cache = hashes(output), (WEBSITE / 'release.json').read_bytes()
            invalid = copy.deepcopy(FIXTURE)
            invalid['assets'].pop()
            for fetcher in (lambda: invalid, lambda: (_ for _ in ()).throw(URLError('offline'))):
                with self.assertRaises((ValueError, OSError)):
                    build.build(repository_root=repo, release_fetcher=fetcher)
                self.assertEqual(previous, hashes(output))
                self.assertEqual(cache, (WEBSITE / 'release.json').read_bytes())
            (repo / 'docs/mcp.md').unlink()
            with self.assertRaises(OSError):
                build.build(offline=True, repository_root=repo)
            self.assertEqual(previous, hashes(output))

    def test_normal_build_refreshes_only_validated_public_cache(self):
        with tempfile.TemporaryDirectory() as directory, patch('build.atomic_text') as write:
            output = Path(directory) / 'site'
            result = build.build(output=output, release_fetcher=lambda: copy.deepcopy(FIXTURE))
            self.assertEqual(result['version'], '0.1.3')
            cached = json.loads(write.call_args.args[1])
            self.assertEqual(cached['release'], validate_release(FIXTURE).payload)
            self.assertEqual(len(cached['release']['assets']), 7)
            self.assertEqual(set(hashes(output)), set(build.public_files()))

    def test_output_never_replaces_sources_arbitrary_files_or_symlinks(self):
        for destination in (REPO, REPO / 'docs', WEBSITE, WEBSITE / 'assets', REPO / 'tests'):
            with self.assertRaises(ValueError):
                build.build(offline=True, output=destination)
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / 'existing'
            target.mkdir()
            private = target / 'important.txt'
            private.write_text('keep this')
            with self.assertRaises(ValueError):
                build.build(offline=True, output=target)
            self.assertEqual(private.read_text(), 'keep this')
            link = Path(directory) / 'symlink'
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaises(ValueError):
                build.build(offline=True, output=link)
            self.assertEqual(private.read_text(), 'keep this')

    def test_provenance_uses_commit_only_for_verified_clean_canonical_docs(self):
        revision = 'a' * 40
        def runner(args, **_kwargs):
            return SimpleNamespace(stdout=revision if 'rev-parse' in args else '')
        with patch('build.subprocess.run', side_effect=runner):
            self.assertEqual(build.source_provenance(REPO, {})[0], revision)
            self.assertEqual(build.source_provenance(REPO, {'GITHUB_SHA': 'b' * 40})[0], 'main')
        def dirty(args, **_kwargs):
            return SimpleNamespace(stdout=revision if 'rev-parse' in args else ' M docs/user-guide.md' if 'status' in args else '')
        with patch('build.subprocess.run', side_effect=dirty):
            self.assertEqual(build.source_provenance(REPO, {})[0], 'main')
        with patch('build.subprocess.run', side_effect=OSError('no git')):
            self.assertEqual(build.source_provenance(REPO, {})[0], 'main')


if __name__ == '__main__':
    unittest.main()
