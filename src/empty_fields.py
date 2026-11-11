# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Confirm blank numeric edits against the current geometric construction."""
from dataclasses import dataclass
from decimal import Decimal
from copy import deepcopy
import time


def minimum(family, values, key, bounds, *, quality=None, check=lambda:None,
            accept=None, seconds=30., max_candidates=5000, integer=None):
    """Find a verified compatible lower boundary; prefer zero when valid.

    Scan discrete domains in ascending order, without monotonicity assumptions.
    For continuous fields refine the first detected feasible boundary to six
    decimal places. Never alter another field or return an untested value.
    A current off-grid value is an additional upper bound. Limits fail
    explicitly, rather than labelling an unfinished search a proven minimum.
    """
    from geometry import generate, validate, INTEGER
    from precise_numbers import attach, from_text
    low,high,step=map(lambda x:Decimal(str(x)),bounds)
    step=abs(step)
    if step<=0:raise ValueError('Minimum search needs a positive field step.')
    integer=key in INTEGER if integer is None else integer
    quantum=min(step,Decimal('0.000001'))
    current=Decimal(str(float(values[key])))
    deadline=time.monotonic()+seconds;tested={};count=0
    def valid(value):
        nonlocal count
        check()
        if time.monotonic()>deadline or count>=max_candidates:
            raise ValueError('Minimum compatible value search limit reached. Enter a value.')
        if value in tested:return tested[value]
        count+=1
        candidate=deepcopy(values);attach(candidate,key,from_text(str(value)))
        try:
            if accept is not None:passed=bool(accept(candidate))
            else:
                validate(family,candidate)
                design=generate(family,candidate,quality=quality)
                passed=key in design.values and float(design.values[key])==float(candidate[key])
        except ValueError:passed=False
        tested[value]=passed
        return passed
    def refined(left,right):
        if integer or left is None:return format(right,'f')
        # Refine the first detected feasible boundary, rather than treating the
        # coarse input increment as the final precision of a continuous field.
        from decimal import ROUND_FLOOR,ROUND_CEILING
        lo=int((left/quantum).to_integral_value(rounding=ROUND_FLOOR))
        hi=int((right/quantum).to_integral_value(rounding=ROUND_CEILING))
        if not valid(hi*quantum):return format(right,'f')
        while hi-lo>1:
            middle=(lo+hi)//2
            if valid(middle*quantum):hi=middle
            else:lo=middle
        return format(hi*quantum,'f')
    if low<=0<=high and valid(Decimal(0)):return '0'
    value=low;last_invalid=None
    while value<=high:
        if low<=current<value and current not in tested and valid(current):return refined(last_invalid,current)
        if valid(value):return refined(last_invalid,value)
        last_invalid=value
        value+=step
    raise ValueError('No compatible value was found for the empty field.')


@dataclass(frozen=True)
class Request:
    family: str
    values: dict
    fields: tuple
    signature: object
    quality: dict


def prepare(request,current):
    from rust_geometry import control_scope
    from precise_numbers import attach,from_text
    deadline=time.monotonic()+30.
    def check():
        if not current():raise RuntimeError('Minimum search superseded')
        if time.monotonic()>deadline:raise ValueError('Minimum compatible value search limit reached. Enter a value.')
    values=deepcopy(request.values);result={}
    with control_scope(check):
        while True:
            previous=dict(result)
            for key,bounds in request.fields:
                result[key]=minimum(request.family,values,key,bounds,quality=request.quality,check=check)
                attach(values,key,from_text(result[key]))
            # Simultaneous blank edits can relax each other's constraints.
            # Recheck all requested fields until their verified minima agree.
            if len(request.fields)==1 or result==previous:break
    return result


class Controller:
    def __init__(self,app):
        from gi.repository import GLib
        from geometry_refresh import LatestOnly
        self.app=app;self.pending=set();self.scheduled=0;self.waiting=False
        self.worker=LatestOnly(prepare,lambda callback,*args:GLib.idle_add(callback,*args),self.completed)
        app.win.connect('unrealize',lambda *_:self.worker.close())
    def discard(self):
        from gi.repository import GLib
        self.pending.clear();self.worker.invalidate();self.waiting=False
        if self.scheduled:GLib.source_remove(self.scheduled);self.scheduled=0
    def signature(self):
        a=self.app
        return (a.document.token[0],a.family,tuple((k,id(w),w.get_text()) for k,w in a.inputs.items()),
                tuple(sorted(a.option_values.items())),a.motion_speed_text.get_text(),tuple(sorted(a.quality.items())))
    def changed(self):
        from gi.repository import GLib
        self.worker.invalidate();self.waiting=False
        if self.pending and not self.scheduled:self.scheduled=GLib.idle_add(self.submit)
    def request(self,widget):
        a=self.app
        if a.building or getattr(a,'project_restoring',False):return
        key=next((k for k,w in a.inputs.items() if w is widget),None)
        if key is not None:self.pending.add(key);self.changed()
    def submit(self):
        from gui_workflow import numeric_value
        from precise_numbers import attach
        a=self.app;self.scheduled=0
        self.pending={k for k in self.pending if k in a.inputs and not a.inputs[k].get_text().strip() and a.inputs[k].get_sensitive()}
        if not self.pending:return False
        accepted=a.canvas.design
        if accepted is None or accepted.family!=a.family:return False
        values=deepcopy(accepted.values);values.update(a.option_values)
        fields=[]
        try:
            for key,widget in a.inputs.items():
                if key in self.pending:
                    q=widget.get_adjustment()
                    step=getattr(widget,'_minimum_search_step',q.get_step_increment())
                    fields.append((key,(q.get_lower(),q.get_upper(),step)))
                else:attach(values,key,numeric_value(widget))
            attach(values,'input_rpm',numeric_value(a.motion_speed_text))
        except ValueError:return False  # Keep unrelated incomplete drafts intact.
        self.waiting=True
        a.status_text('Searching for the minimum compatible value…')
        self.worker.submit(Request(a.family,values,tuple(fields),self.signature(),deepcopy(a.quality)))
        return False
    def completed(self,request,result,error):
        if not self.app.project_alive:return
        if request.signature!=self.signature():self.changed();return
        self.waiting=False
        if error is not None:
            self.app.status_text(str(error));return
        from gui_workflow import _set_explicit_numeric_text
        self.pending.difference_update(result)
        for key,text in result.items():_set_explicit_numeric_text(self.app.inputs[key],text)
        self.app.changed(self.app.inputs[next(iter(result))])
