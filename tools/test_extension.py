"""Import the packaged extension as a package and register it.

The package uses relative imports (bl_ext.<repo>.<id> at install time), which
the working tree's path-based loaders cannot express. This is where that
rewrite either works or does not.
"""
import bpy, os, sys, json, traceback

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, "ext"))
res = {}
try:
    import plnt_planet
    res["imported"] = True
    plnt_planet.register()
    res["registered"] = True
    # the classes the panel needs must actually exist now
    res["panels"] = sorted(c for c in dir(bpy.types) if c.startswith("PLNT_PT_"))
    res["operators"] = sorted(c for c in dir(bpy.types) if c.startswith("PLNT_OT_"))
    res["scene_prop"] = hasattr(bpy.types.Scene, "plnt")
    # and the generators must be reachable through the package
    from plnt_planet.core import rings, orbital, mega, atmosphere, params, lod, render
    res["modules"] = {"rings": len(rings.RING_IN),
                      "orbital": len(orbital.ORBITAL_IN),
                      "mega": len(mega.MEGA_IN),
                      "atmosphere": len(atmosphere.ATMO_IN),
                      "params": params.validate(),
                      "lod_modes": list(lod.MODES),
                      "qualities": sorted(render.PRESETS)}
    # build one group through the package path to prove imports resolve
    g = rings.build_shader("EXT_RingTest")
    res["ring_shader_nodes"] = len(g.nodes)
    plnt_planet.unregister()
    res["unregistered"] = True
    res["ok"] = True
except Exception as ex:
    res["ok"] = False
    res["error"] = "%s: %s" % (type(ex).__name__, ex)
    res["trace"] = traceback.format_exc().splitlines()[-10:]
print("EXTTEST " + json.dumps(res, default=str), flush=True)
