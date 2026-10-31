# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Anonymous, bounded GitHub release discovery and package metadata."""
from dataclasses import dataclass
import json
from math import isfinite
import os
from pathlib import Path
import platform
import re
import sys
import time
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, build_opener, HTTPRedirectHandler

from app_paths import SOURCE_ROOT
from release_version import RELEASE_VERSION, CHANNEL, Version

REPOSITORY = 'NoOneExceptEnderk/RatioLab'
RELEASES_URL = 'https://github.com/'+REPOSITORY+'/releases'
API_URL = 'https://api.github.com/repos/'+REPOSITORY+'/releases?per_page=100'
MAX_RESPONSE = 2*1024*1024
DAY = 24*60*60
RETRY = 60*60


@dataclass(frozen=True)
class Release:
    version: str
    url: str
    notes: str
    download: str
    asset_name: str = ''
    asset_size: int | None = None
    checksums_url: str = ''


def automatic_enabled(environ=None):
    env=os.environ if environ is None else environ
    flag=env.get('RATIOLAB_UPDATE_CHECK','').lower()
    if flag in ('0','false','no','off'):return False
    if flag in ('1','true','yes','on'):return True
    return not (SOURCE_ROOT/'pyproject.toml').is_file()


def disabled_reason(environ=None):
    """Explain the check policy separately from the saved automatic preference."""
    env = os.environ if environ is None else environ
    if env.get('RATIOLAB_UPDATE_CHECK', '').lower() in ('0', 'false', 'no', 'off'):
        return 'Update checks are disabled by RATIOLAB_UPDATE_CHECK=0.'
    if not automatic_enabled(env):
        return 'Update checks are disabled for source development. Set RATIOLAB_UPDATE_CHECK=1 to enable them.'
    return ''


def installation_format(system=None, executable=None):
    system=sys.platform if system is None else system
    if system=='win32':return 'setup.exe'
    if system=='darwin':return '.dmg'
    if system.startswith('linux'):
        # Debian packages install this fixed executable; wheel/user bundles use .run.
        return '.deb' if str(executable or sys.executable).startswith('/opt/ratiolab/') else '.run'
    return None


def _download_asset(assets, tag, system=None, machine=None, executable=None, package_format=None):
    system=sys.platform if system is None else system
    arch=(machine or platform.machine()).lower()
    arch={'amd64':'x86_64','aarch64':'arm64'}.get(arch,arch)
    if arch not in ('x86_64','arm64'):return None
    suffix=installation_format(system,executable) if package_format is None else package_format
    if suffix not in ('.run','.deb','.tar.gz','.dmg','setup.exe'):return None
    allowed=('setup.exe',) if system=='win32' else ('.dmg',) if system=='darwin' else ('.run','.deb','.tar.gz') if system.startswith('linux') else ()
    if suffix not in allowed:return None
    if suffix is None:return None
    osname='windows' if system=='win32' else 'macos' if system=='darwin' else 'linux'
    prefix=RELEASES_URL+'/download/'+quote(tag,safe='')+'/'
    version=Version(tag)
    bases={'.'.join(map(str,version.core)),tag.removeprefix('v')}
    if suffix=='.deb':
        names={f'ratiolab_{base}_{"amd64" if arch=="x86_64" else "arm64"}.deb' for base in bases}
    else:
        names={f'RatioLab-{base}-{osname}-{arch}'+('-setup.exe' if suffix=='setup.exe' else suffix) for base in bases}
    for asset in assets if isinstance(assets,list) else []:
        if not isinstance(asset,dict):continue
        name=asset.get('name');url=asset.get('browser_download_url')
        if not isinstance(name,str) or not isinstance(url,str) or asset.get('state')!='uploaded':continue
        if not re.fullmatch(r'[A-Za-z0-9_.+-]+',name) or not name.lower().startswith('ratiolab'):continue
        if url!=prefix+quote(name,safe=''):continue
        if name in names:return asset
    return None


def _download(assets, tag, system=None, machine=None, executable=None, package_format=None):
    asset=_download_asset(assets,tag,system,machine,executable,package_format)
    return asset['browser_download_url'] if asset else None


def _checksums(assets,tag):
    expected=RELEASES_URL+'/download/'+quote(tag,safe='')+'/SHA256SUMS'
    matches=[asset for asset in assets if isinstance(asset,dict)
             and asset.get('name')=='SHA256SUMS' and asset.get('state')=='uploaded'
             and asset.get('browser_download_url')==expected] if isinstance(assets,list) else []
    return expected if len(matches)==1 else ''


def select_release(records,current=RELEASE_VERSION,channel=CHANNEL,**target):
    if channel not in ('stable','preview'):raise ValueError('Unknown update channel')
    installed=Version(current)
    if not isinstance(records,list):raise ValueError('Invalid release list')
    candidates=[]
    for record in records[:100]:
        if not isinstance(record,dict) or record.get('draft') is not False:continue
        if not isinstance(record.get('prerelease'),bool):continue
        tag=record.get('tag_name')
        try:version=Version(tag)
        except ValueError:continue
        if channel=='stable' and (version.pre or record.get('prerelease') is not False):continue
        if version.pre and version.pre[0] not in ('preview','rc','alpha','beta'):continue
        if not version>installed:continue
        url=RELEASES_URL+'/tag/'+quote(tag,safe='')
        if record.get('html_url')!=url:continue
        notes=record.get('body')
        notes=notes[:100000] if isinstance(notes,str) else 'No published release notes.'
        assets=record.get('assets',[])
        asset=_download_asset(assets,tag,**target)
        size=asset.get('size') if asset else None
        size=size if type(size) is int and size>0 else None
        candidates.append((version,Release(tag.removeprefix('v'),url,notes,
                          asset['browser_download_url'] if asset else url,
                          asset['name'] if asset else '',size,_checksums(assets,tag))))
    return max(candidates,key=lambda item:item[0])[1] if candidates else None


class RetryAfter(Exception):
    def __init__(self,seconds):self.seconds=seconds


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self,*args,**kwargs):return None


def fetch_releases(opener=None):
    """One fixed HTTPS request, 15s socket timeout, <=2 MiB, no redirects/token."""
    request=Request(API_URL,headers={'User-Agent':'RatioLab-update-check',
                    'Accept':'application/vnd.github+json','X-GitHub-Api-Version':'2022-11-28'})
    try:
        with (opener or build_opener(NoRedirect())).open(request,timeout=15) as response:
            if response.geturl()!=API_URL:raise ValueError('Unexpected update endpoint')
            raw=response.read(MAX_RESPONSE+1)
            if len(raw)>MAX_RESPONSE:raise ValueError('Update response too large')
            return json.loads(raw)
    except HTTPError as error:
        if error.code in (403,429):
            try:
                delay=max(RETRY,int(error.headers.get('Retry-After','0')),
                          int(error.headers.get('X-RateLimit-Reset','0'))-int(time.time()))
            except (ValueError,TypeError):delay=DAY
            raise RetryAfter(min(max(delay,RETRY),7*DAY)) from error
        raise


class Preferences:
    """Small separate update state; never reads or rewrites project preferences."""
    def __init__(self,path):
        self.path=Path(path)
        try:
            self.state=json.loads(self.path.read_text(encoding='utf-8'))
            if not isinstance(self.state,dict):self.state={}
            self.state={k:v for k,v in self.state.items() if k in ('skip','remind_until','remind_version','next_allowed','backoff_reason','automatic')}
            for key in ('remind_until','next_allowed'):
                value=self.state.get(key,0)
                if type(value) not in (int,float) or not isfinite(value) or value<0:self.state[key]=0
                elif value>time.time()+(3*DAY if key=='remind_until' else 7*DAY):self.state[key]=0
            if type(self.state.get('automatic', True)) is not bool:self.state.pop('automatic',None)
            if self.state.get('backoff_reason') not in ('network','rate_limit'):
                # Legacy backoffs did not distinguish failures from server limits.
                self.state['backoff_reason']='rate_limit' if self.state.get('next_allowed',0) else ''
        except (OSError,ValueError):self.state={}
    @property
    def automatic(self):return self.state.get('automatic',True)
    def set_automatic(self,enabled):
        if type(enabled) is not bool:raise ValueError('Automatic update checking must be a boolean')
        previous=self.state.copy()
        self.state['automatic']=enabled
        if not self.save():
            self.state=previous
            raise OSError('The automatic update preference could not be saved')
    def save(self):
        try:
            from project_document import atomic_json
            atomic_json(self.path,self.state)
            return True
        except (OSError,ValueError):return False
    def visible(self,release,now=None):
        now=time.time() if now is None else now
        until=self.state.get('remind_until',0)
        if not isinstance(until,(int,float)):until=0
        return self.state.get('skip')!=release.version and (self.state.get('remind_version')!=release.version or now>=until)
    def skip(self,release):self.state['skip']=release.version;self.save()
    def remind(self,release,now=None):
        self.state['remind_version']=release.version
        self.state['remind_until']=(time.time() if now is None else now)+3*DAY;self.save()
