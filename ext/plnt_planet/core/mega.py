"""Megastructures: solar mirror belts, ringworld arcs, Dyson swarm.

Lives on its own PLNT_Mega object so it can be hidden, re-seeded or removed
without touching the orbital rig, and so its geometry is not evaluated at all
when Tech Level is below the activation threshold.

Two things learned the hard way elsewhere in this project apply here:

* No perfectly smooth mirrors. A roughness of exactly 0 on a large curved
  reflector generates non-converging fireflies that survive denoising; a small
  roughness floor costs nothing and removes them.
* Materials go on before geometry becomes an instance. Set Material does not
  reach inside instances.
"""
import bpy
import math

try:
    from . import anim as _anim
except ImportError:
    import anim as _anim

try:
    from .nodeutil import sockin, sockout, new_socket
except ImportError:
    from nodeutil import sockin, sockout, new_socket

MEGA_IN = [
    ("Mega Scale", 'NodeSocketFloat', 0.0, 0.0, 10.0,
     "Overall size of the orbital megastructures. Below 0.5 nothing is built"),
    ("Radius", 'NodeSocketFloat', 1000.0, 1.0, 1e6,
     "Planet radius the structures are placed around"),
    ("Seed", 'NodeSocketFloat', 0.0, -10000.0, 10000.0,
     "Random seed for placement"),
    ("Mirror Orbit", 'NodeSocketFloat', 1.9, 1.05, 12.0,
     "Orbital radius of the solar mirror belt, in planet radii"),
    ("Mirror Count", 'NodeSocketInt', 90, 0, 2000,
     "Number of mirrors in the equatorial belt"),
    ("Mirror Size", 'NodeSocketFloat', 62.0, 1.0, 2000.0,
     "Size of an individual mirror panel"),
    ("Ring Orbit", 'NodeSocketFloat', 2.7, 1.1, 20.0,
     "Orbital radius of the partial ringworld arcs, in planet radii"),
    ("Ring Sweep", 'NodeSocketFloat', 130.0, 5.0, 360.0,
     "How far around the planet each ringworld arc reaches, in degrees"),
    ("Ring Width", 'NodeSocketFloat', 120.0, 1.0, 3000.0,
     "Width of the ringworld habitat band"),
    ("Arc Count", 'NodeSocketInt', 3, 0, 24,
     "Number of separate ringworld arcs"),
    ("Habitat Glow", 'NodeSocketFloat', 1.0, 0.0, 20.0,
     "Brightness of the inhabited inner face of the ringworld arcs"),
    ("Swarm Count", 'NodeSocketInt', 240, 0, 6000,
     "Number of collectors in the Dyson swarm"),
    ("Material", 'NodeSocketMaterial', None, None, None,
     "Structural material"),
    ("Mirror Material", 'NodeSocketMaterial', None, None, None,
     "Reflective material for the mirror panels"),
    ("Glow Material", 'NodeSocketMaterial', None, None, None,
     "Emissive material for inhabited inner faces"),
    ("Arc Motion", 'NodeSocketInt', 0, 0, 2,
     "How the ringworld arcs move. 0 Orbiting: free fall at the Kepler rate "
     "for their radius. 1 Locked: turning with the planet. 2 Inertial: fixed "
     "against the stars"),
]


def _new_any(g, *idnames):
    """First node type that exists in this build.

    Node identifiers move between releases (FunctionNodeAlignEulerToVector
    became FunctionNodeAlignRotationToVector), and creating a missing type
    raises at build time rather than failing quietly.
    """
    last = None
    for nid in idnames:
        try:
            return g.nodes.new(nid)
        except Exception as ex:
            last = ex
    raise RuntimeError("none of %r exist in this Blender: %s" % (idnames, last))


def _sun_dir(g, loc=(-2200, 400)):
    """Unit vector toward the sun, read from the PLNT_SunDir empty.

    Geometry nodes can read an object transform directly through Object Info,
    so unlike the shaders this needs no drivers at all: move the sun and every
    mirror in the belt re-aims on the next evaluation.
    """
    have = None
    for n in g.nodes:
        if n.label == "SUNDIR":
            have = n
            break
    if have is not None:
        return have.outputs[0]
    oi = g.nodes.new("GeometryNodeObjectInfo")
    oi.location = loc
    oi.label = "SUNDIR_OBJ"
    tgt = bpy.data.objects.get("PLNT_SunDir")
    if tgt is not None:
        try:
            oi.inputs["Object"].default_value = tgt
        except Exception:
            pass
    nrm = g.nodes.new("ShaderNodeVectorMath")
    nrm.operation = 'NORMALIZE'
    nrm.location = (loc[0] + 200, loc[1])
    nrm.label = "SUNDIR"
    g.links.new(sockout(oi, "Location"), nrm.inputs[0])
    return nrm.outputs[0]


def _motion_angle(g, S, mode_socket, r_over_R, loc, label):
    """Orbiting / Locked to surface / Inertial, in radians."""
    ph = _anim.geo_orbit_rad(g, r_over_R, loc=(loc[0] - 400, loc[1] + 140),
                             label=label + " orbit")
    spin = _anim.geo_spin_deg(g)
    spinr = _M(g, 'MULTIPLY', y=0.017453292519943295, loc=(loc[0] - 220, loc[1] - 80))
    g.links.new(spin, spinr.inputs[0])
    e0 = _M(g, 'COMPARE', y=0.0, loc=(loc[0] - 220, loc[1] + 220))
    e0.inputs[2].default_value = 0.5
    g.links.new(mode_socket, e0.inputs[0])
    e1 = _M(g, 'COMPARE', y=1.0, loc=(loc[0] - 220, loc[1] + 140))
    e1.inputs[2].default_value = 0.5
    g.links.new(mode_socket, e1.inputs[0])
    a = _M(g, 'MULTIPLY', loc=(loc[0] - 60, loc[1] + 140))
    g.links.new(ph, a.inputs[0]); g.links.new(e0.outputs[0], a.inputs[1])
    b = _M(g, 'MULTIPLY', loc=(loc[0] - 60, loc[1] - 80))
    g.links.new(spinr.outputs[0], b.inputs[0]); g.links.new(e1.outputs[0], b.inputs[1])
    tot = _M(g, 'ADD', loc=loc, nm=label)
    g.links.new(a.outputs[0], tot.inputs[0]); g.links.new(b.outputs[0], tot.inputs[1])
    return tot.outputs[0]


def _setmat(g, geo, mat_socket, loc):
    n = g.nodes.new("GeometryNodeSetMaterial")
    n.location = loc
    g.links.new(geo, sockin(n, "Geometry"))
    g.links.new(mat_socket, sockin(n, "Material"))
    return sockout(n, "Geometry")


def _M(g, op, x=None, y=None, loc=(0, 0), nm=""):
    n = g.nodes.new("ShaderNodeMath")
    n.operation = op; n.location = loc; n.label = nm
    if x is not None:
        n.inputs[0].default_value = x
    if y is not None:
        n.inputs[1].default_value = y
    return n


def _VM(g, op, loc=(0, 0), nm=""):
    n = g.nodes.new("ShaderNodeVectorMath")
    n.operation = op; n.location = loc; n.label = nm
    return n


def _mirror_belt(g, S, gate, y=800):
    """An equatorial belt of flat mirrors, each turned to face outward.

    Points come from a circle rather than a sphere: a solar mirror belt sits in
    the orbital plane, and scattering them over a sphere reads as debris.
    """
    N, L = g.nodes.new, g.links.new
    circ = N("GeometryNodeCurvePrimitiveCircle"); circ.location = (-1600, y)
    rr = _M(g, 'MULTIPLY', loc=(-1800, y - 120))
    L(S["Radius"], rr.inputs[0]); L(S["Mirror Orbit"], rr.inputs[1])
    L(rr.outputs[0], sockin(circ, "Radius"))
    sockin(circ, "Resolution").default_value = 256

    # The belt orbits at its own Kepler rate: 1.9 R is about 98 degrees an
    # hour, so at Timelapse the whole array walks round the planet in under
    # four seconds of footage. Rotating the CURVE rather than the finished
    # instances matters, because the aim of each mirror is computed from where
    # it is, and a mirror that turns with the belt stops facing the sun.
    mphase = _anim.geo_orbit_rad(g, S["Mirror Orbit"], loc=(-1800, y + 300),
                                 label="mirror belt phase")
    mrotv = N("ShaderNodeCombineXYZ"); mrotv.location = (-1620, y + 300)
    L(mphase, mrotv.inputs[2])
    mspin = N("GeometryNodeTransform"); mspin.location = (-1480, y + 160)
    mspin.label = "belt spin"
    L(sockout(circ, "Curve"), sockin(mspin, "Geometry"))
    L(sockout(mrotv, "Vector"), sockin(mspin, "Rotation"))

    c2p = N("GeometryNodeCurveToPoints"); c2p.location = (-1400, y)
    c2p.mode = 'COUNT'
    L(S["Mirror Count"], sockin(c2p, "Count"))
    L(sockout(mspin, "Geometry"), sockin(c2p, "Curve"))

    panel = N("GeometryNodeMeshGrid"); panel.location = (-1400, y - 260)
    L(S["Mirror Size"], sockin(panel, "Size X"))
    L(S["Mirror Size"], sockin(panel, "Size Y"))
    sockin(panel, "Vertices X").default_value = 2
    sockin(panel, "Vertices Y").default_value = 2
    pmat = _setmat(g, sockout(panel, "Mesh"), S["Mirror Material"], (-1200, y - 260))

    ion = N("GeometryNodeInstanceOnPoints"); ion.location = (-1000, y)
    L(sockout(c2p, "Points"), sockin(ion, "Points"))
    L(pmat, sockin(ion, "Instance"))

    # Heliostat aim.
    #
    # A solar mirror belt exists to put sunlight somewhere. Facing outward is
    # the one thing it must never do: that reflects the sun back into space.
    # A mirror that takes light from the sun and lays it on the planet below
    # bisects the two directions, so its normal is the half vector between
    # "toward the sun" and "toward the planet centre". As the belt orbits, the
    # half vector swings, the array visibly re-aims, and the specular flare
    # sweeps along the belt. That sweep is the whole reason to build one.
    pos = N("GeometryNodeInputPosition"); pos.location = (-1400, y - 460)
    nrm = _VM(g, 'NORMALIZE', (-1220, y - 460))
    L(sockout(pos, "Position"), nrm.inputs[0])
    inward = _VM(g, 'SCALE', (-1220, y - 600), "toward planet")
    L(sockout(nrm, "Vector"), inward.inputs[0])
    sockin(inward, "Scale").default_value = -1.0
    sund = _sun_dir(g, (-1800, y - 760))
    half0 = _VM(g, 'ADD', (-1060, y - 600), "half vector")
    L(sund, half0.inputs[0]); L(sockout(inward, "Vector"), half0.inputs[1])
    half = _VM(g, 'NORMALIZE', (-900, y - 600))
    L(sockout(half0, "Vector"), half.inputs[0])
    algn = _new_any(g, "FunctionNodeAlignRotationToVector",
                    "FunctionNodeAlignEulerToVector")
    algn.location = (-740, y - 460)
    algn.label = "heliostat"
    try:
        algn.axis = 'Z'
    except Exception:
        pass
    L(sockout(half, "Vector"), sockin(algn, "Vector"))
    L(sockout(algn, "Rotation"), sockin(ion, "Rotation"))

    sw = N("GeometryNodeSwitch"); sw.location = (-780, y)
    sw.input_type = 'GEOMETRY'
    L(gate(0.5, (-1000, y + 220)), sw.inputs[0])
    L(sockout(ion, "Instances"), sw.inputs[2])
    return sw.outputs[0]


def _ringworld(g, S, gate, y=-600):
    """Partial ringworld arcs with a lit inner face.

    The inner face glows because that is where people live; gating on the sign
    of dot(normal, position) is what separates inside from outside on a curved
    band without needing UVs.
    """
    N, L = g.nodes.new, g.links.new
    arc = N("GeometryNodeCurveArc"); arc.location = (-1600, y)
    rr = _M(g, 'MULTIPLY', loc=(-1800, y - 120))
    L(S["Radius"], rr.inputs[0]); L(S["Ring Orbit"], rr.inputs[1])
    L(rr.outputs[0], sockin(arc, "Radius"))
    sockin(arc, "Resolution").default_value = 128
    sweep = _M(g, 'RADIANS', loc=(-1800, y - 240)); L(S["Ring Sweep"], sweep.inputs[0])
    if "Sweep Angle" in arc.inputs:
        L(sweep.outputs[0], sockin(arc, "Sweep Angle"))
    else:
        L(sweep.outputs[0], sockin(arc, "Angle"))

    prof = N("GeometryNodeCurvePrimitiveQuadrilateral"); prof.location = (-1600, y - 380)
    L(S["Ring Width"], sockin(prof, "Width"))
    hh = _M(g, 'MULTIPLY', y=0.06, loc=(-1800, y - 420)); L(S["Ring Width"], hh.inputs[0])
    L(hh.outputs[0], sockin(prof, "Height"))
    c2m = N("GeometryNodeCurveToMesh"); c2m.location = (-1360, y)
    L(sockout(arc, "Curve"), sockin(c2m, "Curve"))
    L(sockout(prof, "Curve"), sockin(c2m, "Profile Curve"))

    band = _setmat(g, sockout(c2m, "Mesh"), S["Material"], (-1160, y))

    # inner face: normal pointing back toward the planet
    nrm = N("GeometryNodeInputNormal"); nrm.location = (-1360, y - 560)
    pos = N("GeometryNodeInputPosition"); pos.location = (-1360, y - 680)
    dot = _VM(g, 'DOT_PRODUCT', (-1160, y - 620), "inward")
    L(sockout(nrm, "Normal"), dot.inputs[0]); L(sockout(pos, "Position"), dot.inputs[1])
    inward = _M(g, 'LESS_THAN', y=0.0, loc=(-980, y - 620))
    L(dot.outputs["Value"], inward.inputs[0])
    glowsel = N("GeometryNodeSetMaterial"); glowsel.location = (-960, y)
    L(band, sockin(glowsel, "Geometry"))
    L(S["Glow Material"], sockin(glowsel, "Material"))
    L(inward.outputs[0], sockin(glowsel, "Selection"))

    # several arcs, spun to different longitudes and tilts
    inst = N("GeometryNodeGeometryToInstance"); inst.location = (-760, y)
    L(sockout(glowsel, "Geometry"), sockin(inst, "Geometry"))
    line = N("GeometryNodeMeshLine"); line.location = (-760, y - 240)
    L(S["Arc Count"], sockin(line, "Count"))
    sockin(line, "Offset").default_value = (0.0, 0.0, 0.0)
    ion = N("GeometryNodeInstanceOnPoints"); ion.location = (-560, y)
    L(sockout(line, "Mesh"), sockin(ion, "Points"))
    L(sockout(inst, "Instances"), sockin(ion, "Instance"))
    idx = N("GeometryNodeInputIndex"); idx.location = (-760, y - 380)
    spin0 = _M(g, 'MULTIPLY', y=2.399, loc=(-600, y - 380))
    L(sockout(idx, "Index"), spin0.inputs[0])
    # Every arc shares one motion, because they are one structure seen in
    # pieces. 2.7 R is 58 degrees an hour if it is in free fall.
    amot = _motion_angle(g, S, S["Arc Motion"], S["Ring Orbit"],
                         (-760, y - 760), "arc motion")
    spin = _M(g, 'ADD', loc=(-440, y - 380))
    L(spin0.outputs[0], spin.inputs[0]); L(amot, spin.inputs[1])
    tilt = _M(g, 'MULTIPLY', y=0.7, loc=(-600, y - 500))
    L(sockout(idx, "Index"), tilt.inputs[0])
    rot = N("ShaderNodeCombineXYZ"); rot.location = (-440, y - 440)
    L(tilt.outputs[0], rot.inputs[0]); L(spin.outputs[0], rot.inputs[2])
    L(sockout(rot, "Vector"), sockin(ion, "Rotation"))

    sw = N("GeometryNodeSwitch"); sw.location = (-340, y)
    sw.input_type = 'GEOMETRY'
    L(gate(6.5, (-560, y + 220)), sw.inputs[0])
    L(sockout(ion, "Instances"), sw.inputs[2])
    return sw.outputs[0]


def _swarm(g, S, gate, y=-2000):
    """A Dyson swarm: collectors scattered through a thick spherical shell."""
    N, L = g.nodes.new, g.links.new
    sph = N("GeometryNodeMeshIcoSphere"); sph.location = (-1600, y)
    sockin(sph, "Subdivisions").default_value = 4
    rr = _M(g, 'MULTIPLY', y=4.4, loc=(-1800, y - 120)); L(S["Radius"], rr.inputs[0])
    L(rr.outputs[0], sockin(sph, "Radius"))
    dist = N("GeometryNodeDistributePointsOnFaces"); dist.location = (-1400, y)
    L(sockout(sph, "Mesh"), sockin(dist, "Mesh"))
    dens = _M(g, 'DIVIDE', loc=(-1600, y - 260))
    L(S["Swarm Count"], dens.inputs[0])
    rsq = _M(g, 'POWER', y=2.0, loc=(-1780, y - 320)); L(rr.outputs[0], rsq.inputs[0])
    r12 = _M(g, 'MULTIPLY', y=12.566, loc=(-1700, y - 380)); L(rsq.outputs[0], r12.inputs[0])
    L(r12.outputs[0], dens.inputs[1])
    L(dens.outputs[0], sockin(dist, "Density"))
    L(S["Seed"], sockin(dist, "Seed"))

    coll = N("GeometryNodeMeshGrid"); coll.location = (-1400, y - 300)
    sz = _M(g, 'MULTIPLY', y=0.55, loc=(-1600, y - 420)); L(S["Mirror Size"], sz.inputs[0])
    L(sz.outputs[0], sockin(coll, "Size X"))
    L(sz.outputs[0], sockin(coll, "Size Y"))
    sockin(coll, "Vertices X").default_value = 2
    sockin(coll, "Vertices Y").default_value = 2
    cmat = _setmat(g, sockout(coll, "Mesh"), S["Mirror Material"], (-1200, y - 300))

    # Every collector is an independent body on its own orbit, exactly like
    # the satellite shell but eleven times further out, so 4.4 R gives about
    # 28 degrees an hour: the swarm drifts rather than races, which is the
    # correct reading of a structure that size.
    spos = N("GeometryNodeInputPosition"); spos.location = (-1400, y - 560)
    sphat = _VM(g, 'NORMALIZE', (-1240, y - 560))
    L(sockout(spos, "Position"), sphat.inputs[0])
    sax = N("FunctionNodeRandomValue"); sax.location = (-1400, y - 700)
    sax.data_type = 'FLOAT_VECTOR'
    sockin(sax, "Min").default_value = (-1.0, -1.0, -1.0)
    sockin(sax, "Max").default_value = (1.0, 1.0, 1.0)
    saseed = _M(g, 'ADD', y=811.0, loc=(-1580, y - 700)); L(S["Seed"], saseed.inputs[0])
    L(saseed.outputs[0], sockin(sax, "Seed"))
    sdot = _VM(g, 'DOT_PRODUCT', (-1080, y - 640))
    L(sax.outputs[0], sdot.inputs[0]); L(sockout(sphat, "Vector"), sdot.inputs[1])
    sproj = _VM(g, 'SCALE', (-920, y - 640))
    L(sockout(sphat, "Vector"), sproj.inputs[0])
    L(sdot.outputs["Value"], sockin(sproj, "Scale"))
    sperp = _VM(g, 'SUBTRACT', (-760, y - 700))
    L(sax.outputs[0], sperp.inputs[0]); L(sockout(sproj, "Vector"), sperp.inputs[1])
    saxis = _VM(g, 'NORMALIZE', (-600, y - 700), "swarm axis")
    L(sockout(sperp, "Vector"), saxis.inputs[0])
    sphase = _anim.geo_orbit_rad(g, 4.4, loc=(-1080, y - 860), label="swarm phase")
    srot = N("ShaderNodeVectorRotate"); srot.location = (-440, y - 640)
    srot.rotation_type = 'AXIS_ANGLE'; srot.label = "swarm step"
    L(sockout(spos, "Position"), srot.inputs["Vector"])
    L(sockout(saxis, "Vector"), srot.inputs["Axis"])
    L(sphase, srot.inputs["Angle"])
    ssp = N("GeometryNodeSetPosition"); ssp.location = (-1180, y)
    L(sockout(dist, "Points"), sockin(ssp, "Geometry"))
    L(sockout(srot, "Vector"), sockin(ssp, "Position"))

    ion = N("GeometryNodeInstanceOnPoints"); ion.location = (-1000, y)
    L(sockout(ssp, "Geometry"), sockin(ion, "Points"))
    L(cmat, sockin(ion, "Instance"))
    # A collector that is not facing the sun is not collecting anything.
    ssun = _sun_dir(g, (-1800, y - 1000))
    salgn = _new_any(g, "FunctionNodeAlignRotationToVector",
                     "FunctionNodeAlignEulerToVector")
    salgn.location = (-820, y - 400); salgn.label = "sun facing"
    try:
        salgn.axis = 'Z'
    except Exception:
        pass
    L(ssun, sockin(salgn, "Vector"))
    L(sockout(salgn, "Rotation"), sockin(ion, "Rotation"))
    sw = N("GeometryNodeSwitch"); sw.location = (-780, y)
    sw.input_type = 'GEOMETRY'
    L(gate(9.0, (-1000, y + 220)), sw.inputs[0])
    L(sockout(ion, "Instances"), sw.inputs[2])
    return sw.outputs[0]


def build(radius=1000.0, name="PLNT_MegaRig"):
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    I = g.interface
    I.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    I.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    for nm, st, dv, mn, mx, desc in MEGA_IN:
        new_socket(I, nm, 'INPUT', st, dv, mn, mx, desc)

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2200, 0)
    go = N("NodeGroupOutput"); go.location = (200, 0)
    S = gi.outputs

    def gate(thresh, loc):
        n = _M(g, 'GREATER_THAN', y=thresh, loc=loc)
        L(S["Mega Scale"], n.inputs[0])
        return n.outputs["Value"]

    jn = N("GeometryNodeJoinGeometry"); jn.location = (0, 0)
    for part in (_mirror_belt(g, S, gate), _ringworld(g, S, gate),
                 _swarm(g, S, gate)):
        L(part, sockin(jn, "Geometry"))
    L(sockout(jn, "Geometry"), go.inputs["Geometry"])
    ifc = {i.name: i for i in g.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'}
    ifc["Radius"].default_value = radius
    return g


def build_materials():
    """Mirror and habitat-glow materials."""
    mir = bpy.data.materials.get("PLNT_MegaMirror") or \
        bpy.data.materials.new("PLNT_MegaMirror")
    mir.use_nodes = True
    nt = mir.node_tree; nt.nodes.clear()
    b = nt.nodes.new("ShaderNodeBsdfPrincipled"); b.location = (0, 0)
    sockin(b, "Base Color").default_value = (0.92, 0.94, 0.97, 1.0)
    sockin(b, "Metallic").default_value = 1.0
    # never exactly 0: a perfect mirror on a large curved panel throws
    # non-converging fireflies that survive denoising
    sockin(b, "Roughness").default_value = 0.06
    o = nt.nodes.new("ShaderNodeOutputMaterial"); o.location = (300, 0)
    nt.links.new(sockout(b, "BSDF"), sockin(o, "Surface"))

    glow = bpy.data.materials.get("PLNT_MegaGlow") or \
        bpy.data.materials.new("PLNT_MegaGlow")
    glow.use_nodes = True
    nt = glow.node_tree; nt.nodes.clear()
    e = nt.nodes.new("ShaderNodeEmission"); e.location = (0, 0)
    sockin(e, "Color").default_value = (1.0, 0.86, 0.62, 1.0)
    sockin(e, "Strength").default_value = 2.6
    o = nt.nodes.new("ShaderNodeOutputMaterial"); o.location = (300, 0)
    nt.links.new(sockout(e, "Emission"), sockin(o, "Surface"))
    return mir, glow
