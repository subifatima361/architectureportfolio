"""Photoreal Cycles renders of the bench in Karachi contexts.

python renders.py <shot> [<shot> ...] [--preview]
shots: urban, urban_side, park_noon, park_wide, det_arm, det_canopy, det_foot, det_rear, det_terrazzo
"""
import math, os, sys, random
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
import env as E
from mathutils import Vector

OUT = os.path.join(ROOT, "output", "renders")
PREVIEW = "--preview" in sys.argv
RES = (2100, 1400)


# ---------------------------------------------------------------------------
def setup_render(sc, samples=160):
    sc.render.resolution_x, sc.render.resolution_y = RES
    sc.render.resolution_percentage = 34 if PREVIEW else 100
    sc.cycles.samples = 24 if PREVIEW else samples
    sc.cycles.use_adaptive_sampling = True
    sc.cycles.adaptive_threshold = 0.02
    sc.cycles.use_denoising = True
    sc.cycles.denoiser = 'OPENIMAGEDENOISE'
    sc.cycles.max_bounces = 6
    sc.cycles.diffuse_bounces = 3
    sc.cycles.glossy_bounces = 3
    sc.cycles.transmission_bounces = 4
    sc.cycles.transparent_max_bounces = 8
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    sc.cycles.sample_clamp_indirect = 8
    sc.render.film_transparent = False
    sc.view_settings.view_transform = 'AgX'
    try:
        sc.view_settings.look = 'AgX - Medium High Contrast'
    except Exception:
        pass
    sc.render.image_settings.file_format = 'PNG'
    sc.render.image_settings.color_depth = '8'


def sun_and_sky(sc, elev, azim, strength=6.5, sky_strength=0.2, haze_air=1.6):
    """azim: degrees, compass-like measured from +Y (north) clockwise.
    Bench front faces -Y (south)."""
    w = bpy.data.worlds.new("sky")
    sc.world = w
    w.use_nodes = True
    nt = w.node_tree
    bg = nt.nodes['Background']
    sky = nt.nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'MULTIPLE_SCATTERING'
    sky.sun_disc = False
    sky.sun_elevation = math.radians(elev)
    # Blender sky rotation: 0 = sun toward +Y? Use the light direction for consistency.
    sky.sun_rotation = math.radians(-azim)
    sky.air_density = haze_air
    sky.aerosol_density = 2.0
    nt.links.new(sky.outputs[0], bg.inputs[0])
    bg.inputs[1].default_value = sky_strength
    # sun lamp
    ld = bpy.data.lights.new("Sun", 'SUN')
    ld.energy = strength
    ld.angle = math.radians(0.6)
    ld.color = (1.0, 0.96, 0.90)
    so = bpy.data.objects.new("Sun", ld)
    sc.collection.objects.link(so)
    # direction from ground toward sun
    a = math.radians(azim); e = math.radians(elev)
    to_sun = Vector((math.sin(a) * math.cos(e), math.cos(a) * math.cos(e), math.sin(e)))
    so.rotation_euler = (-to_sun).to_track_quat('-Z', 'Y').to_euler()
    return so


def bench(sc):
    coll, parts = BM.build()
    BM.assign_materials(parts)
    return parts


def dof(cam, target, fstop):
    cam.data.dof.use_dof = True
    cam.data.dof.focus_distance = (Vector(target) - cam.location).length
    cam.data.dof.aperture_fstop = fstop


def leaf_mats():
    neem = E.mat_leaf("Neem_Leaf", [(0.16, 0.30, 0.07), (0.22, 0.38, 0.09), (0.30, 0.42, 0.12), (0.40, 0.44, 0.15)])
    palm = E.mat_leaf("Palm_Leaf", [(0.26, 0.34, 0.10), (0.36, 0.42, 0.14), (0.48, 0.48, 0.22)], trans=0.3)
    dry = E.mat_leaf("Dry_Leaf", [(0.55, 0.45, 0.20), (0.62, 0.52, 0.25), (0.45, 0.40, 0.18), (0.40, 0.45, 0.16)], trans=0.1)
    bark = E.mat_bark("Neem_Bark")
    pbark = E.mat_bark("Palm_Bark", (0.36, 0.33, 0.29), (0.55, 0.51, 0.45), rings=True)
    return neem, palm, dry, bark, pbark


HAZE_URBAN = ((0.86, 0.82, 0.74), 140.0, 0.8)
HAZE_PARK = ((0.84, 0.86, 0.86), 160.0, 0.75)


# ---------------------------------------------------------------------------
# Scene A: Karachi street - concrete footpath, painted kerb, shops, neem, wires
# ---------------------------------------------------------------------------
def scene_urban(sc):
    c = E.coll("Context")
    neem, palm, dry, bark, pbark = leaf_mats()
    conc = E.mat_concrete("Concrete_Path", joint=1.22)
    E.box_obj("Footpath", c, (5, 3.6, -0.075), (110, 12.4, 0.15), conc)
    E.box_obj("Kerb", c, (5, -2.62, -0.04), (70, 0.25, 0.32), E.mat_kerb())
    asph = E.mat_asphalt()
    E.box_obj("Road", c, (5, -12, -0.25), (120, 18.5, 0.1), asph)
    line = E.mat_paint("Road_Line", (0.85, 0.84, 0.78), 0.7, streaks=True)
    for i in range(-10, 20):
        E.box_obj(f"Line{i}", c, (i * 4.5, -9.5, -0.195), (2.2, 0.12, 0.01), line)
    # far side of the road: footpath + buildings (seen in reverse/side shots)
    E.box_obj("Footpath_Far", c, (5, -24, -0.075), (120, 5, 0.15), conc)
    # buildings behind the footpath
    x = -40.0
    seed = 3
    while x < 55:
        w = random.Random(seed).uniform(9, 16)
        fl = random.Random(seed + 1).randint(4, 7)
        E.make_building(f"Bldg{seed}", c, x, 9.6, w, 12, fl, seed, facing=-1, haze=HAZE_URBAN)
        x += w + random.Random(seed + 2).uniform(0.0, 1.5)
        seed += 3
    x = -45.0
    while x < 60:
        w = random.Random(seed).uniform(10, 18)
        fl = random.Random(seed + 1).randint(5, 9)
        E.make_building(f"BldgFar{seed}", c, x, -27, w, 12, fl, seed, facing=1, haze=HAZE_URBAN)
        x += w + 1
        seed += 3
    # distant skyline blocks for depth
    for i in range(30):
        rr = random.Random(100 + i)
        E.make_building(f"Sky{i}", c, rr.uniform(-80, 90), rr.uniform(30, 70), rr.uniform(10, 20), 12,
                        rr.randint(6, 14), 200 + i, facing=-1, haze=((0.86, 0.82, 0.74), 60.0, 0.9))
    # street trees (neem) in tree pits
    soil = E.mat_simple("Soil", (0.36, 0.30, 0.22), 0.95)
    for i, (tx, ty, h) in enumerate(((-6.5, 2.8, 8.5), (6.0, 3.4, 9.5), (17.0, 2.9, 8.0), (-17, 3.1, 9))):
        E.box_obj(f"Pit{i}", c, (tx, ty, 0.005), (1.2, 1.2, 0.02), soil)
        E.make_tree(f"Neem{i}", c, (tx, ty, 0), h, seed=10 + i, leaf_mat=neem, bark_mat=bark)
    # electric poles + wires along the kerb
    poles = [(-14, -2.2), (8, -2.2), (30, -2.2)]
    for i, (px, py) in enumerate(poles):
        E.make_electric_pole(f"Pole{i}", c, (px, py, 0), 9.0)
    for i in range(len(poles) - 1):
        a, b = poles[i], poles[i + 1]
        for k, dx in enumerate((-0.7, -0.35, 0.0, 0.35, 0.7)):
            E.make_wire(f"Wire{i}_{k}", c, (a[0] + dx, a[1], 8.4 - 0.05 * k), (b[0] + dx, b[1], 8.4 - 0.05 * k), sag=0.7 + 0.08 * k)
        # cable drop toward buildings
        E.make_wire(f"Drop{i}", c, (a[0], a[1], 8.2), (a[0] + 3, 9.4, 7.0), sag=0.5)
    E.make_street_lamp("Lamp0", c, (-3.5, -2.2, 0), 7.5, facing=-1)
    # leaves on the footpath
    E.scatter_leaves("Litter", c, (-6, -2.4, 8, 5.5), 900, 7, dry, size=0.045)
    # a low planter to the right
    E.box_obj("Planter", c, (3.3, 0.6, 0.25), (1.2, 0.6, 0.5), E.mat_concrete("Planter_Conc", broom=False, tint=(0.70, 0.67, 0.62)))
    E.grass_patch("PlanterGrass", c, (3.3, 0.6, 0.505), (1.1, 0.5), count=1500, length=0.12,
                  mat=E.mat_grass_hair(), ground_mat=E.mat_simple("Planter_Soil", (0.3, 0.25, 0.18), 0.95), seed=3, children=10)


# ---------------------------------------------------------------------------
# Scene B: Burns Garden - lawn, concrete path, palms & neem, peak sun
# ---------------------------------------------------------------------------
def scene_park(sc, grass_dense=True):
    c = E.coll("Context")
    neem, palm, dry, bark, pbark = leaf_mats()
    conc = E.mat_concrete("Concrete_Path", joint=1.5, tint=(0.70, 0.67, 0.62))
    E.box_obj("Path", c, (0, -1.9, -0.06), (80, 2.4, 0.15), conc)
    E.box_obj("Bench_Pad", c, (0, 0.2, -0.06), (2.6, 1.8, 0.15), conc)
    # path edging (brick-red Karachi park kerb)
    edge = E.mat_simple("Path_Edge", (0.62, 0.36, 0.26), 0.9)
    for y in (-3.13, -0.67):
        if y > -1:
            for xs in ((-40, -1.3), (1.3, 40)):
                E.box_obj(f"Edge{y}{xs}", c, ((xs[0] + xs[1]) / 2, y, 0.0), (xs[1] - xs[0], 0.08, 0.12), edge)
        else:
            E.box_obj(f"Edge{y}", c, (0, y, 0.0), (80, 0.08, 0.12), edge)
    lawn_m = E.mat_lawn_ground()
    E.box_obj("Lawn", c, (0, 0, -0.06), (400, 400, 0.1), lawn_m)
    gm = E.mat_grass_hair()
    # dense hair grass around the bench and toward the camera
    if grass_dense:
        E.grass_patch("Grass_Back", c, (0, 4.6, -0.005), (26, 10.5), count=140000, length=0.08, mat=gm, ground_mat=lawn_m, seed=1, children=12)
        E.grass_patch("Grass_Far", c, (0, 15.5, -0.005), (40, 11.5), count=90000, length=0.07, mat=gm, ground_mat=lawn_m, seed=6, children=10)
        E.grass_patch("Grass_Front", c, (0, -7.5, -0.005), (26, 8.6), count=110000, length=0.08, mat=gm, ground_mat=lawn_m, seed=2, children=12)
        E.grass_patch("Grass_L", c, (-1.95, 0.2, -0.005), (1.3, 1.7), count=2500, length=0.08, mat=gm, ground_mat=lawn_m, seed=4, children=12)
        E.grass_patch("Grass_R", c, (1.95, 0.2, -0.005), (1.3, 1.7), count=2500, length=0.08, mat=gm, ground_mat=lawn_m, seed=5, children=12)
    # palms and neem
    for i, (x, y, h, ln) in enumerate(((-7.5, 7.0, 9.5, (0.06, 0.02)), (-10.5, 10.5, 11.0, (-0.04, 0.05)),
                                       (9.0, 11.0, 10.0, (0.05, -0.03)), (14.5, 7.5, 8.5, (-0.06, 0.0)),
                                       (-22, 18, 12, (0.03, 0.03)), (26, 20, 11, (0.0, 0.05)))):
        E.make_palm(f"Palm{i}", c, (x, y, 0), h, seed=30 + i, lean=ln, leaf_mat=palm, bark_mat=pbark)
    for i, (x, y, h, s) in enumerate(((4.5, 8.0, 9.5, 1.1), (-3.0, 16.0, 12.0, 1.2), (18, 15, 11, 1.0),
                                      (-16, 9, 10, 1.1), (-30, 25, 13, 1.2), (34, 28, 13, 1.2), (8, 30, 14, 1.3),
                                      (-8, -14, 10, 1.0), (12, -16, 11, 1.1))):
        E.make_tree(f"Neem{i}", c, (x, y, 0), h, seed=50 + i, spread=s, leaf_mat=neem, bark_mat=bark)
    # far tree line and city beyond, hazy
    hz = HAZE_PARK
    for m_ in (neem, palm, bark, pbark):
        pass
    for i in range(18):
        rr = random.Random(400 + i)
        E.make_tree(f"FarTree{i}", c, (rr.uniform(-70, 70), rr.uniform(40, 55), 0), rr.uniform(10, 15), seed=600 + i,
                    spread=1.2, leaf_mat=neem, bark_mat=bark, leaves_per_tip=30, depth=3, cluster_r=0.8, leaf_len=0.12, leaf_w=0.05)
    for i in range(16):
        rr = random.Random(700 + i)
        E.make_building(f"City{i}", c, rr.uniform(-160, 160), rr.uniform(150, 220), rr.uniform(12, 22), 14,
                        rr.randint(5, 11), 800 + i, facing=-1, haze=((0.84, 0.86, 0.86), 60.0, 0.93))
    # Gizri stone boundary wall with railing, far right
    stone = E.mat_stone_wall()
    E.box_obj("ParkWall", c, (0, 36, 0.6), (140, 0.45, 1.2), stone)
    rail = E.mat_simple("Railing", (0.10, 0.18, 0.12), 0.5, 0.4)
    for i in range(-70, 70):
        E.cyl_obj(f"Rail{i}", c, (i, 36, 1.2), (i, 36, 2.4), 0.012, rail, 6)
    E.box_obj("RailTop", c, (0, 36, 2.38), (140, 0.04, 0.04), rail)
    # fallen neem leaves on path
    E.scatter_leaves("Litter", c, (-6, -3.1, 6, 1.1), 700, 9, dry, size=0.045)
    # haze on background stuff applied to tree materials only for camera rays far away
    E.add_haze(neem, *hz); E.add_haze(palm, *hz); E.add_haze(bark, *hz); E.add_haze(pbark, *hz)
    E.add_haze(lawn_m, *hz); E.add_haze(stone, *hz)


# ---------------------------------------------------------------------------
SHOTS = {
    # name: (scene, cam_loc, target, lens, fstop, sun(elev, azim), extra)
    "urban": ("urban", (-2.7, -4.4, 1.35), (0.2, 0.35, 1.0), 30, 4.0, (58, 215)),
    "urban_side": ("urban", (-6.8, -1.2, 1.25), (0.0, 0.25, 1.05), 50, 8.0, (58, 215)),
    "park_noon": ("park", (-2.9, -5.0, 1.45), (0.15, 0.2, 1.05), 32, 5.6, (82, 200)),
    "park_wide": ("park", (4.8, -8.5, 2.6), (0.0, 0.5, 1.3), 28, 9.0, (82, 200)),
    "det_arm": ("park", (-1.55, -1.05, 0.55), (-0.88, -0.1, 0.52), 55, 3.2, (82, 200)),
    "det_canopy": ("park", (-0.6, -0.55, 1.05), (-0.94, 0.22, 2.22), 30, 5.6, (82, 200)),
    "det_foot": ("park", (-1.25, -0.95, 0.32), (-0.94, -0.3, 0.03), 60, 3.5, (82, 200)),
    "det_rear": ("park", (3.3, 3.9, 1.9), (0.0, 0.2, 1.0), 40, 8.0, (82, 200)),
    "det_terrazzo": ("park", (0.55, -0.62, 0.70), (0.80, -0.18, 0.43), 70, 2.8, (82, 200)),
}


def run(shot):
    scn, loc, tgt, lens, fst, (el, az) = SHOTS[shot]
    sc = reset()
    setup_render(sc, samples=128 if shot.startswith("det") else 96)
    bench(sc)
    if scn == "urban":
        scene_urban(sc)
    else:
        scene_park(sc, grass_dense=True)
    sun_and_sky(sc, el, az)
    cam = camera("Cam", loc, target=tgt, lens=lens)
    sc.camera = cam
    dof(cam, tgt, fst)
    path = os.path.join(OUT, ("_preview_" if PREVIEW else "") + shot + ".png")
    import time
    t = time.time()
    render(path)
    print("saved", path, "render s", round(time.time() - t))


if __name__ == "__main__":
    shots = [a for a in sys.argv[1:] if not a.startswith("--")]
    for s in shots:
        run(s)
