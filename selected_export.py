# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Explicit, nominal subset exports. Original source indices are 1-based.

Never call generate on a selected design: that would silently add components.
Full exports keep their existing APIs and behavior.
"""
from copy import deepcopy
from pathlib import Path
import hashlib
import json
import bom
import cad_export
import profile_export
import stl_export
import package_export
from export_transaction import directory


def source_indices(design):
    return list(getattr(design,'source_indices',range(1,len(design.parts)+1)))


def scope(design):return deepcopy(getattr(design,'export_scope',None))


def subset(design,indices,revision=None):
    """Copy zero-based current positions while retaining one-based source identity."""
    indices=tuple(indices)
    if any(type(i) is not int for i in indices):raise ValueError('Component selection requires source positions.')
    indices=tuple(sorted(set(indices)))
    if not indices:raise ValueError('Select at least one current component.')
    if any(type(i) is not int or i<0 or i>=len(design.parts) for i in indices):raise ValueError('Component selection is out of date.')
    result=deepcopy(design)
    result.parts=[result.parts[i] for i in indices]
    original=source_indices(design)
    result.source_indices=[original[i] for i in indices]
    result.export_scope=dict(kind='selected components',complete_assembly=False,
        source_component_count=getattr(design,'export_scope',{}).get('source_component_count',len(design.parts)),source_indices=result.source_indices,
        components=[dict(source_index=original[i],name=design.parts[i].name) for i in indices],
        document_revision=revision,coordinates='nominal assembly; display motion, explosion and section do not apply')
    # Calculations belong to the source model, never to a newly inferred subset assembly.
    result.analysis=deepcopy(design.analysis)
    result.analysis['export_scope']=deepcopy(result.export_scope)
    result.notes.insert(0,'SELECTED COMPONENTS ONLY. Calculations describe the source configuration, not a complete exported assembly.')
    return result


def export(design,indices,kind,target,config=None,png=None,revision=None):
    selected=subset(design,indices,revision)
    if kind=='package':return package_export.export(selected,config,target,png)
    with directory(target) as staging:
        if kind=='step':cad_export.write_files(selected,staging)
        elif kind=='profiles':profile_export.write_files(selected,staging)
        elif kind=='stl':stl_export.export(selected,staging/'selected')
        else:raise ValueError('Unknown selected export format')
        bom.export(selected,staging/'selected')
        (staging/'selection.json').write_text(json.dumps(selected.export_scope,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        files=[dict(path=str(p.relative_to(staging)),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(staging.rglob('*')) if p.is_file()]
        (staging/'manifest.json').write_text(json.dumps(dict(format='ratiolab-selected-export/1',complete=True,complete_assembly=False,units='mm',scope=selected.export_scope,files=files),indent=2)+'\n',encoding='utf-8')
    return Path(target)
