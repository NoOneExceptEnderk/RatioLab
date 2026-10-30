"""Public GitHub release discovery and strictly validated offline cache. Stdlib only."""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.request import Request, urlopen

REPOSITORY = 'https://github.com/NoOneExceptEnderk/RatioLab'
LATEST_API = 'https://api.github.com/repos/NoOneExceptEnderk/RatioLab/releases/latest'
CACHE_SCHEMA = 'ratiolab-website-release/1'


@dataclass(frozen=True)
class Release:
    version: str
    tag: str
    url: str
    downloads: dict[str, str]
    payload: dict


def asset_names(version):
    return {'windows': f'RatioLab-{version}-windows-x86_64-setup.exe',
            'macos_arm': f'RatioLab-{version}-macos-arm64.dmg',
            'macos_intel': f'RatioLab-{version}-macos-x86_64.dmg',
            'linux_run': f'RatioLab-{version}-linux-x86_64.run',
            'linux_deb': f'ratiolab_{version}_amd64.deb',
            'linux_tar': f'RatioLab-{version}-linux-x86_64.tar.gz',
            'checksums': 'SHA256SUMS'}


def validate_release(payload):
    if not isinstance(payload, dict):
        raise ValueError('Release response must be an object')
    tag = payload.get('tag_name')
    if not isinstance(tag, str) or not re.fullmatch(r'v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)', tag):
        raise ValueError('Expected a stable numeric release tag')
    if payload.get('draft') is not False or payload.get('prerelease') is not False:
        raise ValueError('Release is not public and stable')
    expected_url = REPOSITORY + '/releases/tag/' + tag
    if payload.get('html_url') != expected_url:
        raise ValueError('Release repository or URL mismatch')
    published = payload.get('published_at')
    try:
        if not isinstance(published, str) or not published.endswith('Z'):
            raise ValueError
        datetime.fromisoformat(published.replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Release has no valid publication date') from error
    assets = payload.get('assets')
    if not isinstance(assets, list):
        raise ValueError('Release assets are missing')
    names = [asset.get('name') if isinstance(asset, dict) else None for asset in assets]
    if any(not isinstance(name, str) for name in names) or len(set(names)) != len(names):
        raise ValueError('Invalid or duplicate release assets')
    by_name = {asset['name']: asset for asset in assets}
    downloads, sanitized = {}, []
    for key, name in asset_names(tag[1:]).items():
        asset = by_name.get(name)
        if not asset or asset.get('state') != 'uploaded' or type(asset.get('size')) is not int or asset['size'] <= 0:
            raise ValueError('Required uploaded asset missing or incomplete: ' + name)
        if asset.get('browser_download_url') != REPOSITORY + '/releases/download/' + tag + '/' + name:
            raise ValueError('Unexpected release asset URL: ' + name)
        downloads[key] = asset['browser_download_url']
        sanitized.append({field: asset[field] for field in ('name', 'browser_download_url', 'size', 'state')})
    clean = {'tag_name': tag, 'html_url': expected_url, 'draft': False, 'prerelease': False,
             'published_at': published, 'assets': sanitized}
    return Release(tag[1:], tag, expected_url, downloads, clean)


def fetch_latest(opener=urlopen):
    request = Request(LATEST_API, headers={'Accept': 'application/vnd.github+json',
                                         'X-GitHub-Api-Version': '2022-11-28',
                                         'User-Agent': 'RatioLab-static-site-builder'})
    with opener(request, timeout=30) as response:
        if response.status != 200:
            raise ValueError('GitHub release API did not return success')
        data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise ValueError('Release response exceeds the metadata size limit')
    return json.loads(data)


def cache_document(release):
    return {'schema': CACHE_SCHEMA, 'repository': REPOSITORY,
            'verified_at': datetime.now(timezone.utc).isoformat().replace('+00:00', 'Z'),
            'release': release.payload}


def load_cache(path):
    data = json.loads(path.read_text(encoding='utf-8'))
    if data.get('schema') != CACHE_SCHEMA or data.get('repository') != REPOSITORY:
        raise ValueError('Offline cache has no validated release provenance')
    try:
        if not isinstance(data.get('verified_at'), str) or not data['verified_at'].endswith('Z'):
            raise ValueError
        datetime.fromisoformat(data['verified_at'].replace('Z', '+00:00'))
    except ValueError as error:
        raise ValueError('Offline cache has no verification timestamp') from error
    return validate_release(data.get('release'))
