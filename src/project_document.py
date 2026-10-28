# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Document history and local persistence; no GTK or geometry dependencies."""
from copy import deepcopy
import json
from math import isfinite
import os
from pathlib import Path
import tempfile
import time
import uuid

FORMAT = 'ratiolab-recovery/1'


def atomic_json(path, value):
    """Replace one complete UTF-8 file after flushing a same-directory staging file."""
    path = Path(path)
    payload = json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)+'\n'
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix='.'+path.name+'-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        Path(temporary).unlink(missing_ok=True)


def comparable(snapshot):
    result = deepcopy(snapshot)
    for fields in result.get('raw', {}).values():
        for key, text in fields.items():
            try:
                number = float(text.strip().replace(',', '.'))
                if isfinite(number):
                    fields[key] = number
            except ValueError:
                pass
    return result


def equivalent(first, second):
    return comparable(first) == comparable(second)


class Document:
    def __init__(self, snapshot, path=None, clean=None):
        self.identity = uuid.uuid4().hex
        self.path = Path(path) if path else None
        self.states = [deepcopy(snapshot)]
        self.index = 0
        self.clean = deepcopy(snapshot if clean is None else clean)
        self.revision = 0
        self._group = None
        self._when = 0

    @property
    def current(self):
        return deepcopy(self.states[self.index])

    @property
    def dirty(self):
        return not equivalent(self.states[self.index], self.clean)

    @property
    def token(self):
        """Bind delayed answers to this document and edit, including undo/redo.

        Identity distinguishes newly opened documents with identical contents;
        revision advances even when history returns to an earlier snapshot.
        """
        return self.identity, self.revision

    def barrier(self):
        self._group = None

    def record(self, snapshot, group=None, now=None):
        if equivalent(snapshot, self.states[self.index]):
            return False
        now = time.monotonic() if now is None else now
        combine = (group is not None and group == self._group and now-self._when < .7
                   and self.index > 0 and self.index == len(self.states)-1
                   and not equivalent(self.states[self.index], self.clean))
        del self.states[self.index+1:]
        if combine:
            self.states[self.index] = deepcopy(snapshot)
        else:
            self.states.append(deepcopy(snapshot))
            self.index += 1
        if len(self.states) > 201:
            self.states.pop(0)
            self.index -= 1
        self._group, self._when = group, now
        self.revision += 1
        return True

    def reconcile(self, snapshot):
        """Normalize the represented edit without adding an automatic history step."""
        if equivalent(snapshot, self.states[self.index]):
            return False
        self.states[self.index] = deepcopy(snapshot)
        self.revision += 1
        return True

    def undo(self):
        self.barrier()
        if self.index:
            self.index -= 1
            self.revision += 1
        return self.current

    def redo(self):
        self.barrier()
        if self.index+1 < len(self.states):
            self.index += 1
            self.revision += 1
        return self.current

    def mark_saved(self, path):
        self.path = Path(path)
        self.clean = self.current
        self.barrier()

    def recovery(self):
        return dict(format=FORMAT, path=str(self.path) if self.path else None,
                    snapshot=self.current, clean=self.clean)


def validate_snapshot(value, families):
    if not isinstance(value, dict) or set(value) != {'family', 'values', 'raw'}:
        raise ValueError('Invalid recovery snapshot')
    if value['family'] not in families:
        raise ValueError('Unsupported recovery family')
    if not isinstance(value['values'], dict) or not isinstance(value['raw'], dict):
        raise ValueError('Invalid recovery fields')
    if value['family'] not in value['values']:
        raise ValueError('Recovery configuration is missing')
    for family, parameters in value['values'].items():
        if family not in families or not isinstance(parameters, dict):
            raise ValueError('Invalid recovery configuration')
        if not all(isinstance(k, str) and isinstance(v, (str, bool, int, float))
                   and (not isinstance(v, float) or isfinite(v)) for k, v in parameters.items()):
            raise ValueError('Invalid recovery parameter value')
    for family, fields in value['raw'].items():
        if family not in families or not isinstance(fields, dict) or not all(
                isinstance(k, str) and isinstance(v, str) for k, v in fields.items()):
            raise ValueError('Invalid recovery text')
    return deepcopy(value)


class Store:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.session = self.folder/'recovery'/(uuid.uuid4().hex+'.json')
        self.recent_error = None

    def recent(self):
        try:
            data = json.loads((self.folder/'recent-projects.json').read_text(encoding='utf-8'))
            if not isinstance(data, list) or not all(isinstance(p, str) and Path(p).is_absolute() for p in data):
                raise ValueError('Invalid recent-project list')
            self.recent_error = None
            return list(dict.fromkeys(data))[:12]
        except FileNotFoundError:
            return []
        except (OSError, ValueError) as error:
            self.recent_error = str(error)
            return []

    def remember(self, path):
        path = str(Path(path).absolute())
        atomic_json(self.folder/'recent-projects.json', [path]+[p for p in self.recent() if p != path][:11])

    def checkpoint(self, document):
        if document.dirty:
            atomic_json(self.session, document.recovery())
        else:
            self.session.unlink(missing_ok=True)

    def candidates(self):
        return sorted(p for p in (self.folder/'recovery').glob('*.json') if p != self.session)

    def read_recovery(self, path, families):
        obj = json.loads(Path(path).read_text(encoding='utf-8'))
        if not isinstance(obj, dict) or obj.get('format') != FORMAT:
            raise ValueError('Unknown recovery format')
        snapshot = validate_snapshot(obj.get('snapshot'), families)
        clean = validate_snapshot(obj.get('clean'), families)
        target = obj.get('path')
        if target is not None and (not isinstance(target, str) or not Path(target).is_absolute()):
            raise ValueError('Invalid recovery path')
        document = Document(clean, target, clean)
        document.record(snapshot)
        document.barrier()
        return document
