"""Scene helpers shared by drawing and render scripts."""
import math, os, sys
import bpy, addon_utils
from mathutils import Vector, Euler
sys.path.insert(0, os.path.dirname(__file__))
import bench_model as BM
IN = BM.IN
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def reset():
    bpy.ops.wm.read_factory_settings(use_empty=True)
    addon_utils.enable("cycles", default_set=True)
    sc = bpy.context.scene
    sc.render.engine = 'CYCLES'
    sc.cycles.device = 'CPU'
    sc.unit_settings.system = 'IMPERIAL'
    sc.unit_settings.length_unit = 'INCHES'
    return sc


def camera(name, loc, target=None, rot=None, lens=50, ortho=None, coll=None):
    cd = bpy.data.cameras.new(name)
    cam = bpy.data.objects.new(name, cd)
    (coll or bpy.context.scene.collection).objects.link(cam)
    cam.location = Vector(loc)
    if ortho:
        cd.type = 'ORTHO'
        cd.ortho_scale = ortho
    cd.lens = lens
    cd.clip_start = 0.01
    cd.clip_end = 500
    if target is not None:
        d = Vector(target) - cam.location
        cam.rotation_euler = d.to_track_quat('-Z', 'Y').to_euler()
    if rot is not None:
        cam.rotation_euler = Euler([math.radians(a) for a in rot])
    return cam


def set_res(sc, w, h, samples=64):
    sc.render.resolution_x = w
    sc.render.resolution_y = h
    sc.render.resolution_percentage = 100
    sc.cycles.samples = samples
    sc.cycles.use_denoising = True
    sc.cycles.use_adaptive_sampling = True
    sc.render.image_settings.file_format = 'PNG'
    sc.render.film_transparent = False


def render(path):
    sc = bpy.context.scene
    sc.render.filepath = path
    os.makedirs(os.path.dirname(path), exist_ok=True)
    bpy.ops.render.render(write_still=True)
