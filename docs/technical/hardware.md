<a id="hardware-standard-e-lavorazioni-collegate"></a>

# Standard hardware and related machining

In the **Hardware and assembly** panel, choose **Assembly with standard components**. You can enable retaining rings, keys, fasteners and shims separately, select M3/M4/M5/M6 and the shim thickness. Previous configurations retain the behaviour without additional hardware.

<a id="cosa-viene-generato"></a>

## What is generated

| Category | Purchasable components | Machining / behaviour |
|---|---|---|
| External retaining rings | Springmasters EXT0060, EXT0080, EXT0100, EXT0120, for nominal 6/8/10/12 mm shafts | Groove diameter, width and end margin linked to the component data sheet |
| Internal retaining rings | American Ring DIN472-013/016/019/022/026/028/030/032 | Two grooves in each catalogue bearing seat; part widths and thicknesses are increased where necessary |
| Keys | DIN 6885-1 B designations: 2×2, 3×3, 4×4 mm sections; length selected according to available space | Localised shaft keyway; through keyway in the connected hub. Flat ends, without automatically assigning a fit class |
| Screws and nuts | ISO 4762 M3–M6, ISO 4032 nuts and ISO 7089 washers | Four through connections between external flanges/covers, with tubular spacers. Length calculated from grip, washers, nut and protrusion of at least two pitches |
| Shims | KIPP K1151, DIN 988; thicknesses 0,1 / 0,2 / 0,5 / 1 mm | Dimensions and quantities linked to the stops. The available internal diameter is selected to avoid interference with the shaft |
| Tubular spacers | Parts to manufacture, with internal SC-… code | Fill gaps between gear and bearing inner rings, keep shims clear of retaining-ring lugs, or separate the tie-rod flanges |

The data is in `hardware-catalog.json`, with sources and verification date. Springmasters, American Ring and KIPP codes identify their respective catalogue entries. The DIN/ISO references for keys and fasteners are **dimensional designations**, not manufacturer SKUs: material, strength class and finish still need to be selected. Screw lengths are a nominal series used by the generator; availability of the complete product must be checked with the selected supplier.

Internal grooves follow the dimensions in the specified American Ring metric catalogue, including its published rounded figures; they are not a universal DIN table valid for any supplier. The end margin adopted by the generator for these grooves is stated in the data and must be verified under load. Ring load capacities are not copied onto another geometry.

<a id="applicazione-ai-modelli"></a>

## Application to models

- **Individual gear, free dimensions:** added shaft, key with shaft and gear keyways, shims and external retaining rings. To add frame fasteners, choose the **shaft-supporting** bearing mode, which provides the two flanges to connect.
- **Gear with shaft-supporting bearings:** keyways and key, internal retaining rings in the bearing holders, external stops, shims and spacers in the axial stack. Fasteners connect the two bearing holders.
- **Gear with a bearing in its bore:** outer-ring retention in the hub and spacers on the shaft. The key between that hub and shaft is omitted: the bearing must allow relative rotation.
- **Planetary:** keyways and keys between shafts and sun gears, one per stage where space allows; keyway and key on the output end; internal stops in the selected supports/bearings and an output end retainer. Retention of planet pins in the flanges explicitly remains to be completed.
- **Cycloidal:** internal retention of selected bearings, keyway/key and retainer on the output end, housing fasteners. The final connection of cams, pins and flange is still reported among the open requirements.

Keys and external retaining rings start from nominal diameters of 6, 8, 10 and 12 mm. If a shaft is not covered, the program reports the missing selection in the bill of materials without inventing a code. The smallest included type-B key is 8 mm long and requires at least 9 mm of hub. The output keyway is an interface: the hub of the accessory to be connected is not invented.

Fasteners pass **outside the rotating envelope**. The generator enlarges flanges/covers and adds four spacers: the overall diameter increases and is reported in the results. Heads protrude; threaded holes or counterbores that do not exist are not claimed. Through holes use design diametral clearances: 0,4 mm for M3, 0,5 mm for M4/M5, 0,6 mm for M6. If the required screw exceeds 120 mm, the combination is rejected.

<a id="geometria-e-distinta"></a>

## Geometry and bill of materials

Grooves, keyways and holes are present in the solids, preview and CAD. Modified parts use the STEP BRep transfer shared with the preview; they are not merely bill-of-materials annotations. Stepped sections and keyways with flat ends are not blended by a smooth loft.

Rings are mounted C-shaped envelopes, without lugs; screws and nuts have their main envelopes but no physical threads or detailed drives. Do not use these envelopes to manufacture fasteners: they are components to purchase. End spacers keep large shims clear of the internal retaining-ring planes. Spacers and shims do not model bearing races: verify support on the intended ring only.

The bill of materials distinguishes **PURCHASE**, **MANUFACTURE** and **TO BE DEFINED**. The TXT contains the **Machining present in the model** section; the JSON includes the operations and is accompanied by `.machining.json`. Machining Z dimensions are local to each part. Grooves, keyways and holes also appear in the CAD component metadata `local.solidcraft.machining`; quantities are aggregated in the native bill of materials.

Complete examples: `examples/double-helical-hardware.config.json`, `examples/planetary-hardware.config.json`, `examples/cycloidal-hardware.config.json`, with bills of materials and documents in `examples/cad/`.

<a id="fonti-primarie"></a>

## Primary sources

- [Springmasters — EXT0060 and its groove](https://www.springmasters.com/shop/ext0060/), [EXT0080](https://www.springmasters.com/shop/ext0080/), [EXT0100](https://www.springmasters.com/shop/ext0100/), [EXT0120](https://www.springmasters.com/shop/ext0120/).
- [American Ring — DIN 472, metric table](https://www.americanring.com/products/ringseries.aspx?series=DIN472&units=metric).
- [Ganter — DIN 6885-1 keyways](https://www.ganternorm.com/fileadmin/user_upload/downloads/technischer%20anhang/technical_information/6885-1.pdf), [Gardette — type-B keys](https://gardette.com/en/catalog/parallel-key-b).
- [KIPP — DIN 988 shims](https://www.kippusa.com/en-us/products/METRIC/Machine-and-fixture-components/Screws-nuts-washers/Shim-washers-DIN-988/p/agid.32243).
- [N.S. Socket Screws — ISO 4762](https://stock-api.socketscrews.co.uk/files/Final%20ISO%204762%20Website.pdf), [Böllhoff — ISO 4032 nuts](https://eshop.boellhoff.de/out/media/pdf/ISO_4032_Stahl_8___en.pdf), [India Fastener Parts — ISO 7089 washers](https://www.indiafastenersparts.com/documents/India_Specs/Metric_Flatwasher_ISO7089.pdf).

Data verification: 23 October 2026. Loads, materials, tolerances, tightening and connections declared open remain to be sized. The harmonic and worm-wheel study models do not receive this automatic assembly.
