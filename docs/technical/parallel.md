# Parallel-shaft compound reducers

The `parallel` family retains its single-stage spur/helical/double-helical pairs.
Two- and three-stage constructions use **external cylindrical pairs** on three
or four fixed parallel shafts. Each supports spur, helical and double-helical
teeth. Legacy `two_stage`/`three_stage` keys remain spur; `_helical` and `_double`
suffixes select the new teeth. These are nominal
geometry and ideal kinematics, not rated gearboxes.

## References and conventions

- [Neugart, Multi-stage Gearbox](https://www.neugart.com/en/wiki/multi-stage-gearbox),
  introductory spur direction statement and **How is the gear ratio calculated?**:
  external stages reverse rotation and their ratios multiply. Accessed 2026-11-03.
- Individual cylindrical pairs reuse the equations, sources and domains in
  [calculations](calculations.md), including the current ISO 21771:2007 terminology,
  balanced profile shifts, working centre distance and usable involute limitations.

All axes are world +Z; length is mm, speed rpm, tooth counts integers. Positive
rotation is counterclockwise viewed from +Z toward XY. All shafts are fixed in
position; there is no rotating carrier. Let stage j have pinion teeth zp,j,
wheel teeth zw,j, and the two shaft speeds nj−1 and nj. Equal pitch-line speed
with external engagement gives:

```
zp,j * nj−1 + zw,j * nj = 0
ij = nj−1 / nj = −zw,j / zp,j
i = n0 / nN = (−1)^N * product(zw,j / zp,j)
nN = n0 / i
```

The preceding wheel and following pinion form a rigid compound on each
intermediate shaft. For reverse operation the last shaft is prescribed instead:
`n0 = nN * i`, and the reported input/output ratio is `1/i`. The same equations
hold at zero speed and for signed speeds. Efficiency does not change ideal RPM.
Only overall assumed efficiency is specified; the report does not invent a
per-stage loss distribution or per-stage mesh forces.

## Helical and double-helical stages

[KHK, ABCs of Gears Basic Guide B](https://khkgears.us/media/fqrlut1m/abcs-of-gearing-b.pdf),
printed pp4–5 equations (1.1)/(1.2), gives the external and compound speed
relations; p19 equations (2.13)/(2.14) gives `mt = mn / cos(beta)` and `d = z mt`.
[KHK-USA, Making the Best Selection](https://khkgears.us/media/pk4cfvrt/gear-solutions_khk_making-the-best-selection.pdf),
p22, specifies opposite hands for mating parallel helical gears and adjacent
opposite helices for herringbone gears. References accessed 2026-11-03.

Every active stage has its own signed **pinion** helix angle, normal module `mn`
and normal pressure angle `alpha_n`. Its wheel uses the opposite angle. The
next compound pinion may have a different stage angle. The existing normal-rack
profile construction uses:

```
mt = mn / cos(beta)
alpha_t = atan(tan(alpha_n) / cos(beta))
rp = mn zp / (2 cos(beta)); rw = mn zw / (2 cos(beta))
a0 = rp + rw
```

Balanced shifts and added working centre distance retain their existing rules.
A nonzero helix changes transverse diameters and interaxes, so layout envelope
checks run again. The ideal tooth-count speed ratio is unchanged.

Axial tooth phase follows `phi(z) = z tan(beta) / r`, with z relative to the
stage start. See [Applied Mechanics, section 9.4](https://mechanics.ju.se/MachineElements/herringbone-gears.html),
equations (9.4.1)/(9.4.2); its pitch diameter is translated here to the normal
module convention above. Because `zp kp + zw kw = 0` for slopes `k=tan(beta)/r`,
the weighted mesh phase remains constant at every common axial section.

Double helices reuse the shared mirrored cylindrical surface. **Joined** sets
every stage groove to zero and teeth meet at the mid-plane; **Separated** uses
an independently adjustable positive groove per stage. Width includes the groove;
each active half is `(width − gap)/2`. Matching halves and groove shoulders have
the same axial phase function and opposite weighted slopes. Contact overlap is
reported for **one active half**, including Joined:

```
epsilon_beta = ((width − gap)/2) abs(sin(beta)) / (pi mn)
```

The groove must leave more than 1 mm total tooth width under the existing pair
policy. Separated halves retain the existing short transition to a continuous
root hub. An equal-load assumption could balance opposing axial forces; this
model does not establish that condition or calculate stage thrust/support loads.

## Planar placement and tooth clocking

The first centre line points along +X. **Centre-line turn · stage 2** rotates
the A→B direction into B→C; the stage-3 turn rotates B→C into C→D. These are
signed XY turns about +Z, not angles between shaft axes. Zero continues straight;
+90° folds left and −90° folds right viewed from +Z. Turns accumulate.

For canonical working centre distance aj and cumulative angle theta,j:

```
Cj = Cj−1 + aj * (cos(theta,j), sin(theta,j))
theta,1 = 0
theta,j = sum(turn2 ... turnj)
```

Each stage has its own module, face width, pressure angle, backlash, balanced
profile shift and centre-distance increase. The axial face bands advance along
+Z with positive `stage_gap` between pairs. Intermediate shaft bores are shared
by their two gears and connecting hub. The hub bridges the gap and must fit
strictly below both tooth roots. Nominal shafts span their own gear bands plus
the specified end extensions.

Pinions have a fixed zero tooth datum in the constructed compound. Wheel datum
phi,w satisfies the external mesh phase relation:

```
zp * phi,p + zw * phi,w = (zp+zw)*theta + pi*(zw+1)  (modulo 2*pi)
```

The datum reduces to the existing single-stage `phi,w = pi + pi/zw` at zero
centre-line angle and zero pinion phase. Differentiating recovers the shaft
speed equation. Different tooth datums on a rigid compound are fixed offsets,
not independent rotations. Ports carry explicit shaft and rigid-group identities;
preview animation and RPM-only updates use these identities rather than names.

## Layout validity and limits

Every stage runs the canonical external mesh checks. Nonmating gears, shafts
and connecting hubs are also checked as **full-rotation swept cylinders** using
tip radii and their actual axial spans. Unrelated cylinders must have either
the requested axial or radial separation. Same-shaft interfaces and the two
intentionally meshing gears in each stage are excluded from this envelope test.
It conservatively rejects some potentially feasible interleaved layouts; it
does not prove tooth conjugacy, manufacturing clearance or loaded contact.
Discrete interference remains available and reports its own coverage limits.

For example, a 180° turn can fail because an extended shaft enters a previous
gear's envelope. The angle itself is not forbidden: different axial spans can
make the same turn admissible. Rejected browser generation retains the accepted
worker source while the invalid draft blocks export in the document UI.

Compound wheels, hubs and pinions are exported as touching **separate solids**
with common shaft metadata. There is no Boolean fusion or automatic CAD motion
joint. Nominal bores/shafts do not define keys, splines, fits or torque capacity.
Automatic catalog bearing seats and standard hardware currently cover the
single-stage pair only; multistage constructions use manual shaft dimensions.
The working-backlash solver likewise remains limited to single-stage pairs.

## Independent checks

For tooth pairs 20/60 and 20/80, `i=+12`; at 1500 rpm the shaft speeds are
`1500, −500, +125 rpm`. Adding 20/60 gives `i=−36` and output `−125/3 rpm`.
Reverse prescribed output recovers the original input. At module 2, zero shift
and centre increase, the first two interaxes are 80 and 100 mm; a +90° second
turn gives centres `(0,0), (80,0), (80,100)`. The three-stage default uses module
2.5 in its final pair (100 mm interaxis) to clear the preceding wheel with the
default shaft overhangs. Mirroring turn signs preserves ratios and distances.

The KHK normal-system example gives `d=60/cos(15°)=62.1165708246 mm` for
30 teeth and normal module 2. The first default pair at 20° helix has interaxis
`80/cos(20°)=85.1342217981 mm`; zero helix recovers the old spur contours and
interaxes. Tests also probe actual sections across both halves, closed moving
surfaces and intentionally wrong phase controls.

Tests cover these Fraction benchmarks, signed/zero speeds, independent pair
dimensions, phase relations, rigid compounds, nonmating envelope rejection,
rate-only surface/pose preservation, finite searches, saved projects and shared
STEP/STL/SVG/DXF exports. These checks do not establish strength, durability,
bearing life or physical backdrivability.
