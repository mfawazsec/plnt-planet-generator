"""Post-processing: the difference between a render and a shot.

Everything here is a camera artefact, not a filter. Cycles hands back a linear
HDR image of a scene lit by one very bright, very distant light against a black
sky, which is the highest-contrast subject there is. A real telescope or a real
spacecraft camera pointed at that would show halation around the bright limb,
a little chromatic spread at the frame edge, some falloff into the corners and
a floor of sensor noise. None of that is in the raw render, and its absence is
most of what reads as "CG" in an otherwise correct frame.

Order matters and follows the light path through a real system:

    glare      -> in the optics, before anything else touches the image
    grade      -> the colourist's pass on the captured image
    dispersion -> the lens again, at the edges of the frame
    vignette   -> the lens/sensor falloff
    grain      -> the sensor, last, so nothing downstream smears it

Blender 5 moved the compositor onto `scene.compositing_node_group`, a real
node group rather than the old per-scene tree, and its nodes take their
settings as sockets instead of RNA properties. Both are why this module looks
nothing like a 4.x compositing script.
"""
import bpy

GROUP = "PLNT_Comp"

# One place to retune the whole look.
LOOK = {
    # Halation. Threshold is in scene-linear units, so it keys off what is
    # genuinely bright -- sun glint, lava, city cores -- and leaves the
    # midtones of a lit disc alone.
    "bloom_threshold": 1.10,
    "bloom_strength": 0.10,
    "bloom_size": 8,
    # Streaks, kept subtle. Six of them reads as a lens, four reads as a
    # lens flare plugin.
    "streak_threshold": 6.00,
    "streak_strength": 0.010,
    "streaks": 6,
    "streak_fade": 0.88,
    "streak_size": 6,
    # Cool the shadows, warm the highlights. A degree of separation between
    # the black of space and the light of a G-type star, nothing more. Kept
    # deliberately shallow: a neutral-grey subject like an airless moon has
    # nothing to hide a colour cast behind, and the first pass at these
    # values turned one blue.
    "lift": (0.992, 0.997, 1.010, 1.0),
    "gain": (1.018, 1.000, 0.982, 1.0),
    # Lens dispersion only. Distortion is deliberately 0: barrel distortion
    # would bend the limb, and the limb of a planet is a circle. Bending it
    # is the one artefact an audience reads as an error rather than as a lens.
    "dispersion": 0.012,
    # Corner falloff, measured from the centre in uniform coordinates.
    "vignette_start": 0.72,
    "vignette_end": 1.45,
    "vignette_depth": 0.88,
    # Sensor floor. High enough to break up denoiser flatness in the dark
    # sky, low enough that a still frame does not look dirty.
    "grain": 0.012,
}


def _mix(g, blend, loc, label=""):
    n = g.nodes.new("ShaderNodeMix")
    n.data_type = 'RGBA'
    n.blend_type = blend
    n.location = loc
    n.label = label
    n.inputs[0].default_value = 1.0
    return n


def build(look=None):
    """Create (or rebuild) the compositing group. Returns the node group."""
    v = dict(LOOK)
    if look:
        v.update(look)

    old = bpy.data.node_groups.get(GROUP)
    if old:
        bpy.data.node_groups.remove(old)
    g = bpy.data.node_groups.new(GROUP, "CompositorNodeTree")
    N, L = g.nodes.new, g.links.new

    # The scene's compositing group is not fed through its Group Input: a
    # group with an Image input renders black, because nothing binds the
    # render result to that socket. The render enters through a Render Layers
    # node inside the group, exactly as it did in the old per-scene tree, and
    # only the output is a group socket.
    g.interface.new_socket("Image", in_out='OUTPUT', socket_type='NodeSocketColor')
    gi = N("CompositorNodeRLayers"); gi.location = (-1400, 0)
    gi.scene = bpy.context.scene
    go = N("NodeGroupOutput"); go.location = (1500, 0)

    # ---- glare -------------------------------------------------------------
    bloom = N("CompositorNodeGlare"); bloom.location = (-1150, 0)
    bloom.label = "halation"
    # Blender 5's menu sockets take the label, not an UPPER_CASE identifier.
    bloom.inputs["Type"].default_value = 'Bloom'
    bloom.inputs["Quality"].default_value = 'High'
    bloom.inputs["Threshold"].default_value = v["bloom_threshold"]
    bloom.inputs["Strength"].default_value = v["bloom_strength"]
    bloom.inputs["Size"].default_value = v["bloom_size"]
    L(gi.outputs["Image"], bloom.inputs["Image"])

    streak = N("CompositorNodeGlare"); streak.location = (-900, 0)
    streak.label = "streaks"
    streak.inputs["Type"].default_value = 'Streaks'
    streak.inputs["Quality"].default_value = 'High'
    streak.inputs["Threshold"].default_value = v["streak_threshold"]
    streak.inputs["Strength"].default_value = v["streak_strength"]
    streak.inputs["Streaks"].default_value = v["streaks"]
    streak.inputs["Fade"].default_value = v["streak_fade"]
    streak.inputs["Size"].default_value = v["streak_size"]
    L(bloom.outputs["Image"], streak.inputs["Image"])

    # ---- grade -------------------------------------------------------------
    cb = N("CompositorNodeColorBalance"); cb.location = (-650, 0)
    cb.label = "grade"
    cb.inputs["Type"].default_value = 'Lift/Gamma/Gain'
    # Both a float and a colour socket carry each name; the colour one is the
    # one the node actually uses, and it is always the later of the two.
    def setcol(name, value):
        socks = [s for s in cb.inputs if s.name == name and s.type == 'RGBA']
        socks[-1].default_value = value
    setcol("Lift", v["lift"])
    setcol("Gain", v["gain"])
    L(streak.outputs["Image"], cb.inputs["Image"])

    # ---- lens --------------------------------------------------------------
    ld = N("CompositorNodeLensdist"); ld.location = (-400, 0)
    ld.label = "dispersion"
    ld.inputs["Distortion"].default_value = 0.0
    ld.inputs["Dispersion"].default_value = v["dispersion"]
    L(cb.outputs["Image"], ld.inputs["Image"])

    # ---- vignette ----------------------------------------------------------
    ic = N("CompositorNodeImageCoordinates"); ic.location = (-1150, -400)
    L(gi.outputs["Image"], ic.inputs["Image"])
    rad = N("ShaderNodeVectorMath"); rad.operation = 'LENGTH'
    rad.location = (-950, -400); rad.label = "radius"
    L(ic.outputs["Uniform"], rad.inputs[0])
    vig = N("ShaderNodeMapRange"); vig.location = (-750, -400); vig.label = "vignette"
    vig.interpolation_type = 'SMOOTHSTEP'
    vig.inputs["From Min"].default_value = v["vignette_start"]
    vig.inputs["From Max"].default_value = v["vignette_end"]
    vig.inputs["To Min"].default_value = 1.0
    vig.inputs["To Max"].default_value = v["vignette_depth"]
    L(rad.outputs["Value"], vig.inputs["Value"])
    vmul = _mix(g, 'MULTIPLY', (-150, 0), "apply vignette")
    L(ld.outputs["Image"], vmul.inputs[6])
    L(vig.outputs["Result"], vmul.inputs[7])

    # ---- grain -------------------------------------------------------------
    # White noise needs a coordinate that differs per pixel AND per frame, or
    # the grain freezes into a fixed dirt pattern that reads as a dirty lens
    # the moment the camera moves. Frame number on the 4th axis fixes that
    # and costs one socket.
    st = N("CompositorNodeSceneTime"); st.location = (-950, -700)
    gsc = N("ShaderNodeVectorMath"); gsc.operation = 'SCALE'
    gsc.location = (-750, -620); gsc.label = "grain coords"
    L(ic.outputs["Uniform"], gsc.inputs[0])
    gsc.inputs["Scale"].default_value = 1370.0
    wn = N("ShaderNodeTexWhiteNoise"); wn.location = (-550, -620)
    wn.noise_dimensions = '4D'
    L(gsc.outputs["Vector"], wn.inputs["Vector"])
    L(st.outputs["Frame"], wn.inputs["W"])
    gctr = N("ShaderNodeMath"); gctr.operation = 'SUBTRACT'
    gctr.location = (-350, -620); gctr.inputs[1].default_value = 0.5
    L(wn.outputs["Value"], gctr.inputs[0])
    gamt = N("ShaderNodeMath"); gamt.operation = 'MULTIPLY'
    gamt.location = (-150, -620); gamt.label = "grain amount"
    gamt.inputs[1].default_value = v["grain"]
    L(gctr.outputs["Value"], gamt.inputs[0])
    gadd = _mix(g, 'ADD', (250, 0), "apply grain")
    L(vmul.outputs[2], gadd.inputs[6])
    L(gamt.outputs["Value"], gadd.inputs[7])

    L(gadd.outputs[2], go.inputs["Image"])
    return g


def attach(scene=None, look=None, rebuild=True):
    """Build the group if needed and hand it to the scene."""
    sc = scene or bpy.context.scene
    g = bpy.data.node_groups.get(GROUP)
    if g is None or rebuild:
        g = build(look)
    sc.use_nodes = True
    sc.compositing_node_group = g
    return {"group": g.name, "nodes": len(g.nodes), "attached": True}


def detach(scene=None):
    """Raw render, for A/B comparison and for anyone grading downstream."""
    sc = scene or bpy.context.scene
    sc.compositing_node_group = None
    return {"attached": False}
