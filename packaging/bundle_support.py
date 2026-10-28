# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Bundle provenance and installed license texts collected from native packages.

The notices inventory is generated from Analysis.binaries and native icon/
typelib resources, not a guessed list of GTK dependencies. Build paths never
enter the distributed metadata.
"""
import hashlib
import importlib.metadata
import json
import ntpath
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile

_packages = {}
_windows_files = None
_msys_notice_root = Path(__file__).resolve().parent/'notices/msys2'


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, encoding='utf-8',
                            errors='replace', env=os.environ | {'LC_ALL': 'C'}, timeout=120)
    return result.stdout.strip() if result.returncode == 0 else ''


def license_name(name):
    name = name.lower()
    return name.startswith(('copying', 'copyright', 'license', 'licence', 'notice'))


def referenced_common_licenses(paths):
    result = list(paths)
    for source in paths:
        text = source.read_text(encoding='utf-8', errors='replace')
        for name in re.findall(r'/usr/share/common-licenses/([A-Za-z0-9_.+-]+)', text):
            candidate = Path('/usr/share/common-licenses')/name.rstrip('.')
            if not candidate.is_file():
                raise RuntimeError(f'Referenced license document missing: {candidate}')
            result.append(candidate)
    return list(dict.fromkeys(result))


def pip_component(name):
    dist = importlib.metadata.distribution(name)
    files = [Path(dist.locate_file(path)) for path in dist.files or []
             if license_name(Path(path).name) and Path(dist.locate_file(path)).is_file()]
    return dict(name=name, version=dist.version, provider='PyPI',
                homepage=dist.metadata.get('Home-page', ''),
                license_declarations=[dist.metadata.get('License-Expression') or dist.metadata.get('License', 'see license files')],
                source=f'https://pypi.org/project/{name}/{dist.version}/',
                _licenses=files)


def linux_component(path):
    match = command(['dpkg-query', '-S', str(path)])
    if not match:
        # On usrmerged Ubuntu/Debian, realpath() resolves /lib to /usr/lib
        # while dpkg's database may retain the pre-merge installed spelling.
        spelling = str(path)
        for prefix in ('/usr/lib/', '/usr/bin/', '/usr/sbin/'):
            if spelling.startswith(prefix):
                alias = '/'+spelling.removeprefix('/usr/')
                match = command(['dpkg-query', '-S', alias])
                if match:
                    break
    if not match:
        return None
    package = match.splitlines()[0].split(': ', 1)[0]
    if package in _packages:
        return _packages[package]
    fields = command(['dpkg-query', '-W', '-f=${Version}\n${Homepage}\n${source:Package}\n${source:Version}', package]).splitlines()
    fields += [''] * (4-len(fields))
    version, homepage, source, source_version = fields[:4]
    copyright_file = Path('/usr/share/doc')/package.split(':')[0]/'copyright'
    licenses = [copyright_file] if copyright_file.is_file() else []
    declarations = []
    if licenses:
        declarations = sorted(set(re.findall(r'^License:\s*(.+)$', copyright_file.read_text(errors='replace'), re.M)))
    component = dict(name=package, version=version, provider='dpkg', homepage=homepage,
                     source=f'https://launchpad.net/ubuntu/+source/{source}/{source_version}',
                     license_declarations=declarations, _licenses=referenced_common_licenses(licenses))
    _packages[package] = component
    return component


def _windows_key(path):
    path = Path(path)
    if not path.is_absolute() or '..' in path.parts:
        return None
    return ntpath.normcase(ntpath.normpath(str(path.resolve())))


def _inside_windows_root(key, root):
    try:
        return key is not None and ntpath.commonpath([key, root]) == root
    except ValueError:  # Different drives or incompatible absolute paths.
        return False


def _windows_inventory():
    """One exact installed-file index; never infer ownership from a directory."""
    global _windows_files
    if _windows_files is not None:
        return _windows_files
    root = Path(command(['cygpath', '-w', '/']))
    root_key = _windows_key(root)
    if root_key is None:
        raise RuntimeError('MSYS2 did not return an absolute native installation root.')
    listing = command(['pacman', '-Ql'])
    if not listing:
        raise RuntimeError('The MSYS2 installed-file inventory could not be queried.')
    owners, files = {}, {}
    for line in listing.splitlines():
        package, separator, spelling = line.partition(' ')
        if not separator or not package or not spelling.startswith('/') or ':' in spelling \
                or spelling.startswith('//') or '\\' in spelling \
                or any(part in ('.', '..') for part in spelling.split('/')):
            raise RuntimeError('Unsafe path in the MSYS2 installed-file inventory.')
        if spelling.endswith('/'):
            continue  # Shared directories do not establish ownership of files.
        source = root.joinpath(*spelling.lstrip('/').split('/'))
        key = _windows_key(source)
        if not _inside_windows_root(key, root_key):
            continue  # Symlinks escaping MSYS2 cannot establish trusted ownership.
        if key in owners and owners[key] != package:
            owners[key] = None  # Ambiguous ownership stays unassignable.
        else:
            owners.setdefault(key, package)
        files.setdefault(package, {})[key] = source
    common = []
    for package_files in files.values():
        for key, source in package_files.items():
            spelling = source.relative_to(root).as_posix().lower()
            if owners[key] is not None and spelling.startswith(
                    ('usr/share/licenses/common/', 'ucrt64/share/licenses/common/')):
                common.append(source)
    _windows_files = dict(root=root_key, owners=owners, files=files, common_licenses=list(dict.fromkeys(common)))
    return _windows_files


def windows_component(path):
    inventory = _windows_inventory()
    key = _windows_key(path)
    if not _inside_windows_root(key, inventory['root']):
        return None
    package = inventory['owners'].get(key)
    if not package:
        return None
    if package in _packages:
        return _packages[package]
    fields = {}
    for line in command(['pacman', '-Qi', package]).splitlines():
        if ' : ' in line:
            key, value = line.split(' : ', 1)
            fields[key.strip()] = value.strip()
    licenses = []
    for license_key, candidate in inventory['files'][package].items():
        if '/share/licenses/' in candidate.as_posix().lower() \
                and inventory['owners'].get(license_key) == package:
            if candidate.is_file():
                licenses.append(candidate)
    declarations = fields.get('Licenses', '').split()
    # Pacman packages using standard licenses may refer to the common license
    # package instead of repeating a copy in every library package.
    if not licenses:
        for candidate in inventory['common_licenses']:
            relative = candidate.as_posix().lower().split('/share/licenses/common/', 1)[1]
            if candidate.is_file() and any(re.sub(r'[^a-z0-9]', '', label.lower().removeprefix('spdx:').replace('-or-later', '').replace('-only', '').replace('.0', ''))
                                          in re.sub(r'[^a-z0-9]', '', relative.replace('.0', ''))
                                          for label in declarations):
                licenses.append(candidate)
    component = dict(name=package, version=fields.get('Version', ''), provider='MSYS2 UCRT64',
                     homepage=fields.get('URL', ''), license_declarations=declarations,
                     source=f'https://packages.msys2.org/packages/{package}', _licenses=licenses)
    _packages[package] = component
    return component


def vendored_windows_notices(component):
    """Exact source notices omitted from particular MSYS2 package versions.

    Archive-backed entries verify .SRCINFO checksums; pinned Git entries retain
    per-file commit/blob/SHA-256 provenance without claiming an archive checksum.
    ANGLE supplements its installed root LICENSE with static dependency notices.
    No PKGBUILD code is executed.
    New versions or changed license declarations require a verified registry update.
    """
    registry = json.loads((_msys_notice_root/'registry.json').read_text(encoding='utf-8'))
    if registry.get('format') != 'ratiolab-msys2-source-notices/1':
        raise RuntimeError('Unknown MSYS2 source-notice registry format.')
    for record in registry['components']:
        if (component['name'], component['version']) != (record['name'], record['version']):
            continue
        normalize = lambda labels: sorted(label.removeprefix('spdx:') for label in labels)
        if normalize(component['license_declarations']) != normalize(record['license_declarations']):
            return []
        paths = []
        for entry in record['license_files']:
            path = (_msys_notice_root/entry['path']).resolve()
            if not path.is_relative_to(_msys_notice_root.resolve()):
                raise RuntimeError('Unsafe path in MSYS2 source-notice registry.')
            if not path.is_file() or hashlib.sha256(path.read_bytes()).hexdigest() != entry['sha256']:
                raise RuntimeError(f'MSYS2 source-notice checksum mismatch: {entry["path"]}')
            paths.append(path)
        component['notice_provenance'] = {key: record[key] for key in
            ('source', 'source_sha256', 'source_recipe', 'source_recipe_sha256', 'source_info_sha256')}
        for key in ('source_method', 'source_commit', 'source_package',
                    'source_package_sha256', 'source_package_verification'):
            if key in record:
                component['notice_provenance'][key] = record[key]
        component['notice_provenance']['original_files'] = [
            {key: value for key, value in entry.items() if key != 'path'}
            for entry in record['license_files']]
        return paths
    return []


def brew_component(path):
    parts = path.resolve().parts
    if 'Cellar' not in parts:
        return None
    offset = parts.index('Cellar')
    name, version = parts[offset+1:offset+3]
    if name in _packages:
        return _packages[name]
    prefix = Path(*parts[:offset+3])
    data = command(['brew', 'info', '--json=v2', name])
    formula = json.loads(data)['formulae'][0] if data else {}
    files = [candidate for candidate in prefix.rglob('*')
             if candidate.is_file() and license_name(candidate.name)
             and not any(item in candidate.parts for item in ('__pycache__', '.git'))]
    source = formula.get('urls', {}).get('stable', {})
    recipe = prefix/'.brew'/f'{name}.rb'
    declaration = formula.get('license')
    if recipe.is_file():
        recipe_text = recipe.read_text(encoding='utf-8')
        actual_url = re.search(r'^\s*url\s+"([^"]+)"', recipe_text, re.M)
        actual_checksum = re.search(r'^\s*sha256\s+"([a-f0-9]{64})"', recipe_text, re.M)
        actual_license = re.search(r'^\s*license\s+(.+)$', recipe_text, re.M)
        if actual_url and actual_checksum:
            source = dict(url=actual_url.group(1), checksum=actual_checksum.group(1))
        if actual_license:
            declaration = actual_license.group(1)
    component = dict(name=name, version=version, provider='Homebrew',
                     homepage=formula.get('homepage', ''),
                     license_declarations=[declaration if isinstance(declaration, str)
                                           else json.dumps(declaration or 'see license files')],
                     source=source.get('url', f'https://formulae.brew.sh/formula/{name}'),
                     source_sha256=source.get('checksum'), _licenses=files)
    _packages[name] = component
    return component


def collect_source_licenses(component, destination):
    """Recover exact Homebrew source notices when the bottle omits them.

    Only archives with the formula's SHA-256 are read; no extracted source or
    archive code is executed. Files are copied to a build staging directory.
    """
    checksum = component.get('source_sha256')
    url = component.get('source', '')
    if not checksum or not url.startswith('https://'):
        return []
    archive = destination/'source-archive'
    archive.parent.mkdir(parents=True, exist_ok=True)
    if not archive.is_file() or hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        request = urllib.request.Request(url, headers={'User-Agent': 'RatioLab-build/0.1'})
        with urllib.request.urlopen(request, timeout=180) as response, archive.open('wb') as target:
            shutil.copyfileobj(response, target)
    if hashlib.sha256(archive.read_bytes()).hexdigest() != checksum:
        raise RuntimeError(f'Upstream source checksum mismatch for {component["name"]}')
    found = []
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive) as source:
            for member in source.getmembers():
                relative = Path(member.name)
                if member.isfile() and len(relative.parts) <= 4 and member.size <= 2_000_000 and license_name(relative.name):
                    target = destination/(hashlib.sha256(member.name.encode()).hexdigest()[:8]+'-'+relative.name)
                    target.write_bytes(source.extractfile(member).read())
                    found.append(target)
    elif zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as source:
            for member in source.infolist():
                relative = Path(member.filename)
                if not member.is_dir() and len(relative.parts) <= 4 and member.file_size <= 2_000_000 and license_name(relative.name):
                    target = destination/(hashlib.sha256(member.filename.encode()).hexdigest()[:8]+'-'+relative.name)
                    target.write_bytes(source.read(member))
                    found.append(target)
    return found


def component_for_binary(path):
    path = Path(path).resolve()
    if sys.platform.startswith('linux'):
        component = linux_component(path)
    elif sys.platform == 'win32':
        component = windows_component(path)
    else:
        component = brew_component(path)
    if component:
        return component
    # Native extensions installed by pip (for example a matching Pycairo build)
    # are mapped to their actual distribution RECORD and license files.
    for dist in importlib.metadata.distributions():
        for entry in dist.files or []:
            if Path(entry).name == path.name and Path(dist.locate_file(entry)).resolve() == path:
                return pip_component(dist.metadata['Name'])
    return None


def _typelib_build_inputs(namespace, version):
    try:
        from PyInstaller.config import CONF
    except ImportError:
        return None
    # Attribution can also run outside Analysis (unit tests or tooling). No
    # active work directory means there is no trusted generated-file origin.
    workpath = CONF.get('workpath')
    if not workpath:
        return None
    from PyInstaller.compat import base_prefix
    from PyInstaller.utils.hooks.gi import GiModuleInfo
    info = GiModuleInfo(namespace, version)
    if not info.available or not info.typelib:
        return None
    return Path(info.typelib), Path(base_prefix), Path(workpath)


def _relocated_gir(text):
    """The exact shared-library rewrite in PyInstaller 6.22 gir_library_path_fix."""
    lines = []
    for line in text.splitlines(keepends=True):
        if 'shared-library' in line:
            split = re.split('(=)', line)
            files = re.split('(["|,])', split[2])
            for count, item in enumerate(files):
                if 'lib' in item:
                    files[count] = '@loader_path/' + os.path.basename(item)
            line = ''.join(split[:2]) + ''.join(files)
        lines.append(line)
    return ''.join(lines)


def derived_typelib_component(destination, source):
    """Attribute only Darwin typelibs regenerated by PyInstaller's GIR helper.

    Check the exact Analysis work path and original GIRepository namespace/version,
    then compare its generated GIR with the upstream helper's documented rewrite.
    A matching filename elsewhere, a changed GIR or an unknown owner stays unmapped.
    """
    parts = Path(destination).parts
    if sys.platform != 'darwin' or len(parts) != 2 or parts[0] != 'gi_typelibs':
        return None
    match = re.fullmatch(r'([A-Za-z][A-Za-z0-9_]*)-([0-9]+(?:\.[0-9]+)*)\.typelib', parts[1])
    if not match:
        return None
    inputs = _typelib_build_inputs(*match.groups())
    if inputs is None:
        return None
    original, base_prefix, workpath = inputs
    source = Path(source)
    if source.resolve() != (workpath/parts[1]).resolve() or original.name != parts[1]:
        return None
    # Follow PyInstaller's prefix calculation before resolving Homebrew symlinks.
    common = os.path.commonprefix([str(base_prefix), str(original)])
    if common == '/':
        common = os.path.abspath(os.path.join(str(original), '..', '..', '..'))
    gir_name = source.with_suffix('.gir').name
    original_gir = Path(common)/'share/gir-1.0'/gir_name
    generated_gir = workpath/gir_name
    if not all(path.is_file() for path in (source, original, original_gir, generated_gir)):
        return None
    if generated_gir.read_text(encoding='utf-8') != _relocated_gir(original_gir.read_text(encoding='utf-8')):
        return None
    component = component_for_binary(original_gir)
    original_owner = component_for_binary(original)
    if component is None or original_owner is None or any(
            component[key] != original_owner[key] for key in ('provider', 'name', 'version')):
        return None
    return component, {
        'from': 'share/gir-1.0/'+gir_name,
        'description': 'Typelib regenerated from this GIR by PyInstaller gir_library_path_fix and g-ir-compiler.',
        'source_sha256': hashlib.sha256(original_gir.read_bytes()).hexdigest(),
        'rewritten_gir_sha256': hashlib.sha256(generated_gir.read_bytes()).hexdigest(),
    }


def write_notices(binaries, staging, datas=()):
    staging = Path(staging)
    staging.mkdir(parents=True, exist_ok=True)
    components = {}
    unknown = []
    native_data = [(destination, source, kind) for destination, source, kind in datas
                   if '/share/icons/' in Path(source).as_posix()
                   or Path(source).suffix == '.typelib']
    for destination, source, kind in list(binaries) + native_data:
        component = component_for_binary(source)
        derived = None
        if component is None:
            typelib = derived_typelib_component(destination, source)
            if typelib is not None:
                component, derived = typelib
        # gtk-update-icon-cache generates this file after package installation;
        # dpkg need not own the cache itself. Attribute only this exact derived
        # resource to the package that owns its adjacent theme definition.
        parts = Path(destination).parts
        if component is None and len(parts) == 4 and parts[:2] == ('share', 'icons') \
                and parts[-1] == 'icon-theme.cache' and Path(source).name == 'icon-theme.cache':
            definition = Path(source).parent/'index.theme'
            if definition.is_file():
                component = component_for_binary(definition)
                derived = {
                    'from': str(Path(destination).parent/'index.theme').replace(os.sep, '/'),
                    'description': 'Icon cache generated by gtk-update-icon-cache for this theme.',
                }
        if component is None:
            unknown.append(destination)
            continue
        key = component['provider']+':'+component['name']
        entry = components.setdefault(key, dict(component, bundled_files=[]))
        entry['bundled_files'].append(destination)
        if derived:
            entry.setdefault('derived_resources', {})[destination] = derived
    for name in ('pyinstaller', 'pyinstaller-hooks-contrib'):
        component = pip_component(name)
        if not component['_licenses'] and sys.platform == 'win32':
            import importlib.util
            module = 'PyInstaller' if name == 'pyinstaller' else '_pyinstaller_hooks_contrib'
            origin = importlib.util.find_spec(module).origin
            component = windows_component(Path(origin)) or component
        components['PyPI:'+name] = dict(component, bundled_files=['Python modules / bootloader'])
    font_root = Path(__file__).resolve().parent/'fonts'
    font_source = json.loads((font_root/'SOURCE.json').read_text(encoding='utf-8'))
    components['vendored:DejaVu-fonts'] = dict(name='DejaVu fonts', version=font_source['version'],
        provider='vendored upstream fonts', source=font_source['source'],
        license_declarations=['Bitstream Vera license; DejaVu changes are public domain'],
        bundled_files=['share/fonts/'+name for name in font_source['files']],
        _licenses=list(font_root.glob('*.txt')))
    records = []
    for key, component in sorted(components.items()):
        identifier = re.sub(r'[^A-Za-z0-9_.+-]', '_', key)
        paths = component.pop('_licenses')
        if component['provider'] == 'MSYS2 UCRT64':
            # The ANGLE package installs its own BSD LICENSE, but not all
            # notices for code statically linked into libEGL/libGLESv2. This
            # requirement must survive a package version unknown to the registry.
            supplement_required = component['name'] == 'mingw-w64-ucrt-x86_64-angleproject'
            if not paths or supplement_required:
                supplement = vendored_windows_notices(component)
                if supplement_required and not supplement:
                    raise RuntimeError('Required ANGLE source notices are not verified for '
                                       f'{component["version"]}. Update the exact-version registry.')
                paths = [*paths, *supplement]
        if not paths and component['provider'] == 'Homebrew':
            paths = collect_source_licenses(component, staging/'source-notices'/identifier)
        copied = []
        for index, source in enumerate(paths):
            target = staging/'licenses'/identifier/f'{index:02d}-{source.name}'
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
            copied.append(str(target.relative_to(staging)).replace(os.sep, '/'))
        component['license_files'] = copied
        component['notices_present'] = bool(copied)
        component['bundled_files'] = sorted(set(component['bundled_files']))
        records.append(component)
    report = {'format': 'ratiolab-native-notices/1', 'components': records,
              'unmapped_native_files': sorted(set(unknown)),
              'complete': not unknown and all(item['notices_present'] for item in records)}
    (staging/'components.json').write_text(json.dumps(report, indent=2, ensure_ascii=False)+'\n', encoding='utf-8')
    text = ['RatioLab — bundled third-party components', '',
            'Generated from the native files collected by PyInstaller. The component inventory',
            'records exact installed package versions, source references and license documents.',
            'Each component retains its own license. These notices do not assign a license to',
            'the RatioLab application. Free DejaVu fonts are included with their copyright/license.',
            'GPU drivers and operating-system libraries not collected by PyInstaller are not shipped.',
            '', 'See components.json and the adjacent license documents for the complete inventory.', '']
    for item in records:
        text += [f'{item["name"]} {item["version"]} ({item["provider"]})',
                 'Source: '+item['source'], 'License: '+', '.join(item['license_declarations']),
                 'Documents: '+', '.join(item['license_files']), '']
    if not report['complete']:
        text += ['INCOMPLETE NATIVE NOTICES: this build must not be packaged for redistribution.',
                 'Unmapped files: '+', '.join(unknown)]
    (staging/'THIRD-PARTY-NOTICES.txt').write_text('\n'.join(text), encoding='utf-8')
    if not report['complete']:
        missing = [item['name'] for item in records if not item['notices_present']]
        raise RuntimeError(f'Native notices incomplete. Unmapped files: {unknown}; missing license files: {missing}. '
                           f'See {staging / "components.json"}')
    return [(path, 'notices/'+str(path.relative_to(staging)).replace(os.sep, '/'))
            for path in staging.rglob('*') if path.is_file() and 'source-notices' not in path.relative_to(staging).parts]
