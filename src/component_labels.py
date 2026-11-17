# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Readable component names for both workspace inspectors."""
import re


def component_title(part):
    """Readable presentation only; source names and indices remain authoritative."""
    name=part.name;stage=re.match(r'^S(\d+)_(.*)$',name)
    if stage:name=stage.group(2)
    qualifier=re.search(r'_(envelope|generated|prescribed)$',name)
    if qualifier:name=name[:qualifier.start()]
    compound=re.fullmatch(r'Compound_(\d+)_(rim(\d+)|hub)',name)
    if compound:
        title=f'Compound planet {compound.group(1)} · '+(f'rim {compound.group(3)}' if compound.group(3) else 'hub')
    else:
        def words(value):
            tokens=re.sub(r'(?<=[a-z])(?=[A-Z])',' ',value.replace('_',' ')).split()
            return ' '.join(token if token.isupper() else token.lower() for token in tokens)
        prefixes={'Generator_wave':'wave generator','Disc_cycloidal':'cycloidal disc',
            'Bearing_eccentric':'eccentric bearing','Bearing_planetcarrier':'planet carrier bearing',
            'Shaft_input':'input shaft','Shaft_output':'output shaft','Flange_output':'output flange',
            'Pin_output':'output pin','Ring_output':'output ring','Ring_fixed':'fixed ring',
            'Sun_input':'input sun','Pinion_input':'input pinion'}
        title=words(name)
        for prefix,replacement in prefixes.items():
            if name==prefix or name.startswith(prefix+'_'):
                title=replacement+(' '+words(name[len(prefix)+1:]) if name!=prefix else '');break
        if title.endswith((' lower',' upper')):
            body,position=title.rsplit(' ',1);title=position+' '+body
        title=title[:1].upper()+title[1:]
    if qualifier:title+=' · '+qualifier.group(1)
    layer=part.port.get('layer')
    if type(layer) is int:title+=f' · layer {layer}'
    return (f'Stage {stage.group(1)} · ' if stage else '')+title
