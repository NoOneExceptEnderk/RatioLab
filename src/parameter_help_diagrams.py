# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Original technical help drawings, rendered directly with Cairo.

This module deliberately imports neither GTK nor a CAD/mesh renderer. Geometry
is illustrative: it identifies dimensions and reference planes, not the exact
current model, contact, manufacturing accuracy or strength. Supplied variants,
double-helix style and thread hand select structure; sizes/counts are schematic.
"""
from dataclasses import dataclass
from math import acos, atan2, cos, hypot, pi, sin, tan

PAPER = (.965, .975, .981)
INK = (.20, .28, .35)
MUTED = (.38, .47, .54)
EDGE = (.60, .68, .74)
FILL = (.79, .84, .88)
BLUE = (.25, .48, .61)
BLUE_FILL = (.83, .90, .94)
ORANGE = (.84, .32, .10)
ORANGE_FILL = (.98, .85, .73)
WHITE = (1., 1., 1.)


@dataclass(frozen=True)
class TextBox:
    text: str
    x: float
    y: float
    width: float
    height: float


@dataclass(frozen=True)
class RenderInfo:
    kind: str
    labels: tuple


def gear_outline(cx, cy, radius=55, teeth=18, phase=0.):
    """Sampled involute flanks with a schematic root transition.

    Used for visual recognition only. The app's canonical gear construction is
    deliberately not imported or replaced. ``radius`` is the pitch radius.
    """
    m = 2*radius/teeth
    base = radius*cos(pi/9)
    tip = radius+m
    root = max(radius-1.25*m, .1)
    inv_ref = tan(pi/9)-pi/9

    def half(r):
        a = acos(min(1., base/max(base, r)))
        return pi/(2*teeth)+inv_ref-(tan(a)-a)

    points = []
    for j in range(teeth):
        a = phase+2*pi*j/teeth
        points.append((cx+root*cos(a-pi/teeth), cy+root*sin(a-pi/teeth)))
        points.append((cx+root*cos(a-half(base)), cy+root*sin(a-half(base))))
        for k in range(8):
            r = max(root, base)+(tip-max(root, base))*k/7
            points.append((cx+r*cos(a-half(r)), cy+r*sin(a-half(r))))
        for k in range(1, 5):
            q = a-half(tip)+2*half(tip)*k/4
            points.append((cx+tip*cos(q), cy+tip*sin(q)))
        for k in range(7, -1, -1):
            r = max(root, base)+(tip-max(root, base))*k/7
            points.append((cx+r*cos(a+half(r)), cy+r*sin(a+half(r))))
        points.append((cx+root*cos(a+half(base)), cy+root*sin(a+half(base))))
        points.append((cx+root*cos(a+pi/teeth), cy+root*sin(a+pi/teeth)))
    return points


def pressure_contact_geometry():
    """Reference points whose flank tangent and normal are perpendicular."""
    a = 28*pi/180
    p = (164., 118.)
    return p, (cos(a), -sin(a)), (sin(a), cos(a))


class Drawing:
    def __init__(self, cr):
        self.cr = cr
        self.labels = []

    def path(self, points, *, close=False, color=INK, fill=None, width=1.5, dash=()):
        if not points:
            return
        c = self.cr
        c.new_path(); c.move_to(*points[0])
        for p in points[1:]:c.line_to(*p)
        if close:c.close_path()
        c.set_line_width(width);c.set_dash(dash)
        if fill:
            c.set_source_rgb(*fill);c.fill_preserve()
        c.set_source_rgb(*color);c.stroke();c.set_dash(())

    def line(self, x, y, X, Y, color=INK, width=1.5, dash=()):
        self.path(((x,y),(X,Y)),color=color,width=width,dash=dash)

    def circle(self, x, y, r, *, color=INK, fill=None, width=1.5, dash=()):
        c=self.cr;c.new_path();c.arc(x,y,r,0,2*pi)
        c.set_line_width(width);c.set_dash(dash)
        if fill:c.set_source_rgb(*fill);c.fill_preserve()
        c.set_source_rgb(*color);c.stroke();c.set_dash(())

    def ellipse(self, x, y, rx, ry, *, color=INK, fill=None, width=1.5, dash=()):
        points=[(x+rx*cos(i*2*pi/128),y+ry*sin(i*2*pi/128)) for i in range(129)]
        self.path(points,close=True,color=color,fill=fill,width=width,dash=dash)

    def rect(self, x, y, w, h, *, color=INK, fill=None, width=1.5):
        self.path(((x,y),(x+w,y),(x+w,y+h),(x,y+h)),close=True,color=color,fill=fill,width=width)

    def text(self, x, y, value, *, color=INK, size=13, anchor='left', max_width=None, bold=False):
        """Measure every annotation; fit by wrapping instead of tiny fonts."""
        c=self.cr;c.select_font_face('Sans',0,1 if bold else 0);c.set_font_size(size)
        lines=[]
        for paragraph in str(value).split('\n'):
            line=''
            for word in paragraph.split(' '):
                proposed=(line+' '+word).strip()
                if max_width and c.text_extents(proposed)[4] > max_width and line:
                    lines.append(line);line=word
                else:line=proposed
            lines.append(line)
        for index,line in enumerate(lines):
            xb,yb,w,h,advance,_=c.text_extents(line)
            px=x-(advance/2 if anchor=='center' else advance if anchor=='right' else 0)
            py=y+index*(size+4)
            c.set_source_rgb(*color);c.move_to(px,py);c.show_text(line)
            self.labels.append(TextBox(line,px+xb,py+yb,w,h))

    def caption(self, value):
        self.text(20,24,value,color=MUTED,size=12)

    def footer(self, value):
        self.text(180,204,value,color=MUTED,size=13,anchor='center',max_width=330)

    def leader(self, points, *, color=MUTED):
        self.path(points,color=color,width=1.)
        self.circle(*points[0],2,color=color,fill=color,width=.5)

    def axis(self, x, y, X, Y):
        self.line(x,y,X,Y,BLUE,width=1.,dash=(6,3,1,3))

    def arrow(self, x, y, X, Y, *, color=ORANGE, width=1.8, head=6):
        self.line(x,y,X,Y,color,width)
        a=atan2(Y-y,X-x)
        self.path(((X-head*cos(a-.42),Y-head*sin(a-.42)),(X,Y),
                   (X-head*cos(a+.42),Y-head*sin(a+.42))),color=color,width=width)

    def dimension(self, p, q, value, *, offset=0, label_offset=12, color=ORANGE):
        x,y=p;X,Y=q;length=hypot(X-x,Y-y)
        if length < 1e-9:return
        ux,uy=(X-x)/length,(Y-y)/length
        nx,ny=uy,-ux
        a=(x+offset*nx,y+offset*ny);b=(X+offset*nx,Y+offset*ny)
        if abs(offset)>1:
            for p0,p1 in ((p,a),(q,b)):
                self.line(*p0,p1[0]+nx*4,p1[1]+ny*4,color=EDGE,width=.8)
        self.line(*a,*b,color=color,width=1.4)
        head=min(5,length*.23)
        self.arrow(a[0]+ux*head,a[1]+uy*head,*a,color=color,head=head,width=1.3)
        self.arrow(b[0]-ux*head,b[1]-uy*head,*b,color=color,head=head,width=1.3)
        mid=((a[0]+b[0])/2,(a[1]+b[1])/2)
        if abs(ux)>.5:
            self.text(mid[0],mid[1]-label_offset,value,color=color,anchor='center',size=14,bold=True)
        else:
            self.text(mid[0]+label_offset,mid[1]+5,value,color=color,size=14,bold=True)

    def gear(self, x, y, radius, teeth=18, *, fill=FILL, active=False, bore=12, phase=0):
        self.path(gear_outline(x,y,radius,teeth,phase),close=True,
                  fill=ORANGE_FILL if active else fill,color=ORANGE if active else INK,width=1.6)
        self.circle(x,y,radius,color=BLUE,dash=(4,3),width=1.)
        if bore:self.circle(x,y,bore,fill=PAPER,color=INK,width=1.2)

    def ring(self, x, y, pitch=74, teeth=54, *, active=False, rim=10):
        m=2*pitch/teeth
        self.circle(x,y,pitch+1.25*m+rim,fill=FILL,color=INK)
        pts=[]
        for j in range(teeth):
            a=j*2*pi/teeth
            for da,r in ((-.5,pitch+1.25*m),(-.28,pitch-m),(.28,pitch-m),(.5,pitch+1.25*m)):
                pts.append((x+r*cos(a+da*2*pi/teeth),y+r*sin(a+da*2*pi/teeth)))
        self.path(pts,close=True,fill=PAPER,color=ORANGE if active else INK,width=1.3)
        self.circle(x,y,pitch,color=BLUE,width=1.,dash=(4,3))


def _module(d, family, key, values):
    d.caption('Tooth size at the same tooth count')
    d.gear(88,104,35,16,bore=10)
    d.gear(254,104,57,16,bore=16,active=True)
    d.text(88,174,'smaller module',anchor='center',size=13)
    d.text(254,183,'larger module',anchor='center',color=ORANGE,size=13)
    d.footer('Larger module means larger teeth and pitch diameter')


def _teeth(d, family, key, values):
    d.caption('Front view')
    d.gear(124,109,64,18,bore=19,phase=-pi/2)
    # Show a recognisable run of teeth, without claiming these are current z.
    tooth=gear_outline(0,0,64,18,-pi/2)
    per_tooth=len(tooth)//18
    for j in range(3):
        d.path([(x+124,y+109) for x,y in tooth[j*per_tooth:(j+1)*per_tooth]],color=ORANGE,width=3)
    d.text(238,87,'z',color=ORANGE,size=28,bold=True)
    d.text(238,113,'Count teeth',max_width=104,size=14)
    d.text(238,149,'around the\nwhole gear',color=MUTED,size=13)
    d.footer('The dashed circle is the reference pitch circle')


def _pressure(d, family, key, values):
    section='Axial section' if family=='worm' else 'Transverse section' if family=='differential' else 'Normal tooth section'
    d.caption(section)
    p,n,t=pressure_contact_geometry()
    c=d.cr
    if family=='worm' and values.get('variant','za')=='za':
        upper=p[0]-(p[1]-54)*t[0]/t[1]
        lower=p[0]+(169-p[1])*t[0]/t[1]
        d.path(((63,169),(upper-25,54),(upper,54),(lower,169)),
               close=True,fill=FILL,width=1.8)
    else:
        c.new_path();c.move_to(63,169);c.line_to(82,105)
        c.curve_to(90,78,105,57,117,54);c.line_to(137,54)
        c.curve_to(140,77,p[0]-t[0]*28,p[1]-t[1]*28,*p)
        c.curve_to(p[0]+t[0]*28,p[1]+t[1]*28,184,156,190,169)
        c.close_path();c.set_source_rgb(*FILL);c.fill_preserve();c.set_source_rgb(*INK);c.set_line_width(1.8);c.stroke()
    d.axis(30,118,329,118)
    d.line(*p,p[0]+n[0]*127,p[1]+n[1]*127,color=ORANGE,width=2)
    d.circle(*p,3,color=ORANGE,fill=ORANGE)
    c.new_path();c.arc(*p,46,-28*pi/180,0);c.set_source_rgb(*ORANGE);c.stroke()
    d.text(217,109,'alpha',color=ORANGE,size=14)
    d.text(246,43,'common\nnormal',color=ORANGE,size=13)
    d.text(240,140,'pitch tangent',color=BLUE,size=13)
    d.leader(((142,153),(113,180),(99,180)))
    d.text(25,185,'tooth flank',size=12)
    d.footer('Angle between the normal and the pitch tangent')


def _helix(d, family, key, values):
    d.caption('Tooth trace on a reference cylinder')
    # Cylinder at left; the developed surface explains the angle precisely.
    d.rect(43,69,118,87,fill=FILL,color=EDGE)
    d.ellipse(161,112.5,11,43.5,fill=FILL)
    d.ellipse(43,112.5,11,43.5,fill=BLUE_FILL)
    for y in (75,92,109,126):
        d.path(((45,y),(78,y+10),(117,y+18),(160,min(153,y+24))),color=BLUE,width=2.)
    d.axis(23,112,178,112)
    d.rect(217,65,119,96,fill=WHITE,color=EDGE)
    d.axis(228,91,327,91)
    d.line(228,91,317,141,color=ORANGE,width=2.8)
    c=d.cr;c.new_path();c.arc(228,91,38,0,atan2(50,89));c.set_source_rgb(*ORANGE);c.set_line_width(1.5);c.stroke()
    d.text(274,107,'beta',color=ORANGE,size=14)
    d.text(217,52,'Unrolled surface',size=12,color=MUTED)
    d.text(232,180,'shaft direction',size=12,color=BLUE)
    d.footer('The angle is measured from the shaft axis')


def _double_helix(d, family, key, values):
    d.caption('Opposing tooth traces, axial side view')
    joined=values.get('double_style')=='joined' or family=='double' and values.get('variant')=='joined'
    a,b=(173,173) if joined else (163,183)
    for x,X in ((50,a),(b,296)):
        d.rect(x,73,X-x,86,fill=FILL,color=EDGE)
    d.ellipse(50,116,10,43,fill=BLUE_FILL)
    d.ellipse(296,116,10,43,fill=FILL)
    c=d.cr
    for x,X,reverse in ((50,a,False),(b,296,True)):
        c.save();c.rectangle(x,74,X-x,84);c.clip()
        for offset in (-40,-10,20,50):
            y,Y=(140+offset,75+offset) if reverse else (75+offset,140+offset)
            d.line(x,y,X,Y,color=ORANGE if key=='helix' and offset==-10 else BLUE,width=2.7 if key=='helix' and offset==-10 else 1.5)
        c.restore()
    d.axis(25,116,330,116)
    if key=='double_style':
        d.line(a,73,a,159,color=ORANGE,width=2.5)
        d.line(b,73,b,159,color=ORANGE,width=2.5)
        if joined:
            d.leader(((173,73),(199,48),(221,48)),color=ORANGE)
            d.text(226,52,'join',color=ORANGE,size=14)
            d.footer('Joined halves meet at the centre: no groove')
        else:
            d.dimension((a,73),(b,73),'g',offset=24,label_offset=8)
            d.footer('The central groove separates the opposing halves')
    else:
        d.text(97,183,'one hand',color=ORANGE,size=13,anchor='center')
        d.text(249,183,'opposite hand',color=ORANGE,size=13,anchor='center')
        d.footer('Each half has the same angle magnitude')


def _width(d, family, key, values):
    d.caption('Front view and axial side view')
    d.gear(76,105,43,18,bore=13)
    d.rect(173,60,117,88,fill=FILL)
    for y in (68,82,128,142):d.line(173,y,290,y,color=EDGE,width=1)
    d.rect(150,94,163,22,fill=BLUE_FILL,color=BLUE)
    for x in (173,290):d.line(x,60,x,148,color=ORANGE,width=2.5)
    d.axis(138,105,326,105)
    d.dimension((173,148),(290,148),'b',offset=-30)
    d.footer('Axial distance between the two gear faces')


def _cone(d, family, key, values):
    d.caption('Bevel pitch cone')
    apex=(30,111);inner=(158,79);outer=(290,46)
    d.path((inner,outer,(290,176),(158,143)),close=True,fill=FILL,color=INK)
    d.ellipse(290,111,13,65,fill=BLUE_FILL)
    d.ellipse(158,111,7,32,fill=BLUE_FILL)
    d.axis(16,111,325,111)
    d.line(*apex,*inner,color=BLUE,width=1,dash=(4,3))
    d.line(*apex,158,143,color=BLUE,width=1,dash=(4,3))
    for y,Y in ((87,61),(97,83),(126,141),(136,163)):
        d.line(158,y,290,Y,color=EDGE,width=1)
    if key=='width':
        d.line(*inner,*outer,color=ORANGE,width=2.5)
        d.dimension(inner,outer,'b',offset=17,label_offset=7)
        d.footer('Face width follows the pitch-cone generator')
    elif key in ('spiral_angle','spiral_hand'):
        c=d.cr;c.new_path();c.move_to(166,88);c.curve_to(203,63,246,68,290,91)
        c.set_source_rgb(*ORANGE);c.set_line_width(3);c.stroke()
        d.text(176,174,'curved tooth trace',color=ORANGE,size=13)
        d.footer('Angle magnitude and local hand are separate controls')
    elif key in ('side_teeth','output_teeth'):
        # Emphasise the bevel's tooth-bearing outer rim, not a diameter.
        for angle in (-1.35,-.95,-.55,0.,.55,.95,1.35):
            X,Y=290+13*cos(angle),111+65*sin(angle)
            d.line(X-10,Y,X+5,Y,color=ORANGE,width=3)
        d.text(94,174,'z = teeth on this bevel',color=ORANGE,size=14)
        d.footer('Each side gear' if key=='side_teeth' else 'Transverse output / spider gear')
    else:
        d.dimension((290,46),(290,176),'do',offset=30)
        d.text(35,161,'apex',size=12,color=MUTED)
        d.footer('Outer reference diameter: do = mo x z')


def _bore(d, family, key, values):
    d.caption('Front view')
    if family=='cycloidal':
        _disc(d,seat=True)
        x,y=126,106
    elif family=='harmonic' and key=='bore':
        d.ellipse(124,105,75,61,fill=FILL)
        d.ellipse(124,105,56,43,fill=BLUE_FILL,color=BLUE)
        x,y=124,105
    else:
        d.gear(124,105,66,18,bore=0)
        x,y=124,105
    d.circle(x,y,25,fill=PAPER,color=ORANGE,width=2.7)
    d.axis(x-86,y,x+86,y)
    d.dimension((x-25,y),(x+25,y),'d',label_offset=10)
    d.leader(((x+14,y+21),(220,148),(237,148)))
    d.text(238,153,'through hole',size=13,max_width=102)
    if family=='cycloidal':d.footer('The disc seat is centred on the eccentric axis')
    elif family=='harmonic' and key=='bore':d.footer('Wave-generator input opening')
    else:d.footer('Diameter across the opening, not its radius')


def _backlash(d, family, key, values):
    d.caption('Enlarged tooth-space detail')
    # Locally developed mating tooth sections, with their tangent gap exposed.
    d.path(((36,172),(62,172),(91,71),(117,71),(149,172),(184,172)),close=True,fill=FILL)
    d.path(((164,43),(183,43),(155,140),(178,140),(211,43),(245,43)),close=True,fill=BLUE_FILL,color=BLUE)
    d.axis(24,112,326,112)
    left=117+(149-117)*(112-71)/(172-71)
    right=183+(155-183)*(112-43)/(140-43)
    d.line(117,71,149,172,color=ORANGE,width=2.5)
    d.line(183,43,155,140,color=ORANGE,width=2.5)
    d.dimension((left,112),(right,112),'j',label_offset=14)
    d.leader(((right+4,112),(247,155),(265,155)))
    d.text(256,171,'free space',color=ORANGE,size=13,anchor='center')
    d.footer('Allowance along the reference pitch tangent')


def _tooth_height(d, family, key, values):
    d.caption('Reference tooth section')
    pts=((43,176),(43,160),(86,160),(116,55),(151,55),(184,160),(219,160),(219,176))
    d.path(pts,close=True,fill=FILL)
    d.axis(27,113,327,113)
    d.text(31,104,'pitch line',color=BLUE,size=12)
    if key=='addendum':
        d.line(116,55,151,55,color=ORANGE,width=3)
        d.dimension((219,113),(219,55),'ha* mn',offset=45)
        d.footer('Tooth height above the pitch line, before shift')
    else:
        d.line(43,160,86,160,color=ORANGE,width=3)
        d.line(184,160,219,160,color=ORANGE,width=3)
        d.dimension((219,113),(219,160),'hf* mn',offset=45)
        d.footer('Root depth below the pitch line, before shift')


def _shift(d, family, key, values):
    d.caption('Rack displacement relative to the reference')
    nominal=((43,61),(276,61),(276,83),(256,83),(242,132),(215,132),(200,83),(177,83),(162,132),(135,132),(120,83),(97,83),(82,132),(55,132),(43,83))
    d.path(nominal,close=True,color=EDGE,width=1.2,dash=(4,3))
    raised=[(x,y-23) for x,y in nominal]
    d.path(raised,close=True,fill=BLUE_FILL,color=BLUE,width=1.5)
    d.line(39,83,281,83,color=EDGE,width=1,dash=(3,3))
    d.line(39,60,281,60,color=ORANGE,width=2)
    d.dimension((281,83),(281,60),'x mn',offset=24)
    d.axis(31,155,326,155)
    d.text(36,179,'gear reference pitch line',color=BLUE,size=12)
    d.footer('Rack shift = x * mn; x is dimensionless')


def _planetary(d, family, key, values):
    d.caption('Sun, planets and internal ring')
    x,y=123,109
    d.ring(x,y,72,54,rim=7)
    d.circle(x,y,48,color=BLUE,width=1,dash=(3,4))
    d.gear(x,y,24,18,bore=7,active=key in ('sun','sun2'))
    for a in (-pi/2,pi/6,5*pi/6):
        d.gear(x+48*cos(a),y+48*sin(a),24,18,bore=5,phase=pi/18,
               active=key in ('planet','planet2','planets'))
    d.text(230,72,'sun',color=ORANGE if key in ('sun','sun2') else MUTED,size=14)
    d.text(230,110,'planet' if key!='planets' else 'N planets',color=ORANGE if key in ('planet','planet2','planets') else MUTED,size=14)
    d.text(230,148,'ring',color=MUTED,size=14)
    d.footer('Ring teeth = sun teeth + 2 x planet teeth')


def _disc(d, *, seat=False, selected=''):
    x,y=117,106;e=9
    # A deliberately schematic lobed contour; not the generated cycloidal map.
    pts=[]
    for j in range(441):
        a=2*pi*j/440;r=56+3.8*cos(11*a)
        pts.append((x+e+r*cos(a),y+r*sin(a)))
    d.path(pts,close=True,fill=FILL,color=INK,width=1.4)
    d.circle(x,y,72,color=ORANGE if selected=='radius' else BLUE,width=1,dash=(4,3))
    for j in range(12):
        a=2*pi*j/12
        active=selected=='pins' or selected in ('pin_radius','clearance') and j==0
        d.circle(x+72*cos(a),y+72*sin(a),7,fill=ORANGE_FILL if active else BLUE_FILL,
                 color=ORANGE if active else BLUE,width=2 if active else 1.3)
    for j in range(6):
        a=j*2*pi/6
        hole=(x+e+34*cos(a),y+34*sin(a));pin=(x+34*cos(a),y+34*sin(a))
        d.circle(*hole,14.5,color=EDGE,fill=PAPER,width=1)
        active=selected=='output_count' or selected in ('output_radius','output_pin','output_clearance') and j==0
        d.circle(*pin,4.5,color=ORANGE if active else BLUE,fill=ORANGE if active else BLUE,width=1)
    if not seat:d.circle(x+e,y,16,fill=PAPER,color=INK,width=1.3)
    d.circle(x,y,2,color=BLUE,fill=BLUE,width=1)
    d.circle(x+e,y,2,color=ORANGE,fill=ORANGE,width=1)


def _cycloidal(d, family, key, values):
    d.caption('Disc and roller ring')
    _disc(d,selected=key)
    if key=='radius':
        d.dimension((117,106),(117+72*cos(-pi/4),106+72*sin(-pi/4)),'R',label_offset=9)
        d.text(238,82,'to roller',size=14)
        d.text(238,102,'centres',size=14)
    elif key=='eccentric':
        d.text(228,61,'Enlarged axes',size=12,color=MUTED)
        d.circle(263,109,29,color=BLUE,dash=(4,3),width=1)
        d.axis(235,109,323,109)
        d.axis(263,76,263,145)
        d.circle(263,109,3,fill=BLUE,color=BLUE)
        d.circle(292,109,3,fill=ORANGE,color=ORANGE)
        d.dimension((263,109),(292,109),'e',offset=-31,label_offset=9)
        d.text(257,164,'O',color=BLUE,size=13)
        d.text(287,164,'E',color=ORANGE,size=13)
        d.footer('O: main axis     E: orbiting disc axis')
    elif key=='pin_radius':
        d.text(225,60,'Ring roller',size=13,color=MUTED)
        d.circle(278,111,33,fill=BLUE_FILL,color=ORANGE,width=2.5)
        d.circle(278,111,2,fill=INK)
        d.dimension((278,111),(311,111),'r',label_offset=12)
        d.leader(((196,106),(220,88),(245,92)),color=EDGE)
    elif key=='pins':
        d.text(239,83,'N',color=ORANGE,size=26,bold=True)
        d.text(239,110,'ring rollers',size=14)
        d.text(239,146,'N - 1\ndisc lobes',size=13,color=MUTED)
    elif key=='output_radius':
        d.circle(117,106,34,color=ORANGE,width=1,dash=(4,3))
        d.dimension((117,106),(151,106),'Ro',offset=-48,label_offset=9)
        d.text(231,92,'Output-pin',size=14)
        d.text(231,112,'centre circle',size=14)
    elif key=='output_count':
        d.text(239,83,'K',color=ORANGE,size=26,bold=True)
        d.text(231,111,'output pins',size=14)
        d.footer('The smaller pins connect the disc to the output')
    elif key in ('output_pin','output_clearance'):
        d.text(229,53,'Output hole detail',size=12,color=MUTED)
        d.circle(277,111,43,fill=PAPER,color=INK)
        d.circle(277,111,18,color=BLUE,dash=(3,3),width=1)
        d.circle(295,111,17,fill=ORANGE_FILL if key=='output_pin' else BLUE_FILL,
                 color=ORANGE if key=='output_pin' else BLUE,width=2)
        d.circle(277,111,2,color=BLUE,fill=BLUE)
        if key=='output_pin':
            d.dimension((295,111),(312,111),'ro',offset=-29,label_offset=9)
        else:
            d.line(312,111,320,111,color=ORANGE,width=4)
            d.leader(((316,111),(333,84)),color=ORANGE)
            d.text(333,77,'c',color=ORANGE,anchor='center',size=15,bold=True)
        d.footer('Hole radius = pin radius + eccentricity + c')
    elif key=='clearance':
        d.text(230,57,'Profile gap detail',size=12,color=MUTED)
        d.circle(279,90,27,fill=BLUE_FILL,color=BLUE)
        d.path(((233,154),(234,134),(253,130),(279,126),(303,130),(327,134),(328,154)),
               close=True,fill=FILL)
        d.dimension((279,117),(279,126),'c',offset=33,label_offset=10)
        d.footer('Relief at the outer disc / roller interface')
    else:
        d.text(231,83,'roller ring',color=BLUE,size=13)
        d.text(231,123,'orbiting disc',size=13)


def _sampling(d, family, key, values):
    d.caption('Curve sampling detail')
    c=d.cr;c.new_path();c.move_to(47,156);c.curve_to(100,32,234,39,312,137)
    c.set_source_rgb(*BLUE);c.set_line_width(2.5);c.stroke()
    # The actual cubic midpoint is used; the chord midpoint has the same x.
    p=(47,156);q=(312,137)
    mid=((47+3*100+3*234+312)/8,(156+3*32+3*39+137)/8)
    chord_y=156+(137-156)*(mid[0]-47)/(312-47)
    d.line(*p,*q,color=EDGE,width=1.5,dash=(5,4))
    for point in (p,q):d.circle(*point,3,color=ORANGE,fill=ORANGE)
    d.dimension(mid,(mid[0],chord_y),'deviation',offset=0,label_offset=10)
    d.text(48,181,'sample',color=ORANGE,size=12)
    d.text(270,167,'sample',color=ORANGE,size=12)
    d.footer('Numerical curve-to-chord distance')


def _worm(d, family, key, values):
    d.caption('Axial side view of the worm')
    d.rect(48,78,253,70,fill=FILL,color=EDGE)
    d.ellipse(301,113,7,35,fill=BLUE_FILL)
    d.ellipse(48,113,7,35,fill=BLUE_FILL)
    d.rect(27,101,21,24,fill=FILL)
    d.rect(301,101,28,24,fill=FILL)
    hand=-1 if values.get('worm_hand',1)==-1 else 1
    for x in range(50,290,27):
        if hand>0:d.line(x,80,x+24,145,color=BLUE,width=2)
        else:d.line(x+24,80,x,145,color=BLUE,width=2)
    d.axis(18,113,339,113)
    d.line(39,88,309,88,color=BLUE,width=.8,dash=(4,4))
    d.line(39,138,309,138,color=BLUE,width=.8,dash=(4,4))
    if key=='module':
        d.dimension((104,80),(131,80),'px',offset=25,label_offset=9)
        d.line(104,80,128,145,color=ORANGE,width=2.5)
        d.line(131,80,155,145,color=ORANGE,width=2.5)
        d.footer('Axial pitch px = pi x axial module mx')
    elif key=='diameter':
        d.dimension((302,88),(302,138),'d',offset=24,label_offset=10)
        d.footer('Diameter of the reference pitch cylinder')
    elif key=='length':
        d.dimension((48,148),(301,148),'threaded length',offset=-31,label_offset=10)
        d.footer('End journals are additional to the threaded body')
    elif key=='journal_length':
        d.dimension((301,125),(329,125),'Lj',offset=-48,label_offset=10)
        d.line(301,125,329,125,color=ORANGE,width=2.5)
    elif key=='journal_diameter':
        d.dimension((329,101),(329,125),'dj',offset=3,label_offset=5)
    else:
        d.line(131,80,155,145,color=ORANGE,width=3)
        d.text(180,53,'one highlighted thread',color=ORANGE,size=13,anchor='center')
        d.footer('Changing hand reverses the thread inclination')


def _starts(d, family, key, values):
    d.caption('Unrolled worm reference cylinder')
    d.rect(43,67,274,95,fill=BLUE_FILL,color=EDGE)
    # Two schematic starts. Repeated continuations identify one helix, not
    # the superficial count of diagonal lines crossing a visible half-cylinder.
    for start in (-100,-40,20,80,140,200,260):
        a=max(43,43+start);b=min(317,43+start+120)
        if b<=a:continue
        y1=67+(a-(43+start))*95/120;y2=67+(b-(43+start))*95/120
        d.line(a,y1,b,y2,color=ORANGE if start==20 else BLUE,width=2.5 if start==20 else 1.3)
    # One revolution around the cylinder corresponds to the vertical span;
    # the axial advance of the highlighted trace is the horizontal lead.
    d.dimension((63,162),(183,162),'lead L',offset=-23,label_offset=8)
    d.text(202,48,'one start = one helix',color=ORANGE,size=12,anchor='center')
    d.footer('Lead L = axial pitch px x number of starts')


def _wave(d, family, key, values):
    d.caption('Flexible member inside the rigid ring')
    x,y=120,108
    d.ring(x,y,70,38,rim=6)
    points=gear_outline(0,0,57,36)
    d.path([(x+1.16*X,y+.80*Y) for X,Y in points],close=True,fill=FILL,color=INK,width=1.3)
    wall_active=key=='wall'
    d.ellipse(x,y,58,38,color=ORANGE if wall_active else BLUE,fill=BLUE_FILL,width=2 if wall_active else 1.1)
    d.ellipse(x,y,51,31,color=ORANGE if wall_active else BLUE,fill=PAPER,width=2 if wall_active else 1.1)
    d.circle(x,y,57,color=BLUE,width=1,dash=(4,3))
    d.axis(32,y,205,y)
    if key=='wave_factor':
        d.line(177,108,186,108,color=ORANGE,width=4)
        d.leader(((182,108),(229,76)),color=ORANGE)
        d.text(240,76,'A',color=ORANGE,size=23,bold=True)
        d.text(226,105,'major-axis\noffset',size=13)
        d.footer('Major semiaxis a = reference radius rp + A')
    elif key=='teeth':
        d.text(230,77,'flex: zf teeth',color=ORANGE,size=13)
        d.text(230,118,'ring: zf + 2',size=13)
        d.footer('Two extra teeth belong to the rigid ring')
    else:
        d.text(225,56,'Radial section',size=12,color=MUTED)
        active_name='t' if key in ('wall','bearing_thickness') else 'c'
        d.rect(231,78,97,16,fill=ORANGE_FILL if key=='wall' else FILL,color=ORANGE if key=='wall' else INK)
        d.rect(231,105,97,19,fill=ORANGE_FILL if key=='bearing_thickness' else BLUE_FILL,color=ORANGE if key=='bearing_thickness' else BLUE)
        if key=='wall':d.dimension((328,78),(328,94),active_name,offset=9,label_offset=7)
        elif key=='bearing_thickness':d.dimension((328,105),(328,124),active_name,offset=9,label_offset=7)
        else:d.dimension((319,94),(319,105),active_name,offset=15,label_offset=7)
        d.text(232,153,'flexible wall',size=12)
        d.text(232,173,'wave bearing',size=12,color=BLUE)


def _annulus(d, family, key, values):
    d.caption('Radial section / front view')
    if key=='rim':
        d.ring(132,108,53,36,rim=15)
        inner=53+1.25*2*53/36
        outer=inner+15
    else:
        d.circle(132,108,72,fill=FILL)
        d.circle(132,108,50,fill=PAPER,color=ORANGE,width=2.5)
        inner,outer=50,72
    d.axis(43,108,223,108)
    d.dimension((132+inner,108),(132+outer,108),'w' if key=='flange_width' else 't',offset=-44,label_offset=9)
    d.line(132+inner,108,132+outer,108,color=ORANGE,width=4)
    if key=='flange_width':
        d.text(244,95,'flange width',size=14,color=ORANGE)
        d.text(244,126,'beyond the\nflexible body',size=12,color=MUTED)
        d.footer('Radial extension beyond the flexible body')
    else:
        d.text(244,95,'radial wall',size=14,color=ORANGE)
        d.text(244,126,'outside the\ninner opening',size=12,color=MUTED)
        d.footer('Thickness is a radial amount')


def _printed_bolts(d, family, key, values):
    d.caption('Printed eccentric shaft / cap face')
    d.circle(130,109,66,fill=FILL,color=INK)
    d.axis(45,109,214,109);d.axis(121,30,121,184)
    # The two axial bolt axes are intentionally asymmetric about the shaft
    # centre, matching the construction rather than a generic flange pattern.
    top=(121,71);bottom=(121,140)
    for p in (top,bottom):
        d.circle(*p,13,fill=PAPER,color=ORANGE if key=='print_hole_clearance' else INK,width=1.7)
        d.circle(*p,8,fill=BLUE_FILL,color=BLUE,width=1.2)
    if key=='print_bolt_pitch':
        d.dimension(top,bottom,'p',offset=100,label_offset=11)
        d.text(251,97,'two axial',size=13)
        d.text(251,117,'M3 bolts',size=13)
        d.footer('Spacing is measured between the two bolt axes')
    elif key=='print_min_wall':
        d.dimension((121,58),(121,43),'tmin',offset=90,label_offset=9)
        d.footer('Minimum material remaining beside holes / pockets')
    else:
        d.text(232,52,'Hole detail',size=12,color=MUTED)
        d.circle(282,112,35,fill=PAPER,color=ORANGE,width=2.5)
        d.circle(282,112,24,fill=BLUE_FILL,color=BLUE)
        d.dimension((247,112),(317,112),'d hole',offset=-47,label_offset=9)
        d.footer('Hole diameter = nominal bolt diameter + allowance')


def _centre_distance(d, family, key, values):
    d.caption('External pair with fixed reference tooth sizes')
    d.gear(81,105,36,18,bore=11)
    d.gear(230,105,61,30,bore=17)
    nominal=81+36+61
    d.axis(26,105,317,105)
    d.line(nominal,54,nominal,173,color=EDGE,width=1,dash=(4,3))
    d.line(230,96,230,177,color=ORANGE,width=1)
    d.dimension((81,169),(nominal,169),'a0',offset=-19,label_offset=8)
    d.dimension((nominal,169),(230,169),'extra',offset=-19,label_offset=8)
    d.text(139,49,'reference\noutput axis',color=MUTED,size=12,anchor='center')
    d.leader(((nominal,70),(nominal,40),(175,40)),color=EDGE)
    d.footer('Centre distance = reference a0 + extra')


def _cup(d, family, key, values):
    d.caption('Flexible body, axial section')
    # Open cup, with an end diaphragm at left and the tooth band at right.
    d.path(((80,62),(276,62),(276,82),(96,82),(96,144),(276,144),(276,164),(80,164)),
           close=True,fill=FILL,color=INK)
    for x in range(237,275,8):
        d.rect(x,55,5,7,fill=FILL,color=INK,width=1)
        d.rect(x,164,5,7,fill=FILL,color=INK,width=1)
    d.rect(80,102,16,22,fill=PAPER,color=INK)
    d.axis(44,113,319,113)
    if key=='cup_length':
        d.line(80,62,235,62,color=ORANGE,width=3)
        d.dimension((80,164),(235,164),'body length L',offset=-22,label_offset=9)
    elif key=='diaphragm':
        d.line(80,62,80,102,color=ORANGE,width=3)
        d.line(96,82,96,102,color=ORANGE,width=3)
        d.dimension((80,164),(96,164),'t',offset=-22,label_offset=9)
        d.text(28,47,'end plate',color=ORANGE,size=12)
    else:
        for x in (235,276):d.line(x,55,x,171,color=ORANGE,width=1.5)
        d.dimension((235,62),(276,62),'b',offset=24,label_offset=8)
        d.footer('Only the tooth band, independent of the cup length')


def _pin_clearance(d, family, key, values):
    d.caption('Pin and bore, front view')
    d.circle(130,106,70,fill=FILL,color=INK)
    d.circle(130,106,43,fill=PAPER,color=INK)
    d.circle(130,106,30,fill=BLUE_FILL,color=BLUE)
    d.axis(43,106,217,106)
    d.line(160,106,173,106,color=ORANGE,width=4)
    d.leader(((167,106),(239,72)),color=ORANGE)
    d.text(250,74,'c',color=ORANGE,size=23,bold=True)
    d.text(230,116,'radial\nrunning gap',size=13)
    d.footer('Bore diameter = pin diameter + 2 x radial clearance')


def _flange(d, family, key, values):
    d.caption('Connection face')
    d.circle(130,108,72,fill=FILL)
    d.circle(130,108,22,fill=PAPER,color=INK)
    d.circle(130,108,50,color=BLUE,dash=(4,3),width=1)
    for j in range(6):
        a=j*2*pi/6;x,y=130+50*cos(a),108+50*sin(a)
        active=key in ('bolt_count','hardware_bolts','hardware_screw') or key in ('bolt_diameter','carrier_bolt_diameter','print_hole_clearance') and j==0
        d.circle(x,y,7,fill=PAPER,color=ORANGE if active else INK,width=2.2 if active else 1.3)
    if key=='flange_radius':d.dimension((130,108),(202,108),'R',offset=-86,label_offset=9)
    elif key=='bolt_count':
        d.text(238,88,'N holes',size=17,color=ORANGE)
        d.text(238,121,'equally\nspaced',size=13)
    elif key=='print_bolt_pitch':
        d.dimension((130,58),(130,158),'p',offset=105,label_offset=12)
    else:
        d.dimension((173,108),(187,108),'d',offset=-48,label_offset=9)
        d.text(238,137,'hole diameter',size=13,color=ORANGE,max_width=95)


def _fit(d, family, key, values):
    d.caption('Bearing and its mating diameters')
    d.circle(131,107,72,fill=FILL)
    d.circle(131,107,52,fill=BLUE_FILL,color=BLUE)
    d.circle(131,107,30,fill=PAPER,color=BLUE)
    d.circle(131,107,24,fill=FILL,color=INK)
    shaft=key in ('shaft_allowance','print_journal_allowance','journal_diameter')
    if shaft:
        d.circle(131,107,24,color=ORANGE,width=3)
        d.dimension((107,107),(155,107),'d shaft',offset=-52,label_offset=10)
        d.text(235,93,'bearing bore',size=13,color=BLUE)
        d.text(235,131,'shaft',size=14,color=ORANGE)
    else:
        d.circle(131,107,52,color=ORANGE,width=3)
        d.dimension((79,107),(183,107),'D seat',offset=-77,label_offset=10)
        d.text(235,93,'outer seat',size=14,color=ORANGE)
        d.text(235,131,'bearing',size=13,color=BLUE)
    d.footer('Allowances change diameters, not radial values')


def _section(d, family, key, values):
    d.caption('Axial section')
    d.rect(35,96,288,27,fill=BLUE_FILL,color=BLUE)
    if key in ('gap','disc_gap','stage_gap','assembly_clearance'):
        d.rect(85,61,73,97,fill=FILL)
        d.rect(184,61,73,97,fill=FILL)
        d.dimension((158,61),(184,61),'g',offset=23,label_offset=9)
        d.line(158,61,158,158,color=ORANGE,width=2.5)
        d.line(184,61,184,158,color=ORANGE,width=2.5)
        d.footer('Axial separation between the two facing surfaces')
    elif key in ('input_shaft','output_shaft','spider_pin_diameter'):
        d.rect(117,63,92,92,fill=FILL)
        d.rect(35,96,288,27,fill=BLUE_FILL,color=ORANGE,width=2.5)
        d.dimension((309,96),(309,123),'d',offset=21,label_offset=7)
        d.footer('Diameter perpendicular to the shaft axis')
    elif key in ('shaft_extension','output_extension','cup_length'):
        d.rect(104,63,92,92,fill=FILL)
        d.line(196,96,323,96,color=ORANGE,width=2.5)
        d.line(196,123,323,123,color=ORANGE,width=2.5)
        d.dimension((196,155),(323,155),'L',offset=-24,label_offset=9)
        d.footer('Axial length along the shaft')
    else:
        d.rect(123,59,32,101,fill=ORANGE_FILL,color=ORANGE,width=2)
        d.rect(155,70,80,79,fill=FILL)
        d.dimension((123,160),(155,160),'t',offset=-23,label_offset=8)
        d.footer('Thickness measured along the assembly axis')
    d.axis(21,109.5,339,109.5)


def _motion(d, family, key, values):
    if family=='differential':
        d.caption('Both side speeds use world +X signs')
        d.gear(77,110,30,18,bore=7)
        d.gear(283,110,30,18,bore=7)
        d.path(((108,70),(252,70),(252,149),(108,149)),close=True,color=BLUE,width=2)
        d.axis(29,110,331,110)
        d.arrow(57,48,96,48);d.arrow(262,48,301,48)
        d.text(76,84,'A',color=ORANGE,size=17,anchor='center')
        d.text(282,84,'B',color=ORANGE,size=17,anchor='center')
        d.text(180,106,'carrier C',color=BLUE,size=14,anchor='center')
        d.text(180,180,'C = (A + B) / 2',color=ORANGE,size=15,anchor='center')
        d.footer('Prescribed difference: B - A')
    elif family in ('spur','helical','double'):
        d.caption('One rotating gear')
        d.gear(176,110,57,20,bore=15)
        c=d.cr;c.new_path();c.arc(176,110,76,-2.6,-.54);c.set_source_rgb(*ORANGE);c.set_line_width(2.5);c.stroke()
        d.arrow(233,59,241,71)
        d.text(280,110,'T' if key=='input_torque' else 'n',color=ORANGE,size=20)
        d.footer('Torque T acts on this gear' if key=='input_torque' else 'Speed n describes this gear, without an output pair')
    elif family in ('planetary','cycloidal','harmonic'):
        {'planetary':_planetary,'cycloidal':_cycloidal,'harmonic':_wave}[family](d,family,key,values)
    else:
        d.caption('Driving and driven members')
        d.gear(119,111,42,18,bore=12,active=True)
        d.gear(230,111,69,30,bore=17)
        d.text(92,179,'input',color=ORANGE,size=14)
        d.text(218,197,'output',color=BLUE,size=14)


def _wolfrom(d, family, key, values):
    """Original axial schematic: two rims on one compound, output annulus."""
    d.caption('Two-rim Wolfrom · axial schematic')
    # Aligned compound portions and their joining hub. This shows member
    # connectivity and axial separation, rather than claiming tooth geometry.
    d.axis(24, 145, 333, 145)
    d.rect(68, 54, 70, 21, color=BLUE, fill=BLUE_FILL)
    d.rect(196, 54, 70, 21, color=ORANGE, fill=ORANGE_FILL)
    d.rect(80, 88, 46, 35, color=BLUE, fill=BLUE_FILL)
    d.rect(208, 88, 46, 35, color=ORANGE, fill=ORANGE_FILL)
    d.rect(126, 99, 82, 12, color=INK, fill=BLUE_FILL)
    d.rect(80, 135, 46, 21, color=ORANGE, fill=ORANGE_FILL)
    d.line(54, 85, 54, 175, BLUE, 3)
    d.line(280, 85, 280, 175, BLUE, 3)
    d.line(54, 105, 280, 105, BLUE, 1, (4, 4))
    d.text(103, 46, 'Rf fixed', size=13, anchor='center')
    d.text(231, 46, 'Ro output', size=13, anchor='center', color=ORANGE)
    d.text(103, 109, 'P1', size=14, anchor='center')
    d.text(231, 109, 'P2', size=14, anchor='center')
    d.text(166, 91, 'rigid hub', size=12, anchor='center')
    d.text(103, 173, 'S input', size=13, anchor='center', color=ORANGE)
    d.text(225, 173, 'carrier free', size=13, anchor='center', color=BLUE)
    if key in ('width', 'width2', 'layer_gap'):
        x, X, name = (80, 126, 'b1') if key=='width' else (208, 254, 'b2') if key=='width2' else (126, 208, 'gap')
        d.dimension((x, 124), (X, 124), name, offset=0, label_offset=-16)
    d.footer('+Z signs · ring output; carrier is free')


def diagram_kind(family, key, help=None):
    """Context-sensitive dispatch, kept public for renderer coverage checks."""
    if family=='wolfrom' and key in ('sun','planet','planet2','output_ring','planets','module','width','width2','layer_gap','plate','rim','assembly_clearance','input_rpm','io_scheme'):return 'wolfrom'
    if key=='pressure':return 'pressure'
    if key=='backlash':return 'backlash'
    if key in ('addendum','dedendum'):return 'tooth_height'
    if key=='profile_shift':return 'profile_shift'
    if key=='center_extra':return 'centre_distance'
    if key=='spider_clearance':return 'pin_clearance'
    if key in ('print_bolt_pitch','print_hole_clearance','print_min_wall'):return 'printed_bolts'
    if family=='differential' and key in ('module','width','spiral_angle','spiral_hand','side_teeth','output_teeth'):
        return 'cone'
    if family=='worm' and key in ('module','diameter','length','worm_hand','journal_length','journal_diameter'):
        return 'worm'
    if family=='worm' and key=='starts':return 'starts'
    if key=='module':return 'module'
    if key=='double_style':return 'double_helix'
    if key=='helix':return 'helix'
    if family=='harmonic' and key in ('width','cup_length','diaphragm'):return 'cup'
    if key in ('width','width2'):return 'width'
    if key in ('teeth','pinion','wheel') and family!='harmonic':return 'teeth'
    if key in ('sun','sun2','planet','planet2','planets'):return 'planetary'
    if key in ('bore','output_bore','wheel_bore','passage_diameter'):return 'bore'
    if family=='cycloidal' and key in ('pins','radius','pin_radius','eccentric','output_count','output_radius','output_pin','output_clearance','clearance','eccentric_design'):
        return 'cycloidal'
    if key=='profile_tolerance':return 'sampling'
    if family=='harmonic' and key in ('wave_factor','wall','bearing_thickness','wave_clearance','teeth'):
        return 'wave'
    if key in ('rim','housing_wall','flange_width'):return 'annulus'
    if key in ('flange_radius','bolt_count','bolt_diameter','carrier_bolt_diameter','hardware_bolts','hardware_screw'):
        return 'flange'
    if key in ('bearing','bearing_mode','fit','seat_allowance','shaft_allowance','print_seat_allowance','print_journal_allowance'):
        return 'fit'
    if key in ('input_rpm','input_b_rpm','output_difference_rpm','input_torque','io_scheme','io_scheme2'):
        return 'motion'
    if key in ('plate','assembly_clearance','shaft_extension','stage_gap','disc_gap','gap',
               'input_shaft','output_shaft','spider_pin_diameter','output_extension',
               'shoulder','hardware_shim'):
        return 'section'
    return 'text'


RENDERERS = {
    'wolfrom':_wolfrom,
    'module':_module,'teeth':_teeth,'pressure':_pressure,'helix':_helix,
    'double_helix':_double_helix,
    'width':_width,'cone':_cone,'bore':_bore,'backlash':_backlash,
    'tooth_height':_tooth_height,'profile_shift':_shift,'planetary':_planetary,
    'cycloidal':_cycloidal,'sampling':_sampling,'worm':_worm,'starts':_starts,
    'wave':_wave,'annulus':_annulus,'flange':_flange,'fit':_fit,
    'section':_section,'motion':_motion,'printed_bolts':_printed_bolts,
    'centre_distance':_centre_distance,'cup':_cup,'pin_clearance':_pin_clearance,
}


def draw_diagram(area, cr, width, height, help, *, key='', family='', values=None):
    """Render a 360 x 220 logical technical illustration into any viewport.

    Aspect ratio and context state are preserved. ``area`` is accepted for GTK
    DrawingArea compatibility but never inspected. The returned text metrics
    allow tests to check annotation clipping; callers may ignore the result.
    """
    values=values or {}
    if width<=0 or height<=0:return RenderInfo('empty',())
    kind=diagram_kind(family,key,help)
    if kind=='text':return RenderInfo('text',())
    if key=='helix' and (family=='double' or values.get('variant') in ('double','two_stage_double')):
        kind='double_helix'
    cr.save()
    try:
        cr.rectangle(0,0,width,height);cr.clip()
        cr.set_source_rgb(*PAPER);cr.rectangle(0,0,width,height);cr.fill()
        scale=min(width/360.,height/220.)
        cr.translate((width-360*scale)/2,(height-220*scale)/2)
        cr.scale(scale,scale)
        cr.set_line_join(1);cr.set_line_cap(1)
        d=Drawing(cr)
        RENDERERS[kind](d,family,key,values)
        return RenderInfo(kind,tuple(d.labels))
    finally:
        cr.restore()
