"""Recheck curated ANGLE notices; network access is opt-in, never part of build.

Only immutable individual files are downloaded. The 2.14 GB source archive is
not downloaded; the PKGBUILD recipe is compared as text and never executed.
"""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path, PurePosixPath
import urllib.request

ROOT = Path(__file__).resolve().parent
PACKAGE = 'mingw-w64-ucrt-x86_64-angleproject'


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def verify_source_bytes(entry, original):
    """Verify an immutable source blob, then return its exact notice byte range."""
    if sha256(original) != entry['source_original_sha256']:
        raise ValueError('Original source SHA-256 mismatch: '+entry['original_path'])
    blob = hashlib.sha1(b'blob '+str(len(original)).encode()+b'\0'+original).hexdigest()
    if blob != entry['source_blob_sha1']:
        raise ValueError('Git blob mismatch: '+entry['original_path'])
    start, end = entry['selection_bytes']
    if not 0 <= start < end <= len(original):
        raise ValueError('Invalid notice byte range: '+entry['original_path'])
    notice = original[start:end]
    if sha256(notice) != entry['sha256']:
        raise ValueError('Notice SHA-256 mismatch: '+entry['original_path'])
    return notice


def verify_local(root=ROOT):
    registry = json.loads((root/'registry.json').read_text(encoding='utf-8'))
    record, = [item for item in registry['components'] if item['name'] == PACKAGE]
    if record['source_method'] != 'pinned-git-files' or record['source_sha256'] is not None:
        raise ValueError('ANGLE must use individual pinned Git files, not an unverified archive hash.')
    for path_key, hash_key in [('source_info', 'source_info_sha256'),
                               ('source_recipe_file', 'source_recipe_sha256')]:
        if sha256((root/record[path_key]).read_bytes()) != record[hash_key]:
            raise ValueError('Recipe metadata mismatch: '+record[path_key])
    info = (root/record['source_info']).read_text(encoding='utf-8')
    if ('pkgver = '+record['version'].rsplit('-', 1)[0]) not in info \
            or ('pkgrel = '+record['version'].rsplit('-', 1)[1]) not in info \
            or record['source_commit'] not in info:
        raise ValueError('ANGLE version/commit does not match .SRCINFO.')
    for entry in record['license_files']:
        path = (root/entry['path']).resolve()
        if not path.is_relative_to(root.resolve()) or sha256(path.read_bytes()) != entry['sha256']:
            raise ValueError('Vendored notice mismatch: '+entry['path'])
        commit = entry['source_commit']
        expected = f'{entry["source_repository"]}/+/{commit}/{entry["source_path"]}?format=TEXT'
        if len(commit) != 40 or entry['source_original'] != expected:
            raise ValueError('Unpinned source reference: '+entry['original_path'])
    return record


def verify_online(record, cache, root=ROOT):
    cache.mkdir(parents=True, exist_ok=True)
    recipe_a = urllib.request.urlopen(record['source_recipe'], timeout=60).read()
    recipe_b = urllib.request.urlopen(record['source_recipe'], timeout=60).read()
    if recipe_a != recipe_b or sha256(recipe_a) != record['source_recipe_sha256']:
        raise ValueError('Official pinned PKGBUILD differs from recorded recipe.')
    (cache/'PKGBUILD-verified.txt').write_bytes(recipe_a)
    # One directory query per distinct parent, rather than one per notice.
    trees = {}
    for entry in record['license_files']:
        parent = PurePosixPath(entry['source_path']).parent.as_posix()
        parent = '' if parent == '.' else parent+'/'
        url = f'{entry["source_repository"]}/+/{entry["source_commit"]}/{parent}?format=JSON'
        if url not in trees:
            data = urllib.request.urlopen(url, timeout=60).read()
            trees[url] = json.loads(data.split(b'\n', 1)[1])
        blob, = [item['id'] for item in trees[url]['entries']
                 if item['name'] == PurePosixPath(entry['source_path']).name]
        if blob != entry['source_blob_sha1']:
            raise ValueError('Official tree/blob mismatch: '+entry['original_path'])

    def check(entry):
        # Independent HTTP requests, followed by both content and Git-object checks.
        # Official GitHub mirrors avoid unnecessary repeated requests to Gitiles;
        # their bytes must still match the exact original Gitiles blob above.
        url = entry.get('source_mirror', entry['source_original'])
        decode = (lambda data: data) if 'source_mirror' in entry else base64.b64decode
        original = decode(urllib.request.urlopen(url, timeout=60).read())
        repeated = decode(urllib.request.urlopen(url, timeout=60).read())
        if original != repeated:
            raise ValueError('Independent downloads differ: '+entry['original_path'])
        notice = verify_source_bytes(entry, original)
        if notice != (root/entry['path']).read_bytes():
            raise ValueError('Selected upstream bytes differ from vendored notice.')
        name = Path(entry['path']).name
        (cache/(name+'.original')).write_bytes(original)
        return dict(path=entry['path'], sha256=entry['sha256'],
                    source_original_sha256=sha256(original), git_blob_sha1=entry['source_blob_sha1'],
                    download_url=url, independent_downloads=2, matched=True)

    with ThreadPoolExecutor(max_workers=3) as executor:
        return list(executor.map(check, record['license_files']))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--online', action='store_true', help='Fetch only pinned original notice sources twice.')
    parser.add_argument('--cache', type=Path, default=Path('work/angle-notices-verification'))
    args = parser.parse_args()
    record = verify_local()
    proof = dict(package=record['name'], version=record['version'], local_verified=True,
                 notices=len(record['license_files']), source_archive_verified=False)
    if args.online:
        proof['files'] = verify_online(record, args.cache)
        args.cache.joinpath('proof.json').write_text(json.dumps(proof, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(proof, indent=2))


if __name__ == '__main__':
    main()
