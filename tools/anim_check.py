"""Render a short sequence to prove the system actually moves.

  blender -b <blend> -P tools/anim_check.py -- --shot 2 --frames 48 \
          --time-scale 1.0 --out <dir> [--rx 640 --ry 360 --spp 48]

Runs with no add-on registered on purpose: that is how the batch renderer loads
the file, and the clock has to work there too. The drivers read scene ID
properties rather than scene.plnt for exactly this reason, and if that ever
regresses this script renders 48 identical frames and says so.
"""
import bpy
import importlib.util
import json
import os
import sys
import time

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(name, default=None):
    return argv[argv.index(name) + 1] if name in argv else default


def load(path, name):
    sp = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(sp)
    sys.modules[name] = m
    sp.loader.exec_module(m)
    return m


SHOT = int(arg("--shot", "2"))
FRAMES = int(arg("--frames", "48"))
TS = float(arg("--time-scale", "1.0"))
OUT = arg("--out", os.path.join(D, "logs", "anim"))
RX, RY = int(arg("--rx", "640")), int(arg("--ry", "360"))
SPP = int(arg("--spp", "48"))

os.makedirs(OUT, exist_ok=True)
res = {"shot": SHOT, "frames": FRAMES, "time_scale": TS, "out": OUT}

sc = bpy.context.scene
prefs = bpy.context.preferences.addons["cycles"].preferences
for backend in ('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL'):
    try:
        prefs.compute_device_type = backend
    except TypeError:
        continue
    prefs.refresh_devices()
    if any(d.type == backend for d in prefs.devices):
        for d in prefs.devices:
            d.use = (d.type == backend)
        sc.cycles.device = 'GPU'
        res["backend"] = backend
        break
else:
    sc.cycles.device = 'CPU'

shots = load(os.path.join(D, "plnt_shots.py"), "plnt_shots")
anim = load(os.path.join(D, "core", "anim.py"), "plnt_anim")

shot = next(s for s in shots.SHOTS if s["n"] == SHOT)
res["applied"] = shots.apply_shot(shot)
res["clock"] = anim.set_time(sc, time_scale=TS)

sc.render.engine = 'CYCLES'
sc.render.resolution_x, sc.render.resolution_y = RX, RY
sc.render.resolution_percentage = 100
sc.render.film_transparent = False
sc.cycles.samples = SPP
sc.cycles.use_adaptive_sampling = True
sc.cycles.adaptive_threshold = 0.05
sc.cycles.use_denoising = True
sc.cycles.dicing_rate = 4.0
sc.cycles.dicing_camera = sc.camera
sc.view_settings.view_transform = 'AgX'
sc.render.image_settings.file_format = 'PNG'
# One process, many frames: this is the case persistent data is actually for.
sc.render.use_persistent_data = True

means = []
t0 = time.time()
for i in range(FRAMES):
    f = i + 1
    sc.frame_set(f)
    path = os.path.join(OUT, "shot%02d_ts%s_%03d.png" % (SHOT, TS, f))
    sc.render.filepath = path
    bpy.ops.render.render(write_still=True)
    try:
        img = bpy.data.images.load(path)
        px = img.pixels[:]
        n = len(px) // 4
        step = max(1, n // 20000)
        vals = [px[k * 4] + px[k * 4 + 1] + px[k * 4 + 2]
                for k in range(0, n, step)]
        means.append(round(sum(vals) / len(vals), 6))
        bpy.data.images.remove(img)
    except Exception:
        means.append(None)

res["seconds"] = round(time.time() - t0, 1)
res["frame_means"] = means
ok = [m for m in means if m is not None]
if len(ok) > 1:
    spread = max(ok) - min(ok)
    res["mean_spread"] = round(spread, 6)
    # Identical frames are the failure this script exists to catch.
    res["moved"] = spread > 1e-4
else:
    res["moved"] = None
print("ANIM " + json.dumps(res), flush=True)
