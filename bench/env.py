"""Procedural Karachi context: materials, trees, palms, buildings, street furniture.
Everything is generated from code (no downloaded assets), units in metres."""
import math, random
import bpy, bmesh
from mathutils import Vector, Matrix, Euler, noise

from bench_model import _lin, _sk


# ---------------------------------------------------------------------------
# generic helpers
# ---------------------------------------------------------------------------
def coll(name):
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    c = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(c)
    return c


def mesh_obj(name, verts, faces, c, mat=None, smooth=False):
    me = bpy.data.meshes.new(name)
    me.from_pydata(verts, [], faces)
    me.validate()
    if smooth:
        for p in me.polygons:
            p.use_smooth = True
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    if mat:
        me.materials.append(mat)
    return ob


def box_obj(name, c, center, size, mat=None, rot=(0, 0, 0), bevel=0.0):
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    for v in bm.verts:
        v.co = Vector((v.co.x * size[0], v.co.y * size[1], v.co.z * size[2]))
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    ob.location = center
    ob.rotation_euler = rot
    if mat:
        me.materials.append(mat)
    if bevel:
        m = ob.modifiers.new("bv", 'BEVEL'); m.width = bevel; m.segments = 2
    return ob


def cyl_obj(name, c, p0, p1, r, mat=None, verts=16):
    p0, p1 = Vector(p0), Vector(p1)
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts, radius1=r, radius2=r, depth=(p1 - p0).length)
    bm.to_mesh(me); bm.free()
    for p in me.polygons:
        p.use_smooth = len(p.vertices) == 4
    ob = bpy.data.objects.new(name, me)
    c.objects.link(ob)
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = Vector((0, 0, 1)).rotation_difference((p1 - p0).normalized())
    ob.location = (p0 + p1) / 2
    if mat:
        me.materials.append(mat)
    return ob


def new_mat(name):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    return m, nt, nt.nodes, nt.links, nt.nodes['Principled BSDF']


def ramp(N, cols, pos=None, interp='LINEAR'):
    r = N.new('ShaderNodeValToRGB')
    r.color_ramp.interpolation = interp
    els = r.color_ramp.elements
    pos = pos or [i / (len(cols) - 1) for i in range(len(cols))]
    els[0].position = pos[0]; els[0].color = _lin(cols[0]) + (1,)
    els[1].position = pos[-1]; els[1].color = _lin(cols[-1]) + (1,)
    for p, c in zip(pos[1:-1], cols[1:-1]):
        e = els.new(p); e.color = _lin(c) + (1,)
    return r


def noise_tex(N, L, vec, scale, detail=4, rough=0.5, dist=0.0):
    n = N.new('ShaderNodeTexNoise')
    n.inputs['Scale'].default_value = scale
    n.inputs['Detail'].default_value = detail
    n.inputs['Roughness'].default_value = rough
    n.inputs['Distortion'].default_value = dist
    if vec is not None:
        L.new(vec, n.inputs['Vector'])
    return n


def math_node(N, L, op, a, b=None, clamp=False):
    m = N.new('ShaderNodeMath'); m.operation = op; m.use_clamp = clamp
    if isinstance(a, (int, float)):
        m.inputs[0].default_value = a
    else:
        L.new(a, m.inputs[0])
    if b is not None:
        if isinstance(b, (int, float)):
            m.inputs[1].default_value = b
        else:
            L.new(b, m.inputs[1])
    return m.outputs[0]


def mix_rgb(N, L, fac, a, b, blend='MIX'):
    m = N.new('ShaderNodeMix'); m.data_type = 'RGBA'; m.blend_type = blend
    for sock, v in ((_sk(m.inputs, 'Factor_Float'), fac), (_sk(m.inputs, 'A_Color'), a), (_sk(m.inputs, 'B_Color'), b)):
        if isinstance(v, (int, float)):
            sock.default_value = v
        elif isinstance(v, tuple):
            sock.default_value = _lin(v) + (1,)
        else:
            L.new(v, sock)
    return _sk(m.outputs, 'Result_Color')


def bump(N, L, height, strength, dist=0.01, normal=None):
    b = N.new('ShaderNodeBump')
    b.inputs['Strength'].default_value = strength
    b.inputs['Distance'].default_value = dist
    L.new(height, b.inputs['Height'])
    if normal is not None:
        L.new(normal, b.inputs['Normal'])
    return b.outputs[0]


def add_haze(m, color=(0.80, 0.78, 0.72), dist=180.0, amount=0.85):
    """Aerial perspective for camera rays: mix toward haze colour by distance."""
    nt = m.node_tree; N = nt.nodes; L = nt.links
    out = next(n for n in N if n.type == 'OUTPUT_MATERIAL')
    src = out.inputs['Surface'].links[0].from_socket
    cd = N.new('ShaderNodeCameraData')
    f = math_node(N, L, 'DIVIDE', cd.outputs['View Distance'], dist)
    f = math_node(N, L, 'MULTIPLY', f, -1.0)
    f = math_node(N, L, 'EXPONENT', f)
    f = math_node(N, L, 'SUBTRACT', 1.0, f)
    f = math_node(N, L, 'MULTIPLY', f, amount, clamp=True)
    lp = N.new('ShaderNodeLightPath')
    f = math_node(N, L, 'MULTIPLY', f, lp.outputs['Is Camera Ray'])
    em = N.new('ShaderNodeEmission'); em.inputs['Color'].default_value = _lin(color) + (1,)
    em.inputs['Strength'].default_value = 1.0
    ms = N.new('ShaderNodeMixShader')
    L.new(f, ms.inputs[0]); L.new(src, ms.inputs[1]); L.new(em.outputs[0], ms.inputs[2])
    L.new(ms.outputs[0], out.inputs['Surface'])
    return m


# ---------------------------------------------------------------------------
# materials
# ---------------------------------------------------------------------------
def mat_concrete(name="Concrete_Path", joint=1.22, tint=(0.66, 0.63, 0.58), broom=True):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord')
    co = tc.outputs['Object']
    big = noise_tex(N, L, co, 0.6, 6, 0.6)
    mid = noise_tex(N, L, co, 6, 8, 0.6)
    fine = noise_tex(N, L, co, 160, 3, 0.5)
    base = ramp(N, [tuple(c * 0.86 for c in tint), tint, tuple(min(1, c * 1.08) for c in tint)])
    L.new(mid.outputs['Fac'], base.inputs[0])
    stain = ramp(N, [(0, 0, 0), (1, 1, 1)], [0.45, 0.62])
    L.new(big.outputs['Fac'], stain.inputs[0])
    col = mix_rgb(N, L, 0.0, base.outputs[0], (0.42, 0.39, 0.35), 'MIX')
    # stains via factor
    mixn = col.node
    L.new(math_node(N, L, 'MULTIPLY', _sk(stain.outputs, 'Color') if False else stain.outputs[0], 0.45), _sk(mixn.inputs, 'Factor_Float'))
    # expansion joints using a brick texture as a grid
    br = N.new('ShaderNodeTexBrick')
    br.offset = 0.0
    br.inputs['Scale'].default_value = 1.0
    br.inputs['Mortar Size'].default_value = 0.008
    br.inputs['Brick Width'].default_value = joint
    br.inputs['Row Height'].default_value = joint
    br.inputs['Mortar Smooth'].default_value = 0.3
    L.new(co, br.inputs['Vector'])
    col2 = mix_rgb(N, L, br.outputs['Fac'], col, (0.30, 0.28, 0.26))
    # fine aggregate speckle
    sp = N.new('ShaderNodeTexVoronoi'); sp.inputs['Scale'].default_value = 400
    L.new(co, sp.inputs['Vector'])
    spm = math_node(N, L, 'LESS_THAN', sp.outputs['Distance'], 0.12)
    col3 = mix_rgb(N, L, math_node(N, L, 'MULTIPLY', spm, 0.35), col2, (0.35, 0.33, 0.30))
    L.new(col3, b.inputs['Base Color'])
    rr = ramp(N, [(0.78, 0.78, 0.78), (0.95, 0.95, 0.95)])
    L.new(mid.outputs['Fac'], rr.inputs[0])
    L.new(rr.outputs[0], b.inputs['Roughness'])
    # broom finish (fine grooves across the path)
    h = fine.outputs['Fac']
    if broom:
        mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (1, 70, 1)
        L.new(co, mp.inputs['Vector'])
        wv = noise_tex(N, L, mp.outputs[0], 30, 2, 0.5)
        h = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', wv.outputs['Fac'], 1.2), fine.outputs['Fac'])
    hb = math_node(N, L, 'SUBTRACT', h, math_node(N, L, 'MULTIPLY', br.outputs['Fac'], 3.0))
    L.new(bump(N, L, hb, 0.35, 0.002), b.inputs['Normal'])
    return m


def mat_asphalt(name="Asphalt"):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord'); co = tc.outputs['Object']
    n1 = noise_tex(N, L, co, 2, 6, 0.6)
    r = ramp(N, [(0.10, 0.10, 0.10), (0.20, 0.19, 0.18), (0.26, 0.25, 0.23)])
    L.new(n1.outputs['Fac'], r.inputs[0])
    v = N.new('ShaderNodeTexVoronoi'); v.inputs['Scale'].default_value = 300; L.new(co, v.inputs['Vector'])
    agg = math_node(N, L, 'LESS_THAN', v.outputs['Distance'], 0.25)
    col = mix_rgb(N, L, math_node(N, L, 'MULTIPLY', agg, 0.3), r.outputs[0], (0.45, 0.43, 0.40))
    L.new(col, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.9
    L.new(bump(N, L, v.outputs['Distance'], 0.4, 0.002), b.inputs['Normal'])
    return m


def mat_kerb(name="Kerb_Painted"):
    """Karachi kerbs: alternating yellow / black paint, chipped and dusty."""
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord'); co = tc.outputs['Object']
    sep = N.new('ShaderNodeSeparateXYZ'); L.new(co, sep.inputs[0])
    stripe = math_node(N, L, 'FLOORED_MODULO', sep.outputs['X'], 1.2)
    st = math_node(N, L, 'LESS_THAN', stripe, 0.6)
    col = mix_rgb(N, L, st, (0.08, 0.08, 0.08), (0.86, 0.68, 0.10))
    wear = noise_tex(N, L, co, 14, 8, 0.7)
    wm = ramp(N, [(0, 0, 0), (1, 1, 1)], [0.58, 0.66])
    L.new(wear.outputs['Fac'], wm.inputs[0])
    col = mix_rgb(N, L, wm.outputs[0], col, (0.60, 0.57, 0.52))
    dust = noise_tex(N, L, co, 3, 4, 0.5)
    col = mix_rgb(N, L, math_node(N, L, 'MULTIPLY', dust.outputs['Fac'], 0.35), col, (0.70, 0.64, 0.55))
    L.new(col, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.8
    L.new(bump(N, L, wear.outputs['Fac'], 0.2, 0.003), b.inputs['Normal'])
    return m


def mat_stone_wall(name="Gizri_Stone"):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord'); co = tc.outputs['Object']
    # stones roughly 40x25 cm on vertical faces: use X/Z
    mp = N.new('ShaderNodeMapping'); mp.inputs['Rotation'].default_value = (math.radians(90), 0, 0)
    L.new(co, mp.inputs['Vector'])
    warp = noise_tex(N, L, mp.outputs[0], 3, 2, 0.5)
    wv = N.new('ShaderNodeMix'); wv.data_type = 'VECTOR'; _sk(wv.inputs, 'Factor_Float').default_value = 0.03
    L.new(mp.outputs[0], _sk(wv.inputs, 'A_Vector')); L.new(warp.outputs['Color'], _sk(wv.inputs, 'B_Vector'))
    br = N.new('ShaderNodeTexBrick')
    br.inputs['Scale'].default_value = 1.0
    br.inputs['Brick Width'].default_value = 0.42
    br.inputs['Row Height'].default_value = 0.26
    br.inputs['Mortar Size'].default_value = 0.022
    br.inputs['Mortar Smooth'].default_value = 0.6
    br.inputs['Bias'].default_value = 0.0
    br.inputs['Color1'].default_value = _lin((0.80, 0.68, 0.48)) + (1,)
    br.inputs['Color2'].default_value = _lin((0.70, 0.58, 0.40)) + (1,)
    br.inputs['Mortar'].default_value = _lin((0.78, 0.72, 0.60)) + (1,)
    L.new(_sk(wv.outputs, 'Result_Vector'), br.inputs['Vector'])
    pit = noise_tex(N, L, co, 40, 8, 0.7)
    col = mix_rgb(N, L, math_node(N, L, 'MULTIPLY', pit.outputs['Fac'], 0.4), br.outputs['Color'], (0.55, 0.45, 0.30))
    L.new(col, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.95
    h = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', br.outputs['Fac'], -1.0), math_node(N, L, 'MULTIPLY', pit.outputs['Fac'], 0.6))
    L.new(bump(N, L, h, 0.8, 0.02), b.inputs['Normal'])
    return m


def mat_paint(name, rgb, rough=0.85, streaks=True, haze=False):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord'); co = tc.outputs['Generated'] if False else tc.outputs['Object']
    mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (6, 6, 0.6)
    L.new(co, mp.inputs['Vector'])
    st = noise_tex(N, L, mp.outputs[0], 3, 6, 0.6)
    r = ramp(N, [(0, 0, 0), (1, 1, 1)], [0.40, 0.75])
    L.new(st.outputs['Fac'], r.inputs[0])
    dirty = tuple(c * 0.62 for c in rgb)
    col = mix_rgb(N, L, math_node(N, L, 'MULTIPLY', r.outputs[0], 0.7 if streaks else 0.15), rgb, dirty)
    L.new(col, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = rough
    return m


def mat_simple(name, rgb, rough=0.6, metal=0.0, coat=0.0):
    m, nt, N, L, b = new_mat(name)
    b.inputs['Base Color'].default_value = _lin(rgb) + (1,)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Coat Weight'].default_value = coat
    return m


def mat_glass_dark(name="Window_Dark"):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord')
    n = noise_tex(N, L, tc.outputs['Object'], 2, 2, 0.5)
    r = ramp(N, [(0.05, 0.06, 0.07), (0.20, 0.22, 0.24)])
    L.new(n.outputs['Fac'], r.inputs[0])
    L.new(r.outputs[0], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.12
    b.inputs['Specular IOR Level'].default_value = 0.7
    return m


def mat_shutter(name="Shop_Shutter"):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord')
    w = N.new('ShaderNodeTexWave'); w.wave_type = 'BANDS'; w.bands_direction = 'Z'
    w.inputs['Scale'].default_value = 60
    L.new(tc.outputs['Object'], w.inputs['Vector'])
    n = noise_tex(N, L, tc.outputs['Object'], 4, 6, 0.6)
    col = mix_rgb(N, L, n.outputs['Fac'], (0.45, 0.47, 0.48), (0.30, 0.28, 0.25))
    L.new(col, b.inputs['Base Color'])
    b.inputs['Metallic'].default_value = 0.6
    b.inputs['Roughness'].default_value = 0.55
    L.new(bump(N, L, w.outputs['Fac'], 0.5, 0.01), b.inputs['Normal'])
    return m


def mat_leaf(name, cols, trans=0.35):
    """Two-sided leaf with per-island colour variation and translucency."""
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    for n in list(N):
        N.remove(n)
    out = N.new('ShaderNodeOutputMaterial')
    geo = N.new('ShaderNodeNewGeometry')
    rnd = N.new('ShaderNodeObjectInfo')
    rpi = None
    try:
        g = N.new('ShaderNodeNewGeometry')
        rpi = g.outputs['Random Per Island']
    except Exception:
        rpi = rnd.outputs['Random']
    r = ramp(N, cols)
    L.new(rpi, r.inputs[0])
    pb = N.new('ShaderNodeBsdfPrincipled')
    L.new(r.outputs[0], pb.inputs['Base Color'])
    pb.inputs['Roughness'].default_value = 0.45
    pb.inputs['Specular IOR Level'].default_value = 0.45
    tr = N.new('ShaderNodeBsdfTranslucent')
    tcol = N.new('ShaderNodeMix'); tcol.data_type = 'RGBA'; tcol.blend_type = 'MULTIPLY'
    _sk(tcol.inputs, 'Factor_Float').default_value = 1.0
    L.new(r.outputs[0], _sk(tcol.inputs, 'A_Color'))
    _sk(tcol.inputs, 'B_Color').default_value = (1.0, 1.15, 0.45, 1)
    L.new(_sk(tcol.outputs, 'Result_Color'), tr.inputs['Color'])
    ms = N.new('ShaderNodeMixShader'); ms.inputs[0].default_value = trans
    L.new(pb.outputs[0], ms.inputs[1]); L.new(tr.outputs[0], ms.inputs[2])
    L.new(ms.outputs[0], out.inputs['Surface'])
    return m


def mat_bark(name="Bark", c0=(0.25, 0.21, 0.17), c1=(0.42, 0.37, 0.31), rings=False):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord'); co = tc.outputs['Object']
    mp = N.new('ShaderNodeMapping'); mp.inputs['Scale'].default_value = (8, 8, 1.2)
    L.new(co, mp.inputs['Vector'])
    n = noise_tex(N, L, mp.outputs[0], 6, 8, 0.7, 1.5)
    r = ramp(N, [c0, c1])
    L.new(n.outputs['Fac'], r.inputs[0])
    h = n.outputs['Fac']
    if rings:
        w = N.new('ShaderNodeTexWave'); w.wave_type = 'BANDS'; w.bands_direction = 'Z'
        w.inputs['Scale'].default_value = 1.0
        w.inputs['Distortion'].default_value = 2
        mp2 = N.new('ShaderNodeMapping'); mp2.inputs['Scale'].default_value = (1, 1, 6)
        L.new(co, mp2.inputs['Vector']); L.new(mp2.outputs[0], w.inputs['Vector'])
        h = math_node(N, L, 'ADD', h, w.outputs['Fac'])
    L.new(r.outputs[0], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.9
    L.new(bump(N, L, h, 0.9, 0.02), b.inputs['Normal'])
    return m


def mat_grass_hair(name="Grass_Blades"):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree; N = nt.nodes; L = nt.links
    b = N['Principled BSDF']
    hi = N.new('ShaderNodeHairInfo')
    tc = N.new('ShaderNodeTexCoord')
    n = noise_tex(N, L, tc.outputs['Generated'], 4, 4, 0.5)
    r = ramp(N, [(0.20, 0.33, 0.08), (0.36, 0.45, 0.14), (0.58, 0.55, 0.26)], [0.0, 0.55, 1.0])
    mx = math_node(N, L, 'ADD', math_node(N, L, 'MULTIPLY', hi.outputs['Random'], 0.55), math_node(N, L, 'MULTIPLY', n.outputs['Fac'], 0.5))
    L.new(mx, r.inputs[0])
    dark = mix_rgb(N, L, math_node(N, L, 'SUBTRACT', 1.0, hi.outputs['Intercept']), r.outputs[0], (0.06, 0.09, 0.03))
    _sk(dark.node.inputs, 'Factor_Float').default_value = 0.0
    L.new(math_node(N, L, 'MULTIPLY', math_node(N, L, 'SUBTRACT', 1.0, hi.outputs['Intercept']), 0.55), _sk(dark.node.inputs, 'Factor_Float'))
    L.new(dark, b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.55
    b.inputs['Transmission Weight'].default_value = 0.0
    return m


def mat_lawn_ground(name="Lawn_Soil"):
    m, nt, N, L, b = new_mat(name)
    tc = N.new('ShaderNodeTexCoord')
    n = noise_tex(N, L, tc.outputs['Object'], 0.8, 6, 0.6)
    r = ramp(N, [(0.20, 0.27, 0.08), (0.33, 0.38, 0.13), (0.52, 0.47, 0.30)], [0.2, 0.55, 0.8])
    L.new(n.outputs['Fac'], r.inputs[0])
    L.new(r.outputs[0], b.inputs['Base Color'])
    b.inputs['Roughness'].default_value = 0.95
    return m


# ---------------------------------------------------------------------------
# trees
# ---------------------------------------------------------------------------
def _rand_unit(rng):
    while True:
        v = Vector((rng.uniform(-1, 1), rng.uniform(-1, 1), rng.uniform(-1, 1)))
        if 0.01 < v.length <= 1:
            return v.normalized()


def make_tree(name, c, loc, height=8.0, seed=1, spread=1.0, leaf_mat=None, bark_mat=None,
              leaf_len=0.14, leaf_w=0.05, leaves_per_tip=80, depth=5, cluster_r=0.55):
    """Broadleaf (neem / rain tree style) via recursive branching."""
    rng = random.Random(seed)
    cu = bpy.data.curves.new(name + "_wood", 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = 1.0
    cu.bevel_resolution = 2
    cu.use_fill_caps = True
    tips = []

    def grow(p, d, length, radius, lvl):
        n = 6
        pts = [p.copy()]
        dd = d.copy()
        step = length / n
        for i in range(n):
            dd = (dd + _rand_unit(rng) * 0.18 + Vector((0, 0, 0.10 if lvl < 2 else -0.04))).normalized()
            p = p + dd * step
            pts.append(p.copy())
        sp = cu.splines.new('POLY')
        sp.points.add(len(pts) - 1)
        for i, q in enumerate(pts):
            sp.points[i].co = (q.x, q.y, q.z, 1)
            sp.points[i].radius = radius * (1 - 0.45 * i / n)
        if lvl >= depth:
            tips.append((pts[-1], dd))
            tips.append((pts[-3], dd))
            return
        kids = 3 if lvl == 0 else rng.choice((2, 3, 3, 4))
        for k in range(kids):
            t = rng.uniform(0.55, 1.0) if lvl == 0 else rng.uniform(0.35, 1.0)
            idx = min(n, max(1, int(t * n)))
            base = pts[idx]
            ang = math.radians(rng.uniform(28, 55) * (1.25 if lvl == 0 else 1.0) * spread)
            axis = dd.cross(_rand_unit(rng)).normalized()
            nd = (Matrix.Rotation(ang, 3, axis) @ dd).normalized()
            if lvl == 0:
                az = 2 * math.pi * k / kids + rng.uniform(-0.4, 0.4)
                nd = Vector((math.cos(az) * 0.75 * spread, math.sin(az) * 0.75 * spread, 0.8)).normalized()
            if lvl == 0:
                base = pts[rng.choice((n - 1, n))]
            grow(base, nd, length * rng.uniform(0.62, 0.78), radius * 0.6 * (1 - 0.45 * idx / n) / 0.7, lvl + 1)

    trunk_h = height * 0.36
    grow(Vector(loc), Vector((rng.uniform(-.08, .08), rng.uniform(-.08, .08), 1)).normalized(), trunk_h * 1.25,
         height * 0.028, 0)
    wood = bpy.data.objects.new(name + "_wood", cu)
    c.objects.link(wood)
    if bark_mat:
        cu.materials.append(bark_mat)

    # leaves: small lanceolate quads clustered at tips
    verts, faces = [], []
    zmin = loc[2] + height * 0.36
    for tp, td in tips:
        if tp.z < zmin:
            continue
        for i in range(leaves_per_tip):
            off = _rand_unit(rng) * cluster_r * rng.random() ** 0.5
            ctr = tp + off + td * cluster_r * 0.3
            ax = (_rand_unit(rng) + Vector((0, 0, -0.5))).normalized()
            side = ax.cross(_rand_unit(rng)).normalized()
            l = leaf_len * rng.uniform(0.7, 1.3)
            w = leaf_w * rng.uniform(0.7, 1.3)
            a = ctr - ax * l / 2
            bpt = ctr + ax * l / 2
            k = len(verts)
            verts += [a[:], (ctr + side * w / 2)[:], bpt[:], (ctr - side * w / 2 + ax * 0.004)[:]]
            faces.append((k, k + 1, k + 2, k + 3))
    leaves = mesh_obj(name + "_leaves", verts, faces, c, leaf_mat)
    return wood, leaves


def make_palm(name, c, loc, height=8.0, seed=1, lean=(0.05, 0.02), leaf_mat=None, bark_mat=None, fronds=16):
    """Coconut palm: curved ringed trunk + drooping pinnate fronds."""
    rng = random.Random(seed)
    cu = bpy.data.curves.new(name + "_trunk", 'CURVE')
    cu.dimensions = '3D'; cu.bevel_depth = 1.0; cu.bevel_resolution = 4; cu.use_fill_caps = True
    sp = cu.splines.new('POLY')
    n = 20
    sp.points.add(n)
    base = Vector(loc)
    pts = []
    for i in range(n + 1):
        t = i / n
        p = base + Vector((lean[0] * height * t * t, lean[1] * height * t * t, height * t))
        pts.append(p)
        sp.points[i].co = (p.x, p.y, p.z, 1)
        sp.points[i].radius = 0.19 * (1 - 0.35 * t) * (1.25 if i == 0 else 1)
    tr = bpy.data.objects.new(name + "_trunk", cu)
    c.objects.link(tr)
    if bark_mat:
        cu.materials.append(bark_mat)
    top = pts[-1]
    verts, faces = [], []
    for f in range(fronds):
        az = 2 * math.pi * f / fronds + rng.uniform(-0.2, 0.2)
        el = math.radians(rng.uniform(-10, 55))
        d = Vector((math.cos(az) * math.cos(el), math.sin(az) * math.cos(el), math.sin(el)))
        L = rng.uniform(3.0, 4.2)
        m = 26
        p = top.copy()
        rach = []
        dd = d.copy()
        for i in range(m + 1):
            rach.append((p.copy(), dd.copy()))
            dd = (dd + Vector((0, 0, -0.07))).normalized()
            p = p + dd * (L / m)
        # rachis as thin quads strip
        for i in range(2, m):
            p0, d0 = rach[i]
            side = d0.cross(Vector((0, 0, 1))).normalized()
            if side.length < 0.1:
                side = Vector((1, 0, 0))
            ll = 0.75 * math.sin(math.pi * (i / m) ** 0.8) + 0.15
            for s in (-1, 1):
                for j in range(2):
                    q0 = p0 + d0 * (j * 0.05)
                    droop = Vector((0, 0, -0.55 - 0.3 * i / m))
                    ldir = (side * s + droop + d0 * 0.35).normalized()
                    tip = q0 + ldir * ll * rng.uniform(0.85, 1.1)
                    w = 0.025
                    up = ldir.cross(d0).normalized() * w
                    k = len(verts)
                    verts += [(q0 - up)[:], (q0 + up)[:], (tip + up * 0.2)[:], (tip - up * 0.2)[:]]
                    faces.append((k, k + 1, k + 2, k + 3))
        # rachis strip
        for i in range(m):
            p0, d0 = rach[i]; p1, d1 = rach[i + 1]
            side = d0.cross(Vector((0, 0, 1))).normalized() * 0.02 * (1 - i / m + 0.2)
            k = len(verts)
            verts += [(p0 - side)[:], (p0 + side)[:], (p1 + side)[:], (p1 - side)[:]]
            faces.append((k, k + 1, k + 2, k + 3))
    fr = mesh_obj(name + "_fronds", verts, faces, c, leaf_mat)
    # coconuts
    nm = bpy.data.materials.get("Coconut") or mat_simple("Coconut", (0.45, 0.42, 0.18), 0.5)
    for i in range(rng.randint(4, 8)):
        az = rng.uniform(0, 2 * math.pi)
        p = top + Vector((math.cos(az) * 0.22, math.sin(az) * 0.22, -0.25 - rng.uniform(0, 0.2)))
        me = bpy.data.meshes.new("nut")
        bm = bmesh.new(); bmesh.ops.create_uvsphere(bm, u_segments=12, v_segments=8, radius=0.11)
        bm.to_mesh(me); bm.free()
        for pp in me.polygons:
            pp.use_smooth = True
        ob = bpy.data.objects.new(name + "_nut", me); ob.location = p; c.objects.link(ob)
        me.materials.append(nm)
    return tr, fr


# ---------------------------------------------------------------------------
# buildings (Karachi mid-rise apartment block)
# ---------------------------------------------------------------------------
BUILDING_PAINTS = [(0.86, 0.82, 0.72), (0.84, 0.74, 0.58), (0.74, 0.80, 0.74), (0.86, 0.70, 0.62),
                   (0.80, 0.80, 0.78), (0.70, 0.74, 0.80), (0.90, 0.86, 0.60)]
SIGN_COLS = [(0.80, 0.12, 0.10), (0.10, 0.35, 0.70), (0.95, 0.75, 0.10), (0.10, 0.55, 0.25), (0.95, 0.95, 0.92)]


def make_building(name, c, x0, y0, w, d, floors, seed, facing=-1, haze=None):
    """facing=-1 : facade faces -Y.  x0,y0 = facade-left corner at ground."""
    rng = random.Random(seed)
    fh = 3.0
    H = floors * fh + 0.9
    paint = mat_paint(f"{name}_paint", rng.choice(BUILDING_PAINTS))
    dark = bpy.data.materials.get("Window_Dark") or mat_glass_dark()
    grill = bpy.data.materials.get("Grill") or mat_simple("Grill", (0.12, 0.12, 0.12), 0.6, 0.5)
    tankm = bpy.data.materials.get("Tank_Black") or mat_simple("Tank_Black", (0.05, 0.05, 0.05), 0.45)
    tankb = bpy.data.materials.get("Tank_Blue") or mat_simple("Tank_Blue", (0.10, 0.25, 0.55), 0.45)
    shutter = bpy.data.materials.get("Shop_Shutter") or mat_shutter()
    acm = bpy.data.materials.get("AC_Unit") or mat_simple("AC_Unit", (0.85, 0.85, 0.82), 0.5)
    mats = [paint, dark, grill, tankm, tankb, shutter, acm]
    if haze:
        for m_ in mats:
            if not m_.get("hazed"):
                add_haze(m_, *haze); m_["hazed"] = True
    fy = y0                      # facade plane
    sgn = facing
    objs = []
    objs.append(box_obj(name + "_mass", c, (x0 + w / 2, y0 - sgn * d / 2, H / 2), (w, d, H), paint))
    # floor bands and windows / balconies
    bays = max(2, int(w / 3.2))
    bw = w / bays
    for f in range(floors):
        z = f * fh
        objs.append(box_obj(f"{name}_band{f}", c, (x0 + w / 2, fy + sgn * 0.08, z + fh - 0.1), (w + 0.1, 0.25, 0.22), paint))
        for b in range(bays):
            cx = x0 + bw * (b + 0.5)
            if f == 0:
                # shops with shutters + signboards
                objs.append(box_obj(f"{name}_sh{b}", c, (cx, fy + sgn * 0.02, 1.35), (bw * 0.8, 0.05, 2.5), shutter))
                sc_ = rng.choice(SIGN_COLS)
                sm = bpy.data.materials.get(f"Sign_{sc_}") or mat_simple(f"Sign_{sc_}", sc_, 0.5)
                if haze and not sm.get("hazed"):
                    add_haze(sm, *haze); sm["hazed"] = True
                objs.append(box_obj(f"{name}_sg{b}", c, (cx, fy + sgn * 0.12, 2.85), (bw * 0.9, 0.08, 0.55), sm))
                continue
            balcony = rng.random() < 0.45
            if balcony:
                objs.append(box_obj(f"{name}_bs{f}_{b}", c, (cx, fy + sgn * 0.6, z + 0.1), (bw * 0.86, 1.2, 0.15), paint))
                objs.append(box_obj(f"{name}_bp{f}_{b}", c, (cx, fy + sgn * 1.17, z + 0.65), (bw * 0.86, 0.08, 1.0), paint))
                objs.append(box_obj(f"{name}_bw{f}_{b}", c, (cx, fy + sgn * 0.01, z + 1.4), (bw * 0.6, 0.04, 2.0), dark))
            else:
                objs.append(box_obj(f"{name}_w{f}_{b}", c, (cx, fy + sgn * 0.02, z + 1.55), (bw * 0.5, 0.04, 1.3), dark))
                objs.append(box_obj(f"{name}_g{f}_{b}", c, (cx, fy + sgn * 0.08, z + 1.55), (bw * 0.54, 0.03, 1.36), grill))
                objs.append(box_obj(f"{name}_sun{f}_{b}", c, (cx, fy + sgn * 0.25, z + 2.3), (bw * 0.7, 0.5, 0.08), paint))
                if rng.random() < 0.4:
                    objs.append(box_obj(f"{name}_ac{f}_{b}", c, (cx + bw * 0.35, fy + sgn * 0.3, z + 0.9), (0.8, 0.5, 0.55), acm))
    # parapet + rooftop water tanks (very Karachi)
    objs.append(box_obj(name + "_par", c, (x0 + w / 2, y0 - sgn * d / 2, H + 0.5), (w, d, 1.0), paint))
    for i in range(rng.randint(2, 5)):
        tx = x0 + rng.uniform(1, w - 1)
        ty = y0 - sgn * rng.uniform(1.5, d - 1)
        r_ = rng.uniform(0.55, 0.8)
        objs.append(cyl_obj(f"{name}_tank{i}", c, (tx, ty, H + 1.0), (tx, ty, H + 1.0 + r_ * 2.2), r_,
                            tankm if rng.random() < 0.7 else tankb, 20))
    return objs


def make_electric_pole(name, c, p, h=9.0, mat=None):
    mat = mat or bpy.data.materials.get("Pole_Concrete") or mat_simple("Pole_Concrete", (0.55, 0.53, 0.50), 0.85)
    o = [cyl_obj(name, c, p, (p[0], p[1], p[2] + h), 0.11, mat, 10)]
    o.append(box_obj(name + "_arm", c, (p[0], p[1], p[2] + h - 0.6), (1.6, 0.1, 0.1), mat))
    return o


def make_wire(name, c, a, b, sag=0.6, r=0.008, mat=None):
    mat = mat or bpy.data.materials.get("Wire") or mat_simple("Wire", (0.02, 0.02, 0.02), 0.5)
    cu = bpy.data.curves.new(name, 'CURVE'); cu.dimensions = '3D'; cu.bevel_depth = r; cu.bevel_resolution = 1
    sp = cu.splines.new('POLY'); n = 24; sp.points.add(n)
    a, b = Vector(a), Vector(b)
    for i in range(n + 1):
        t = i / n
        p = a.lerp(b, t) - Vector((0, 0, sag * 4 * t * (1 - t)))
        sp.points[i].co = (p.x, p.y, p.z, 1)
    ob = bpy.data.objects.new(name, cu); c.objects.link(ob)
    cu.materials.append(mat)
    return ob


def make_street_lamp(name, c, p, h=7.5, facing=1):
    m = bpy.data.materials.get("Lamp_Grey") or mat_simple("Lamp_Grey", (0.35, 0.36, 0.37), 0.4, 0.6)
    cyl_obj(name, c, p, (p[0], p[1], p[2] + h), 0.07, m, 12)
    cyl_obj(name + "_arm", c, (p[0], p[1], p[2] + h - 0.05), (p[0], p[1] + facing * 1.4, p[2] + h + 0.25), 0.04, m, 8)
    box_obj(name + "_head", c, (p[0], p[1] + facing * 1.55, p[2] + h + 0.22), (0.25, 0.6, 0.12), m)


def scatter_leaves(name, c, area, n, seed, mat, z=0.003, size=0.05):
    rng = random.Random(seed)
    verts, faces = [], []
    (x0, y0, x1, y1) = area
    for i in range(n):
        x, y = rng.uniform(x0, x1), rng.uniform(y0, y1)
        a = rng.uniform(0, math.pi)
        l = size * rng.uniform(0.6, 1.3); w = l * 0.28
        dx, dy = math.cos(a), math.sin(a)
        zz = z + rng.uniform(0, 0.004)
        k = len(verts)
        verts += [(x - dx * l / 2, y - dy * l / 2, zz), (x - dy * w / 2, y + dx * w / 2, zz + 0.003),
                  (x + dx * l / 2, y + dy * l / 2, zz), (x + dy * w / 2, y - dx * w / 2, zz + 0.002)]
        faces.append((k, k + 1, k + 2, k + 3))
    return mesh_obj(name, verts, faces, c, mat)


def grass_patch(name, c, center, size, count=40000, length=0.07, mat=None, ground_mat=None, seed=0, children=6):
    bpy.ops.mesh.primitive_plane_add(size=1, location=center)
    ob = bpy.context.active_object
    ob.name = name
    ob.scale = (size[0], size[1], 1)
    bpy.ops.object.transform_apply(scale=True)
    for cc in ob.users_collection:
        cc.objects.unlink(ob)
    c.objects.link(ob)
    # subdivide so the particle distribution is even
    ob.data.materials.append(ground_mat)
    ob.data.materials.append(mat)
    ps = ob.modifiers.new("grass", 'PARTICLE_SYSTEM').particle_system
    st = ps.settings
    st.type = 'HAIR'
    st.count = count
    st.use_advanced_hair = True
    st.material = 2
    st.render_type = 'PATH'
    st.child_type = 'INTERPOLATED'
    st.child_percent = children
    st.rendered_child_count = children
    st.child_length = 1.0
    st.child_length_threshold = 0.4
    st.clump_factor = 0.0
    st.roughness_2 = 0.03
    st.roughness_endpoint = 0.02
    st.roughness_1 = 0.01
    st.child_parting_factor = 0.0
    st.child_radius = 0.03
    st.root_radius = 1.0
    st.tip_radius = 0.0
    st.radius_scale = 0.003
    st.use_close_tip = True
    st.normal_factor = 1.0
    st.factor_random = length * 0.35
    st.brownian_factor = length * 0.1
    st.length_random = 0.5
    st.use_rotations = True
    st.rotation_factor_random = 0.2
    ps.seed = seed
    st.hair_length = length          # must be set last (other props reset it)
    st.hair_step = 4
    st.display_step = 2
    st.render_step = 3
    return ob
