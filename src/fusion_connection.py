# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Authenticated local Fusion bridge and persistent, verified STEP packages.

Fusion's Python API remains inside its add-in. RatioLab only exports solids and
sends two narrowly defined RPC methods; an uncertain import is never retried.
"""
import hashlib
from dataclasses import dataclass
import json
import os
from pathlib import Path, PurePosixPath, PureWindowsPath
import shutil
import socket
import sys
import tempfile
import uuid

import app_paths
from export_transaction import directory

PROTOCOL = 'ratiolab-fusion/1'
ADDIN_FILES = ('RatioLabBridge.py', 'RatioLabBridge.manifest', 'bridge_server.py', 'fusion_import.py')
INSTALL_RECORD = '.ratiolab-install.json'
START_HELP = 'In Fusion open Utilities > Scripts and Add-Ins > Add-Ins, then run RatioLabBridge.'


class FusionError(RuntimeError):
    pass


@dataclass(frozen=True)
class WineContext:
    """One selected Wine C: drive/profile, frozen for an RPC session."""
    prefix: Path
    profile: Path

    @property
    def drive_c(self):
        return self.prefix/'drive_c'

    def contained(self,path):
        path=Path(path).resolve()
        if not path.is_relative_to(self.drive_c.resolve()):
            raise FusionError('Fusion Wine path escapes the selected C: drive. Check the Wine profile mappings.')
        return path

    def local_data(self):
        return self.contained(self.profile/'AppData/Local/RatioLab')

    def endpoint(self):
        path=self.local_data()/'fusion-bridge/endpoint.json'
        self.contained(path)
        # Preserve the final file path so read_endpoint can reject a symlink,
        # after independently proving that its resolved target stays on C:.
        return path

    def addins(self):
        return self.contained(self.profile/'AppData/Roaming/Autodesk/Autodesk Fusion 360/API/AddIns')

    def windows_path(self,path):
        relative=self.contained(path).relative_to(self.drive_c.resolve())
        if any(':' in part or '\\' in part or part in ('.','..') for part in relative.parts):
            raise FusionError('Fusion Wine path cannot be represented safely on the C: drive.')
        return str(PureWindowsPath('C:/').joinpath(*relative.parts))


def discover_wine_context():
    """Find Fusion's Wine profile without scanning arbitrary home directories."""
    selection=os.environ.get('RATIOLAB_FUSION_WINEUSER')
    if selection is not None and (not selection or selection in ('.','..') or any(c in selection for c in '/\\:')):
        raise FusionError('RATIOLAB_FUSION_WINEUSER must name one Wine user profile, without path separators.')
    explicit=None
    for name in ('RATIOLAB_FUSION_WINEPREFIX','WINEPREFIX'):
        if name in os.environ:
            value=os.environ[name]
            candidate=Path(value).expanduser()
            if not value or not candidate.is_absolute() or not candidate.is_dir():
                raise FusionError(f'{name} must be an absolute existing Wine prefix; no fallback was attempted.')
            explicit=candidate.resolve()
            break
    home=Path.home()
    candidates=[explicit] if explicit is not None else [
        home/'.autodesk_fusion/wineprefixes/default',
        home/'.fusion360/wineprefixes/default',
        home/'.var/app/org.winehq.Wine/data/wineprefixes/fusion360',
        home/'.autodesk/wineprefixes/default',home/'.wine']
    matches=[]
    seen=set()
    for candidate in candidates:
        if not candidate.is_dir():continue
        prefix=candidate.resolve()
        if prefix in seen:continue
        seen.add(prefix)
        drive=prefix/'drive_c'
        users=drive/'users'
        if not users.is_dir() or not users.resolve().is_relative_to(drive.resolve()) or not drive.resolve().is_relative_to(prefix):
            if explicit is not None:
                raise FusionError('Selected Wine prefix needs a contained drive_c/users directory.')
            continue
        profiles=[p for p in users.iterdir() if p.is_dir() and p.name.lower() not in ('public','default','default user','all users')]
        for profile in profiles:
            if selection is not None and profile.name!=selection:continue
            context=WineContext(prefix,profile.resolve())
            try:
                context.contained(profile)
                context.local_data();context.addins();context.endpoint()
            except FusionError:
                if explicit is not None:raise
                continue
            markers=(profile/'AppData/Local/Autodesk/webdeploy',
                     profile/'AppData/Roaming/Autodesk/Autodesk Fusion 360/API',
                     profile/'AppData/Roaming/Autodesk/Autodesk Fusion360/API')
            marked=any(p.is_dir() for p in markers)
            # An explicit prefix with exactly one user is sufficient for a
            # fresh installation, even before Fusion creates its API folder.
            if marked or explicit is not None and (selection is not None or len(profiles)==1):
                matches.append(context)
    if len(matches)!=1:
        reason='Several Fusion Wine profiles were found.' if matches else 'No Fusion Wine profile was found.'
        raise FusionError(reason+' Set RATIOLAB_FUSION_WINEPREFIX to the prefix and, when needed, '
                          'RATIOLAB_FUSION_WINEUSER to its user directory name. Start Fusion and RatioLab in the same host/network namespace.')
    return matches[0]


def endpoint_path():
    if sys.platform.startswith('linux'):
        return discover_wine_context().endpoint()
    return app_paths.data_dir()/'fusion-bridge'/'endpoint.json'


def _json_bytes(value):
    return (json.dumps(value, ensure_ascii=False, allow_nan=False, indent=2)+'\n').encode('utf-8')


def _digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def read_endpoint(path=None):
    path = Path(path) if path is not None else endpoint_path()
    try:
        if path.is_symlink() or path.stat().st_size > 65536:
            raise ValueError('Invalid endpoint file')
        value = json.loads(path.read_text(encoding='utf-8'))
        if (not isinstance(value, dict) or value.get('protocol') != PROTOCOL
                or value.get('host') != '127.0.0.1'
                or type(value.get('port')) is not int or not 1 <= value['port'] <= 65535
                or not isinstance(value.get('token'), str) or not 32 <= len(value['token']) <= 1024
                or type(value.get('pid')) is not int or value['pid'] <= 0
                or not isinstance(value.get('session_id'), str) or not value['session_id']):
            raise ValueError('Invalid local endpoint')
        return value
    except (OSError, ValueError, TypeError) as error:
        raise FusionError('Fusion bridge unavailable. Install the add-in, then start it. '+START_HELP) from error


def addins_directory():
    if sys.platform.startswith('linux'):
        return discover_wine_context().addins()
    if sys.platform == 'win32':
        base = Path(os.environ.get('APPDATA', Path.home()/'AppData/Roaming'))
        if not base.is_absolute():
            raise FusionError('APPDATA must be an absolute path.')
        return base/'Autodesk'/'Autodesk Fusion 360'/'API'/'AddIns'
    if sys.platform == 'darwin':
        return Path.home()/'Library'/'Application Support'/'Autodesk'/'Autodesk Fusion 360'/'API'/'AddIns'
    raise FusionError('Fusion needs Windows, macOS, or a configured Linux Wine prefix.')


def _managed_install(target):
    """Never replace an unrelated add-in or edited managed files."""
    if target.is_symlink() or not target.is_dir():
        raise FusionError('Existing Fusion add-in is unmanaged; preserve it and choose a separate location.')
    try:
        record = json.loads((target/INSTALL_RECORD).read_text(encoding='utf-8'))
        expected = set(ADDIN_FILES) | {INSTALL_RECORD}
        actual = {p.name for p in target.iterdir() if p.name != '__pycache__'}
        cache = target/'__pycache__'
        if (actual != expected or record.get('format') != 'ratiolab-fusion-install/1'
                or set(record.get('files', {})) != set(ADDIN_FILES)
                or cache.is_symlink()
                or (cache.exists() and (not cache.is_dir() or any(p.is_symlink() or not p.is_file() or p.suffix != '.pyc' for p in cache.iterdir())))
                or any((target/name).is_symlink() or _digest(target/name) != record['files'][name] for name in ADDIN_FILES)):
            raise ValueError('Modified add-in')
    except (OSError, ValueError, TypeError, AttributeError) as error:
        raise FusionError('Existing RatioLabBridge files were modified or are unmanaged. Installation stopped to preserve them.') from error


def install_addin(destination=None, source=None):
    """Stage the four known resources, then atomically publish one add-in folder."""
    source = Path(source) if source is not None else app_paths.resource_path('fusion_addin/RatioLabBridge')
    base = Path(destination) if destination is not None else addins_directory()
    base.mkdir(parents=True, exist_ok=True)
    target = base/'RatioLabBridge'
    if target.exists() or target.is_symlink():
        _managed_install(target)
    staging = Path(tempfile.mkdtemp(prefix='.RatioLabBridge-', dir=base))
    backup = None
    try:
        for name in ADDIN_FILES:
            item = source/name
            if item.is_symlink() or not item.is_file():
                raise FusionError(f'Missing packaged Fusion add-in resource: {name}')
            shutil.copyfile(item, staging/name)
        record = dict(format='ratiolab-fusion-install/1', files={name:_digest(staging/name) for name in ADDIN_FILES})
        (staging/INSTALL_RECORD).write_bytes(_json_bytes(record))
        if target.exists():
            _managed_install(target)
            backup = base/('.RatioLabBridge-backup-'+uuid.uuid4().hex)
            target.rename(backup)
        try:
            staging.rename(target)
        except Exception:
            if backup is not None:
                backup.rename(target)
                backup = None
            raise
        if backup is not None:
            shutil.rmtree(backup)
            backup = None
    finally:
        if staging.exists():
            shutil.rmtree(staging)
    return target


def prepare_import(design, output_dir, visible_roles=None):
    """Persist one STEP per component and all metadata before submitting work."""
    import bom
    import cad_export
    from solid_geometry import signature
    package_id = str(uuid.uuid4())
    target = Path(output_dir).resolve()/('fusion-'+design.family+'-'+package_id)
    with directory(target) as staging:
        part_folder = staging/'step-parts'
        part_folder.mkdir()
        components = []
        indices = getattr(design, 'source_indices', range(1,len(design.parts)+1))
        for index, part in zip(indices, design.parts):
            path = part_folder/(cad_export.filename(index,part.name)+'.step')
            info = cad_export.write(path,[part],indices=[index],explicit_topology=True)[0]
            shape = signature(part)
            volume = info.get('cad_volume_mm3',info.get('sampled_volume_mm3',shape['volume_mm3']))
            components.append(dict(index=index,name=part.name,role=part.role,
                visible=visible_roles is None or part.role in visible_roles,
                color=list(part.color),step=path.relative_to(staging).as_posix(),sha256=_digest(path),
                expected_volume_mm3=volume,expected_bounds_mm=[shape['min'],shape['max']]))
        manifest = dict(format='ratiolab-fusion-import/1',id=package_id,family=design.family,
            name=f'RatioLab {design.family} {package_id[:8]}',units='mm',parameters=design.values,
            components=components,bom=bom.build(design),notes=list(design.notes))
        (staging/'manifest.json').write_bytes(_json_bytes(manifest))
        (staging/'model.config.json').write_bytes(_json_bytes(dict(format='solidcraft-riduttori/1',family=design.family,parameters=design.values)))
        bom.export(design,staging/'model')
        (staging/'README.txt').write_text('Fusion transfer: STEP solids with RatioLab parameter metadata.\n'
            'Imported solids do not recreate a native Fusion parametric timeline.\n'
            'Keep this package until Fusion finishes. If a request times out, inspect Fusion before sending again.\n',encoding='utf-8')
    return target/'manifest.json'


def _verify_import_package(manifest):
    manifest=Path(manifest)
    if manifest.name!='manifest.json' or manifest.is_symlink() or manifest.stat().st_size>16*1024*1024:
        raise FusionError('Invalid Fusion package manifest.')
    package=manifest.parent.resolve()
    try:
        value=json.loads(manifest.read_text(encoding='utf-8'))
        if value.get('format')!='ratiolab-fusion-import/1' or not isinstance(value.get('components'),list) or not value['components']:
            raise ValueError('Invalid manifest format')
        for component in value['components']:
            relative=component['step']
            path=PurePosixPath(relative)
            if not isinstance(relative,str) or path.is_absolute() or '..' in path.parts or '\\' in relative or ':' in relative:
                raise ValueError('Unsafe STEP path')
            step=package.joinpath(*path.parts)
            if step.is_symlink() or not step.is_file() or not step.resolve().is_relative_to(package) or _digest(step)!=component['sha256']:
                raise ValueError('Missing or modified STEP file')
        return value
    except (OSError,ValueError,TypeError,KeyError,AttributeError) as error:
        raise FusionError('Fusion import package is invalid or was modified; nothing was submitted.') from error


def stage_wine_import(manifest,context):
    """Keep a verified copy inside Wine C:, without depending on a Z: mapping."""
    manifest=Path(manifest)
    _verify_import_package(manifest)
    source=manifest.parent.resolve()
    target=context.contained(context.local_data()/'fusion-imports'/source.name)
    with directory(target) as staging:
        # Only local regular files/directories are copied. Verify every copied
        # byte, including BOM/config sidecars; never follow an external link.
        for item in sorted(source.rglob('*')):
            if item.is_symlink() or not item.resolve().is_relative_to(source):
                raise FusionError('Fusion package contains a link or an external path.')
            relative=item.relative_to(source)
            copied=staging/relative
            if item.is_dir():copied.mkdir(parents=True,exist_ok=True)
            elif item.is_file():
                expected=_digest(item)
                copied.parent.mkdir(parents=True,exist_ok=True)
                shutil.copyfile(item,copied)
                if _digest(copied)!=expected:
                    raise FusionError('Fusion package changed while copying; nothing was submitted.')
            else:raise FusionError('Fusion package contains an unsupported file type.')
        _verify_import_package(staging/'manifest.json')
    return target/'manifest.json'


class Client:
    def __init__(self, endpoint=None, timeout=180):
        self.endpoint_file = endpoint
        self.timeout = timeout
        self.sock = None
        self.io = None
        self.wine_context = None

    def __enter__(self):
        if sys.platform.startswith('linux'):
            self.wine_context=discover_wine_context()
            expected=self.wine_context.endpoint()
            if self.endpoint_file is not None and Path(self.endpoint_file).resolve()!=expected.resolve():
                raise FusionError('Explicit Fusion endpoint does not match the selected Wine prefix/profile. '
                                  'Set RATIOLAB_FUSION_WINEPREFIX and RATIOLAB_FUSION_WINEUSER consistently.')
            self.endpoint=read_endpoint(expected)
        else:
            self.endpoint = read_endpoint(self.endpoint_file)
        return self

    def __exit__(self,*args):
        try:
            if self.io is not None:self.io.close()
        finally:
            if self.sock is not None:self.sock.close()
            self.io = None
            self.sock = None

    def _exchange(self,payload):
        # BridgeServer intentionally accepts exactly one request per socket.
        # Reusing the authenticated session means reusing its endpoint, not a
        # closed TCP stream. Every status/import has its own bounded transport.
        try:
            self.sock = socket.create_connection(('127.0.0.1',self.endpoint['port']),timeout=5)
            self.sock.settimeout(self.timeout)
            self.io = self.sock.makefile('rwb')
            self.io.write(payload);self.io.flush()
            return self.io.readline(1024*1024+1)
        finally:
            self.__exit__()

    def call(self,method,params=None):
        if method not in ('status','import_model'):
            raise FusionError('Unsupported Fusion bridge method.')
        request_id = str(uuid.uuid4())
        payload = _json_bytes(dict(protocol=PROTOCOL,id=request_id,token=self.endpoint['token'],method=method,params=params or {}))
        if len(payload)>65536:
            raise FusionError('Fusion request is too large.')
        # RPC is one JSON line; manifest metadata is read from the verified file.
        payload = (json.dumps(json.loads(payload),ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n').encode('utf-8')
        try:
            line = self._exchange(payload)
            if not line.endswith(b'\n') or len(line)>1024*1024:
                raise ValueError('Incomplete or oversized reply')
            reply = json.loads(line)
            if not isinstance(reply,dict) or reply.get('id') != request_id or type(reply.get('ok')) is not bool:
                raise ValueError('Invalid bridge reply')
        except (OSError,ValueError,TypeError) as error:
            raise FusionError('No valid response from Fusion. The operation may still be running. '
                              'Check Fusion before trying again; do not resend the model.') from error
        if not reply['ok']:
            if reply.get('running'):
                raise FusionError('Fusion may still be running the operation. Check Fusion; do not resend the model.')
            raise FusionError(str(reply.get('error','Fusion bridge rejected the operation.')))
        result = reply.get('result')
        if not isinstance(result,dict):
            raise FusionError('Invalid Fusion result. Check Fusion before trying again; do not resend the model.')
        return result

    def status(self):
        result = self.call('status')
        document = result.get('document')
        if (result.get('application') != 'Fusion' or result.get('bridge_session') != self.endpoint['session_id']
                or not isinstance(result.get('version'),str) or 'document' not in result
                or document is not None and (not isinstance(document,dict) or not isinstance(document.get('id'),str)
                    or not document['id'] or not isinstance(document.get('name'),str))):
            raise FusionError('Fusion bridge status is invalid or stale. Restart RatioLabBridge and reconnect.')
        return result

    def insert(self,design,output_dir,visible_roles=None):
        status = self.status()
        if status['document'] is None:
            raise FusionError('Open a design document in Fusion before creating the model.')
        manifest = prepare_import(design,output_dir,visible_roles)
        submitted=stage_wine_import(manifest,self.wine_context) if self.wine_context is not None else manifest
        path=self.wine_context.windows_path(submitted) if self.wine_context is not None else str(submitted)
        result = self.call('import_model',dict(manifest_path=path,manifest_sha256=_digest(submitted),document_id=status['document']['id']))
        return dict(result,package_path=str(manifest.parent))
