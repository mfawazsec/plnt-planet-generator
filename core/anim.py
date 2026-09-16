"""One clock for the whole system.

Nothing in this project moved. Not the planet, not the weather, not a single
satellite, and the megastructures least of all. A Dyson swarm that hangs
motionless is the one thing about it that reads as fake. This module gives
every moving part its real period and drives all of them from one number.

The number
----------
`scene.plnt.time_scale` is WORLD HOURS PER SECOND OF FOOTAGE. At 1.0 a
24-hour planet turns once every 24 seconds of playback and a low satellite
goes round in about 90, fast enough to read and slow enough to be legible. At
1/3600 everything runs at real time. At 0 the system is frozen, which is what
the ten hero stills want.

`scene.plnt.day_length_h` is the planet's rotation period. Everything else
keeps its own physical period regardless, so a tidally-locked world with a
600-hour day gets a sky full of fast traffic over a nearly static surface,
which is correct and is also the more interesting picture.

Scale
-----
1 Blender unit = 6 km, so radius 1000 is a 6000 km planet, the value the
ground patch rig already assumes through Planet Radius KM. A circular orbit
just above such a planet has a period of

    T0 = 2*pi*sqrt(R^3 / GM) = 84.5 minutes

for Earth-like density, and Kepler's third law gives every other altitude:

    T(r) = T0 * (r/R)^1.5          hours = T0/60 * (r/R)^1.5
    w(r) = 360 / T(r)              degrees per world hour

so the orbital band at 1.24 R sweeps 185 deg/h, the ring system shears from
162 deg/h at its inner edge to 73 deg/h at its outer, and the Dyson collectors
at 4.4 R crawl round at 28. Those ratios are what make the motion read as
gravity rather than as a turntable.

How it reaches the nodes
------------------------
Shaders have no concept of the current frame, so each shader group carries a
Value node labelled PLNT_TIME with a driver that evaluates `frame / fps *
time_scale`. Geometry nodes do have a Scene Time node, so the rigs read
seconds from it and multiply by a plain PLNT_TS value that `sync()` writes --
no driver, nothing to go stale. Both paths end up holding the same number of
world hours, so shading and geometry can never disagree about what time it is.
"""
import bpy
import math

# 1 BU = 6 km. Surface-skimming orbital period for an Earth-density planet.
KM_PER_UNIT = 6.0
LEO_PERIOD_H = 84.5 / 60.0

# The drivers read ID properties on the Scene, NOT scene.plnt.
#
# scene.plnt only exists while the add-on is registered, and the batch renderer
# loads the .blend with no add-on at all: plnt_headless.py runs the file
# directly. A driver whose data path cannot resolve does not raise, it simply
# stops updating, so the whole system would have silently frozen in every
# headless render while working perfectly in the GUI. Custom ID properties are
# part of the file and resolve whether anything is registered or not.
SCENE_TS = "plnt_time_scale"
SCENE_DAY = "plnt_day_length_h"
SCENE_BEACON = "plnt_beacon_rate"
SCENE_DEFAULTS = {SCENE_TS: 0.0, SCENE_DAY: 24.0, SCENE_BEACON: 1.0}

TIME_LABEL = "PLNT_TIME"     # world hours, shader trees (driven)
TS_LABEL = "PLNT_TS"         # hours per footage-second, geometry trees
DAY_LABEL = "PLNT_DAY"       # rotation period in hours, geometry trees

PRESET_SCALES = [
    ('FROZEN', 0.0, "Frozen", "Nothing moves. What the hero stills want"),
    ('REALTIME', 1.0 / 3600.0, "Real time", "One second of world time per second"),
    ('SLOW', 0.1, "Slow", "A satellite crosses the disc in about fifteen minutes"),
    ('TIMELAPSE', 1.0, "Timelapse", "A day in 24 seconds, an orbit in 90"),
    ('FAST', 6.0, "Fast", "Six hours a second. Weather systems visibly evolve"),
]


def ensure_scene_props(scene=None):
    """Make sure the three clock values exist on the scene itself."""
    scene = scene or bpy.context.scene
    for k, v in SCENE_DEFAULTS.items():
        if k not in scene.keys():
            scene[k] = v
    return {k: scene[k] for k in SCENE_DEFAULTS}


def period_h(r_over_R):
    """Orbital period in hours at a radius given in planet radii."""
    return LEO_PERIOD_H * (max(1.0, float(r_over_R)) ** 1.5)


def omega_deg_h(r_over_R):
    """Angular rate in degrees per world hour at a radius in planet radii."""
    return 360.0 / period_h(r_over_R)


# --------------------------------------------------------------------------
# The clock inside a node tree
# --------------------------------------------------------------------------
def _by_label(tree, label):
    for n in tree.nodes:
        if n.label == label:
            return n
    return None


def _drive_time(node, scene=None):
    """frame / fps * time_scale, in world hours."""
    sock = node.outputs[0]
    # driver_remove on this socket only. NEVER animation_data_clear() on
    # node.id_data: that is the whole node GROUP, and clearing it took the
    # three drivers that track PLNT_SunDir out of PLNT_SurfaceShader with it.
    # The sun vector then read as a constant, the day/night mask in the
    # technology layer stopped meaning anything, and the volcanic and
    # night-side hero frames came back uniformly lit and three times too
    # bright, with nothing in the graph looking wrong.
    try:
        sock.driver_remove("default_value")
    except Exception:
        pass
    fc = sock.driver_add("default_value")
    d = fc.driver
    d.type = 'SCRIPTED'
    scene = scene or bpy.context.scene
    ensure_scene_props(scene)
    v = d.variables.new(); v.name = "ts"; v.type = 'SINGLE_PROP'
    t = v.targets[0]; t.id_type = 'SCENE'; t.id = scene
    t.data_path = '["%s"]' % SCENE_TS
    v2 = d.variables.new(); v2.name = "fps"; v2.type = 'SINGLE_PROP'
    t2 = v2.targets[0]; t2.id_type = 'SCENE'; t2.id = scene
    t2.data_path = "render.fps"
    # A zero fps is impossible in practice, but a driver that raises leaves the
    # value at whatever it was and is invisible until a render looks wrong.
    d.expression = "frame / max(fps, 1) * ts"
    return fc


def shader_time(tree, loc=(-3200, 1200), scene=None):
    """The PLNT_TIME value node of a shader tree, created on first use."""
    n = _by_label(tree, TIME_LABEL)
    if n is None:
        n = tree.nodes.new("ShaderNodeValue")
        n.label = TIME_LABEL
        n.name = TIME_LABEL
        n.location = loc
        _drive_time(n, scene)
    return n.outputs[0]


def geo_time(tree, loc=(-3200, 1200)):
    """World hours inside a geometry node tree: Scene Time x PLNT_TS.

    No driver: Scene Time already supplies the frame, and the scale is a plain
    number that sync() keeps up to date. One less thing that can silently stop
    evaluating.
    """
    mul = _by_label(tree, "PLNT_TIME_MUL")
    if mul is not None:
        return mul.outputs[0]
    st = tree.nodes.new("GeometryNodeInputSceneTime")
    st.location = (loc[0] - 200, loc[1])
    st.label = "PLNT_SCENETIME"
    ts = tree.nodes.new("ShaderNodeValue")
    ts.label = TS_LABEL
    ts.name = TS_LABEL
    ts.location = (loc[0] - 200, loc[1] - 140)
    ts.outputs[0].default_value = 1.0
    mul = tree.nodes.new("ShaderNodeMath")
    mul.operation = 'MULTIPLY'
    mul.label = "PLNT_TIME_MUL"
    mul.location = loc
    tree.links.new(st.outputs["Seconds"], mul.inputs[0])
    tree.links.new(ts.outputs[0], mul.inputs[1])
    return mul.outputs[0]


def tree_time(tree, loc=(-3200, 1200), scene=None):
    """World hours, whichever kind of node tree this is.

    Geometry nodes have a Scene Time node; shaders do not, and a Scene Time
    node created in a shader tree is accepted by the API and then evaluates to
    nothing, which is how the ring differential rotation was built, saved and
    reported as present while standing perfectly still. Dispatching on the tree
    type is the only way this stays correct as helpers get reused.
    """
    if getattr(tree, "bl_idname", "") == 'ShaderNodeTree':
        return shader_time(tree, loc, scene)
    return geo_time(tree, loc)


def geo_day(tree, loc=(-3200, 940)):
    """Rotation period in hours inside a geometry tree, written by sync()."""
    n = _by_label(tree, DAY_LABEL)
    if n is None:
        n = tree.nodes.new("ShaderNodeValue")
        n.label = DAY_LABEL
        n.name = DAY_LABEL
        n.location = loc
        n.outputs[0].default_value = 24.0
    return n.outputs[0]


def geo_spin_deg(tree, loc=(-3000, 940)):
    """Degrees the planet has turned: 360 * t / day_length."""
    have = _by_label(tree, "PLNT_SPIN")
    if have is not None:
        return have.outputs[0]
    t = tree_time(tree)
    d = geo_day(tree)
    div = tree.nodes.new("ShaderNodeMath"); div.operation = 'DIVIDE'
    div.location = (loc[0] - 180, loc[1])
    tree.links.new(t, div.inputs[0])
    tree.links.new(d, div.inputs[1])
    spin = tree.nodes.new("ShaderNodeMath"); spin.operation = 'MULTIPLY'
    spin.label = "PLNT_SPIN"; spin.name = "PLNT_SPIN"
    spin.location = loc
    spin.inputs[1].default_value = 360.0
    tree.links.new(div.outputs[0], spin.inputs[0])
    return spin.outputs[0]


def geo_orbit_rad(tree, r_over_R_socket_or_value, loc=(-2800, 700), label=""):
    """Orbit phase in RADIANS at a radius given in planet radii.

    angle = radians(360 / (T0 * (r/R)^1.5)) * t
    Built from nodes rather than baked to a constant so a rig whose orbital
    radius is a slider still obeys Kepler when the slider moves.
    """
    N = tree.nodes.new
    L = tree.links.new
    t = tree_time(tree)
    p = N("ShaderNodeMath"); p.operation = 'POWER'; p.location = (loc[0] - 360, loc[1])
    p.inputs[1].default_value = 1.5
    if hasattr(r_over_R_socket_or_value, "is_output"):
        L(r_over_R_socket_or_value, p.inputs[0])
    else:
        p.inputs[0].default_value = float(r_over_R_socket_or_value)
    per = N("ShaderNodeMath"); per.operation = 'MULTIPLY'
    per.location = (loc[0] - 180, loc[1])
    per.inputs[1].default_value = LEO_PERIOD_H
    L(p.outputs[0], per.inputs[0])
    safe = N("ShaderNodeMath"); safe.operation = 'MAXIMUM'
    safe.location = (loc[0] - 60, loc[1] - 120)
    safe.inputs[1].default_value = 1e-4
    L(per.outputs[0], safe.inputs[0])
    turns = N("ShaderNodeMath"); turns.operation = 'DIVIDE'
    turns.location = (loc[0], loc[1])
    L(t, turns.inputs[0])
    L(safe.outputs[0], turns.inputs[1])
    rad = N("ShaderNodeMath"); rad.operation = 'MULTIPLY'
    rad.location = (loc[0] + 180, loc[1])
    rad.label = label or "orbit phase"
    rad.inputs[1].default_value = math.tau
    L(turns.outputs[0], rad.inputs[0])
    return rad.outputs[0]


# --------------------------------------------------------------------------
# Object-level motion
# --------------------------------------------------------------------------
def _drive_rot_z(ob, expr, scene=None, extra=()):
    scene = scene or bpy.context.scene
    ensure_scene_props(scene)
    try:
        ob.driver_remove("rotation_euler", 2)
    except Exception:
        pass
    ob.rotation_mode = 'XYZ'
    fc = ob.driver_add("rotation_euler", 2)
    d = fc.driver
    d.type = 'SCRIPTED'
    for name, path in (("ts", '["%s"]' % SCENE_TS),
                       ("dl", '["%s"]' % SCENE_DAY),
                       ("fps", "render.fps")) + tuple(extra):
        v = d.variables.new(); v.name = name; v.type = 'SINGLE_PROP'
        t = v.targets[0]; t.id_type = 'SCENE'; t.id = scene
        t.data_path = path
    d.expression = expr
    return fc


# The globe turns; the shading is object-space, so terrain, cities and roads
# turn with it. The sun vector is transformed into object space inside every
# shader that uses it, which is what keeps the terminator standing still in
# world space while the surface rotates underneath it.
SPIN_EXPR = "frame / max(fps,1) * ts / max(dl,1e-6) * 6.283185307179586"

# Clouds turn with the planet plus a zonal drift. A 50 m/s jet on a 38000 km
# circumference is about 1.5 degrees of extra longitude per hour, which is why
# a weather system walks around a planet over a week rather than staying put.
CLOUD_EXPR = SPIN_EXPR + " + frame / max(fps,1) * ts * 0.02617993877991494"


def apply_object_motion(scene=None):
    """Drive the two objects whose whole body rotates."""
    scene = scene or bpy.context.scene
    out = {}
    g = bpy.data.objects.get("PLNT_Globe")
    if g:
        _drive_rot_z(g, SPIN_EXPR, scene)
        out["globe"] = SPIN_EXPR
    c = bpy.data.objects.get("PLNT_Clouds")
    if c:
        _drive_rot_z(c, CLOUD_EXPR, scene)
        out["clouds"] = CLOUD_EXPR
    return out


# --------------------------------------------------------------------------
# Keeping everything in step
# --------------------------------------------------------------------------
RIG_OBJECTS = ("PLNT_Globe", "PLNT_Clouds", "PLNT_Atmosphere", "PLNT_Rings",
               "PLNT_Orbital", "PLNT_Mega", "PLNT_Patch")


def sync(scene=None):
    """Push time_scale and day_length into every rig, and set motion blur.

    Called whenever the Time Scale or Day Length control changes. Writing the
    two numbers into the geometry trees is what lets the geometry side work
    without drivers; the shader side is already driven and needs nothing.
    """
    scene = scene or bpy.context.scene
    ensure_scene_props(scene)
    p = getattr(scene, "plnt", None)
    # The panel is the authority when it is there; the scene properties are the
    # authority when it is not, which is every headless render.
    if p is not None:
        scene[SCENE_TS] = float(getattr(p, "time_scale", 1.0))
        scene[SCENE_DAY] = float(getattr(p, "day_length_h", 24.0))
        scene[SCENE_BEACON] = float(getattr(p, "beacon_rate", 1.0))
    ts = float(scene[SCENE_TS])
    dl = float(scene[SCENE_DAY])
    n = 0
    for g in bpy.data.node_groups:
        if not g.name.startswith("PLNT"):
            continue
        for node in g.nodes:
            if node.label == TS_LABEL:
                node.outputs[0].default_value = ts
                n += 1
            elif node.label == DAY_LABEL:
                node.outputs[0].default_value = max(1e-6, dl)
                n += 1
    if p is not None:
        scene.render.use_motion_blur = bool(getattr(p, "motion_blur", False))
    for name in RIG_OBJECTS:
        ob = bpy.data.objects.get(name)
        if ob:
            ob.update_tag()
    # A frozen system should look identical to the v2 stills, so make sure the
    # drivers are re-evaluated rather than left holding the previous frame.
    try:
        scene.frame_set(scene.frame_current)
    except Exception:
        pass
    return {"nodes": n, "time_scale": ts, "day_length_h": dl,
            "beacon_rate": float(scene[SCENE_BEACON]),
            "motion_blur": scene.render.use_motion_blur}


def set_time(scene=None, time_scale=None, day_length_h=None, beacon_rate=None):
    """Set the clock from code (headless renders, tests), then re-sync.

    Writes the scene properties first so this works with or without the add-on
    registered, and mirrors into the panel when the panel exists.
    """
    scene = scene or bpy.context.scene
    ensure_scene_props(scene)
    if time_scale is not None:
        scene[SCENE_TS] = float(time_scale)
    if day_length_h is not None:
        scene[SCENE_DAY] = float(day_length_h)
    if beacon_rate is not None:
        scene[SCENE_BEACON] = float(beacon_rate)
    p = getattr(scene, "plnt", None)
    if p is not None:
        p.time_scale = float(scene[SCENE_TS])
        p.day_length_h = float(scene[SCENE_DAY])
        p.beacon_rate = float(scene[SCENE_BEACON])
        return sync(scene)
    # sync() would copy the panel back over what was just set, so do the
    # geometry-side write here instead.
    n = 0
    for g in bpy.data.node_groups:
        if not g.name.startswith("PLNT"):
            continue
        for node in g.nodes:
            if node.label == TS_LABEL:
                node.outputs[0].default_value = float(scene[SCENE_TS])
                n += 1
            elif node.label == DAY_LABEL:
                node.outputs[0].default_value = max(1e-6, float(scene[SCENE_DAY]))
                n += 1
    for name in RIG_OBJECTS:
        ob = bpy.data.objects.get(name)
        if ob:
            ob.update_tag()
    try:
        scene.frame_set(scene.frame_current)
    except Exception:
        pass
    return {"nodes": n, "time_scale": float(scene[SCENE_TS]),
            "day_length_h": float(scene[SCENE_DAY]),
            "beacon_rate": float(scene[SCENE_BEACON])}


def rates_table(day_length_h=24.0):
    """What every moving part actually does, for the report and the docs."""
    rows = [("Planet surface", 1.0, 360.0 / max(day_length_h, 1e-6)),
            ("Cloud deck", 1.0, 360.0 / max(day_length_h, 1e-6) + 1.5)]
    for label, r in (("Satellites (low)", 1.02), ("Satellites (high)", 1.16),
                     ("Orbital band 1", 1.24), ("Orbital band 2", 1.34),
                     ("Orbital band 3", 1.46),
                     ("Ring inner edge", 1.35), ("Ring outer edge", 2.30),
                     ("Mirror belt", 1.90), ("Ringworld arcs", 2.70),
                     ("Dyson swarm", 4.40)):
        rows.append((label, r, omega_deg_h(r)))
    return [(lbl, r, round(w, 1), round(360.0 / w, 2)) for lbl, r, w in rows]
