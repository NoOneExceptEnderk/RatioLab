# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Canonical installed release identity and SemVer precedence; no GTK/network."""
from functools import total_ordering
from importlib.resources import files
import json
import re
import ratiolab_resources

SEMVER = re.compile(r'v?(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?\Z')


@total_ordering
class Version:
    """SemVer precedence, including numeric prerelease identifiers and metadata."""
    def __init__(self, value):
        match = SEMVER.fullmatch(value) if isinstance(value,str) and len(value)<=128 else None
        if not match:raise ValueError('Invalid release version')
        self.core = tuple(int(v) for v in match.group(1,2,3))
        self.pre = tuple(match.group(4).split('.')) if match.group(4) else ()
        if any(v.isdigit() and len(v)>1 and v[0]=='0' for v in self.pre):raise ValueError('Invalid prerelease number')
    def __eq__(self, other):
        return isinstance(other,Version) and (self.core,self.pre)==(other.core,other.pre)
    def __lt__(self, other):
        if self.core!=other.core:return self.core<other.core
        if not self.pre or not other.pre:return bool(self.pre) and not other.pre
        for a,b in zip(self.pre,other.pre):
            if a==b:continue
            if a.isdigit() and b.isdigit():return int(a)<int(b)
            if a.isdigit()!=b.isdigit():return a.isdigit()
            return a<b
        return len(self.pre)<len(other.pre)



def validate_identity(identity):
    if not isinstance(identity,dict) or any(not isinstance(identity.get(k),str) for k in ('base','release','channel')):
        raise ValueError('Invalid RatioLab release identity')
    base=Version(identity['base']);release=Version(identity['release'])
    if base.pre or base.core!=release.core or identity['base']!='.'.join(map(str,base.core)):
        raise ValueError('Release identity base does not match its release version')
    channel=identity['channel']
    if channel not in ('stable','preview') or (channel=='stable')!=bool(not release.pre):
        raise ValueError('Release channel does not match its version')
    return dict(identity)


IDENTITY = validate_identity(json.loads(files(ratiolab_resources).joinpath('version.json').read_text(encoding='utf-8')))
BASE_VERSION = IDENTITY['base']
RELEASE_VERSION = IDENTITY['release']
CHANNEL = IDENTITY['channel']
