"""Save the bench as an editable .blend and export OBJ / FBX (for SketchUp, Rhino, etc.)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common import *

OUT = os.path.join(ROOT, "output", "model")
os.makedirs(OUT, exist_ok=True)
sc = reset()
coll, parts = BM.build()
BM.assign_materials(parts)
bpy.context.view_layer.update()
# keep editable curves/modifiers in the .blend
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(OUT, "urban_canopy_bench.blend"), compress=True)
# exchange formats: apply modifiers, curves -> meshes, Z-up, metres
bpy.ops.object.select_all(action='SELECT')
bpy.ops.wm.obj_export(filepath=os.path.join(OUT, "urban_canopy_bench.obj"), apply_modifiers=True,
                      export_materials=True, up_axis='Z', forward_axis='Y')
bpy.ops.export_scene.fbx(filepath=os.path.join(OUT, "urban_canopy_bench.fbx"), use_selection=False,
                         apply_scale_options='FBX_SCALE_UNITS', axis_up='Z', axis_forward='Y', use_mesh_modifiers=True)
print("exported", os.listdir(OUT))
