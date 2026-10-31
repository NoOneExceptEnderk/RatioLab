# SPDX-FileCopyrightText: 2026 NoOneExceptEnderk
# SPDX-License-Identifier: GPL-3.0-only
"""Offline, family-aware explanations for the live design controls.

Content follows the canonical technical guides under docs/technical, especially
calculations, worm, strain-wave, differential, io-models and printed-shaft.
Drawings are original schematics rendered by parameter_help_ui, not CAD views.
Keep this registry independent of GTK so coverage can be checked headlessly.
"""
from dataclasses import dataclass, replace


@dataclass(frozen=True)
class Help:
    title: str
    meaning: str
    effect: str
    diagram: str
    dimension: str


def H(title, meaning, effect, diagram='section', dimension=''):
    return Help(title, meaning, effect, diagram, dimension or title)


COMMON = {
    'worm_static_friction': H('Static tooth-contact friction', 'Optional dimensionless coefficient μ for static friction at the actual worm tooth contact. Missing means unknown; explicit 0 assumes frictionless contact.', 'Apply commits the entered coefficient; Clear removes it as unknown; editing or emptying the text alone does not clear the saved value. The wheel-to-worm startup limit is μcritical = cos(αn) tan(γ), with γ = atan(mx × starts / d) and αn = atan(tan(αx) cos(γ)); αx is the axial pressure angle. At or above this limit, wheel-driven startup is refused by this static contact model. Below it, motion is only potentially backdrivable. Bearings, seals, loads and dynamics are not evaluated; this is not a brake or a real-world holding/startup guarantee.', 'text', 'Static tooth-contact model'),
    'module': H('Normal module · mm', 'Size of the teeth, measured in the normal section across the tooth trace.', 'Increase module to make the teeth and gear larger at the same tooth count. Pitch diameter d = mn × z / cos β, where z is tooth count and β is helix angle. For straight teeth, d = mn × z.', 'pitch', 'mn = tooth size'),
    'teeth': H('Tooth count', 'How many teeth are spaced around the gear.', 'Add teeth to enlarge the gear while keeping each tooth the same size. A single gear has no transmission ratio until paired with another member.', 'pitch', 'z = teeth around circle'),
    'width': H('Face width · mm', 'Axial distance between the two gear faces.', 'Increase width to make the gear thicker along its shaft. The pitch diameter stays the same. For double helices, total width includes both halves and the central groove.', 'section', 'b = axial width'),
    'bore': H('Bore diameter · mm', 'Diameter of the central through hole.', 'Increase this diameter to make the central hole larger. This leaves less material below the teeth. A bearing catalog can link this value to its seat or shaft.', 'bore', 'Ø bore'),
    'pressure': H('Normal pressure angle · °', 'Angle between the tooth common normal and the pitch-circle tangent, in the normal section.', 'Changes base-circle size and flank shape. Mating teeth must use compatible pressure angles; it does not change tooth count.', 'pressure', 'α = pressure angle'),
    'backlash': H('Tangential backlash · mm', 'Pair tooth-thickness allowance measured tangentially at the reference circles.', 'Increase backlash to leave more space between the mating tooth flanks. It is tangential play, not radial clearance. For helical gears the normal allowance is converted to the transverse plane.', 'pitch', 'j = tangential tooth space'),
    'helix': H('Helix angle · °', 'Inclination of the tooth trace to the shaft axis at the reference cylinder.', 'Its sign selects hand; zero gives straight teeth. At fixed normal module, a larger magnitude increases transverse pitch diameter. Double helices use opposing hands.', 'helix', 'β to shaft axis'),
    'gap': H('Central groove · mm', 'Axial space separating the two opposing helix halves.', 'Each active half has width (total width − groove) / 2. Joined helices have zero groove; the groove must fit inside the total width.', 'section', 'g = central gap'),
    'profile_shift': H('Profile shift coefficient x', 'Dimensionless rack displacement relative to the reference pitch position.', 'The radial shift is x × normal module. It changes tooth thickness and root/tip geometry without changing reference pitch diameter.', 'pitch', 'x mn = rack shift'),
    'addendum': H('Addendum coefficient ha*', 'Dimensionless height of the tooth above the reference pitch circle before profile shift.', 'The nominal addendum contribution is ha* × normal module. Increasing it extends tooth tips; root and contact checks still apply.', 'pitch', 'ha* mn = tip height'),
    'dedendum': H('Dedendum coefficient hf*', 'Dimensionless depth below the reference pitch circle before profile shift.', 'The nominal dedendum contribution is hf* × normal module. Increasing it moves the root inward and changes the available root material.', 'pitch', 'hf* mn = root depth'),
    'sun': H('Sun teeth', 'Tooth count of the central gear in stage 1.', 'Together with the planet teeth, sets ring teeth zr = zs + 2 zp. The chosen input, output and fixed members determine the signed speed ratio.', 'planetary', 'zs = sun teeth'),
    'planet': H('Planet teeth', 'Tooth count of each orbiting gear in stage 1.', 'With the sun, determines the derived ring tooth count and planet-centre radius. Equal-spacing and neighbouring-planet checks must also pass.', 'planetary', 'zp = planet teeth'),
    'planets': H('Planet count', 'Number of equally spaced planet gears in the stage.', 'Changes how many planets are placed around the sun. It does not alone change the ideal ratio or establish equal load sharing.', 'planetary', 'N = number of planets'),
    'sun2': H('Sun teeth · stage 2', 'Tooth count of the central gear in the second stage.', 'Stage 1 output drives stage 2 input. With the second-stage planet tooth count it determines the second ring teeth; the two selected stage arrangements determine the total ratio.', 'planetary', 'zs2 = stage 2 sun'),
    'planet2': H('Planet teeth · stage 2', 'Tooth count of each second-stage planet.', 'The second ring has zs2 + 2 zp2 teeth. Stage 2 must independently satisfy coaxiality, spacing and contact checks.', 'planetary', 'zp2 = stage 2 planet'),
    'output_ring': H('Output ring teeth', 'Tooth count Ro of the moving second ring in a two-rim Wolfrom.', 'Together with P2 sets the derived second module. Ro must exceed P2; the exact determinant P1 Ro − Rf P2 must be nonzero, and identical compounds must satisfy all mesh phases.', 'wolfrom', 'Ro = output ring teeth'),
    'layer_gap': H('Gap between toothed layers · mm', 'Positive axial gap from the first layer end face to the second layer start face.', 'Separates the two toothed layers of each rigid compound. A bored hub joins them; this is not spacing between independent planetary stages.', 'wolfrom', 'g = gap between tooth layers'),
    'width2': H('Face width · stage 2 · mm', 'Axial tooth width of the second planetary stage.', 'Independent of the first-stage width. For double helices it includes both active halves and the central groove.', 'section', 'b2 = stage 2 width'),
    'rim': H('Ring radial thickness · mm', 'Radial material outside the internal gear tooth roots.', 'Enlarges the outside of the ring without changing the reference tooth count or pitch diameter.', 'bore', 't = ring wall'),
    'plate': H('Flange / carrier thickness · mm', 'Axial thickness of the assembly flange or carrier plate.', 'Changes the support stack length. Catalog bearings and assembly hardware may impose linked minimum dimensions.', 'section', 't = plate thickness'),
    'assembly_clearance': H('Axial assembly clearance · mm', 'Axial separation used between adjacent moving assembly members and their covers.', 'Changes assembly spacing, not tooth backlash. Cycloidal output-hole clearance and profile clearance have separate controls.', 'section', 'c = axial gap'),
    'housing_wall': H('Housing thickness · mm', 'Radial wall of the enclosing housing.', 'Enlarges the housing outside the mechanism. Enable Housing in the preview to see the enclosure; this value does not set a load rating.', 'bore', 't = housing wall'),
    'shaft_extension': H('Shaft extension · mm', 'Axial length by which the shaft extends beyond its assembly.', 'Provides external connection length and changes the total axial envelope; it does not change the ideal ratio.', 'section', 'L = shaft extension'),
    'stage_gap': H('Additional stage spacing · mm', 'Extra axial distance between the two planetary stages.', 'Moves stage 2 farther from stage 1 in addition to the normal stack dimensions. Tooth counts and stage speed ratios stay the same.', 'section', 'g = extra stage gap'),
    'pins': H('Ring roller count', 'Number N of fixed-pitch rollers around the cycloidal ring.', 'The generated disc has N − 1 lobes. With eccentric input, fixed ring and pin-flange output, the signed ratio is −(N − 1). Other connections give other ratios.', 'eccentric', 'N rollers; N − 1 lobes'),
    'radius': H('Roller pitch radius · mm', 'Distance from the housing axis to each ring roller centre.', 'Sets the ring roller circle, not the roller surface radius. Increasing it enlarges the disc and housing arrangement.', 'eccentric', 'R = roller-centre radius'),
    'pin_radius': H('Ring roller radius · mm', 'Radius of each roller contacting the outer cycloidal profile.', 'The disc profile is the inward normal offset of the roller-centre trajectory. Changing roller radius changes the generated contact profile.', 'eccentric', 'r = ring roller radius'),
    'eccentric': H('Eccentricity · mm', 'Offset e between the main shaft axis and the disc / eccentric-bearing centre.', 'Increase eccentricity to make the disc centre travel in a larger orbit. The output holes must also grow: hole radius = output pin radius + eccentricity + output clearance.', 'eccentric', 'e = axis offset'),
    'output_count': H('Output pin count', 'Number of pins transferring disc motion to the output flange.', 'Pins and matching disc holes are distributed around the output pitch circle. Count does not change the cycloidal ideal ratio.', 'eccentric', 'K = output pins'),
    'output_radius': H('Output pin pitch radius · mm', 'Distance from the output flange axis to each output pin centre.', 'Moves the output pins and their matching disc holes radially. Pins must fit between the eccentric seat and the outer disc profile.', 'eccentric', 'Ro = output-pin circle'),
    'output_pin': H('Output pin radius · mm', 'Radius of each pin connected to the output flange.', 'Disc holes accommodate this radius plus eccentricity and output clearance; a larger pin therefore needs a larger disc hole.', 'eccentric', 'ro = output pin radius'),
    'clearance': H('Cycloidal profile clearance · mm', 'Radial relief of the generated disc relative to its ring rollers.', 'Changes the outer contact profile. It is separate from output pin-hole clearance and axial assembly spacing.', 'eccentric', 'c = profile relief'),
    'output_clearance': H('Output pin radial clearance · mm', 'Additional radial space around an output pin after allowing for the disc orbit.', 'Hole radius = output pin radius + eccentricity + this clearance. This is a radial value, not a diametral allowance.', 'eccentric', 'rh = ro + e + c'),
    'profile_tolerance': H('Profile sampling tolerance · mm', 'Chord-deviation target used when sampling the cycloidal contour.', 'A smaller value requests finer sampling and can increase mesh size. This numerical target is not a manufacturing tolerance or a proven global error bound.', 'eccentric', 'δ = chord deviation'),
    'disc_gap': H('Disc spacing · mm', 'Axial free space between the two opposing cycloidal discs.', 'Adds to the two individual disc thicknesses. It is independent of radial profile and output-hole clearances.', 'section', 'g = between discs'),
    'input_shaft': H('Input shaft diameter · mm', 'Diameter of the shaft connected to the selected driving interface.', 'Changes the shaft and available surrounding wall. A bearing catalog or the printed eccentric construction can impose compatibility constraints.', 'bore', 'Ø input shaft'),
    'output_shaft': H('Output shaft diameter · mm', 'Diameter of the shaft on the output connection.', 'Changes the output interface and its surrounding clearance. An active bearing catalog can link this field to the catalog bore.', 'bore', 'Ø output shaft'),
    'wall': H('Flexible wall thickness · mm', 'Radial thickness of the strain-wave flexible gear body below its teeth.', 'Changes the inside of the deforming shell. The prescribed deformation is geometric; wall thickness does not calculate stiffness or fatigue life.', 'wave', 't = flexible wall'),
    'wave_factor': H('Wave amplitude factor', 'Dimensionless multiplier of the prescribed two-lobe deformation amplitude.', 'Amplitude A = module × factor. The major semiaxis is the reference pitch radius + A; the minor semiaxis is solved to preserve the reference perimeter. Changing it also changes the matching generated rigid ring.', 'wave', 'A = m × factor'),
    'cup_length': H('Flexible body length · mm', 'Axial length of the flexible cup or hat body.', 'Separates the tooth band from the diaphragm / flange. The body deformation blends along this length; no elastic strain solution is calculated.', 'section', 'L = flexible body'),
    'diaphragm': H('Diaphragm / flange thickness · mm', 'Axial thickness of the flexible member’s end diaphragm or external flange.', 'Changes the output end and stack length. Cup and flat-cup use an end diaphragm; the hat variant uses an external flange.', 'section', 't = end plate'),
    'bearing_thickness': H('Wave bearing radial thickness · mm', 'Radial thickness assigned to the wave-generator bearing representation.', 'Changes the nested generator/bearing geometry inside the flexspline. It is a dimensional model, not a selected bearing load capacity.', 'wave', 't = wave bearing'),
    'wave_clearance': H('Generator radial clearance · mm', 'Radial separation in the generator and wave-bearing fit.', 'Changes the internal generator fit; it is separate from tooth-thickness backlash and the ring-envelope numerical relief.', 'wave', 'c = generator gap'),
    'output_bore': H('Output bore diameter · mm', 'Diameter of the through hole in the driven wheel / output member.', 'Changes the output connection without changing the gear pitch diameter. Check the remaining material to the tooth roots.', 'bore', 'Ø output bore'),
    'flange_width': H('Flange radial width · mm', 'Radial projection of the strain-wave hat flange beyond the flexible body.', 'Enlarges the external flange while preserving the tooth count and prescribed wave amplitude.', 'bore', 'w = radial flange'),
    'starts': H('Worm starts', 'Number s of independent helical threads on the worm.', 'Lead per revolution L = π mx s. For worm input, the magnitude of the ideal ratio is wheel teeth / starts; more starts also increase lead angle.', 'worm', 's starts; L = π mx s'),
    'diameter': H('Worm pitch diameter · mm', 'Diameter of the reference cylinder of the worm.', 'With axial module and starts, sets lead angle γ = atan(mx s / d). Centre distance uses this diameter and the wheel pitch diameter.', 'worm', 'd = worm pitch diameter'),
    'length': H('Worm length · mm', 'Axial length of the threaded worm body.', 'Changes the screw envelope along its shaft. End journals, when enabled, extend beyond this threaded length.', 'worm', 'Lbody = threaded length'),
    'worm_hand': H('Worm hand · −1 / +1', 'Select −1 for a left-hand screw or +1 for a right-hand screw.', 'Reverses the thread hand and the signed wheel speed for the same worm input. It does not establish backdrivability or self-locking.', 'worm', 'h = screw hand'),
    'wheel_bore': H('Wheel bore diameter · mm', 'Central hole in the worm wheel, independent of the worm bore.', 'Changes the wheel shaft connection. The worm shaft runs on a perpendicular axis.', 'bore', 'Ø wheel bore'),
    'journal_length': H('Length of each journal · mm', 'Axial length of each cylindrical worm end journal.', 'Zero omits the journals. A positive value extends both ends beyond the threaded worm body.', 'section', 'Lj = each journal'),
    'journal_diameter': H('Journal diameter · mm', 'Diameter of the cylindrical worm end journals.', 'Must fit between the worm bore and root diameter. This control changes the end connections, not the reference pitch cylinder.', 'bore', 'Ø end journal'),
    'pinion': H('Pinion teeth', 'Tooth count of the smaller / input-named gear.', 'Together with wheel teeth sets pitch diameters and the ideal ratio. Reversing input/output roles changes the driving member, not these saved names.', 'pitch', 'z1 = pinion teeth'),
    'wheel': H('Wheel teeth', 'Tooth count of the driven-named wheel.', 'For external pairs the gears turn oppositely; for fixed-axis internal pairs they turn in the same direction. Input/output reversal is chosen separately.', 'pitch', 'z2 = wheel teeth'),
    'center_extra': H('Centre distance increase · mm', 'Extra axis separation above the external pair’s reference centre distance.', 'Increases working pressure angle and working tangential backlash. Changes contact conditions; it does not resize the reference pitch circles.', 'pitch', 'a = a0 + Δa'),
    'side_teeth': H('Side gear teeth', 'Tooth count of each of the two equal opposing side bevel gears.', 'Together with the transverse bevel tooth count sets pitch-cone angles. Both side gears retain equal counts.', 'bevel', 'zs = each side gear'),
    'output_teeth': H('Transverse bevel teeth', 'Tooth count of the bevel member on the transverse axis.', 'In wrist mode this is the output bevel; in classic mode it is the spider bevel. Preset tooth ratios link this field to the side gear count.', 'bevel', 'zt = transverse bevel'),
    'flange_radius': H('Output flange radius · mm', 'Outside radius of the wrist output’s drilled flange.', 'Enlarges the flange around its mounting pattern. This field is active only with the drilled flange output connection.', 'bore', 'R = output flange'),
    'bolt_count': H('Flange mounting hole count', 'Number of equally spaced holes in the drilled output flange.', 'Changes the mounting pattern count. The holes are nominal geometry; an external mating part must be designed separately.', 'bore', 'N = flange holes'),
    'bolt_diameter': H('Flange mounting hole diameter · mm', 'Diameter of each hole in the drilled output flange.', 'Enlarges the mounting holes and reduces the remaining ligament to the flange edge and shaft.', 'bore', 'Ø mounting hole'),
    'output_extension': H('Output shaft extension · mm', 'Axial extension of the wrist solid or hollow output shaft.', 'Sets the external shaft connection length. The flange output has its own geometry instead of this extension.', 'section', 'L = output extension'),
    'passage_diameter': H('Output passage diameter · mm', 'Diameter of the internal passage through the hollow output.', 'Must fit within the outside output shaft. Active with the hollow output connection.', 'bore', 'Ø hollow passage'),
    'carrier_bolt_diameter': H('Carrier joining hole diameter · mm', 'Diameter of holes joining or mounting the differential carrier.', 'Changes the split-carrier / classic-carrier connection holes. It is distinct from the wrist output flange hole diameter.', 'bore', 'Ø carrier hole'),
    'spiral_angle': H('Unsigned spiral angle · °', 'Magnitude of tooth-trace inclination on the bevel pitch cone.', 'Hand is selected separately. Zero produces a straight trace; increasing the angle curves the trace across the cone face.', 'bevel', 'β = cone spiral angle'),
    'spiral_hand': H('Local side spiral hand · −1 / +1', 'Hand of the side-gear spiral in its own local shaft frame.', 'The opposing side frames face opposite directions. The mating transverse hand is derived; this sign is not a global spin direction.', 'bevel', 'h = local spiral hand'),
    'spider_pin_diameter': H('Spider pin diameter · mm', 'Diameter of the cross pin carrying the classic differential’s spider bevels.', 'Changes the pin and the matching spider support geometry. It is independent of the side output shaft diameter.', 'bore', 'Ø spider pin'),
    'spider_clearance': H('Spider pin radial clearance · mm', 'Radial running space between the spider pin and its bore.', 'A radial clearance c adds 2c to the bore diameter relative to the pin. It is separate from bevel tooth backlash.', 'bore', 'Ø bore = Ø pin + 2c'),
    'output_difference_rpm': H('Prescribed side-speed difference · rpm', 'Signed difference Δ = speed B − speed A in a classic differential.', 'With carrier speed C, A = C − Δ/2 and B = C + Δ/2, using world +X signs. This is a prescribed speed boundary, not a prediction from loads.', 'motion', 'Δ = B − A'),
    'input_b_rpm': H('Input B speed · rpm', 'Second independent wrist input, signed about world +X.', 'A and B use the same world axis despite opposite-facing shafts. Their average drives carrier tilt; their difference drives relative output spin.', 'motion', 'A, B use world +X'),
    'input_rpm': H('Input speed · rpm', 'Revolutions per minute of the selected driving member.', 'Sets the physical input used for ideal member speeds and nominal operating calculations. The chosen drive connection determines which member receives it.', 'motion', 'n = revolutions / minute'),
    'input_torque': H('Input torque · N·m', 'Nominal torque applied to the selected driving member.', 'Used with input speed, ideal ratio and assumed efficiency to calculate nominal power, torque and mesh forces. It is not an allowable load.', 'motion', 'T = input torque'),
    'efficiency': H('Assumed overall efficiency · %', 'User-entered fraction of input power assumed to reach the output.', 'Scales nominal output torque and power; it does not alter geometry or ideal speed ratio. For two stages this is the overall value.', 'motion', 'Pout = η Pin'),
    'shoulder': H('Minimum axial margin · mm', 'Extra axial margin around catalog bearing seats.', 'Catalog preparation can increase linked face or plate widths to leave this margin. It is a geometric minimum, not a bearing preload.', 'section', 's = axial margin'),
    'seat_allowance': H('Seat diameter allowance · mm', 'Signed amount added to the catalog bearing outside diameter D.', 'Seat diameter = D + allowance. Positive enlarges the housing seat; negative reduces it. Available only with custom seat dimensions.', 'bore', 'Ø seat = D + allowance'),
    'shaft_allowance': H('Shaft diameter allowance · mm', 'Signed amount added to the catalog bearing bore d.', 'Shaft diameter = d + allowance. Positive enlarges the shaft; negative reduces it. This is a diametral amount.', 'bore', 'Ø shaft = d + allowance'),
    'print_bolt_pitch': H('Through bolt spacing · mm', 'Centre-to-centre distance between the two axial M3 reinforcement bolt holes.', 'Changes the asymmetric two-hole pattern through the printed eccentric pieces. Both holes and head pockets must leave the required wall.', 'bore', 'p = two bolt centres'),
    'print_hole_clearance': H('Bolt hole diametral clearance · mm', 'Amount added to the nominal M3 bolt diameter and associated pocket dimensions.', 'Bolt hole diameter = 3 mm + this value. This is a diameter increase, not a radial gap or an as-printed fit guarantee.', 'bore', 'Ø hole = 3 mm + c'),
    'print_seat_allowance': H('6804 seat diametral allowance · mm', 'Amount added to the 6804 bearing’s 32 mm outside diameter.', 'Links the disc eccentric seat to 32 mm + allowance. Changing this option controls the linked seat instead of editing its diameter directly.', 'bore', 'Ø seat = 32 mm + c'),
    'print_journal_allowance': H('6804 journal diametral clearance · mm', 'Amount subtracted from the 6804 bearing’s 20 mm bore diameter.', 'Printed eccentric journal diameter = 20 mm − clearance. Positive values make the journal smaller; calibrate on the actual print.', 'bore', 'Ø journal = 20 mm − c'),
    'print_min_wall': H('Minimum printed wall · mm', 'Geometric wall criterion around holes and pockets in the printed eccentric pieces.', 'Rejects layouts leaving less material than this criterion. It does not predict strength, print quality or service life.', 'bore', 'tmin = remaining wall'),
}

OPTIONS = {
    'variant': H('Construction variant', 'Selects the current family’s geometric construction.', 'Available variants change the applicable controls. Dimensions remain subject to the selected construction’s checks.', 'section'),
    'double_style': H('Double helix construction', 'Joined uses two opposing helices meeting at the centre; separated adds a central groove.', 'The total width contains both halves and any groove. Each active half has width (width − gap) / 2.', 'helix', 'opposing hands'),
    'configuration': H('Differential configuration', 'Wrist uses two independent side inputs; classic uses a carrier input and two side outputs.', 'Classic exposes a prescribed side-speed difference and spider support dimensions. The configuration changes which shafts are inputs and outputs.', 'bevel'),
    'ratio_mode': H('Side / transverse tooth ratio', 'Custom permits independent tooth counts; presets link the transverse bevel count to the side count.', 'The 1:1 preset uses equal counts. The 2:1 spin preset uses twice as many transverse teeth; it refers to relative spin, not a universal differential ratio.', 'bevel'),
    'output_interface': H('Output connection', 'Choose a drilled flange, solid output shaft or hollow output shaft for the differential.', 'Shows the matching flange or shaft dimensions. It changes the mechanical interface, not the bevel speed equations.', 'bore'),
    'carrier_style': H('Carrier construction', 'Open carrier or a split carrier with bearing-seat halves.', 'Changes carrier support geometry and exposes joining-hole dimensions where applicable. It does not select a bearing load capacity.', 'section'),
    'eccentric_design': H('Eccentric shaft construction', 'Standard shaft or the printed eccentric stack reinforced by two axial M3 through bolts.', 'The printed stack uses dedicated 6804 seats and manual catalog modes. Its compatible-dimensions preset is an explicit action; entering the mode does not silently replace shaft/disc dimensions.', 'eccentric'),
    'bearing_mode': H('Standard fit', 'Free dimensions leave catalog links off. Bearing in bore seats a bearing inside the member; shaft support places bearings on a shaft.', 'Catalog modes derive linked diameters and can enlarge axial dimensions. Supported modes depend on the family and drive connection.', 'bore'),
    'bearing': H('NSK bearing designation', 'Selects the local open-bearing catalog entry, labelled d × D × B in mm.', 'd is bore diameter, D outside diameter and B axial width. Linked seat/shaft dimensions use these values plus the chosen allowances.', 'bore', 'd × D × B'),
    'fit': H('Seat dimensions', 'Nominal uses catalog diameters; custom exposes signed seat and shaft diameter allowances.', 'These values define geometry only. They are not an ISO fit-class selection or a guaranteed manufactured interference.', 'bore'),
    'hardware_mode': H('Hardware and assembly', 'Choose whether supported standard hardware and matching geometric features are added.', 'Standard mode exposes retainers, keys, fasteners and shims. Unsupported connections remain described in the BOM rather than invented.', 'section'),
    'hardware_screw': H('Flange fasteners', 'Nominal metric size used for supported flange screw/nut patterns.', 'Controls available standard screws and matching holes. Some fixed-axis pairs have no supported automatic flange-bolt arrangement.', 'bore'),
    'hardware_shim': H('DIN 988 shim thickness · mm', 'Axial thickness of the selected catalog shim.', 'Changes the supported shim/spacer stack. Shaft compatibility determines available diameters.', 'section', 't = shim thickness'),
    'hardware_retaining': H('Retaining rings and grooves', 'Adds supported catalog retaining rings and their matching grooves.', 'Geometry is selected from the supported shaft/seat dimensions; unavailable retainers are reported in the BOM.', 'section'),
    'hardware_keys': H('Compatible keys and keyways', 'Adds supported parallel keys and matching shaft/hub keyways.', 'Requires a compatible nominal diameter and enough axial and radial material. External mating hubs may remain outside the generated assembly.', 'section'),
    'hardware_bolts': H('Flange screws, nuts and holes', 'Adds the supported flange fastening pattern and standard hardware.', 'Availability depends on the assembly. The fixed-axis parallel and internal pairs do not provide this automatic bolt pattern.', 'bore'),
    'hardware_shims': H('Shims and spacers', 'Adds supported catalog shims and geometric spacers around shaft supports.', 'Changes the axial support stack without changing tooth count or ideal transmission ratio.', 'section'),
    'io_scheme': H('Drive connections', 'Select the driven member and output member; the remaining third member is fixed to the frame.', 'Changing roles changes speeds, signs and interfaces. A two-member pair can reverse input/output; worm reversal does not prove backdrivability.', 'motion'),
    'io_scheme2': H('Drive connections · stage 2', 'Select stage 2 input and output, with the third member fixed.', 'Stage 1 output drives stage 2 input. The total signed ratio combines both selected stage arrangements.', 'motion'),
}

# Only exact labels emitted by app.choice are used by the late binding pass.
OPTION_LABELS = {
    'Differential configuration': 'configuration', 'Side / transverse tooth ratio': 'ratio_mode',
    'Output connection': 'output_interface', 'Carrier construction': 'carrier_style',
    'Local side spiral hand': 'spiral_hand', 'Eccentric shaft construction': 'eccentric_design',
    'Double helix construction': 'double_style', 'Standard fit': 'bearing_mode',
    'NSK bearing · d × D × B': 'bearing', 'Seat dimensions': 'fit',
    'Hardware and assembly': 'hardware_mode', 'Flange fasteners': 'hardware_screw',
    'DIN 988 shim thickness': 'hardware_shim',
}
CHECK_LABELS = {OPTIONS[k].title: k for k in (
    'hardware_retaining', 'hardware_keys', 'hardware_bolts', 'hardware_shims')}


def lookup(family, key, values=None):
    """Resolve a known control without silently inventing a generic fallback."""
    values = values or {}
    result = COMMON[key] if key in COMMON else OPTIONS[key]
    if family == 'wolfrom':
        changes = {
            'module': H('First layer module · mm', 'Transverse module m1 shared by the sun, first planet rims and fixed first ring.', 'Only m1 is editable. The second module is derived as m2 = m1 (S + P1) / (Ro − P2), so both layers share the same planet centre distance.', 'wolfrom', 'a = m1 (S + P1) / 2'),
            'sun': H('Sun teeth · input', 'Tooth count S of the central input sun in the first layer.', 'The fixed first ring has Rf = S + 2 P1 teeth. Both layers and all identical compound phases must be compatible.', 'wolfrom', 'S = input sun teeth'),
            'planet': H('First planet teeth', 'Tooth count P1 of the first rim of each rigid compound planet.', 'Meshes with the input sun and fixed first ring at m1. The second rim has its own tooth count and derived module; both rims have the same absolute spin.', 'wolfrom', 'P1 = first compound rim'),
            'planet2': H('Second planet teeth', 'Tooth count P2 of the second rim of each rigid compound planet.', 'Meshes with output ring Ro at derived m2. Both rims share one rigid clocking on every compound; they are not two stages in cascade.', 'wolfrom', 'P2 = second compound rim'),
            'planets': H('Compound planet count', 'Number of equally spaced, identically clocked rigid compounds on the common free carrier.', 'Exact integer assembly conditions enforce all three mesh phases. Adjacent addendum circles must clear in both layers.', 'wolfrom', 'n = identical compounds'),
            'width': H('First layer face width · mm', 'Axial tooth width of the sun, first planet rims and fixed first ring.', 'The second toothed layer starts at this width plus the positive layer gap. Both layers belong to one compound train.', 'wolfrom', 'b1 = first layer width'),
            'width2': H('Second layer face width · mm', 'Axial tooth width of the second compound rims and output ring.', 'Independent of first layer width. This is the second rim of the same compound, with ring output and a free common carrier.', 'wolfrom', 'b2 = second layer width'),
            'bore': H('Sun and compound bore diameter · mm', 'Nominal bore through the sun and each rigid compound.', 'Sun shaft nominally touches its bore. Carrier pins use radial assembly clearance inside compound bores; fits, bearings and torque transfer require external design.', 'bore', 'Ø sun / compound bore'),
            'assembly_clearance': H('Assembly clearance · mm', 'Radial clearance of carrier pins in compound bores and axial clearance to carrier plates.', 'Pin radius is half the bore diameter minus this clearance. Carrier plates remain outside both toothed layers.', 'wolfrom', 'c = pin / plate clearance'),
            'plate': H('Carrier plate thickness · mm', 'Axial thickness of each of the two common carrier plates.', 'The carrier is free and carries compound pins; it is not the output. No enclosing housing is generated.', 'wolfrom', 't = each carrier plate'),
            'rim': H('Ring thickness beyond root · mm', 'Radial material beyond each internal ring tooth root.', 'Enlarges each ring outside diameter. The first ring is fixed; the exposed second annulus is output.', 'wolfrom', 't = ring radial wall'),
            'input_rpm': H('Sun input speed · rpm', 'Signed sun input speed about world +Z, positive counterclockwise viewed from +Z toward XY.', 'The first ring stays fixed. Carrier, compound absolute spin and output ring speeds follow the three mesh equations. Reverse input reverses all moving speeds; zero input stops all members. Physical backdrivability is not established.', 'wolfrom', 'nS = signed sun input'),
            'io_scheme': H('Fixed Wolfrom drive connections', 'Sun input, first ring fixed and second ring output, with a free common carrier.', 'No role swaps are supported. Compound rims share one absolute spin and one rigid clocking. Physical backdrivability is not established.', 'wolfrom', 'S input · Rf fixed · Ro output'),
            'variant': H('Two-rim spur Wolfrom', 'Zero-shift spur teeth in two axially separate layers of the same compound train.', 'Sun input, first ring fixed, second ring output. The second module and first ring teeth are derived. No one-rim or helical variant is supported.', 'text', 'two-rim spur'),
        }
        result = changes.get(key, result)
    elif family == 'worm':
        changes = {
            'module': H('Worm axial module · mm', 'Size of the worm threads along the shaft: axial pitch divided by π.', 'Increase axial module to spread the threads farther apart and enlarge the wheel. Lead L = π × axial module × starts; wheel pitch diameter = axial module × wheel teeth. This is axial, not normal module.', 'worm', 'px = π mx'),
            'pressure': H('Worm axial pressure angle · °', 'Pressure angle in the axial section of the worm.', 'ZA has straight axial flanks; ZI has a transverse involute. The generator converts this axial angle to its normal and transverse equivalents.', 'pressure', 'αx = axial pressure angle'),
            'backlash': H('Worm pair axial backlash · mm', 'Total reference tooth-thickness allowance along the worm axis.', 'The worm is thinned by half and the generating wheel gap widened by the other half. It is separate from radial root clearance.', 'worm', 'j = axial allowance'),
            'bore': H('Worm bore diameter · mm', 'Central through hole along the worm shaft axis.', 'Independent of the wheel bore. End journals must remain outside this bore and inside the worm root.', 'bore', 'Ø worm bore'),
            'teeth': replace(COMMON['wheel'], title='Worm wheel teeth', effect='With worm input, ideal ratio magnitude is wheel teeth / starts. Increasing teeth at fixed axial module enlarges the wheel pitch diameter.'),
            'width': replace(COMMON['width'], meaning='Axial face width of the wheel along its own shaft.', effect='The wheel shaft is perpendicular to the worm shaft. This width is independent of the worm threaded length.'),
        }
        result = changes.get(key, result)
    elif family == 'differential':
        classic = values.get('configuration') == 'classic'
        changes = {
            'module': H('Outer bevel module · mm', 'Tooth size at the outer end of the bevel pitch cone.', 'Outer pitch diameter = module × tooth count. Tooth sections shrink toward the cone apex; this is not a cylindrical normal module.', 'bevel', 'do = mo z'),
            'pressure': H('Transverse pressure angle · °', 'Bevel tooth pressure angle in the transverse reference section.', 'Sets the spherical involute flank. It is independent of the unsigned spiral trace angle.', 'pressure', 'αt = transverse angle'),
            'width': H('Pitch-cone face width · mm', 'Distance along a generator of the pitch cone from its outer end toward the apex.', 'A longer face extends the teeth inward along the cone, where sections get smaller. This is not the axial projection along the shaft.', 'bevel', 'b = along cone generator'),
            'backlash': H('Outer tangential backlash · mm', 'Tooth-thickness allowance at the outer bevel reference circle.', 'The generated inner sections scale with cone distance. This outer allowance is not a radial spider-pin clearance.', 'bevel', 'jo = outer allowance'),
            'input_rpm': H('Carrier input speed · rpm' if classic else 'Input A speed · rpm', 'Signed speed of the carrier about world +X.' if classic else 'First independent wrist side input, signed about world +X.', 'Classic side speeds are C ± (B−A)/2; their difference is prescribed independently.' if classic else 'Both side inputs share world +X signs despite opposing shaft frames. Equal speeds tilt the carrier; opposite speeds drive relative output spin.', 'motion', 'C = carrier speed' if classic else 'A = side input'),
            'input_shaft': replace(COMMON['input_shaft'], title='Side output shaft diameter · mm' if classic else 'Input shaft diameter · mm', meaning='Diameter of each opposing side output shaft.' if classic else 'Diameter of each opposing side input shaft.'),
            'shaft_extension': replace(COMMON['shaft_extension'], meaning='Axial extension of the opposing side output shafts.' if classic else 'Axial extension of the opposing side input shafts.'),
        }
        result = changes.get(key, result)
    elif family == 'cycloidal':
        if key == 'bore':
            result = H('Eccentric seat diameter · mm', 'Diameter of the eccentric bearing / drive seat in each cycloidal disc.', 'This opening is centred on the orbiting disc, not the main housing axis. The printed construction links it to 32 mm + the 6804 seat allowance.', 'eccentric', 'Ø eccentric seat')
        elif key == 'width':
            result = replace(COMMON[key], title='Disc thickness · mm', meaning='Axial thickness of each individual cycloidal disc.', effect='Dual-disc assemblies use two discs of this thickness plus their separate axial gap. The printed eccentric stack imposes its own fit constraints.')
        elif key == 'input_shaft':
            result = replace(COMMON[key], meaning='Diameter of the physical eccentric shaft on the main axis.', effect='The saved input-shaft name identifies this physical shaft even when another member drives the reducer. Its wall and eccentric seat must remain compatible.')
    elif family == 'harmonic':
        if key == 'teeth':
            result = H('Flexspline teeth', 'Number zf of teeth on the flexible member.', 'The rigid ring has zf + 2 teeth. With wave input and fixed ring the ideal ratio is −zf/2; other member roles change the ratio.', 'wave', 'zc = zf + 2')
        elif key == 'bore':
            result = replace(COMMON[key], title='Wave-generator bore · mm', meaning='Central input opening in the wave generator.', effect='Independent of the cup / flat-cup output diaphragm bore. Must fit inside the nested generator geometry.')
        elif key == 'output_bore':
            result = replace(COMMON[key], title='Output diaphragm bore · mm', meaning='Central through hole in the cup or flat-cup output diaphragm.', effect='Changes the flexible output connection, independently of the wave-generator input bore.')
        elif key == 'backlash':
            result = replace(COMMON[key], meaning='Reference tooth-thickness allowance between flexible teeth and the generated rigid ring.', effect='Separate from the ring-envelope numerical relief and generator clearance. It is not a prediction of loaded rotational lost motion.')
        elif key == 'width':
            result = replace(COMMON[key], meaning='Axial width of the flexible tooth band and its matching rigid ring.', effect='Changes the tooth band, independently of the flexible body length and diaphragm thickness.')
    if family == 'differential' and values.get('configuration') == 'classic' and key in ('flange_radius', 'bolt_count', 'bolt_diameter', 'passage_diameter'):
        meanings = {
            'flange_radius': 'Outside radius of each drilled side-output flange.',
            'bolt_count': 'Number of mounting holes on each drilled side-output flange.',
            'bolt_diameter': 'Diameter of each mounting hole on the two side-output flanges.',
            'passage_diameter': 'Internal passage diameter through each hollow side-output shaft.',
        }
        result = replace(result, meaning=meanings[key], effect='Applies to both opposing side outputs. The output-connection option selects drilled flange, solid shaft or hollow shaft geometry.')
    if key == 'io_scheme':
        members = {'planetary': 'sun, carrier and ring', 'cycloidal': 'eccentric shaft, pin flange and ring / housing', 'harmonic': 'wave generator, flexible gear and rigid ring'}
        if family in members:
            result = replace(result, meaning='Assign input and output among the '+members[family]+'. The remaining member is fixed to the frame.')
        elif family in ('worm', 'parallel', 'internal'):
            result = replace(result, meaning='Choose which of the two meshing members is the input and which is the output.', effect='Reversing the roles changes the speed ratio and driving interface. There is no third fixed member; worm reversal does not establish backdrivability.')
    if family == 'parallel' and key == 'profile_shift':
        result = replace(result, effect='Applies x to the pinion and −x to the wheel. This balanced pair keeps the reference centre distance; a separate control adds working centre distance.')
    if key in ('teeth', 'pinion', 'wheel', 'module') and result.diagram == 'pitch':
        result = replace(result, diagram='gear')
    if family == 'differential' and key in ('input_rpm', 'input_b_rpm', 'output_difference_rpm'):
        result = replace(result, diagram='differential_motion')
    if key == 'variant':
        descriptions = {
            'double': 'Joined helices meet at the centre; separated helices leave an axial groove.',
            'planetary': 'Choose spur, helical or opposing double helices, with one stage or two stages in cascade. Each stage has a sun, planets and a ring.',
            'cycloidal': 'Single uses one orbiting disc; dual uses two equal discs on opposing eccentric phases with a separate axial spacing.',
            'harmonic': 'Cup and flat cup have an end diaphragm; hat has an external flange. Body length and the generated flexible/ring geometry remain explicit controls.',
            'worm': 'ZA uses straight axial screw flanks. ZI uses a transverse involute screw profile. The wheel is generated from the matching selected screw.',
            'parallel': 'Spur teeth are straight, helical teeth have one hand, and double helices use opposing hands with a selectable join/groove.',
            'internal': 'Spur, helical or double-helical pinion inside a ring with fixed parallel axes. The ring tooth count must exceed the pinion count.',
            'differential': 'Straight bevel uses straight cone traces; spiral bevel uses a curved trace with separate angle and local hand controls.',
        }
        if family in descriptions:
            result = replace(result, meaning=descriptions[family])
    return result


def coverage_rows():
    """Explicit family/variant matrix; includes conditional catalog/print fields."""
    from geometry import FAMILIES, VARIANTS, get_specs
    from catalog import SUPPORTED
    rows = []
    for family in FAMILIES:
        for variant in VARIANTS.get(family, {None: 'Standard'}):
            keys = {s[0] for s in get_specs(family, variant)}
            options = {'variant'} if family in VARIANTS else set()
            if family in SUPPORTED:
                keys.update(('shoulder', 'seat_allowance', 'shaft_allowance'))
                options.update(('bearing_mode', 'bearing', 'fit', 'hardware_mode', 'hardware_screw', 'hardware_shim', 'hardware_retaining', 'hardware_keys', 'hardware_bolts', 'hardware_shims'))
            if family in ('planetary', 'cycloidal', 'harmonic', 'worm', 'parallel', 'internal', 'wolfrom'):
                options.add('io_scheme')
            if family == 'planetary' and variant in ('two_stage', 'two_stage_double'):
                options.add('io_scheme2')
            if variant in ('double', 'two_stage_double') and family != 'double':
                options.add('double_style')
            if family == 'cycloidal':
                options.add('eccentric_design')
            if family == 'worm':
                keys.add('worm_static_friction')
            if family == 'differential':
                options.update(('configuration', 'ratio_mode', 'output_interface', 'carrier_style'))
            all_keys = keys | options
            missing = sorted(k for k in all_keys if k not in COMMON and k not in OPTIONS)
            rows.append(dict(family=family, variant=variant or 'standard', parameters=sorted(keys), options=sorted(options), missing=missing))
    return rows
