"""PLNT hero shot definitions + renderer (works interactively and headless).

Composition model
-----------------
`ang_r`  angular radius of the planet in degrees -> camera distance. Compared
         against the camera's half-FOV this sets how much of the frame the
         planet fills (planet_fraction below).
`push`   (x, y) in units of half-frame. The camera aims at the planet centre
         then yaws/pitches so the planet sits off-centre; +x pushes the planet
         right, +y pushes it up. This is what puts the limb across a frame edge
         instead of leaving a centred disc with margin all round.
`sun`    (delta_azimuth from the camera, sun elevation). delta 0 = full day,
         90 = terminator, 180 = full night. Sun elevation differing from the
         camera elevation is what tilts the terminator off vertical.
"""
import bpy
import math
import os
from mathutils import Vector, Euler

R = 1000.0
HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "renders")


def out_dir(where=None):
    """Resolve an output directory.

    A bare name is taken relative to the project, so `--out renders_v3` cannot
    silently resolve against the sandbox root the way relative paths have done
    on this project before. An absolute path is used as given.
    """
    if not where:
        return OUT
    return where if os.path.isabs(where) else os.path.join(HERE, where)

SHOTS = [
    dict(n=1, preset="pristine_alien", seed=8123, tech=0.0,
         focal=85.0, frac=1.30, theta=-118.0, phi=6.0, push=(-0.42, -0.34),
         sun=(88.0, 22.0), roll=-8.0,
         note="close limb, near-backlit, atmosphere band dominant (ref 1)"),
    dict(n=2, preset="earthlike", seed=2291, tech=0.0,
         focal=58.0, frac=1.05, theta=34.0, phi=17.0, push=(0.52, -0.06),
         sun=(52.0, 30.0), roll=4.0,
         note="3/4 disc pushed right, strong side-light, fine cloud (ref 4)"),
    dict(n=3, preset="ringed_ice", seed=5514, tech=0.0,
         focal=72.0, frac=0.80, theta=-14.0, phi=3.0, push=(0.44, 0.30),
         sun=(62.0, -18.0), roll=-6.0,
         note="rings edge-on crossing frame, ring shadow on planet (ref 3)"),
    dict(n=4, preset="ocean_world", seed=7702, tech=1.0,
         focal=35.0, frac=1.15, theta=96.0, phi=-12.0, push=(-0.44, 0.22), dice=3.0,
         sun=(38.0, -10.0), roll=7.0,
         note="wide, low sun, specular sun-glint on water"),
    dict(n=5, preset="volcanic", seed=3346, tech=0.0,
         focal=100.0, frac=1.30, theta=150.0, phi=-20.0, push=(0.44, 0.14), dice=2.5,
         sun=(142.0, 24.0), roll=-4.0,
         note="night-heavy, lava emission as the only light on the dark side"),
    dict(n=6, preset="desert", seed=9188, tech=2.0,
         focal=200.0, frac=1.45, theta=-72.0, phi=28.0, push=(-0.44, -0.32), dice=3.0,
         sun=(26.0, 44.0), roll=3.0,
         note="high sun, long lens, dune-scale surface texture"),
    dict(n=7, preset="colonial_outpost", seed=6035, tech=3.0,
         focal=120.0, frac=1.20, theta=-160.0, phi=14.0, push=(0.38, -0.28),
         sun=(132.0, -16.0), roll=-9.0,
         note="night side, sparse warm settlement lights, faint roads"),
    dict(n=8, preset="industrial_world", seed=4457, tech=6.0,
         focal=85.0, frac=1.10, theta=62.0, phi=-8.0, push=(-0.42, 0.22),
         sun=(92.0, 28.0), roll=6.0,
         note="terminator shot, polluted haze, light webs crossing into night"),
    dict(n=9, preset="hyperdeveloped", seed=1874, tech=9.0,
         focal=65.0, frac=1.05, theta=-38.0, phi=-24.0, push=(0.34, 0.30),
         sun=(142.0, 34.0), roll=-5.0,
         note="dark planet, cyan geometric grid arcs and ring nodes (ref 5)"),
    dict(n=10, preset="megastructure", seed=6690, tech=10.0,
         focal=45.0, frac=0.72, theta=118.0, phi=9.0, push=(-0.20, -0.14),
         sun=(112.0, 22.0), roll=8.0,
         note="orbital bands in foreground, planet behind, cool city lights (ref 6)"),
]


def _presets():
    # packaged extension: presets is a real sibling module
    if __package__:
        try:
            import importlib as _il
            return _il.import_module(".presets", __package__).__dict__
        except Exception:
            pass
    txt = bpy.data.texts.get("PLNT_presets.py")
    ns = {"__name__": "plnt_presets_mod"}
    exec(compile(txt.as_string(), "PLNT_presets.py", 'exec'), ns)
    return ns


def half_fov(cam_data, scene, horizontal=True):
    sw = cam_data.sensor_width
    rx, ry = scene.render.resolution_x, scene.render.resolution_y
    if horizontal:
        return math.atan((sw * 0.5) / cam_data.lens)
    return math.atan((sw * 0.5) * (ry / rx) / cam_data.lens)


def place_camera(cam, shot, scene):
    cam.data.lens = shot["focal"]
    cam.data.clip_start = 0.01
    cam.data.clip_end = 100000.0
    if "frac" in shot:
        ang = math.degrees(shot["frac"] * half_fov(cam.data, scene, False))
    else:
        ang = shot["ang_r"]
    ang = max(0.05, min(75.0, ang))
    d = R / math.sin(math.radians(ang))
    th, ph = math.radians(shot["theta"]), math.radians(shot["phi"])
    loc = Vector((d * math.cos(ph) * math.cos(th),
                  d * math.cos(ph) * math.sin(th),
                  d * math.sin(ph)))
    cam.location = loc
    q = (loc - Vector((0, 0, 0))).to_track_quat('Z', 'Y')
    px, py = shot.get("push", (0.0, 0.0))
    yaw = -px * half_fov(cam.data, scene, True)
    pitch = py * half_fov(cam.data, scene, False)
    q = q @ Euler((pitch, yaw, math.radians(shot.get("roll", 0.0))), 'XYZ').to_quaternion()
    cam.rotation_mode = 'QUATERNION'
    cam.rotation_quaternion = q
    return {"dist": round(d, 1), "ang_r": round(ang, 2),
            "planet_frac": round(math.radians(ang) / half_fov(cam.data, scene, False), 3)}


def apply_shot(shot, ns=None):
    sc = bpy.context.scene
    ns = ns or _presets()
    ns["apply_preset"](shot["preset"], seed=shot["seed"])
    # tech override
    for m in ("PLNT_Surface", "PLNT_PatchSurface"):
        mat = bpy.data.materials.get(m)
        if mat and mat.node_tree:
            n = mat.node_tree.nodes.get("PLNT_CTL")
            if n and "Tech Level" in n.inputs:
                n.inputs["Tech Level"].default_value = shot["tech"]
    orb = bpy.data.objects.get("PLNT_Orbital")
    if orb and orb.modifiers.get("PLNT_OrbitalRig"):
        ns["gset"](orb.modifiers["PLNT_OrbitalRig"], "Orbital Level",
                   float(ns["P"][shot["preset"]].get("orbital", 0.0)))
        ns["gset"](orb.modifiers["PLNT_OrbitalRig"], "Seed", float(shot["seed"]))
    # sun: delta relative to the camera azimuth so lighting is framing-relative
    ns["sun"](shot["theta"] + shot["sun"][0], shot["sun"][1])
    cam = bpy.data.objects["PLNT_CAM_Orbital"]
    info = place_camera(cam, shot, sc)
    sc.camera = cam
    sc.cycles.dicing_camera = cam
    # ground patch never appears in hero shots
    p = bpy.data.objects.get("PLNT_Patch")
    if p:
        p.hide_render = True
    return info


def _core(mod):
    """Import a core/ module without depending on the package layout."""
    import importlib.util
    import sys as _s
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core",
                     mod + ".py")
    spec = importlib.util.spec_from_file_location(mod, p)
    m = importlib.util.module_from_spec(spec)
    _s.modules[mod] = m
    spec.loader.exec_module(m)
    return m


def render_shot(shot, res=(2560, 1440), samples=1024, tag="", dice=1.0,
                quality=None, disp_mode=None, out=None):
    """Render one hero shot.

    quality/disp_mode route through core/render.py and core/lod.py when given,
    so a batch can be re-rendered at a different quality without editing shot
    definitions. Left None, the explicit samples/dice arguments are used and
    behaviour is unchanged.
    """
    sc = bpy.context.scene
    dest = out_dir(out)
    os.makedirs(dest, exist_ok=True)
    info = apply_shot(shot)
    if disp_mode:
        try:
            _core("nodeutil")
            _core("lod").apply_mode(disp_mode)
            info["disp_mode"] = disp_mode
        except Exception as ex:
            info["disp_mode_error"] = str(ex)
    if quality:
        try:
            q = _core("render").apply_quality(quality, sc,
                                              dicing_override=shot.get("dice", dice))
            info["quality"] = q
        except Exception as ex:
            info["quality_error"] = str(ex)
    sc.render.resolution_x, sc.render.resolution_y = res
    sc.render.film_transparent = False
    if not quality:
        sc.render.resolution_percentage = 100
        sc.cycles.samples = samples
    if not quality:
        sc.cycles.use_adaptive_sampling = True
        sc.cycles.adaptive_threshold = 0.01
        sc.cycles.use_denoising = True
        sc.cycles.denoiser = 'OPENIMAGEDENOISE'
        sc.cycles.max_bounces = 12
        sc.cycles.transmission_bounces = 12
        sc.cycles.volume_bounces = 4
        sc.cycles.dicing_rate = dice
    sc.view_settings.view_transform = 'AgX'
    name = "PLNT_shot_%02d%s.png" % (shot["n"], tag)
    path = os.path.join(dest, name)
    sc.render.filepath = path
    sc.render.image_settings.file_format = 'PNG'
    bpy.ops.render.render(write_still=True)
    info.update({"path": path, "preset": shot["preset"], "seed": shot["seed"]})
    return info
