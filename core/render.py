"""Render quality presets, performance tiers and device setup.

Two dials, not one
------------------
QUALITY is what the picture is worth: resolution, samples, bounces, dicing and
displacement mode. PERFORMANCE is what the machine can afford: base
subdivision, how adaptive subdivision measures an edge, how many noise octaves
the terrain runs, and where denoising happens. They are separate because they
answer to different people: a laptop wants Low performance at Final quality,
and a workstation wants High performance at Draft while framing up.

Values here are chosen against measured behaviour on this project, not copied
from generic optimisation lists. In particular:

  use_guiding            CPU only. Useless on OptiX; left off.
  use_persistent_data    False for a batch of stills -- one process per shot,
                         so it cannot help, and it raises peak RSS, which makes
                         the out-of-memory kills that ended two shots more
                         likely. True for interactive and animation work, where
                         the BVH is reused every frame.
  sample_clamp_direct    stays 0. Clamping direct light would clip shot 04's
                         sun glint and shot 05's lava cores, which ARE the
                         subject of those frames.
  transparent_max_bounces  must stay >= 4. The cloud shell is Transparent and
                         every camera ray crosses it twice; below that the limb
                         goes black.
  denoising_use_gpu      False on this card. Denoising on 6 GB at 2560x1440
                         competes with the render for VRAM.
  dicing_rate            drives MEMORY, not speed: 2560x1440 costs 2.56 GB of
                         VRAM at 1.0 against 1.29 GB at 2.0, and 1.0 is what
                         out-of-memory-killed shots 07-10. Only ARCHIVE, which
                         nobody runs to a deadline, goes below 2.0.
  displacement           GEOMETRY, not TRUE. Paired and thermally gated on shot
                         02, real displaced geometry renders in 74% of the time
                         geometry-plus-bump takes, for an image whose mean
                         differs in the fourth decimal place. The bump chain
                         re-evaluates the terrain field three extra times per
                         shading hit; the geometry does not.

volume_step_rate and volume_max_steps used to be set here. They are gone:
Blender 5.0 moved Cycles to unbiased null-scattering volumes, where both are
inert unless cycles.volume_biased is on. Carrying them implied a speed/quality
trade-off that has not existed since 5.0.
"""
import bpy
import json
import os
import time

QUALITIES = ('DRAFT', 'FAST', 'PREVIEW', 'FINAL', 'ARCHIVE')

# resolution_percentage is against the scene's 2560x1440 base:
#   50% = 1280x720,  75% = 1920x1080,  100% = 2560x1440
PRESETS = {
    'DRAFT': dict(
        samples=64, adaptive_threshold=0.05, use_adaptive_sampling=True,
        max_bounces=4, diffuse_bounces=2, glossy_bounces=2,
        transmission_bounces=4, volume_bounces=1, transparent_max_bounces=6,
        use_denoising=True, dicing_rate=4.0, resolution_percentage=50,
        displacement='GEOMETRY',
    ),
    'FAST': dict(
        samples=96, adaptive_threshold=0.05, use_adaptive_sampling=True,
        max_bounces=4, diffuse_bounces=2, glossy_bounces=3,
        transmission_bounces=4, volume_bounces=1, transparent_max_bounces=6,
        use_denoising=True, dicing_rate=2.0, resolution_percentage=75,
        displacement='GEOMETRY',
    ),
    'PREVIEW': dict(
        samples=192, adaptive_threshold=0.02, use_adaptive_sampling=True,
        max_bounces=6, diffuse_bounces=3, glossy_bounces=3,
        transmission_bounces=6, volume_bounces=2, transparent_max_bounces=8,
        use_denoising=True, dicing_rate=2.0, resolution_percentage=75,
        displacement='GEOMETRY',
    ),
    'FINAL': dict(
        samples=512, adaptive_threshold=0.015, use_adaptive_sampling=True,
        max_bounces=6, diffuse_bounces=4, glossy_bounces=4,
        transmission_bounces=6, volume_bounces=2, transparent_max_bounces=8,
        use_denoising=True, dicing_rate=2.0, resolution_percentage=100,
        displacement='GEOMETRY',
    ),
    'ARCHIVE': dict(
        samples=2048, adaptive_threshold=0.005, use_adaptive_sampling=True,
        max_bounces=12, diffuse_bounces=6, glossy_bounces=6,
        transmission_bounces=12, volume_bounces=4, transparent_max_bounces=12,
        use_denoising=True, dicing_rate=1.0, resolution_percentage=100,
        displacement='TRUE',
    ),
}

# Applied at every quality; these are correctness or memory constraints rather
# than a speed/quality dial.
INVARIANT = dict(
    sample_clamp_direct=0.0,        # clipping direct light would kill the glint
    sample_clamp_indirect=10.0,     # fireflies from the mirror arrays
    blur_glossy=1.0,
    caustics_reflective=False,
    caustics_refractive=False,
    use_light_tree=True,
    denoiser='OPENIMAGEDENOISE',
    use_auto_tile=True,
    tile_size=1024,
    offscreen_dicing_scale=16.0,
    max_subdivisions=12,
    use_guiding=False,              # CPU-only feature; no effect on OptiX
)

DESCRIPTIONS = {
    'DRAFT': "1280x720, 64 samples. Framing and colour.",
    'FAST': "1920x1080, 96 samples. A shareable frame in well under a minute.",
    'PREVIEW': "1920x1080, 192 samples. For judging detail.",
    'FINAL': "2560x1440, 512 adaptive samples. The delivery setting.",
    'ARCHIVE': "2048 samples, geometry-plus-bump displacement, dicing 1.0. "
               "Reference stills you intend to print. Wants more than 6 GB of "
               "VRAM at full resolution.",
}

# Measured on the development machine (RTX 2060 6 GB, Ryzen 5 3600), shot 02,
# Balanced performance: render seconds, excluding scene load. record_time()
# overwrites a tier as real renders happen, so the panel can quote the user's
# own machine rather than someone else's.
TIER_SECONDS = {'DRAFT': 13.0, 'FAST': 23.0, 'PREVIEW': 48.0,
                'FINAL': 134.0, 'ARCHIVE': 520.0}

# --------------------------------------------------------------------------
# Performance tiers: what the machine can afford.
# --------------------------------------------------------------------------
#   subdiv          base mesh subdivision of the globe. Memory and interaction,
#                   not render time: level 8 is 983,040 quads and 2.2 s per
#                   parameter change in the viewport, level 7 is 0.56 s.
#   adaptive_space  OBJECT measures a dice edge in object units, so micropolygon
#                   memory stops scaling with how close the camera is, which is
#                   what made a close-up cost 2.56 GB of VRAM.
#   adaptive_edge   OBJECT-space edge length in BLENDER UNITS, on a planet
#                   of radius 1000. Dicing rate 2.0 at 2560x1440 produces
#                   roughly a 3-unit micropolygon at the hero framings, so 3.0
#                   is the like-for-like setting and 6.0 is the cheap one.
#                   Small numbers here are a trap: 0.045 units is 270 m of
#                   planet per micropolygon and runs a 6 GB card out of memory
#                   before the first tile.
#   detail_scale    multiplier on every noise octave count in the terrain,
#                   cloud and ring shaders. Measured -6% at 0.6 and nothing
#                   measurable at 0.85, so only the Low tier takes it.
#   denoise_gpu     GPU denoising needs headroom a 6 GB card does not have at
#                   2560x1440, so it is only taken up above 8 GB.
PERFORMANCE = {
    'LOW': dict(subdiv=7, adaptive_space='OBJECT', adaptive_edge=6.0,
                detail_scale=0.6, denoise_gpu=False, persistent=False,
                note="Laptops and 4 GB cards. Coarser terrain, much less VRAM"),
    'BALANCED': dict(subdiv=8, adaptive_space='OBJECT', adaptive_edge=3.0,
                     detail_scale=1.0, denoise_gpu=False, persistent=True,
                     note="The tested setting on a 6 GB card"),
    'HIGH': dict(subdiv=8, adaptive_space='PIXEL', adaptive_edge=0.01,
                 detail_scale=1.0, denoise_gpu=True, persistent=True,
                 note="8 GB or more. Camera-relative dicing and every octave"),
}
PERFORMANCE_LEVELS = ('LOW', 'BALANCED', 'HIGH')


def _logs_dir():
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = os.path.join(here, "logs")
    return d if os.path.isdir(d) else None


_TIMES_CACHE = {"data": None}


def measured_times(force=False):
    """Seconds per quality tier: the measured table, overlaid with this
    machine's own numbers once it has rendered any."""
    if _TIMES_CACHE["data"] is not None and not force:
        return _TIMES_CACHE["data"]
    out = dict(TIER_SECONDS)
    d = _logs_dir()
    if d:
        p = os.path.join(d, "quality_times.json")
        try:
            with open(p) as f:
                out.update({k: float(v) for k, v in json.load(f).items()})
        except Exception:
            pass
    _TIMES_CACHE["data"] = out
    return out


def record_time(quality, seconds):
    """Remember how long this tier actually took, so the panel can say so."""
    d = _logs_dir()
    if not d:
        return None
    p = os.path.join(d, "quality_times.json")
    try:
        cur = {}
        if os.path.exists(p):
            with open(p) as f:
                cur = json.load(f)
        cur[quality.upper()] = round(float(seconds), 1)
        with open(p, "w") as f:
            json.dump(cur, f, indent=1, sort_keys=True)
        _TIMES_CACHE["data"] = None
        return p
    except Exception:
        return None


def setup_device(scene=None, prefer=('OPTIX', 'CUDA', 'HIP', 'ONEAPI', 'METAL')):
    """Enable GPU compute, probing for what is actually present.

    Never hard-code OPTIX: the same file has to work on another machine, and a
    missing backend silently falls back to CPU, which looks like a 40x
    performance regression rather than a configuration problem.
    """
    scene = scene or bpy.context.scene
    try:
        prefs = bpy.context.preferences.addons["cycles"].preferences
    except KeyError:
        return {"error": "cycles addon preferences unavailable"}
    prefs.refresh_devices()
    chosen = None
    for backend in prefer:
        try:
            prefs.compute_device_type = backend
        except TypeError:
            continue
        prefs.refresh_devices()
        if any(d.type == backend for d in prefs.devices):
            chosen = backend
            break
    if chosen is None:
        scene.cycles.device = 'CPU'
        return {"backend": None, "device": 'CPU'}
    for d in prefs.devices:
        d.use = (d.type == chosen)
    scene.cycles.device = 'GPU'
    # Preferences are process-local until saved, and headless renders read the
    # same file -- without this a background render silently drops to CPU.
    try:
        bpy.ops.wm.save_userpref()
    except Exception:
        pass
    return {"backend": chosen, "device": 'GPU',
            "enabled": [d.name for d in prefs.devices if d.use]}


def gpu_vram_gb():
    """Best-effort VRAM of the compute device, in GB, or None.

    Cycles does not report device memory through RNA, so this asks the driver
    and returns None when it cannot. None must never be read as "small".
    """
    try:
        import subprocess
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.total",
             "--format=csv,noheader,nounits"],
            stderr=subprocess.DEVNULL, timeout=6)
        return round(int(out.decode().strip().splitlines()[0]) / 1024.0, 1)
    except Exception:
        return None


def _lod():
    try:
        from . import lod as _l
    except ImportError:
        import lod as _l
    return _l


def apply_quality(quality, scene=None, dicing_override=None, displacement=None):
    quality = quality.upper()
    if quality not in PRESETS:
        raise ValueError("quality must be one of %r" % (QUALITIES,))
    scene = scene or bpy.context.scene
    cy, rd = scene.cycles, scene.render
    vals = dict(PRESETS[quality])
    res_pct = vals.pop("resolution_percentage")
    disp = displacement or vals.pop("displacement")
    vals.pop("displacement", None)
    for k, v in list(vals.items()) + list(INVARIANT.items()):
        if hasattr(cy, k):
            setattr(cy, k, v)
    if dicing_override is not None:
        cy.dicing_rate = float(dicing_override)
    rd.resolution_percentage = res_pct
    rd.engine = 'CYCLES'
    scene.view_settings.view_transform = 'AgX'
    if scene.camera:
        cy.dicing_camera = scene.camera  # was saved pointing at a camera 40 km away
    info = {"quality": quality, "samples": cy.samples,
            "dicing_rate": cy.dicing_rate, "resolution_percentage": res_pct,
            "displacement": disp}
    try:
        info["lod"] = _lod().apply_mode(disp)["mode"]
    except Exception as ex:
        info["lod_error"] = str(ex)[:120]
    return info


def apply_performance(level, scene=None):
    """Apply one performance tier. Independent of quality."""
    level = level.upper()
    if level not in PERFORMANCE:
        raise ValueError("performance must be one of %r" % (PERFORMANCE_LEVELS,))
    scene = scene or bpy.context.scene
    cfg = PERFORMANCE[level]
    L = _lod()
    out = {"level": level}
    out["subdiv"] = L.apply_subdiv(cfg["subdiv"])
    out["adaptive"] = L.apply_adaptive(cfg["adaptive_space"], cfg["adaptive_edge"])
    out["detail"] = L.apply_detail(cfg["detail_scale"])
    vram = gpu_vram_gb()
    want_gpu = bool(cfg["denoise_gpu"]) and (vram is None or vram > 8.0)
    scene.cycles.denoising_use_gpu = want_gpu
    out["denoise_gpu"] = want_gpu
    out["vram_gb"] = vram
    # Persistent data keeps the BVH between frames: a clear win for one process
    # rendering many frames, a clear loss for ten processes rendering one still
    # each. It therefore follows the performance tier, not the quality.
    scene.render.use_persistent_data = bool(cfg["persistent"])
    out["persistent_data"] = scene.render.use_persistent_data
    return out


def timed_render(quality=None, scene=None, write_still=False):
    """Render once and remember how long the tier took."""
    scene = scene or bpy.context.scene
    t0 = time.time()
    bpy.ops.render.render(write_still=write_still)
    dt = time.time() - t0
    if quality:
        record_time(quality, dt)
    return dt
