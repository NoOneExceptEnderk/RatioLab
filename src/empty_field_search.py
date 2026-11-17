# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Search blank numeric edits against the current geometric construction."""
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
