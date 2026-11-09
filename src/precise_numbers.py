# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Keep exact decimal sources while legacy presentation code uses float values.

Expressions describe arithmetic for Rust to evaluate at its working precision;
they are never evaluated with Python Decimal as a geometry implementation.
Ordinary binary64 sampled coordinates remain plain floats.
"""
from decimal import Decimal, InvalidOperation
from math import isfinite

SOURCE_KEY='_decimal_inputs'


def canonical(text):
    text=str(text).strip().replace(',','.')
    if not text or len(text)>512:
        raise ValueError('Invalid decimal input length.')
    try:value=Decimal(text)
    except InvalidOperation as error:raise ValueError('Invalid decimal input.') from error
    if not value.is_finite():raise ValueError('Finite decimal input required.')
    sign,digits,exponent=value.as_tuple()
    digits=list(digits)
    while len(digits)>1 and digits[-1]==0:
        digits.pop();exponent+=1
    if not any(digits):return '0'
    return str(Decimal((sign,tuple(digits),exponent)))


def source(value):
    return value.expression if isinstance(value,PreciseFloat) else value


class _Expression:
    """Build derived sources without evaluating intermediate floats in Python."""
    def __init__(self,expression):self.expression=expression
    def _binary(self,other,op,reverse=False):
        a,b=(other,self) if reverse else (self,other)
        def operand(v):return v.expression if isinstance(v,(_Expression,PreciseFloat)) else v
        return _Expression({'expression':[op,operand(a),operand(b)]})
    def __add__(self,v):return self._binary(v,'add')
    def __radd__(self,v):return self._binary(v,'add',True)
    def __sub__(self,v):return self._binary(v,'sub')
    def __rsub__(self,v):return self._binary(v,'sub',True)
    def __mul__(self,v):return self._binary(v,'mul')
    def __rmul__(self,v):return self._binary(v,'mul',True)
    def __truediv__(self,v):return self._binary(v,'div')
    def __rtruediv__(self,v):return self._binary(v,'div',True)
    def __neg__(self):return _Expression({'expression':['neg',self.expression]})


def symbolic(value):
    return _Expression({"exact":value.expression}) if isinstance(value,PreciseFloat) else value


def select_source(operation,values):
    if operation not in ('min','max'):raise ValueError('Unknown source selector.')
    values=list(values)
    if any(isinstance(v,_Expression) for v in values):
        return _Expression({'choose':[operation,*[v.expression if isinstance(v,_Expression) else v for v in values]]})
    return (min if operation=='min' else max)(values)


def evaluate_sources(data):
    """Resolve a derived layout in one Rust call; ordinary floats keep their
    original Python operation order. Returned precise values keep the full AST.
    """
    rows=[]
    def collect(v):
        if isinstance(v,_Expression):rows.append(v.expression)
        elif isinstance(v,dict):
            for x in v.values():collect(x)
        elif isinstance(v,(list,tuple)):
            for x in v:collect(x)
    collect(data)
    if not rows:return data
    from rust_geometry import call
    results=iter(call('numeric_batch',dict(values=rows,fold_plain_branches=True)))
    def replace(v):
        if isinstance(v,_Expression):
            r=next(results)
            return r['value'] if r['plain'] else PreciseFloat(r['value'],r['source'])
        if isinstance(v,dict):return {k:replace(x) for k,x in v.items()}
        if isinstance(v,list):return [replace(x) for x in v]
        if isinstance(v,tuple):return tuple(replace(x) for x in v)
        return v
    return replace(data)


class PreciseFloat(float):
    def __new__(cls,value,expression=None):
        obj=super().__new__(cls,value)
        if not isfinite(obj):raise ValueError('Finite numerical compatibility value required.')
        obj.expression=expression if expression is not None else canonical(value)
        return obj

    def __reduce__(self):
        return type(self),(float(self),self.expression)

    def _binary(self,other,name,reverse=False):
        if not isinstance(other,(int,float)) or isinstance(other,bool):return NotImplemented
        a,b=(other,self) if reverse else (self,other)
        expression={'expression':[name,source(a),source(b)]}
        # Recompute the compatibility number from the original expression too.
        # Reusing rounded float operands here would accumulate cancellation and
        # could contradict an otherwise valid exact source at validation.
        from rust_geometry import call
        value=call('numeric_compatibility',dict(value=expression))
        return PreciseFloat(value,expression)

    def __add__(self,other):return self._binary(other,'add')
    def __radd__(self,other):return self._binary(other,'add',True)
    def __sub__(self,other):return self._binary(other,'sub')
    def __rsub__(self,other):return self._binary(other,'sub',True)
    def __mul__(self,other):return self._binary(other,'mul')
    def __rmul__(self,other):return self._binary(other,'mul',True)
    def __truediv__(self,other):return self._binary(other,'div')
    def __rtruediv__(self,other):return self._binary(other,'div',True)
    def __pow__(self,other,modulo=None):
        if modulo is not None:return NotImplemented
        return self._binary(other,'pow')
    def __rpow__(self,other):return self._binary(other,'pow',True)
    def __neg__(self):return PreciseFloat(-float(self),{'expression':['neg',self.expression]})
    def __abs__(self):return self if self>=0 else -self


def from_text(text):
    exact=canonical(text);value=float(exact)
    if not isfinite(value):raise ValueError('Finite numeric input required.')
    return value if exact==canonical(str(value)) else PreciseFloat(value,exact)


def attach(values,key,value):
    sources=dict(values.get(SOURCE_KEY,{}))
    if isinstance(value,PreciseFloat):sources[key]=value.expression
    else:sources.pop(key,None)
    if sources:values[SOURCE_KEY]=sources
    else:values.pop(SOURCE_KEY,None)
    values[key]=value


def restore(values):
    result=dict(values)
    sources=result.get(SOURCE_KEY,{})
    if not isinstance(sources,dict) or len(sources)>256:
        raise ValueError('Invalid precise numeric source map.')
    for key,expression in sources.items():
        if key in result and isinstance(result[key],(int,float)) and not isinstance(result[key],bool):
            # Exact interpretation and bounds are checked in Rust during validation.
            result[key]=PreciseFloat(result[key],expression)
    return result


def transport(value):
    if isinstance(value,PreciseFloat):return value.expression
    if isinstance(value,dict):
        result=None
        for key,v in value.items():
            converted=transport(v)
            if converted is not v:
                if result is None:result=dict(value)
                result[key]=converted
        return value if result is None else result
    if isinstance(value,(list,tuple)):
        result=None
        for i,v in enumerate(value):
            converted=transport(v)
            if converted is not v:
                if result is None:result=list(value)
                result[i]=converted
        return value if result is None else result
    return value


def valid_sources(value):
    if not isinstance(value,dict) or len(value)>256:return False
    remaining=[4096]
    def valid(v,depth=0):
        remaining[0]-=1
        if remaining[0]<0 or depth>64:return False
        if isinstance(v,str):
            try:return len(v)<=512 and canonical(v) is not None
            except ValueError:return False
        if type(v) in (int,float):return isfinite(v)
        if not isinstance(v,dict) or set(v)!={'expression'}:return False
        row=v['expression']
        return (isinstance(row,list) and len(row) in (2,3) and row[0] in ('neg','add','sub','mul','div','pow')
                and (len(row)==2)==(row[0]=='neg') and all(valid(q,depth+1) for q in row[1:]))
    return all(isinstance(k,str) and valid(v) for k,v in value.items())
