"""Technical drawing sheets: elevations, plan, isometric (30 deg), plan-oblique
axonometric (45 deg) and exploded axonometric with joinery callouts.

Run:  python drawings.py   (needs the `bpy` module)
Output: ../output/drawings/*.png
"""
import math, os, sys, json
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *
from mathutils import Matrix, Vector
from PIL import Image, ImageDraw, ImageFont

OUT = os.path.join(ROOT, "output", "drawings")
W, H = 4961, 3508                       # A3 landscape @ 300 dpi
MARGIN = 110
TB_H = 300                              # title block strip height
FONT_DIR = "/usr/share/fonts/opentype/inter/"
F = lambda w, s: ImageFont.truetype(FONT_DIR + {"r": "Inter-Regular.otf", "m": "Inter-Medium.otf",
                                                 "b": "Inter-Bold.otf", "l": "Inter-Light.otf"}[w], s)
INK = (20, 20, 22)
GREY = (120, 120, 125)
ACCENT = (200, 45, 35)                  # Bauhaus red accent
FAST = "--fast" in sys.argv


# ---------------------------------------------------------------------------
# scene
# ---------------------------------------------------------------------------
def flat_mat(name, rgb, terrazzo=False):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    nt = m.node_tree
    for n in list(nt.nodes):
        nt.nodes.remove(n)
    out = nt.nodes.new('ShaderNodeOutputMaterial')
    em = nt.nodes.new('ShaderNodeEmission')
    em.inputs['Strength'].default_value = 1.0
    nt.links.new(em.outputs[0], out.inputs[0])
    if terrazzo:
        # pale ghost of the terrazzo chips: reads as material, not as noise
        src = BM.mat_terrazzo()
        # copy node tree by linking: reuse terrazzo colour via a group-less trick:
        # build a light chip pattern directly
        tc = nt.nodes.new('ShaderNodeTexCoord')
        vor = nt.nodes.new('ShaderNodeTexVoronoi'); vor.inputs['Scale'].default_value = 16
        nt.links.new(tc.outputs['Object'], vor.inputs['Vector'])
        sep = nt.nodes.new('ShaderNodeSeparateColor'); nt.links.new(vor.outputs['Color'], sep.inputs[0])
        lt = nt.nodes.new('ShaderNodeMath'); lt.operation = 'LESS_THAN'
        nt.links.new(vor.outputs['Distance'], lt.inputs[0]); lt.inputs[1].default_value = 0.16
        dn = nt.nodes.new('ShaderNodeMath'); dn.operation = 'LESS_THAN'
        nt.links.new(sep.outputs[2], dn.inputs[0]); dn.inputs[1].default_value = 0.6
        mk = nt.nodes.new('ShaderNodeMath'); mk.operation = 'MULTIPLY'
        nt.links.new(lt.outputs[0], mk.inputs[0]); nt.links.new(dn.outputs[0], mk.inputs[1])
        ramp = nt.nodes.new('ShaderNodeValToRGB')
        ramp.color_ramp.elements[0].color = (1, 1, 1, 1)
        ramp.color_ramp.elements[1].color = (0.62, 0.62, 0.64, 1)
        nt.links.new(mk.outputs[0], ramp.inputs[0])
        nt.links.new(ramp.outputs[0], em.inputs['Color'])
    else:
        em.inputs['Color'].default_value = rgb + (1,)
    return m


def build_scene():
    sc = reset()
    coll, parts = BM.build()
    for ob, g in parts.values():
        for md in list(ob.modifiers):
            ob.modifiers.remove(md)
        if ob.type == 'CURVE':
            ob.data.bevel_resolution = 12
    panel = flat_mat("dwg_panel", (1, 1, 1), terrazzo=True)
    steel = flat_mat("dwg_steel", (0.52, 0.53, 0.55))
    fix = flat_mat("dwg_fix", (0.78, 0.78, 0.8))
    for name, (ob, g) in parts.items():
        ob.data.materials.clear()
        if g in ('seat', 'back', 'canopy'):
            ob.data.materials.append(panel)
        elif g in ('screw', 'anchor', 'insert_seat', 'insert_back') or 'Nut' in name or 'Bolt' in name:
            ob.data.materials.append(fix)
        else:
            ob.data.materials.append(steel)
    w = bpy.data.worlds.new("white")
    sc.world = w
    w.use_nodes = True
    bg = w.node_tree.nodes['Background']
    bg.inputs[0].default_value = (1, 1, 1, 1)
    bg.inputs[1].default_value = 1.0
    sc.view_settings.view_transform = 'Standard'
    sc.view_settings.look = 'None'
    sc.render.film_transparent = False
    sc.cycles.samples = 4 if FAST else 16
    sc.cycles.use_denoising = False
    sc.cycles.use_adaptive_sampling = False
    sc.cycles.filter_width = 1.0
    sc.cycles.max_bounces = 0
    sc.render.resolution_x, sc.render.resolution_y = W, H
    sc.render.resolution_percentage = 25 if FAST else 100
    # freestyle
    sc.render.use_freestyle = True
    sc.render.line_thickness_mode = 'ABSOLUTE'
    vl = sc.view_layers[0]
    vl.use_freestyle = True
    fs = vl.freestyle_settings
    fs.crease_angle = math.radians(140)
    for ls in list(fs.linesets):
        fs.linesets.remove(ls)

    def lineset(name, thick, **sel):
        ls = fs.linesets.new(name)
        ls.select_by_visibility = True
        ls.visibility = 'VISIBLE'
        ls.select_by_edge_types = True
        for k in ('select_silhouette', 'select_border', 'select_crease', 'select_external_contour',
                  'select_contour', 'select_material_boundary'):
            setattr(ls, k, sel.get(k, False))
        st = ls.linestyle
        st.color = (0.06, 0.06, 0.07)
        st.thickness = thick * (0.25 if FAST else 1.0)
        st.caps = 'ROUND'
        st.chaining = 'PLAIN'
        return ls
    lineset("edges", 2.6, select_silhouette=True, select_border=True, select_crease=True, select_contour=True)
    lineset("outline", 5.5, select_external_contour=True)
    return sc, coll, parts


# ---------------------------------------------------------------------------
# projection helpers
# ---------------------------------------------------------------------------
class View:
    """Ortho camera + optional world pre-transform M (for plan-oblique)."""

    def __init__(self, sc, name, rot_deg, M=None):
        self.sc = sc
        self.M = M or Matrix.Identity(4)
        self.cam = camera(name, (0, 0, 0), rot=rot_deg, ortho=1.0)
        bpy.context.view_layer.update()
        self.cam.location = self.cam.matrix_world.to_3x3() @ Vector((0, 0, 30))
        sc.camera = self.cam
        bpy.context.view_layer.update()

    def to_cam(self, p_in):
        p = self.M @ (Vector(p_in) * IN)
        return self.cam.matrix_world.inverted() @ p

    def px(self, p_in):
        c = self.to_cam(p_in)
        S = self.cam.data.ortho_scale
        Wp = W
        return (W / 2 + c.x / S * Wp, H / 2 - c.y / S * Wp)

    def fit(self, objs, area):
        """area = (x0,y0,x1,y1) in sheet pixels."""
        pts = []
        for ob in objs:
            for c in ob.bound_box:
                pw = ob.matrix_world @ Vector(c)
                pts.append(self.cam.matrix_world.inverted() @ pw)
        xs = [p.x for p in pts]; ys = [p.y for p in pts]
        ex, ey = max(xs) - min(xs), max(ys) - min(ys)
        aw, ah = area[2] - area[0], area[3] - area[1]
        S = max(ex / aw, ey / ah) * W
        self.cam.data.ortho_scale = S
        cx, cy = (max(xs) + min(xs)) / 2, (max(ys) + min(ys)) / 2
        ax, ay = (area[0] + area[2]) / 2, (area[1] + area[3]) / 2
        dx = cx - (ax - W / 2) * S / W
        dy = cy - (H / 2 - ay) * S / W
        self.cam.location = self.cam.location + self.cam.matrix_world.to_3x3() @ Vector((dx, dy, 0))
        bpy.context.view_layer.update()
        return S / W / IN          # inches per pixel


def apply_M(parts, M):
    """Parent everything to an empty carrying the shear matrix."""
    bpy.context.view_layer.update()
    e = bpy.data.objects.new("ShearRoot", None)
    bpy.context.scene.collection.objects.link(e)
    e.matrix_world = M
    for ob, g in parts.values():
        mw = ob.matrix_world.copy()
        ob.parent = e
        ob.matrix_parent_inverse = Matrix.Identity(4)
        ob.matrix_basis = mw
    bpy.context.view_layer.update()
    return e


def plan_oblique_matrix(angle=45):
    rz = Matrix.Rotation(math.radians(angle), 4, 'Z')
    S = Matrix(((1, 0, 0, 0), (0, 1, 1, 0), (0, -1, 1, 0), (0, 0, 0, 1)))
    return S @ rz


def do_render(name):
    path = os.path.join(OUT, "_raw_" + name + ".png")
    render(path)
    im = Image.open(path).convert("RGB")
    if im.size != (W, H):
        im = im.resize((W, H), Image.LANCZOS)
    return im


# ---------------------------------------------------------------------------
# annotation helpers
# ---------------------------------------------------------------------------
def fmt_in(v):
    """Inches to nearest 1/8 with unicode fraction, plus feet-inches in brackets when >= 24"."""
    v = round(v * 8) / 8
    whole = int(v)
    frac = v - whole
    fr = {0: "", 0.125: "⅛", 0.25: "¼", 0.375: "⅜", 0.5: "½", 0.625: "⅝", 0.75: "¾", 0.875: "⅞"}[round(frac, 3)]
    s = (f"{whole}" if whole or not fr else "") + fr + '"'
    return s


class Sheet:
    def __init__(self, im):
        self.im = im
        self.d = ImageDraw.Draw(im)

    # -- primitives
    def line(self, a, b, w=3, fill=INK):
        self.d.line([tuple(a), tuple(b)], fill=fill, width=w)

    def dashed(self, a, b, dash=22, gap=14, w=3, fill=GREY):
        a, b = Vector(a), Vector(b)
        L = (b - a).length
        if L < 1:
            return
        u = (b - a) / L
        t = 0
        while t < L:
            self.line(a + u * t, a + u * min(t + dash, L), w, fill)
            t += dash + gap

    def text(self, p, s, font, fill=INK, anchor="mm", angle=0):
        if angle == 0:
            self.d.text(tuple(p), s, font=font, fill=fill, anchor=anchor)
            return
        bb = font.getbbox(s)
        tw, th = bb[2] - bb[0] + 20, bb[3] - bb[1] + 30
        tmp = Image.new("RGBA", (tw, th), (255, 255, 255, 0))
        ImageDraw.Draw(tmp).text((tw / 2, th / 2), s, font=font, fill=fill, anchor="mm")
        tmp = tmp.rotate(angle, expand=True, resample=Image.BICUBIC)
        self.im.paste(tmp, (int(p[0] - tmp.width / 2), int(p[1] - tmp.height / 2)), tmp)

    # -- dimension: a,b sheet points of the measured feature, n = unit offset dir in sheet
    def dim(self, a, b, off, label, n=None, font=None, ext_gap=14, ext_over=22):
        font = font or F("m", 46)
        a, b = Vector(a), Vector(b)
        u = (b - a).normalized()
        if n is None:
            n = Vector((u.y, -u.x))
        n = Vector(n).normalized()
        # bring both feature points to a common dimension line
        da = (a).dot(n); db = (b).dot(n)
        base = max(da, db) if off > 0 else min(da, db)
        A = a + n * (base - da + off)
        B = b + n * (base - db + off)
        s = math.copysign(1, off)
        self.line(a + n * s * ext_gap, A + n * s * ext_over, 2, INK)
        self.line(b + n * s * ext_gap, B + n * s * ext_over, 2, INK)
        self.line(A - u * 18, B + u * 18, 3, INK)
        # architectural ticks
        t = (u + n).normalized() * 16
        for P in (A, B):
            self.line(P - t, P + t, 6, INK)
        mid = (A + B) / 2
        ang = math.degrees(math.atan2(-(B - A).y, (B - A).x))
        if ang > 90.1 or ang < -89.9:
            ang += 180
        # text sits on the outer side of the dimension line
        tp = mid + n * s * 40
        self.text(tp, label, font, INK, angle=ang)

    def note(self, p, s, size=40, fill=INK, anchor="lm", weight="r"):
        self.d.text(tuple(p), s, font=F(weight, size), fill=fill, anchor=anchor)

    def angle_arc(self, c, r, a0, a1, label, lp):
        c = Vector(c)
        box = [c.x - r, c.y - r, c.x + r, c.y + r]
        self.d.arc(box, a0, a1, fill=INK, width=3)
        self.note(lp, label, 42, anchor="mm", weight="m")

    def frame(self, title, number, scale_text, desc=""):
        d = self.d
        d.rectangle([MARGIN, MARGIN, W - MARGIN, H - MARGIN], outline=INK, width=5)
        y0 = H - MARGIN - TB_H
        d.line([MARGIN, y0, W - MARGIN, y0], fill=INK, width=4)
        # Bauhaus mark: red square, black circle, yellow triangle
        x = MARGIN + 60
        d.rectangle([x, y0 + 75, x + 70, y0 + 145], fill=ACCENT)
        d.ellipse([x + 90, y0 + 75, x + 160, y0 + 145], fill=INK)
        d.polygon([(x + 180, y0 + 145), (x + 215, y0 + 75), (x + 250, y0 + 145)], fill=(235, 180, 30))
        d.text((x, y0 + 210), "URBAN CANOPY BENCH", font=F("b", 54), fill=INK, anchor="lm")
        d.text((x + 300, y0 + 110), "BURNS GARDEN · KARACHI", font=F("m", 44), fill=GREY, anchor="lm")
        # columns
        cols = [(1500, "DRAWING", title), (2900, "MATERIALS", "Terrazzo-effect recycled plastic · Recycled steel, powder-coated"),
                (3950, "SCALE / UNITS", scale_text)]
        for cx, k, v in cols:
            d.line([cx - 40, y0, cx - 40, H - MARGIN], fill=INK, width=2)
            d.text((cx, y0 + 70), k, font=F("m", 34), fill=GREY, anchor="lm")
            fnt = F("b", 64) if k == "DRAWING" else F("r", 40)
            if k == "MATERIALS":
                d.text((cx, y0 + 140), "Terrazzo-effect recycled plastic", font=fnt, fill=INK, anchor="lm")
                d.text((cx, y0 + 195), "Recycled steel, powder-coated", font=fnt, fill=INK, anchor="lm")
            else:
                d.text((cx, y0 + 150), v, font=fnt, fill=INK, anchor="lm")
            if k == "DRAWING" and desc:
                d.text((cx, y0 + 225), desc, font=F("r", 38), fill=GREY, anchor="lm")
        d.text((W - MARGIN - 60, y0 + 150), number, font=F("b", 110), fill=ACCENT, anchor="rm")

    def scale_bar(self, x, y, px_per_in, inches=48, step=12):
        d = self.d
        L = inches * px_per_in
        for i in range(0, inches, step):
            x0 = x + i * px_per_in
            fill = INK if (i // step) % 2 == 0 else (255, 255, 255)
            d.rectangle([x0, y, x0 + step * px_per_in, y + 22], fill=fill, outline=INK, width=2)
        for i in range(0, inches + 1, step):
            d.text((x + i * px_per_in, y + 55), f'{i}"', font=F("r", 34), fill=INK, anchor="mm")


def save(sheet, name):
    p = os.path.join(OUT, name + ".png")
    sheet.im.save(p, optimize=True)
    print("saved", p)


# ---------------------------------------------------------------------------
# geometry references (inches)
# ---------------------------------------------------------------------------
P = BM.P
D = BM.derived()
X = P['frame_x']; r = P['tube_r']
CY, CZ = D['canopy_c']; CR = D['canopy_R']
_, CTRL, ZTOP = BM.frame_path()
CAN_EDGE_Z = CZ + math.sqrt((CR - P['canopy_t']) ** 2 - (P['canopy_y0'] - CY) ** 2)
BACK_TOP = D['back'][3]                                       # front-top of back (y,z)
DRAW_AREA = (MARGIN + 420, MARGIN + 260, W - MARGIN - 420, H - MARGIN - TB_H - 300)


def all_objs(parts):
    return [o for o, g in parts.values()]


# ---------------------------------------------------------------------------
def sheet_front(sc, parts):
    v = View(sc, "cam_front", (90, 0, 0))
    ipp = v.fit(all_objs(parts), DRAW_AREA)
    s = Sheet(do_render("front"))
    p = lambda x, z, y=-30: v.px((x, y, z))
    g0, g1 = p(-60, 0), p(60, 0)
    s.line(g0, g1, 7)                                          # ground line
    for i in range(int(g0[0]), int(g1[0]), 34):                 # ground hatch
        s.line((i, g0[1] + 4), (i - 22, g0[1] + 30), 2, GREY)
    L2 = P['canopy_len'] / 2
    # horizontal dims (above)
    top = p(0, P['canopy_top'])[1]
    s.dim(p(-L2, P['canopy_top']), p(L2, P['canopy_top']), -110, fmt_in(P['canopy_len']) + "  CANOPY", n=(0, 1))
    s.dim(p(-X - r, 0), p(X + r, 0), 230, fmt_in(2 * (X + r)) + "  OVERALL FRAME", n=(0, 1))
    s.dim(p(-36, 0), p(36, 0), 120, fmt_in(P['length']) + "  SEAT (3 × 24\")", n=(0, 1))
    # vertical dims (right side)
    xr = p(L2, 0)[0]
    s.dim(p(X + r, 0), p(X + r, P['seat_h']), 170, fmt_in(P['seat_h']) + " SEAT", n=(1, 0))
    s.dim(p(X + r, 0), p(X + r, P['arm_h'] + r), 330, fmt_in(P['arm_h'] + r) + " ARM", n=(1, 0))
    s.dim(p(X + r, 0), p(X + r, BACK_TOP.y), 490, fmt_in(BACK_TOP.y) + " BACK", n=(1, 0))
    s.dim(p(L2, 0), p(L2, CAN_EDGE_Z), 650, fmt_in(CAN_EDGE_Z) + " CLEAR", n=(1, 0))
    s.dim(p(L2, 0), p(L2, P['canopy_top']), 810, fmt_in(P['canopy_top']) + " OVERALL", n=(1, 0))
    # left: tube & panel notes
    s.note((p(-L2, 0)[0] - 330, p(0, 60)[1]), "Ø1½\" recycled steel", 36, anchor="lm")
    s.note((p(-L2, 0)[0] - 330, p(0, 60)[1] + 48), "tube, continuous bend", 36, anchor="lm")
    s.line((p(-L2, 0)[0] - 330, p(0, 60)[1] + 80), p(-X, 55), 2)
    s.scale_bar(MARGIN + 120, H - MARGIN - TB_H - 160, 1 / ipp)
    s.frame("FRONT ELEVATION", "01", f'1 : {round(ipp * 300):d} @ A3 · INCHES', "Viewed from the path side (south)")
    save(s, "01_front_elevation")


def sheet_side(sc, parts):
    v = View(sc, "cam_side", (90, 0, -90))
    ipp = v.fit(all_objs(parts), DRAW_AREA)
    s = Sheet(do_render("side"))
    p = lambda y, z, x=-60: v.px((x, y, z))
    g0, g1 = p(-40, 0), p(40, 0)
    s.line(g0, g1, 7)
    for i in range(int(min(g0[0], g1[0])), int(max(g0[0], g1[0])), 34):
        s.line((i, g0[1] + 4), (i - 22, g0[1] + 30), 2, GREY)
    y0, y1 = P['canopy_y0'], P['canopy_y1']
    yf, yb = CTRL[0][0], P['post_y'] + r
    # top: canopy depth
    s.dim(p(y0, P['canopy_top']), p(y1, P['canopy_top']), -110, fmt_in(y1 - y0) + " CANOPY", n=(0, 1))
    # bottom: footprint + seat depth
    s.dim(p(yf, 0), p(yb, 0), 230, fmt_in(yb - yf) + " FOOTPRINT", n=(0, 1))
    s.dim(p(D['F'].x, 0), p(D['B'].x, 0), 120, fmt_in(P['seat_d']) + " SEAT DEPTH", n=(0, 1))
    # verticals on the front (right in this view)
    sx = 1 if p(-10, 0)[0] > p(10, 0)[0] else -1
    s.dim(p(D['F'].x, 0), p(D['F'].x, P['seat_h']), 150 * sx, fmt_in(P['seat_h']) + " SEAT", n=(1, 0))
    s.dim(p(yf, 0), p(yf, P['arm_h'] + r), 300 * sx, fmt_in(P['arm_h'] + r) + " ARM", n=(1, 0))
    s.dim(p(y0, 0), p(y0, CAN_EDGE_Z), 450 * sx, fmt_in(CAN_EDGE_Z) + " CLEAR", n=(1, 0))
    s.dim(p(y0, 0), p(y0, P['canopy_top']), 600 * sx, fmt_in(P['canopy_top']) + " OVERALL", n=(1, 0))
    s.dim(p(yb, 0), p(yb, BACK_TOP.y), -170 * sx, fmt_in(BACK_TOP.y) + " BACK", n=(1, 0))
    # angles
    c = Vector(p(D['back'][0].x, D['back'][0].y))
    pf = Vector(p(D['F'].x, D['F'].y)); pt = Vector(p(BACK_TOP.x, BACK_TOP.y))
    a0 = math.degrees(math.atan2(pt.y - c.y, pt.x - c.x)); a1 = math.degrees(math.atan2(pf.y - c.y, pf.x - c.x))
    lo, hi = sorted((a0, a1))
    if hi - lo > 180:
        lo, hi = hi, lo + 360
    s.angle_arc(c, 150, lo, hi, "100°", c + Vector((sx * 120, -150)))
    s.note(pf + Vector((sx * 40, -95)), "5° rake", 40, anchor="lm" if sx > 0 else "rm", weight="m")
    s.note(pt + Vector((sx * 60, -40)), "15° recline", 40, anchor="lm" if sx > 0 else "rm", weight="m")
    # canopy radius note
    pc = Vector(p(CY, P['canopy_top']))
    pe = Vector(p(P['canopy_y0'], CAN_EDGE_Z))
    pu = Vector(p(CY, CAN_EDGE_Z))
    s.note(pu + Vector((0, 110)), f'BARREL CANOPY R{fmt_in(CR)}', 40, anchor="mm", weight="m")
    s.scale_bar(MARGIN + 120, H - MARGIN - TB_H - 160, 1 / ipp)
    s.frame("SIDE ELEVATION", "02", f'1 : {round(ipp * 300):d} @ A3 · INCHES', "One continuous tube per side: foot, armrest, post, canopy arm")
    save(s, "02_side_elevation")


def sheet_plan(sc, parts):
    v = View(sc, "cam_plan", (0, 0, 0))
    ipp = v.fit(all_objs(parts), DRAW_AREA)
    v.cam.data.clip_start = v.cam.location.z - 45 * IN      # horizontal cut at 45"
    v.cam.data.clip_end = v.cam.location.z + 5
    s = Sheet(do_render("plan"))
    p = lambda x, y: v.px((x, y, 100))
    L2 = P['canopy_len'] / 2
    y0, y1 = P['canopy_y0'], P['canopy_y1']
    s.dim(p(-L2, y1), p(L2, y1), -110, fmt_in(P['canopy_len']) + " CANOPY", n=(0, 1))
    s.dim(p(-X - r, CTRL[0][0]), p(X + r, CTRL[0][0]), 140, fmt_in(2 * (X + r)) + " OVERALL FRAME", n=(0, 1))
    s.dim(p(L2, y0), p(L2, y1), 130, fmt_in(y1 - y0) + " CANOPY", n=(1, 0))
    s.dim(p(-X - r, CTRL[0][0]), p(-X - r, P['post_y'] + r), -130, fmt_in(P['post_y'] + r - CTRL[0][0]) + " FOOTPRINT", n=(1, 0))
    # foot plate centres
    s.dim(p(-X, -12), p(-X, 15.5), -300, fmt_in(27.5) + " ANCHOR C/C", n=(1, 0))
    # canopy above the cut plane: dashed outline
    for (xa, ya), (xb, yb) in [((-L2, y0), (L2, y0)), ((L2, y0), (L2, y1)), ((L2, y1), (-L2, y1)), ((-L2, y1), (-L2, y0))]:
        s.dashed(p(xa, ya), p(xb, yb), dash=40, gap=18, w=4, fill=(70, 70, 75))
    s.note(Vector(p(-L2, y1)) + Vector((20, 50)), "CANOPY ABOVE (DASHED)", 38, anchor="lm", weight="m", fill=GREY)
    # north arrow / orientation
    na = Vector((W - MARGIN - 230, MARGIN + 230))
    s.d.ellipse([na.x - 90, na.y - 90, na.x + 90, na.y + 90], outline=INK, width=4)
    s.d.polygon([(na.x, na.y - 120), (na.x - 35, na.y + 20), (na.x, na.y - 10), (na.x + 35, na.y + 20)], fill=INK)
    s.note((na.x, na.y + 140), "N", 50, anchor="mm", weight="b")
    s.note(Vector(p(0, CTRL[0][0])) + Vector((0, 290)), "PATH SIDE  ↓", 40, anchor="mm", weight="m", fill=GREY)
    s.scale_bar(MARGIN + 120, H - MARGIN - TB_H - 160, 1 / ipp)
    s.frame("PLAN", "03", f'1 : {round(ipp * 300):d} @ A3 · INCHES', "Cut at 45\" above ground · canopy dashed above")
    save(s, "03_plan")


def sheet_iso(sc, parts):
    v = View(sc, "cam_iso", (90 - 35.264, 0, -45))
    area = (MARGIN + 500, MARGIN + 200, W - MARGIN - 500, H - MARGIN - TB_H - 260)
    ipp = v.fit(all_objs(parts), area)
    s = Sheet(do_render("iso"))
    q = lambda x, y, z: v.px((x, y, z))
    L2 = P['canopy_len'] / 2
    # overall height on the right post
    s.dim(q(X + r, P['post_y'] + r, 0), q(X + r, P['post_y'] + r, P['canopy_top']), 200, fmt_in(P['canopy_top']), n=(1, 0))
    # length along x (bottom, front)
    yf = CTRL[0][0]
    a, b = q(-X - r, yf, 0), q(X + r, yf, 0)
    s.dim(a, b, 160, fmt_in(2 * (X + r)), n=Vector((-(b[1] - a[1]), b[0] - a[0])).normalized() * -1)
    a2, b2 = q(-X - r, yf, 0), q(-X - r, P['post_y'] + r, 0)
    s.dim(a2, b2, -160, fmt_in(P['post_y'] + r - yf), n=Vector((-(b2[1] - a2[1]), b2[0] - a2[0])).normalized() * -1)
    # isometric axis key
    k = Vector((MARGIN + 260, MARGIN + 330))
    for ang, lab in ((30, "X"), (150, "Y"), (90, "Z")):
        e = k + Vector((math.cos(math.radians(ang)), -math.sin(math.radians(ang)) * -1 if ang == 270 else -math.sin(math.radians(ang)))) * 130
        e = k + Vector((math.cos(math.radians(ang)), math.sin(math.radians(-ang)))) * 130
        s.line(k, e, 4)
        s.note(e + (e - k).normalized() * 40, lab, 40, anchor="mm", weight="b")
    s.note(k + Vector((0, 230)), "30° / 30° ISOMETRIC", 36, anchor="mm", weight="m", fill=GREY)
    s.frame("ISOMETRIC VIEW", "04", 'True isometric · INCHES', "Axes at 30° to horizontal, equal foreshortening")
    save(s, "04_isometric")


def sheet_axo(sc, parts, M):
    v = View(sc, "cam_axo", (0, 0, 0), M=M)
    area = (MARGIN + 500, MARGIN + 200, W - MARGIN - 500, H - MARGIN - TB_H - 260)
    ipp = v.fit(all_objs(parts), area)
    s = Sheet(do_render("axo"))
    q = lambda x, y, z: v.px((x, y, z))
    yf = CTRL[0][0]
    s.dim(q(X + r, P['post_y'] + r, 0), q(X + r, P['post_y'] + r, P['canopy_top']), 220, fmt_in(P['canopy_top']), n=(1, 0))
    a, b = q(-X - r, yf, 0), q(X + r, yf, 0)
    s.dim(a, b, 150, fmt_in(2 * (X + r)), n=Vector((-(b[1] - a[1]), b[0] - a[0])).normalized() * -1)
    a2, b2 = q(-X - r, yf, 0), q(-X - r, P['post_y'] + r, 0)
    s.dim(a2, b2, -150, fmt_in(P['post_y'] + r - yf), n=Vector((-(b2[1] - a2[1]), b2[0] - a2[0])).normalized() * -1)
    k = Vector((MARGIN + 260, MARGIN + 330))
    for ang, lab in ((45, "X"), (135, "Y"), (90, "Z")):
        e = k + Vector((math.cos(math.radians(ang)), math.sin(math.radians(-ang)))) * 130
        s.line(k, e, 4)
        s.note(e + (e - k).normalized() * 40, lab, 40, anchor="mm", weight="b")
    s.note(k + Vector((0, 230)), "45° / 45° PLAN OBLIQUE", 36, anchor="mm", weight="m", fill=GREY)
    s.frame("AXONOMETRIC VIEW", "05", '45° plan oblique · INCHES', "True plan rotated 45°, verticals true length")
    save(s, "05_axonometric")


EXPLODE = {   # group -> (dx, dy, dz) inches, frames move outward by sign
    'canopy': (0, 0, 46), 'screw': (0, 0, 58), 'rib': (0, 0, 22),
    'back': (0, 22, 26), 'insert_back': (0, 22, 21), 'backrail': (0, 34, 16),
    'seat': (0, -6, 20), 'insert_seat': (0, -6, 14), 'angle': (0, 4, 9),
    'stringer': (0, -2, 3), 'frame': ('out', 0, 0), 'foot': ('out', 0, -14), 'anchor': ('out', 0, -26),
}
CALLOUTS = [
    # num, label, sub, anchor object, anchor point offset in object local? (use bbox centre)
    (1, "Canopy panel", "¾\" terrazzo-effect recycled HDPE, thermoformed R42½\"", "Canopy_Panel"),
    (2, "Countersunk fixings", "#14 stainless CSK screws into tapped rib", "Canopy_Screw_1_0.4"),
    (3, "Canopy rib", "2\" × ⅜\" recycled steel flat bar, rolled", "Canopy_Rib_R"),
    (4, "Purlins", "Ø1\" recycled steel rod, welded to ribs", "Canopy_Purlin_-6.0"),
    (5, "Cleat plates + bolts", "¼\" plate pair, ⅜\" bolts through rib", "Rib_Cleat_L0"),
    (6, "Back panel", "1½\" terrazzo-effect recycled plastic", "Back_Panel"),
    (7, "Threaded inserts", "5/16\"-18 stainless, moulded into panels", "Back_Insert_0"),
    (8, "Back rail + stand-offs", "1½\" SHS + bent ¼\" plate brackets", "Back_Rail"),
    (9, "Seat panel", "1½\" terrazzo-effect recycled plastic", "Seat_Panel"),
    (10, "Corner angles", "L 2\" × 2\" × ¼\", ties seat to back", "Corner_Angle_V_24"),
    (11, "Seat stringers", "2\" × 1\" RHS with welded end plates", "Seat_Stringer_Front"),
    (12, "Frame cleats + bolts", "¼\" plate welded to tube, 5/16\" bolts", "Frame_Cleat_Front1"),
    (13, "End frame / post", "Ø1½\" recycled steel tube, one continuous mandrel bend", "Frame_R"),
    (14, "Foot plates", "6\" × 4\" × ¼\" welded under tube", "Foot_Plate_RF"),
    (15, "Anchors", "⅜\" chemical anchors into 4\" concrete path", "Anchor_Rod_RF2.01.3"),
]


def explode(parts):
    bpy.context.view_layer.update()
    orig = {}
    for name, (ob, g) in parts.items():
        orig[name] = ob.matrix_world.copy()
        if g not in EXPLODE:
            continue
        dx, dy, dz = EXPLODE[g]
        if dx == 'out':
            # bbox centre x sign
            cx = sum((ob.matrix_world @ Vector(c)).x for c in ob.bound_box) / 8
            dx = 12 if cx > 0 else -12
        ob.location = ob.location + Vector((dx, dy, dz)) * IN
    bpy.context.view_layer.update()
    return orig


def bbox_centre(ob):
    return sum(((ob.matrix_world @ Vector(c)) for c in ob.bound_box), Vector()) / 8 / IN


def sheet_exploded(sc, parts, M):
    names = {n: o for n, (o, g) in parts.items()}
    bpy.context.view_layer.update()
    pre = {n: bbox_centre(o) for n, o in names.items()}
    explode(parts)
    e = apply_M(parts, Matrix.Identity(4))
    e.matrix_world = M
    bpy.context.view_layer.update()
    v = View(sc, "cam_exp", (0, 0, 0), M=Matrix.Identity(4))
    area = (MARGIN + 1150, MARGIN + 140, W - MARGIN - 1450, H - MARGIN - TB_H - 120)
    v.M = Matrix.Identity(4)
    # fit on world (already sheared through parent)
    ipp = v.fit(all_objs(parts), area)
    s = Sheet(do_render("exploded"))
    q = lambda pw: v.px(M @ Vector(pw))   # pw: inches world (pre-shear)
    post = {n: (o.matrix_world @ Vector((0, 0, 0))) for n, o in names.items()}
    exp_c = {}
    for n, o in names.items():
        # centre of exploded object in pre-shear inches
        e_inv = M.inverted()
        c = sum(((e_inv @ (o.matrix_world @ Vector(cc))) for cc in o.bound_box), Vector()) / 8 / IN
        exp_c[n] = c
    # explosion trace lines (dashed) for key parts
    for n in ("Anchor_Rod_RF2.01.3", "Foot_Plate_RF", "Canopy_Panel", "Seat_Panel", "Back_Panel", "Canopy_Rib_R", "Back_Rail"):
        if n in names:
            s.dashed(q(pre[n]), q(exp_c[n]), dash=16, gap=12, w=2, fill=(150, 150, 155))
    # callouts: left column for upper parts, right column for the rest
    rows = []
    for num, lab, sub, obn in CALLOUTS:
        if obn not in exp_c:
            print("missing callout target", obn)
            continue
        rows.append((num, lab, sub, Vector(q(exp_c[obn]))))
    # leader bubbles placed in a column to the left of the drawing, sorted by height
    rows.sort(key=lambda r: r[3].y)
    x_b = MARGIN + 960
    ys = [MARGIN + 260 + i * ((H - MARGIN - TB_H - 260) - (MARGIN + 260)) / (len(rows) - 1) for i in range(len(rows))]
    for (num, lab, sub, pt), yb in zip(rows, ys):
        bub = Vector((x_b, yb))
        s.line(bub + Vector((48, 0)), pt, 2, INK)
        s.d.ellipse([pt.x - 9, pt.y - 9, pt.x + 9, pt.y + 9], fill=INK)
        s.d.ellipse([bub.x - 48, bub.y - 48, bub.x + 48, bub.y + 48], fill=(255, 255, 255), outline=INK, width=4)
        s.note(bub, str(num), 44, anchor="mm", weight="b")
        s.note((MARGIN + 70, yb - 26), lab.upper(), 34, anchor="lm", weight="b")
        s.note((MARGIN + 70, yb + 22), sub, 26, anchor="lm", fill=GREY)
    # wrap long subs: keep column narrow – the subs are short enough at 26px
    s.frame("EXPLODED AXONOMETRIC", "06", '45° plan oblique · NTS', "Joinery, fixings & details. Panels bolt from below: no visible fixings")
    # restore
    e.matrix_world = Matrix.Identity(4)
    return s, ipp


def detail_insets(sc, parts, s):
    """Three enlarged joint details on the right hand side of the exploded sheet."""
    names = {n: o for n, (o, g) in parts.items()}
    # reset to assembled, unsheared
    for n, (o, g) in parts.items():
        pass
    details = [
        ("A", "CANOPY ARM / RIB CLEAT", (X, 9.5, ZTOP + 1.0), 22, (112, 0, -55),
         "¼\" cleat pair welded to tube arm · 2 no. ⅜\" bolts through rib"),
        ("B", "STRINGER TO FRAME", (X - 1, -7.5, 14.5), 13, (108, 0, -40),
         "RHS end plate bolted to welded frame cleat · 2 no. 5/16\" bolts"),
        ("C", "FOOT PLATE + ANCHORS", (X, -12, 1.0), 13, (62, 0, 205),
         "6\"×4\"×¼\" plate welded under tube · 4 no. ⅜\" chemical anchors"),
    ]
    box_w, box_h = 1240, 860
    x0 = W - MARGIN - box_w - 60
    y = MARGIN + 80
    out = []
    for tag, title, centre, span, rot, note in details:
        cam = camera("det" + tag, (0, 0, 0), rot=rot, ortho=span * IN)
        bpy.context.view_layer.update()
        cam.location = Vector(centre) * IN + cam.matrix_world.to_3x3() @ Vector((0, 0, 60 * IN))
        cam.data.clip_start = 40 * IN
        sc.camera = cam
        sc.render.resolution_x, sc.render.resolution_y = box_w, box_h
        sc.render.resolution_percentage = 50 if FAST else 100
        path = os.path.join(OUT, f"_raw_det{tag}.png")
        render(path)
        im = Image.open(path).convert("RGB").resize((box_w, box_h), Image.LANCZOS)
        s.im.paste(im, (x0, y))
        s.d.rectangle([x0, y, x0 + box_w, y + box_h], outline=INK, width=4)
        s.d.ellipse([x0 + 20, y + 20, x0 + 130, y + 130], fill=ACCENT)
        s.note((x0 + 75, y + 75), tag, 60, fill=(255, 255, 255), anchor="mm", weight="b")
        s.note((x0 + 150, y + 75), "DETAIL " + tag + " · " + title, 38, anchor="lm", weight="b")
        s.d.rectangle([x0 + 4, y + box_h - 80, x0 + box_w - 4, y + box_h - 4], fill=(255, 255, 255))
        s.d.line([x0, y + box_h - 80, x0 + box_w, y + box_h - 80], fill=INK, width=2)
        s.note((x0 + 30, y + box_h - 40), note, 30, anchor="lm", fill=INK)
        y += box_h + 70
    sc.render.resolution_x, sc.render.resolution_y = W, H


def main():
    os.makedirs(OUT, exist_ok=True)
    which = [a for a in sys.argv[1:] if not a.startswith("--")] or ["front", "side", "plan", "iso", "axo", "exploded"]
    for w in which:
        sc, coll, parts = build_scene()
        M = plan_oblique_matrix(45)
        if w == "front": sheet_front(sc, parts)
        if w == "side": sheet_side(sc, parts)
        if w == "plan": sheet_plan(sc, parts)
        if w == "iso": sheet_iso(sc, parts)
        if w == "axo":
            apply_M(parts, M)
            sheet_axo(sc, parts, M)
        if w == "exploded":
            s, ipp = sheet_exploded(sc, parts, M)
            # details are rendered from the un-exploded, un-sheared model
            sc, coll, parts = build_scene()
            detail_insets(sc, parts, s)
            save(s, "06_exploded_axonometric")
    for f in os.listdir(OUT):
        if f.startswith("_raw_"):
            os.remove(os.path.join(OUT, f))


if __name__ == "__main__":
    main()
