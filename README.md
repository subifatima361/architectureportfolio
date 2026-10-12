# Urban Canopy Bench — Burns Garden, Karachi

A Bauhaus-inspired urban bench with a barrel canopy, designed for Burns Garden, Karachi.
Each side is **one continuous bent tube** that forms the foot, armrest, canopy post and canopy arm,
in the spirit of Breuer and Stam's tubular-steel furniture. Slab-like **terrazzo-effect recycled-plastic**
panels make the seat, back and canopy.

## Deliverables

| Folder | Contents |
| --- | --- |
| `output/drawings/` | A3 @ 300 dpi technical sheets, dimensioned in inches: front elevation, side elevation, plan, isometric (30°), axonometric (45° plan oblique), exploded axonometric with joinery details |
| `output/renders/` | Cycles renders: urban Karachi footpath, Burns Garden at peak sun, detail views |
| `output/model/` | `urban_canopy_bench.blend` (editable), `.obj` + `.mtl`, `.fbx` for SketchUp/Rhino import |

### Image list

**Drawings** (`output/drawings/`): `01_front_elevation`, `02_side_elevation`, `03_plan` (cut at 45"),
`04_isometric` (30°), `05_axonometric` (45° plan oblique), `06_exploded_axonometric` (15 numbered parts + details A/B/C).

**Renders** (`output/renders/`, 2100 × 1400):
`urban` and `urban_side` (concrete footpath, Karachi street with shops, neem trees, painted kerb),
`park_noon` and `park_wide` (Burns Garden at peak sun), `det_rear` (back rail and fixings),
`det_arm` (armrest bend and stringer cleats), `det_canopy` (canopy underside, rib and post),
`det_foot` (foot plate and anchors), `det_terrazzo` (recycled-plastic terrazzo edge).

## Key dimensions (inches, based on standard anthropometrics)

| | |
| --- | --- |
| Seat length | 72" (3 seats × 24") |
| Seat height | 17" at front edge, 5° rake |
| Seat depth | 18" |
| Backrest | 18" panel, 15° recline, 100° seat-to-back angle, top at 33" |
| Armrest | 26¾" (≈ 9¾" above seat) |
| Canopy | 80" × 36" barrel (R 42½"), crown at 91", 86⅛" clear at edges |
| Footprint | 75½" × 35¾" |
| Tube | Ø1½" recycled steel, powder-coated |
| Panels | 1½" seat/back, ¾" thermoformed canopy: terrazzo-effect recycled HDPE |

## Joinery summary

1. Canopy panel → rolled flat-bar ribs with countersunk stainless screws; Ø1" purlins tie the ribs.
2. Each tube's top arm → rib through a welded ¼" cleat pair and 2 no. ⅜" bolts.
3. Seat → two 2"×1" RHS stringers; their end plates bolt to cleats welded on the frame tubes.
4. Panels → screws into moulded-in stainless threaded inserts (no visible fixings on the sitting surfaces).
5. Back → 1½" SHS back rail between posts, with bent-plate stand-offs; L-angles tie the seat to the back.
6. Ground → 6"×4"×¼" foot plates welded under the tube, with 4 no. ⅜" chemical anchors into the concrete path.

## Regenerating

Everything is generated from code with the `bpy` (Blender 5.1) Python module:

```bash
python -m venv venv && ./venv/bin/pip install bpy==5.1.2 pillow
./venv/bin/python bench/drawings.py                 # all drawing sheets
./venv/bin/python bench/renders.py urban park_noon  # renders (see SHOTS in renders.py)
./venv/bin/python bench/export_model.py             # .blend / .obj / .fbx
```

Design parameters live in `bench/bench_model.py` (`P` dict); change a value and re-run to update every drawing and render.
