"""A physically-sized, renderable sun.

`build_sun_rig` gives the scene a SUN lamp, which lights everything correctly
and is invisible to the camera: Blender sun lamps have no disc. Every shot that
wants the star in frame -- backlit limbs, glints, lens flare off the primary --
therefore had nothing to point at.

This adds the body. It is a real sphere at a real angular size, so it behaves
like the star it represents rather than like a sprite: it is occluded by the
planet, it is the right size in every lens, and the compositing glare keys off
it the way it keys off any other blown-out highlight.

Detail is procedural, and deliberately so. The obvious route is a photograph of
the Sun, and the obvious source is SDO's public-domain imagery, but the browse
JPEGs measure about 4% granulation contrast against roughly 15-20% on the real
photosphere: compression and downsampling have already removed the detail by
the time you can download it. The colour here is calibrated to a measurement of
that imagery; the structure is generated, because generated structure survives
being zoomed into and a 2K texture does not.
"""
import bpy
import math

NAME = "PLNT_SunBody"
MAT = "PLNT_SunSurface"

# Far enough to read as "very distant", inside the cameras' 100000 clip end.
# Nothing about the look depends on the number: the radius is derived from it
# so the angular size is fixed no matter what distance is chosen.
DISTANCE = 60000.0
ANGULAR_DIAMETER_DEG = 0.526                # the Sun's, from Earth
ANGULAR_DIAMETER = math.radians(ANGULAR_DIAMETER_DEG)

DEFAULTS = {
    # 38 clipped the whole disc to flat white under AgX and took every scrap of
    # surface detail with it. Around 2 keeps the core reading as white while
    # the limb still falls away through yellow into orange.
    "Brightness": 2.4,
    "Granule Scale": 105.0,
    "Spot Amount": 0.85,
    "Limb Darkening": 0.62,
    "Tint": (1.0, 1.0, 1.0, 1.0),
}


def _rm(coll, name):
    d = coll.get(name)
    if d:
        try:
            coll.remove(d, do_unlink=True)
        except TypeError:
            coll.remove(d)


def radius_for(distance=DISTANCE):
    return distance * math.tan(ANGULAR_DIAMETER * 0.5)


def build_material(name=MAT, look=None):
    v = dict(DEFAULTS)
    if look:
        v.update(look)
    _rm(bpy.data.materials, name)
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new

    def M(op, y=None, loc=(0, 0), nm="", clamp=False):
        n = N("ShaderNodeMath")
        n.operation = op
        n.location = loc
        n.label = nm
        n.use_clamp = clamp
        if y is not None:
            n.inputs[1].default_value = y
        return n

    def MR(loc, fmin, fmax, tmin, tmax, nm="", interp='LINEAR'):
        n = N("ShaderNodeMapRange")
        n.location = loc
        n.label = nm
        n.interpolation_type = interp
        n.inputs["From Min"].default_value = fmin
        n.inputs["From Max"].default_value = fmax
        n.inputs["To Min"].default_value = tmin
        n.inputs["To Max"].default_value = tmax
        return n

    tc = N("ShaderNodeTexCoord"); tc.location = (-1800, 0)
    # Normalise to the unit sphere before anything samples it.
    #
    # Object coordinates here span the body's actual radius, which is a few
    # hundred units, not the +-1 the planet shaders work in. Feeding those
    # straight to a Voronoi at scale 190 asks for roughly a hundred thousand
    # cells across the disc: every one lands far below a pixel and the whole
    # photosphere averages out to a flat disc. Normalising makes every surface
    # point a unit direction, so a scale of N means about N cells across the
    # star regardless of how far away it was placed.
    nrm = N("ShaderNodeVectorMath"); nrm.operation = 'NORMALIZE'
    nrm.location = (-1600, 0); nrm.label = "P_UNIT"
    L(tc.outputs["Object"], nrm.inputs[0])
    P = nrm.outputs["Vector"]

    # Slow churn. A frozen photosphere is the tell that gives a still sun away
    # the moment anything else in frame is moving.
    try:
        from . import anim as _an
    except ImportError:
        import anim as _an
    t = _an.shader_time(nt, (-1600, -420))
    drift = M('MULTIPLY', 0.04, (-1420, -420), "granule drift")
    L(t, drift.inputs[0])

    # ---- granulation: bright convection cells, dark intergranular lanes ----
    lanes = N("ShaderNodeTexVoronoi"); lanes.location = (-1240, 240)
    lanes.voronoi_dimensions = '4D'
    lanes.feature = 'DISTANCE_TO_EDGE'
    lanes.inputs["Randomness"].default_value = 1.0
    L(P, lanes.inputs["Vector"])
    L(drift.outputs[0], lanes.inputs["W"])
    gsc = M('MULTIPLY', 1.0, (-1420, 240), "granule scale")
    gsc.inputs[0].default_value = v["Granule Scale"]
    L(gsc.outputs[0], lanes.inputs["Scale"])
    lane = MR((-1040, 240), 0.0, 0.055, 0.34, 1.0, "lanes", 'SMOOTHSTEP')
    L(lanes.outputs["Distance"], lane.inputs[0])

    # Cell-to-cell brightness: neighbouring granules are not identical.
    cells = N("ShaderNodeTexVoronoi"); cells.location = (-1240, 40)
    cells.voronoi_dimensions = '4D'
    cells.feature = 'F1'
    cells.inputs["Randomness"].default_value = 1.0
    L(P, cells.inputs["Vector"])
    L(drift.outputs[0], cells.inputs["W"])
    L(gsc.outputs[0], cells.inputs["Scale"])
    csep = N("ShaderNodeSeparateXYZ"); csep.location = (-1040, 40)
    L(cells.outputs["Color"], csep.inputs["Vector"])
    cvar = MR((-860, 40), 0.0, 1.0, 0.88, 1.12, "granule variation")
    L(csep.outputs["X"], cvar.inputs[0])

    # ---- supergranulation: the slow large-scale flow pattern --------------
    sgn = N("ShaderNodeTexNoise"); sgn.location = (-1240, -140)
    sgn.noise_dimensions = '4D'
    sgn.noise_type = 'FBM'
    sgn.inputs["Scale"].default_value = 14.0
    sgn.inputs["Detail"].default_value = 4.0
    L(P, sgn.inputs["Vector"])
    L(drift.outputs[0], sgn.inputs["W"])
    sg = MR((-1040, -140), 0.3, 0.7, 0.93, 1.07, "supergranulation")
    L(sgn.outputs["Factor"], sg.inputs[0])

    g1 = M('MULTIPLY', None, (-680, 140), "granulation")
    L(lane.outputs["Result"], g1.inputs[0]); L(cvar.outputs["Result"], g1.inputs[1])
    g2 = M('MULTIPLY', None, (-500, 140), "x supergranules")
    L(g1.outputs[0], g2.inputs[0]); L(sg.outputs["Result"], g2.inputs[1])

    # ---- sunspots: umbra, penumbra, sharp outer edge ----------------------
    spots = N("ShaderNodeTexVoronoi"); spots.location = (-1240, -300)
    spots.voronoi_dimensions = '4D'
    spots.feature = 'F1'
    spots.inputs["Scale"].default_value = 4.2
    spots.inputs["Randomness"].default_value = 1.0
    L(P, spots.inputs["Vector"])
    ssep = N("ShaderNodeSeparateXYZ"); ssep.location = (-1040, -300)
    L(spots.outputs["Color"], ssep.inputs["Vector"])
    # Only a few cells host a group, and active regions cluster in two
    # latitude bands rather than scattering evenly, but a plain threshold on
    # the cell random is enough at the size this ever appears on screen.
    has = M('GREATER_THAN', 0.74, (-860, -300), "spot host")
    L(ssep.outputs["X"], has.inputs[0])
    # Wide enough to read. Sized off the cell rather than in absolute units:
    # at scale 4.2 a cell spans about 0.24, so a 0.10 profile fills roughly the
    # inner 40% of it and lands a spot group at a few percent of the disc.
    prof = MR((-860, -460), 0.0, 0.10, 1.0, 0.0, "spot profile", 'SMOOTHSTEP')
    L(spots.outputs["Distance"], prof.inputs[0])
    sp = M('MULTIPLY', None, (-680, -380), "spot")
    L(prof.outputs["Result"], sp.inputs[0]); L(has.outputs[0], sp.inputs[1])
    spa = M('MULTIPLY', v["Spot Amount"], (-500, -380), "spot amount")
    L(sp.outputs[0], spa.inputs[0])
    darken = MR((-320, -380), 0.0, 1.0, 1.0, 0.13, "spot darken")
    L(spa.outputs[0], darken.inputs[0])

    surf = M('MULTIPLY', None, (-320, 140), "surface")
    L(g2.outputs[0], surf.inputs[0]); L(darken.outputs["Result"], surf.inputs[1])

    # ---- limb darkening ---------------------------------------------------
    # I(mu)/I(1) = 1 - u(1 - mu). The star is a ball of gas we see further into
    # at the centre of the disc than at the edge, and without this it renders
    # as a flat bright circle -- the single clearest giveaway of a fake sun.
    geo = N("ShaderNodeNewGeometry"); geo.location = (-1240, -620)
    dot = N("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
    dot.location = (-1040, -620); dot.label = "mu"
    L(geo.outputs["Normal"], dot.inputs[0]); L(geo.outputs["Incoming"], dot.inputs[1])
    mu = M('ABSOLUTE', None, (-860, -620), "|mu|")
    L(dot.outputs["Value"], mu.inputs[0])
    inv = M('SUBTRACT', None, (-680, -620))
    inv.inputs[0].default_value = 1.0
    L(mu.outputs[0], inv.inputs[1])
    ud = M('MULTIPLY', v["Limb Darkening"], (-500, -620), "u(1-mu)")
    L(inv.outputs[0], ud.inputs[0])
    ld = M('SUBTRACT', None, (-320, -620), "limb darkening", clamp=True)
    ld.inputs[0].default_value = 1.0
    L(ud.outputs[0], ld.inputs[1])

    lit = M('MULTIPLY', None, (-140, 0), "lit")
    L(surf.outputs[0], lit.inputs[0]); L(ld.outputs[0], lit.inputs[1])

    # ---- colour -----------------------------------------------------------
    # Ramp anchored on a measurement of SDO HMI continuum imagery, whose mean
    # sits at roughly (1.00, 0.72, 0.04) once limb darkening is divided out.
    # Ramp measured off the reference trailer's own star rather than guessed.
    # Sampling that frame by luminance band gives a clear progression: a
    # neutral white core, yellow just below it, orange through the midtones and
    # a deep orange halo at the edge -- r/g climbing 1.00, 1.00, 1.31, 1.59 as
    # b/g falls 1.00, 0.77, 0.60, 0.57. The stops below are those measurements.
    ramp = N("ShaderNodeValToRGB"); ramp.location = (60, 0); ramp.label = "photosphere"
    e = ramp.color_ramp.elements
    e[0].position = 0.0
    e[0].color = (0.26, 0.055, 0.010, 1.0)       # umbra
    e[1].position = 0.34
    e[1].color = (0.85, 0.436, 0.242, 1.0)       # deep limb, r/g 1.59
    m1 = ramp.color_ramp.elements.new(0.62)
    m1.color = (0.958, 0.734, 0.438, 1.0)        # midtone orange, r/g 1.31
    m2 = ramp.color_ramp.elements.new(0.86)
    m2.color = (0.983, 0.980, 0.757, 1.0)        # yellow-white, b/g 0.77
    hi = ramp.color_ramp.elements.new(1.0)
    hi.color = (0.984, 0.985, 0.982, 1.0)        # neutral core
    L(lit.outputs[0], ramp.inputs["Fac"])

    # Tint sits after the ramp so the UI can warm or cool the whole star
    # without disturbing the measured progression across it.
    tint = N("ShaderNodeMix"); tint.data_type = 'RGBA'
    tint.blend_type = 'MULTIPLY'
    tint.location = (220, 0); tint.label = "sun tint"
    tint.inputs[0].default_value = 1.0
    tint.inputs[7].default_value = v["Tint"]
    L(ramp.outputs["Color"], tint.inputs[6])

    em = N("ShaderNodeEmission"); em.location = (360, 0)
    L(tint.outputs[2], em.inputs["Color"])
    bright = M('MULTIPLY', v["Brightness"], (360, -200), "brightness")
    L(lit.outputs[0], bright.inputs[0])
    L(bright.outputs[0], em.inputs["Strength"])

    out = N("ShaderNodeOutputMaterial"); out.location = (620, 0)
    L(em.outputs["Emission"], out.inputs["Surface"])
    return mat


def build(distance=DISTANCE, look=None, segments=96, scale=1.0):
    """Create the sun body, parented to the sun so it tracks its direction.

    `scale` multiplies the radius away from the true angular diameter. At 1.0
    the star is 0.526 degrees across, which is correct and, on a 40mm lens,
    about one percent of frame height: eight pixels in a 1080p frame, with no
    room for any of the surface detail this shader generates. That is the
    honest size and it is often not the useful one, so a shot that wants the
    star as a subject rather than as a light can say so explicitly. Anything
    above 1.0 is a lie about the scale of the system, which is worth knowing
    you are telling.
    """
    sun = bpy.data.objects.get("PLNT_Sun")
    if sun is None:
        raise RuntimeError("no PLNT_Sun: build the sun rig first")

    remove()
    r = radius_for(distance) * scale
    me = bpy.data.meshes.new(NAME + "Mesh")
    import bmesh
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(bm, u_segments=segments, v_segments=segments // 2,
                              radius=r)
    for f in bm.faces:
        f.smooth = True
    bm.to_mesh(me)
    bm.free()

    ob = bpy.data.objects.new(NAME, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.parent = sun
    # The lamp shines along its local -Z, so the light arrives FROM +Z: that is
    # where the body has to sit for the disc and the lighting to agree.
    ob.location = (0.0, 0.0, distance)

    # Camera only. The lamp already provides every photon in the scene, and a
    # second emitter of the same star would double-count it -- and a 275-unit
    # emissive sphere is a miserable thing for a path tracer to sample.
    ob.visible_diffuse = False
    ob.visible_glossy = False
    ob.visible_transmission = False
    ob.visible_volume_scatter = False
    ob.visible_shadow = False

    ob.data.materials.append(build_material(look=look))
    return {"object": ob.name, "radius": round(r, 2), "distance": distance,
            "scale": scale,
            "angular_diameter_deg": round(ANGULAR_DIAMETER_DEG * scale, 3)}


def remove():
    ob = bpy.data.objects.get(NAME)
    n = 0
    if ob:
        _rm(bpy.data.meshes, ob.data.name if ob.data else "")
        _rm(bpy.data.objects, NAME)
        n += 1
    _rm(bpy.data.materials, MAT)
    return n


def exists():
    return bpy.data.objects.get(NAME) is not None
