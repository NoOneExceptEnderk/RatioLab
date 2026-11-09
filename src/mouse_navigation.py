# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""CAD-inspired pointer mappings, independent of GTK and model geometry."""
LEFT, MIDDLE, RIGHT = 1, 2, 4
PROFILES = {'ratiolab': 'RatioLab', 'freecad': 'FreeCAD (CAD)', 'fusion': 'Fusion',
            'solidworks': 'SOLIDWORKS', 'inventor': 'Inventor', 'solidcraft': 'SolidCraft'}
SUMMARIES = {
    'ratiolab': 'Left drag to orbit · right drag to pan · scroll to zoom · double click to fit',
    'freecad': 'Hold middle, then left or right: orbit · middle drag: pan · wheel: zoom',
    'fusion': 'Shift + middle drag: orbit · middle drag: pan · wheel: zoom',
    'inventor': 'Shift + middle drag: orbit · middle drag: pan · wheel: zoom',
    'solidworks': 'Middle drag: orbit · Ctrl + middle drag: pan · Shift + middle drag or wheel: zoom',
    'solidcraft': 'Right drag or Shift + middle drag: orbit · middle drag: pan · wheel: zoom',
}


def profile(value):
    return value if isinstance(value, str) and value in PROFILES else 'ratiolab'


def drag_mode(value, buttons, *, shift=False, control=False, alt=False, pan_mode=False):
    value = profile(value)
    if pan_mode and buttons == LEFT:
        return 'pan'
    if value == 'ratiolab':
        return 'pan' if buttons == RIGHT else 'orbit' if buttons == LEFT else None
    if value == 'freecad':
        if buttons & MIDDLE:
            return 'orbit' if buttons & (LEFT | RIGHT) else 'pan'
        return None
    if alt:
        return None
    if value == 'solidworks':
        if buttons != MIDDLE or shift and control:
            return None
        return 'zoom' if shift else 'pan' if control else 'orbit'
    if value == 'solidcraft' and buttons == RIGHT:
        return 'orbit'
    if buttons == MIDDLE:
        if control:
            return 'pan' if value == 'inventor' and not shift else None
        return 'orbit' if shift else 'pan'
    return None
