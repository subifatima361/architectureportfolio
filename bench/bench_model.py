"""Parametric model of the Bauhaus-inspired canopy bench for Burns Garden, Karachi.

All design dimensions are in inches (IN) and converted to Blender metres so that
cameras, sun and depth-of-field behave physically.

Coordinate system:  X = bench length (left/right), Y = depth (front is -Y),
Z = up.  Ground is Z = 0.
"""
import math
import bpy
import bmesh
from mathutils import Vector, Matrix

IN = 0.0254

# --------------------------------------------------------------------------
# Anthropometric / design parameters (inches)
# --------------------------------------------------------------------------
P = dict(
    length=72.0,          # seat & back length: 3 seated adults @ 24"
    seat_h=17.0,          # seat height at front edge (popliteal height)
    seat_d=18.0,          # seat depth (buttock-popliteal, 5th pct female)
    seat_tilt=5.0,        # seat rakes back (deg)
    slab_t=1.5,           # recycled-plastic panel thickness
    back_h=18.0,          # back panel length along its slope
    back_rake=15.0,       # back leans back from vertical (deg)
    arm_h=26.0,           # armrest tube centre height (9" above seat)
    tube_r=0.75,          # 1-1/2" OD recycled steel tube
    plate_t=0.25,         # base / foot plates
    frame_x=37.0,         # end-frame centre-line X
    post_y=19.0,          # canopy post centre-line Y
    canopy_top=91.0,      # canopy crown height (7'-7")
    canopy_len=80.0,
    canopy_y0=-16.0, canopy_y1=20.0,
    canopy_rise=4.0,      # sagitta of the barrel curve
    canopy_t=0.75,
    rib_d=2.0, rib_t=0.375,
)

STEEL_PARTS = []      # filled at build time, useful for material assignment


# --------------------------------------------------------------------------
# helpers
# --------------------------------------------------------------------------
def v2(a, b):
    return Vector((a, b))


def fillet_path(pts, radii, seg=14):
    """Polyline (y,z) with rounded corners. radii[i] used at interior pts[i]."""
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p0, p1, p2 = Vector(pts[i - 1]), Vector(pts[i]), Vector(pts[i + 1])
        r = radii[i]
        d1 = (p1 - p0).normalized()
        d2 = (p2 - p1).normalized()
        cosang = max(-1.0, min(1.0, d1.dot(d2)))
        theta = math.acos(cosang)
        if r <= 0 or theta < 1e-4:
            out.append(tuple(p1))
            continue
        t = r * math.tan(theta / 2)
        s = p1 - d1 * t
        e = p1 + d2 * t
        sign = 1.0 if (d1.x * d2.y - d1.y * d2.x) > 0 else -1.0
        n1 = Vector((-d1.y, d1.x)) * sign
        c = s + n1 * r
        a0 = math.atan2(s.y - c.y, s.x - c.x)
        for k in range(seg + 1):
            a = a0 + sign * theta * k / seg
            out.append((c.x + r * math.cos(a), c.y + r * math.sin(a)))
    out.append(pts[-1])
    return out


def link(obj, coll):
    coll.objects.link(obj)
    return obj


def tube_from_yz(name, x, yz, r, coll, caps=True):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r * IN
    cu.bevel_resolution = 8
    cu.use_fill_caps = caps
    sp = cu.splines.new('POLY')
    sp.points.add(len(yz) - 1)
    for i, (y, z) in enumerate(yz):
        sp.points[i].co = (x * IN, y * IN, z * IN, 1)
    sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu)
    return link(ob, coll)


def tube_from_pts(name, pts, r, coll, caps=True):
    cu = bpy.data.curves.new(name, 'CURVE')
    cu.dimensions = '3D'
    cu.bevel_depth = r * IN
    cu.bevel_resolution = 6
    cu.use_fill_caps = caps
    sp = cu.splines.new('POLY')
    sp.points.add(len(pts) - 1)
    for i, p in enumerate(pts):
        sp.points[i].co = (p[0] * IN, p[1] * IN, p[2] * IN, 1)
    sp.use_smooth = True
    ob = bpy.data.objects.new(name, cu)
    return link(ob, coll)


def prism_yz(name, profile, x0, x1, coll, bevel=0.0, smooth=False, band=False):
    """Extrude a closed (y,z) profile between x0..x1 (inches).
    band=True: profile is outer arc + reversed inner arc of equal length; caps are
    built as quad strips (robust for thin curved bands)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    a = [bm.verts.new((x0 * IN, y * IN, z * IN)) for y, z in profile]
    b = [bm.verts.new((x1 * IN, y * IN, z * IN)) for y, z in profile]
    n = len(profile)
    if band:
        h = n // 2
        for cap in (a, b):
            for i in range(h - 1):
                bm.faces.new((cap[i], cap[i + 1], cap[n - 2 - i], cap[n - 1 - i]))
    else:
        bm.faces.new(list(reversed(a)))
        bm.faces.new(b)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    if smooth:
        for poly in me.polygons:
            poly.use_smooth = True
    if bevel > 0:
        m = ob.modifiers.new('bevel', 'BEVEL')
        m.width = bevel * IN
        m.segments = 3
        m.limit_method = 'ANGLE'
        m.angle_limit = math.radians(50)
        m.harden_normals = False
    return ob


def prism_xy(name, profile, z0, z1, coll, bevel=0.0):
    """Extrude a closed (x,y) profile between z0..z1 (inches)."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    a = [bm.verts.new((x * IN, y * IN, z0 * IN)) for x, y in profile]
    b = [bm.verts.new((x * IN, y * IN, z1 * IN)) for x, y in profile]
    n = len(profile)
    bm.faces.new(list(reversed(a)))
    bm.faces.new(b)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((a[i], a[j], b[j], b[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(me)
    bm.free()
    ob = bpy.data.objects.new(name, me)
    link(ob, coll)
    if bevel > 0:
        m = ob.modifiers.new('bevel', 'BEVEL')
        m.width = bevel * IN
        m.segments = 2
        m.limit_method = 'ANGLE'
    return ob


def box(name, cx, cy, cz, sx, sy, sz, coll, bevel=0.0, rot_x=0.0):
    hx, hy, hz = sx / 2, sy / 2, sz / 2
    prof = [(-hy, -hz), (hy, -hz), (hy, hz), (-hy, hz)]
    ob = prism_yz(name, prof, -hx, hx, coll, bevel=bevel)
    ob.rotation_euler = (math.radians(rot_x), 0, 0)
    ob.location = (cx * IN, cy * IN, cz * IN)
    return ob


def cyl(name, p, axis, r, h, coll, verts=24):
    """Cylinder centred at p (inches), axis vector, radius r, length h."""
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=verts,
                          radius1=r * IN, radius2=r * IN, depth=h * IN)
    bm.to_mesh(me)
    bm.free()
    for poly in me.polygons:
        poly.use_smooth = len(poly.vertices) == 4
    ob = bpy.data.objects.new(name, me)
    q = Vector((0, 0, 1)).rotation_difference(Vector(axis).normalized())
    ob.rotation_mode = 'QUATERNION'
    ob.rotation_quaternion = q
    ob.location = Vector(p) * IN
    link(ob, coll)
    return ob


def hexnut(name, p, axis, s, h, coll):
    """Hex head / nut: s = across flats (in)."""
    return cyl(name, p, axis, s / math.sqrt(3), h, coll, verts=6)


def intersect(p, d, q, e):
    """Intersect 2D lines p+t d and q+s e."""
    den = d.x * e.y - d.y * e.x
    t = ((q.x - p.x) * e.y - (q.y - p.y) * e.x) / den
    return p + d * t


# --------------------------------------------------------------------------
# Geometry derivations (shared by drawings)
# --------------------------------------------------------------------------
def derived():
    t = math.radians(P['seat_tilt'])
    sd = v2(math.cos(t), -math.sin(t))          # seat top direction (front->back)
    sn = v2(-math.sin(t), -math.cos(t))         # downward normal of seat
    F = v2(-P['seat_d'] / 2, P['seat_h'])       # seat front-top edge
    B = F + sd * P['seat_d']                    # seat back-top edge
    seat = [F, B, B + sn * P['slab_t'], F + sn * P['slab_t']]

    r = math.radians(P['back_rake'])
    up = v2(math.sin(r), math.cos(r))           # along back panel, upward
    bn = v2(math.cos(r), -math.sin(r))          # rearward normal of back panel
    # rear face of back passes through the seat's back-top edge
    R0 = B
    Q0 = R0 - bn * P['slab_t']                  # a point on the front face line
    Qb = intersect(Q0, up, F, sd)               # front-bottom (on seat top)
    Qt = Qb + up * P['back_h']                  # front-top
    Rt = Qt + bn * P['slab_t']                  # rear-top
    Rb = intersect(Rt, -up, F, sd)              # rear-bottom (on seat top)
    back = [Qb, Rb, Rt, Qt]

    # canopy barrel
    c = (P['canopy_y1'] - P['canopy_y0']) / 2
    s = P['canopy_rise']
    R = (c * c + s * s) / (2 * s)
    cy = (P['canopy_y0'] + P['canopy_y1']) / 2
    cz = P['canopy_top'] - R
    return dict(seat=seat, back=back, sd=sd, sn=sn, F=F, B=B, up=up, bn=bn,
                canopy_R=R, canopy_c=(cy, cz), canopy_half=math.asin(c / R))


def seat_underside_z(y):
    d = derived()
    t = math.radians(P['seat_tilt'])
    ztop = P['seat_h'] - (y - d['F'].x) * math.tan(t)
    return ztop - P['slab_t'] / math.cos(t)


def back_rear_y(z):
    d = derived()
    Rb, Rt = d['back'][1], d['back'][2]
    k = (z - Rb.y) / (Rt.y - Rb.y)
    return Rb.x + (Rt.x - Rb.x) * k


# --------------------------------------------------------------------------
# Build
# --------------------------------------------------------------------------
def frame_path():
    """End-frame + canopy post: ONE continuous bent tube per side."""
    r = P['tube_r']
    z0 = P['plate_t'] + r                     # tube sits on foot plates
    d = derived()
    cy, cz = d['canopy_c']
    rib_bottom_R = d['canopy_R'] - P['canopy_t'] - P['rib_d']
    # horizontal top arm sits tangent to rib bottom at y = 10
    zr = cz + math.sqrt(rib_bottom_R ** 2 - (10 - cy) ** 2)
    ztop = zr - r
    pts = [(-16.0, z0),
           (-7.5, z0),
           (-7.5, P['arm_h']),
           (1.5, P['arm_h']),
           (12.5, z0),
           (P['post_y'], z0),
           (P['post_y'], ztop),
           (3.0, ztop)]
    radii = [0, 3.0, 3.5, 3.5, 5.0, 3.0, 6.0, 0]
    return fillet_path(pts, radii, seg=16), pts, ztop


def build(coll_name="Bench"):
    if coll_name in bpy.data.collections:
        coll = bpy.data.collections[coll_name]
    else:
        coll = bpy.data.collections.new(coll_name)
        bpy.context.scene.collection.children.link(coll)

    parts = {}   # name -> (object, group)  group used for explode / material
    def add(ob, group):
        parts[ob.name] = (ob, group)
        return ob

    d = derived()
    L2 = P['length'] / 2
    X = P['frame_x']
    r = P['tube_r']

    # ---- panels (terrazzo-effect recycled plastic) ------------------------
    add(prism_yz("Seat_Panel", [tuple(p) for p in d['seat']], -L2, L2, coll, bevel=0.2), 'seat')
    add(prism_yz("Back_Panel", [tuple(p) for p in d['back']], -L2, L2, coll, bevel=0.2), 'back')

    # canopy panel (barrel vault)
    cy, cz = d['canopy_c']
    R = d['canopy_R']
    h = d['canopy_half']
    n = 48
    outer = [(cy + R * math.sin(-h + 2 * h * i / n), cz + R * math.cos(-h + 2 * h * i / n)) for i in range(n + 1)]
    Ri = R - P['canopy_t']
    inner = [(cy + Ri * math.sin(-h + 2 * h * i / n), cz + Ri * math.cos(-h + 2 * h * i / n)) for i in range(n + 1)]
    # keep edge cut radial
    can = prism_yz("Canopy_Panel", outer + list(reversed(inner)), -P['canopy_len'] / 2, P['canopy_len'] / 2,
                   coll, bevel=0.2, smooth=True, band=True)
    add(can, 'canopy')

    # ---- steel ------------------------------------------------------------
    path, ctrl, ztop = frame_path()
    for side, sx in (("L", -1), ("R", 1)):
        add(tube_from_yz(f"Frame_{side}", sx * X, path, r, coll), 'frame')

        # canopy rib: curved flat bar under the panel
        Rb = Ri - P['rib_d']
        hh = h - math.radians(1.2)
        ro = [(cy + Ri * math.sin(-hh + 2 * hh * i / n), cz + Ri * math.cos(-hh + 2 * hh * i / n)) for i in range(n + 1)]
        rb = [(cy + Rb * math.sin(-hh + 2 * hh * i / n), cz + Rb * math.cos(-hh + 2 * hh * i / n)) for i in range(n + 1)]
        add(prism_yz(f"Canopy_Rib_{side}", ro + list(reversed(rb)), sx * X - P['rib_t'] / 2, sx * X + P['rib_t'] / 2,
                     coll, smooth=False, band=True), 'rib')

        # cleat plates tying the post top arm to the rib (both faces)
        for k, off in enumerate((-1, 1)):
            xc = sx * X + off * (P['rib_t'] / 2 + 0.125)
            y0, y1 = 4.0, 15.0
            prof = []
            for i in range(9):
                y = y0 + (y1 - y0) * i / 8
                prof.append((y, cz + math.sqrt(Rb ** 2 - (y - cy) ** 2) + 1.0))
            prof = [(y1, ztop - 0.2), (y0, ztop - 0.2)] + prof
            add(prism_yz(f"Rib_Cleat_{side}{k}", prof, xc - 0.125, xc + 0.125, coll), 'rib')
        # bolts through cleats + rib
        for y in (6.5, 12.5):
            zz = cz + math.sqrt(Rb ** 2 - (y - cy) ** 2) + 0.4
            add(cyl(f"Rib_Bolt_{side}_{y}", (sx * X, y, zz), (1, 0, 0), 0.19, 1.6, coll, 12), 'rib')
            for off in (-1, 1):
                add(hexnut(f"Rib_Nut_{side}_{y}_{off}", (sx * X + off * 0.68, y, zz), (1, 0, 0), 0.56, 0.3, coll), 'rib')

        # foot plates + anchor bolts (front runner and rear corner)
        for tag, yc in (("F", -12.0), ("R", 15.5)):
            add(box(f"Foot_Plate_{side}{tag}", sx * X, yc, P['plate_t'] / 2, 4.0, 6.0, P['plate_t'], coll, bevel=0.04), 'foot')
            for yo in (-2.0, 2.0):
                for xo in (-1.3, 1.3):
                    p = (sx * X + xo, yc + yo, P['plate_t'] + 0.15)
                    add(hexnut(f"Anchor_Nut_{side}{tag}{yo}{xo}", p, (0, 0, 1), 0.56, 0.3, coll), 'foot')
                    add(cyl(f"Anchor_Rod_{side}{tag}{yo}{xo}", (p[0], p[1], p[2] - 2.2), (0, 0, 1), 0.19, 5.2, coll, 12), 'anchor')

    # seat stringers (2" x 1" RHS) between frames, welded end plates bolt to frame cleats
    tilt = P['seat_tilt']
    t = math.radians(tilt)
    path_ctrl = ctrl
    for tag, y in (("Front", -7.5), ("Rear", 6.9)):
        zc = seat_underside_z(y) - 0.5 * math.cos(t)
        inner_x = X - r - 0.25 - 0.25
        add(box(f"Seat_Stringer_{tag}", 0, y, zc, 2 * inner_x, 2.0, 1.0, coll, bevel=0.06, rot_x=-tilt), 'stringer')
        for sx in (-1, 1):
            # end plate on stringer
            add(box(f"Stringer_Endplate_{tag}{sx}", sx * (inner_x + 0.125), y, zc, 0.25, 3.0, 2.0, coll, rot_x=-tilt), 'stringer')
            # cleat welded to frame
            add(box(f"Frame_Cleat_{tag}{sx}", sx * (inner_x + 0.375), y, zc, 0.25, 3.0, 2.0, coll, rot_x=-tilt), 'frame')
            for yo in (-0.9, 0.9):
                add(cyl(f"Stringer_Bolt_{tag}{sx}{yo}", (sx * (inner_x + 0.25), y + yo, zc), (1, 0, 0), 0.16, 1.2, coll, 12), 'stringer')
        # seat screws into threaded inserts (hidden, show in exploded view)
        for xs in (-30, -15, 0, 15, 30):
            add(cyl(f"Seat_Insert_{tag}{xs}", (xs, y, seat_underside_z(y) + 0.45), (0, -math.sin(t), math.cos(t)), 0.22, 0.9, coll, 12), 'insert_seat')

    # back rail (1-1/2" square tube) between posts + stand-off brackets
    zr = 30.0
    add(box("Back_Rail", 0, P['post_y'], zr, 2 * (X - r), 1.5, 1.5, coll, bevel=0.06), 'backrail')
    yb = back_rear_y(zr)
    for xs in (-24, 0, 24):
        # bent plate bracket from rail to back panel rear face
        prof = [(yb, zr - 2.0), (P['post_y'] - 0.75, zr - 2.0), (P['post_y'] - 0.75, zr + 2.0), (yb + (back_rear_y(zr + 2) - yb), zr + 2.0)]
        add(prism_yz(f"Back_Bracket_{xs}", prof, xs - 1.5, xs + 1.5, coll, bevel=0.04), 'backrail')
        add(cyl(f"Back_Insert_{xs}", (xs, yb - 0.45 * math.cos(math.radians(P['back_rake'])), zr), (0, 1, 0), 0.22, 0.9, coll, 12), 'insert_back')

    # seat/back corner angles (2x2x1/4 L, 4" long) under the joint
    sb = d['back'][1]
    for xs in (-24, 0, 24):
        yy, zz = sb.x, sb.y
        zu = seat_underside_z(yy - 0.3)
        prof = [(yy - 2.0, zu), (yy + 0.25, zu), (yy + 0.25, zu - 0.25), (yy - 2.0, zu - 0.25)]
        add(prism_yz(f"Corner_Angle_H_{xs}", prof, xs - 2, xs + 2, coll), 'angle')
        prof2 = [(yy, zu - 0.25), (yy + 0.25, zu - 0.25), (yy + 0.25 + 2.0 * math.sin(math.radians(15)), zu + 2.0), (yy + 2.0 * math.sin(math.radians(15)), zu + 2.0)]
        add(prism_yz(f"Corner_Angle_V_{xs}", prof2, xs - 2, xs + 2, coll), 'angle')

    # canopy purlins (1" round) connecting ribs
    for y in (-6.0, 10.0):
        zz = cz + math.sqrt((Ri - 0.5) ** 2 - (y - cy) ** 2)
        add(cyl(f"Canopy_Purlin_{y}", (0, y, zz), (1, 0, 0), 0.5, 2 * X - P['rib_t'], coll, 20), 'rib')
    # countersunk canopy screws (visible on top as flush heads)
    for sx in (-1, 1):
        for a in (-0.8, -0.4, 0.0, 0.4, 0.8):
            ang = h * a
            p = (sx * X, cy + (R + 0.001) * math.sin(ang), cz + (R - 0.02) * math.cos(ang))
            add(cyl(f"Canopy_Screw_{sx}_{a}", p, (0, math.sin(ang), math.cos(ang)), 0.25, 0.06, coll, 16), 'screw')

    return coll, parts


# --------------------------------------------------------------------------
# Materials
# --------------------------------------------------------------------------
TERRAZZO_CHIPS = [
    (0.16, 0.17, 0.42),   # indigo
    (0.40, 0.17, 0.36),   # plum
    (0.18, 0.47, 0.30),   # green
    (0.13, 0.50, 0.52),   # teal
    (0.46, 0.15, 0.20),   # maroon
    (0.45, 0.62, 0.78),   # sky blue
    (0.80, 0.62, 0.22),   # mustard (sparse)
    (0.10, 0.10, 0.12),   # charcoal
]


def _sk(coll, ident):
    return next(x for x in coll if x.identifier == ident)


def _lin(c):
    return tuple(((x + 0.055) / 1.055) ** 2.4 if x > 0.04045 else x / 12.92 for x in c)


def mat_terrazzo(name="Terrazzo_RecycledPlastic", scale=1.0):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    N = nt.nodes
    Lk = nt.links
    for nd in list(N):
        N.remove(nd)
    out = N.new('ShaderNodeOutputMaterial')
    bsdf = N.new('ShaderNodeBsdfPrincipled')
    Lk.new(bsdf.outputs[0], out.inputs[0])

    tc = N.new('ShaderNodeTexCoord')
    # slight warp so chips are irregular flakes, not discs
    warp = N.new('ShaderNodeTexNoise'); warp.inputs['Scale'].default_value = 60 * scale
    Lk.new(tc.outputs['Object'], warp.inputs['Vector'])
    mixv = N.new('ShaderNodeMix'); mixv.data_type = 'VECTOR'; _sk(mixv.inputs, 'Factor_Float').default_value = 0.012
    Lk.new(tc.outputs['Object'], _sk(mixv.inputs, 'A_Vector'))
    Lk.new(warp.outputs['Color'], _sk(mixv.inputs, 'B_Vector'))
    co = _sk(mixv.outputs, 'Result_Vector')

    base = N.new('ShaderNodeTexNoise'); base.inputs['Scale'].default_value = 25
    Lk.new(tc.outputs['Object'], base.inputs['Vector'])
    br = N.new('ShaderNodeValToRGB')
    br.color_ramp.elements[0].color = _lin((0.90, 0.88, 0.83)) + (1,)
    br.color_ramp.elements[1].color = _lin((0.96, 0.95, 0.91)) + (1,)
    Lk.new(base.outputs['Fac'], br.inputs[0])
    col = br.outputs[0]
    mask_total = None

    def chip_layer(col, sc, rmin, rmax, density):
        vor = N.new('ShaderNodeTexVoronoi'); vor.inputs['Scale'].default_value = sc * scale
        vor.inputs['Randomness'].default_value = 1.0
        Lk.new(co, vor.inputs['Vector'])
        sep = N.new('ShaderNodeSeparateColor')
        Lk.new(vor.outputs['Color'], sep.inputs[0])
        # radius in cell units
        rad = N.new('ShaderNodeMapRange')
        rad.inputs['To Min'].default_value = rmin
        rad.inputs['To Max'].default_value = rmax
        Lk.new(sep.outputs[1], rad.inputs['Value'])
        lt = N.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'
        Lk.new(vor.outputs['Distance'], lt.inputs[0])
        Lk.new(rad.outputs[0], lt.inputs[1])
        dens = N.new('ShaderNodeMath'); dens.operation = 'LESS_THAN'
        Lk.new(sep.outputs[2], dens.inputs[0]); dens.inputs[1].default_value = density
        mk = N.new('ShaderNodeMath'); mk.operation = 'MULTIPLY'
        Lk.new(lt.outputs[0], mk.inputs[0]); Lk.new(dens.outputs[0], mk.inputs[1])
        ramp = N.new('ShaderNodeValToRGB')
        ramp.color_ramp.interpolation = 'CONSTANT'
        els = ramp.color_ramp.elements
        weights = [0.20, 0.16, 0.16, 0.14, 0.14, 0.10, 0.04, 0.06]
        acc = 0.0
        els[0].position = 0.0; els[0].color = _lin(TERRAZZO_CHIPS[0]) + (1,)
        els[1].position = weights[0]; els[1].color = _lin(TERRAZZO_CHIPS[1]) + (1,)
        acc = weights[0]
        for i in range(2, len(TERRAZZO_CHIPS)):
            acc += weights[i - 1]
            e = els.new(acc)
            e.color = _lin(TERRAZZO_CHIPS[i]) + (1,)
        Lk.new(sep.outputs[0], ramp.inputs[0])
        mix = N.new('ShaderNodeMix'); mix.data_type = 'RGBA'
        Lk.new(mk.outputs[0], _sk(mix.inputs, 'Factor_Float'))
        Lk.new(col, _sk(mix.inputs, 'A_Color'))
        Lk.new(ramp.outputs[0], _sk(mix.inputs, 'B_Color'))
        return _sk(mix.outputs, 'Result_Color'), mk.outputs[0]

    col, m1 = chip_layer(col, 16, 0.10, 0.27, 0.62)   # big flakes ~10-25 mm
    col, m2 = chip_layer(col, 42, 0.08, 0.22, 0.50)   # small specks
    col, m3 = chip_layer(col, 120, 0.10, 0.25, 0.35)  # fine dust specks
    mt = N.new('ShaderNodeMath'); mt.operation = 'MAXIMUM'
    Lk.new(m1, mt.inputs[0]); Lk.new(m2, mt.inputs[1])
    Lk.new(col, bsdf.inputs['Base Color'])
    rr = N.new('ShaderNodeMapRange')
    rr.inputs['To Min'].default_value = 0.42; rr.inputs['To Max'].default_value = 0.30
    Lk.new(mt.outputs[0], rr.inputs['Value'])
    Lk.new(rr.outputs[0], bsdf.inputs['Roughness'])
    bsdf.inputs['Specular IOR Level'].default_value = 0.45
    # micro surface (moulded plastic)
    bn = N.new('ShaderNodeTexNoise'); bn.inputs['Scale'].default_value = 900; bn.inputs['Detail'].default_value = 4
    Lk.new(tc.outputs['Object'], bn.inputs['Vector'])
    bump = N.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.06; bump.inputs['Distance'].default_value = 0.0005
    Lk.new(bn.outputs['Fac'], bump.inputs['Height'])
    Lk.new(bump.outputs[0], bsdf.inputs['Normal'])
    return m


def mat_steel(name="Recycled_Steel_Powdercoat"):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    b = nt.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = _lin((0.075, 0.08, 0.085)) + (1,)
    b.inputs['Metallic'].default_value = 0.15
    b.inputs['Roughness'].default_value = 0.38
    b.inputs['Coat Weight'].default_value = 0.35
    b.inputs['Coat Roughness'].default_value = 0.25
    tc = nt.nodes.new('ShaderNodeTexCoord')
    nz = nt.nodes.new('ShaderNodeTexNoise'); nz.inputs['Scale'].default_value = 400; nz.inputs['Detail'].default_value = 6
    nt.links.new(tc.outputs['Object'], nz.inputs['Vector'])
    bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.08; bump.inputs['Distance'].default_value = 0.0003
    nt.links.new(nz.outputs['Fac'], bump.inputs['Height'])
    nt.links.new(bump.outputs[0], b.inputs['Normal'])
    return m


def mat_galv(name="Galvanised_Fixings"):
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes['Principled BSDF']
    b.inputs['Base Color'].default_value = (0.55, 0.56, 0.57, 1)
    b.inputs['Metallic'].default_value = 1.0
    b.inputs['Roughness'].default_value = 0.35
    return m


def assign_materials(parts):
    terr = mat_terrazzo()
    steel = mat_steel()
    galv = mat_galv()
    for name, (ob, g) in parts.items():
        if g in ('seat', 'back', 'canopy'):
            m = terr
        elif g in ('screw', 'anchor', 'insert_seat', 'insert_back') or 'Nut' in name or 'Bolt' in name:
            m = galv
        else:
            m = steel
        ob.data.materials.clear()
        ob.data.materials.append(m)
