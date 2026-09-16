"""Orbital infrastructure: an instanced module library, not repeated boxes.

What was wrong with the first version
-------------------------------------
* The greebles along each band never received the curve's Rotation, so every
  box stayed world-axis-aligned. Around a circle that reads as a dashed
  ribbon rather than as a structure following the band. This was the single
  most visible defect in shots 09 and 10.
* Satellites got neither Rotation nor Scale, so all of them were the same
  axis-aligned box at the same size -- 34 identical cubes.
* A Realize Instances node at the end flattened everything into real geometry,
  multiplying memory by the instance count for no benefit.
* Strip lighting came from a world-space Z wave, so the same band of light cut
  across every module at an arbitrary angle regardless of its orientation.

This version instances a library of twelve distinct modules, keeps them as
instances all the way to the material, and reads per-instance randomness so
each module lights its own windows.
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

ORBITAL_IN = [
    ("Orbital Level", 'NodeSocketFloat', 0.0, 0.0, 10.0,
     "Amount of orbital infrastructure, 0-10. Above 0.5 scattered satellites "
     "appear, above 3 a structural band, above 6 three intersecting bands, "
     "above 8 an equatorial space elevator"),
    ("Radius", 'NodeSocketFloat', 1000.0, 1.0, 1e6,
     "Planet radius the structures are placed around"),
    ("Seed", 'NodeSocketFloat', 0.0, -10000.0, 10000.0,
     "Random seed for satellite placement and module selection"),
    ("Band Height", 'NodeSocketFloat', 38.0, 0.1, 400.0,
     "Cross-section height of the orbital bands"),
    ("Band Width", 'NodeSocketFloat', 16.0, 0.1, 400.0,
     "Cross-section width of the orbital bands"),
    ("Band Resolution", 'NodeSocketInt', 220, 16, 2048,
     "Segments around each band. Raise if the band looks polygonal"),
    ("Bay Length", 'NodeSocketFloat', 46.0, 4.0, 600.0,
     "Length of one truss bay. The number of bays is derived from the "
     "circumference so braces meet exactly instead of overlapping"),
    ("Longeron Radius", 'NodeSocketFloat', 2.6, 0.1, 40.0,
     "Thickness of the four continuous rails running the length of the truss"),
    ("Satellite Density", 'NodeSocketFloat', 0.20, 0.0, 1.0,
     "How many of the candidate orbital slots carry a satellite"),
    ("Cluster Scale", 'NodeSocketFloat', 2.6, 0.1, 30.0,
     "Size of the clusters satellites gather into. Real orbital traffic "
     "bunches into shells and planes rather than spreading evenly"),
    ("Shell Thickness", 'NodeSocketFloat', 0.10, 0.0, 1.0,
     "Depth of the orbital shell as a fraction of planet radius, so "
     "satellites sit at a spread of altitudes instead of on one sphere"),
    ("Module Scale", 'NodeSocketFloat', 1.0, 0.05, 12.0,
     "Overall size of the instanced modules"),
    ("Hub Count", 'NodeSocketInt', 5, 0, 60,
     "Number of large station hubs spaced around the main band"),
    ("Lit Fraction", 'NodeSocketFloat', 0.55, 0.0, 1.0,
     "Fraction of modules whose windows are lit"),
    ("Light Colour", 'NodeSocketColor', (0.55, 0.82, 1.0, 1.0), None, None,
     "Colour of the structure's own lighting"),
    ("Tether Taper", 'NodeSocketFloat', 5.5, 1.0, 40.0,
     "How much wider the space elevator ribbon is at geostationary height "
     "than at the anchor. A real tether must taper to carry its own weight"),
    ("Climber Count", 'NodeSocketInt', 7, 0, 60,
     "Number of climbers riding the tether"),
    ("Material", 'NodeSocketMaterial', None, None, None,
     "Structural material"),
    ("Light Material", 'NodeSocketMaterial', None, None, None,
     "Emissive material for lit panels and windows"),
    ("Band Motion", 'NodeSocketInt', 0, 0, 2,
     "How the orbital bands move. 0 Orbiting: each band circles at its own "
     "Kepler rate, which is what an unpowered structure does. 1 Locked: the "
     "bands turn with the planet, the active-support ring of the fiction. "
     "2 Inertial: the bands hold still while the planet turns beneath them"),
]


def _iface(g):
    I = g.interface
    I.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    I.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    for row in ORBITAL_IN:
        name, st, dv, mn, mx, desc = row
        new_socket(I, name, 'INPUT', st, dv, mn, mx, desc)
    return I


# A library of twelve distinct modules. Each is a short list of primitive
# parts; the whole library is joined into one geometry and InstanceOnPoints
# picks between them per point, so thousands of structures cost a few hundred
# unique triangles.
#   ('cube', (x, y, z), (tx, ty, tz))
#   ('cyl',  radius, depth, verts, (tx, ty, tz))
#   ('ico',  radius, subdiv, (tx, ty, tz))
#   ('cone', r_bottom, r_top, depth, verts, (tx, ty, tz))
MODULES = [
    [('cube', (14, 14, 46), (0, 0, 0)), ('cyl', 4.0, 12.0, 8, (0, 0, 30))],
    [('cyl', 11.0, 40.0, 12, (0, 0, 0)), ('ico', 12.0, 1, (0, 0, 22))],
    [('cube', (22, 22, 14), (0, 0, 0)), ('cube', (12, 12, 20), (0, 0, 16))],
    [('cube', (3, 46, 30), (0, 0, 0)), ('cube', (2, 8, 8), (0, 0, 20))],
    [('cyl', 6.0, 34.0, 10, (9, 0, 0)), ('cyl', 6.0, 34.0, 10, (-9, 0, 0)),
     ('cube', (26, 10, 8), (0, 0, 0))],
    [('cube', (30, 30, 30), (0, 0, 0)), ('cyl', 3.0, 40.0, 6, (0, 0, 0))],
    [('cone', 16.0, 2.0, 14.0, 16, (0, 0, 0)), ('cyl', 3.0, 18.0, 8, (0, 0, -14))],
    [('cube', (40, 28, 2.5), (0, 0, 0)), ('cube', (6, 6, 6), (0, 0, 4))],
    [('ico', 16.0, 2, (0, 0, 0)), ('cyl', 3.5, 22.0, 8, (0, 0, -16))],
    [('cube', (18, 18, 34), (0, 0, 0)), ('cube', (8, 26, 8), (0, 0, 10)),
     ('cube', (8, 26, 8), (0, 0, -10))],
    [('cyl', 2.4, 64.0, 6, (0, 0, 0)), ('cube', (9, 9, 9), (0, 0, 30))],
    [('cube', (52, 20, 5), (0, 0, 0)), ('cube', (10, 10, 12), (0, 0, 8))],
    # Solar wings. A satellite with no array is the one detail that reads as
    # wrong even at a few pixels: the wings are what a person recognises.
    # Built as a thin panel on a boom either side of a small bus.
    [('cube', (10, 10, 16), (0, 0, 0)),
     ('cyl', 1.2, 34.0, 6, (0, 0, 0)),
     ('cube', (1.0, 30, 22), (0, 26, 0)),
     ('cube', (1.0, 30, 22), (0, -26, 0))],
    [('cyl', 7.0, 20.0, 10, (0, 0, 0)),
     ('cube', (0.9, 46, 15), (0, 0, 10)),
     ('cone', 9.0, 1.0, 8.0, 14, (0, 0, -14))],
]


def _part(g, spec, loc):
    """One primitive, pre-translated into its place inside a module."""
    N, L = g.nodes.new, g.links.new
    kind = spec[0]
    if kind == 'cube':
        n = N("GeometryNodeMeshCube")
        sockin(n, "Size").default_value = spec[1]
        geo, t = sockout(n, "Mesh"), spec[2]
    elif kind == 'cyl':
        n = N("GeometryNodeMeshCylinder")
        sockin(n, "Radius").default_value = spec[1]
        sockin(n, "Depth").default_value = spec[2]
        sockin(n, "Vertices").default_value = spec[3]
        geo, t = sockout(n, "Mesh"), spec[4]
    elif kind == 'ico':
        n = N("GeometryNodeMeshIcoSphere")
        sockin(n, "Radius").default_value = spec[1]
        sockin(n, "Subdivisions").default_value = spec[2]
        geo, t = sockout(n, "Mesh"), spec[3]
    elif kind == 'cone':
        n = N("GeometryNodeMeshCone")
        sockin(n, "Radius Bottom").default_value = spec[1]
        sockin(n, "Radius Top").default_value = spec[2]
        sockin(n, "Depth").default_value = spec[3]
        sockin(n, "Vertices").default_value = spec[4]
        geo, t = sockout(n, "Mesh"), spec[5]
    else:
        raise ValueError("unknown part kind %r" % kind)
    n.location = loc
    if t == (0, 0, 0):
        return geo
    tr = N("GeometryNodeTransform")
    tr.location = (loc[0] + 200, loc[1])
    L(geo, sockin(tr, "Geometry"))
    sockin(tr, "Translation").default_value = t
    return sockout(tr, "Geometry")


# Small parts scattered over every module: masts, dishes, tanks, fins. They
# are added to the twelve LIBRARY modules, not to the thousands of instances,
# so the whole greeble pass costs a few thousand unique triangles once and is
# then free on every satellite, hub and band module in the scene.
GREEBLES = [
    ('cyl', 0.35, 7.0, 6, (0, 0, 3.0)),        # mast
    ('cyl', 2.2, 0.5, 10, (0, 0, 0.6)),        # dish base
    ('cube', (2.6, 2.6, 1.4), (0, 0, 0.7)),    # avionics box
    ('cyl', 1.5, 3.4, 8, (0, 0, 1.7)),         # tank
    ('cube', (0.4, 3.6, 2.4), (0, 0, 1.2)),    # fin
]


def build_greebles(g, mat, x=-3600, y=3600):
    """One geometry holding the small parts, ready for Pick Instance."""
    N, L = g.nodes.new, g.links.new
    lib = N("GeometryNodeJoinGeometry"); lib.location = (x + 700, y)
    for i, spec in enumerate(GREEBLES):
        row = y - i * 150
        geo = _part(g, spec, (x, row))
        geo = _setmat(g, geo, mat, (x + 400, row))
        g2i = N("GeometryNodeGeometryToInstance"); g2i.location = (x + 540, row)
        L(geo, sockin(g2i, "Geometry"))
        L(sockout(g2i, "Instances"), sockin(lib, "Geometry"))
    return sockout(lib, "Geometry")


def _greeble_module(g, geo, greebles, seed_socket, idx, loc):
    """Scatter small parts over one library module.

    Distribute Points on Faces gives a normal-aligned rotation for free, so
    the parts stand off the surface they land on instead of all pointing the
    same way. Density is per unit area, and these modules are 10 to 60 units
    across, so 0.0045 lands roughly a dozen parts on each.
    """
    N, L = g.nodes.new, g.links.new
    dist = N("GeometryNodeDistributePointsOnFaces")
    dist.location = (loc[0], loc[1] - 120)
    L(geo, sockin(dist, "Mesh"))
    sockin(dist, "Density").default_value = 0.0045
    sd = N("ShaderNodeMath"); sd.operation = 'ADD'
    sd.location = (loc[0] - 180, loc[1] - 260)
    sd.inputs[1].default_value = 53.0 + idx * 7.0
    L(seed_socket, sd.inputs[0])
    L(sd.outputs[0], sockin(dist, "Seed"))

    ion = N("GeometryNodeInstanceOnPoints"); ion.location = (loc[0] + 200, loc[1] - 120)
    L(sockout(dist, "Points"), sockin(ion, "Points"))
    L(greebles, sockin(ion, "Instance"))
    sockin(ion, "Pick Instance").default_value = True
    pick = N("FunctionNodeRandomValue"); pick.location = (loc[0], loc[1] - 400)
    pick.data_type = 'INT'
    sockin(pick, "Min").default_value = 0
    sockin(pick, "Max").default_value = len(GREEBLES) - 1
    L(sd.outputs[0], sockin(pick, "Seed"))
    L(pick.outputs["Value"], sockin(ion, "Instance Index"))
    L(sockout(dist, "Rotation"), sockin(ion, "Rotation"))
    scl = N("FunctionNodeRandomValue"); scl.location = (loc[0], loc[1] - 540)
    scl.data_type = 'FLOAT'
    sockin(scl, "Min").default_value = 0.6
    sockin(scl, "Max").default_value = 1.8
    L(sd.outputs[0], sockin(scl, "Seed"))
    L(scl.outputs[0], sockin(ion, "Scale"))

    jn = N("GeometryNodeJoinGeometry"); jn.location = (loc[0] + 380, loc[1])
    L(sockout(ion, "Instances"), sockin(jn, "Geometry"))
    L(geo, sockin(jn, "Geometry"))
    return sockout(jn, "Geometry")


def build_library(g, mat, x=-2600, y=2600):
    """Join the twelve modules into one geometry of twelve instances.

    InstanceOnPoints picks between them with Pick Instance + Instance Index,
    which is the mechanism that actually works for a library; an Index Switch
    would need a separate branch per module and does not scale.
    """
    N, L = g.nodes.new, g.links.new
    lib = N("GeometryNodeJoinGeometry")
    lib.location = (x + 1400, y)
    greebles = build_greebles(g, mat, x - 1000, y + 400)
    gi = next((n for n in g.nodes if n.bl_idname == 'NodeGroupInput'), None)
    seed = gi.outputs["Seed"] if gi and "Seed" in gi.outputs else None
    for i, parts in enumerate(MODULES):
        row = y - i * 260
        outs = [_part(g, p, (x, row - j * 90)) for j, p in enumerate(parts)]
        if len(outs) == 1:
            geo = outs[0]
        else:
            jn = N("GeometryNodeJoinGeometry")
            jn.location = (x + 450, row)
            for o in outs:
                L(o, sockin(jn, "Geometry"))
            geo = sockout(jn, "Geometry")
        geo = _setmat(g, geo, mat, (x + 560, row))
        if seed is not None:
            geo = _greeble_module(g, geo, greebles, seed, i, (x + 700, row))
        g2i = N("GeometryNodeGeometryToInstance")
        g2i.location = (x + 1180, row)
        L(geo, sockin(g2i, "Geometry"))
        L(sockout(g2i, "Instances"), sockin(lib, "Geometry"))
    return sockout(lib, "Geometry")


def _setmat(g, geo, mat_socket, loc):
    """Apply a material to geometry.

    Must happen before the geometry becomes an instance: Set Material does not
    reach inside instances, which is why the first version needed a Realize
    Instances node and paid for it in memory.
    """
    n = g.nodes.new("GeometryNodeSetMaterial")
    n.location = loc
    g.links.new(geo, sockin(n, "Geometry"))
    g.links.new(mat_socket, sockin(n, "Material"))
    return sockout(n, "Geometry")


def _mathfns(g):
    N, L = g.nodes.new, g.links.new

    def M(op, x=None, y=None, loc=(0, 0), nm=""):
        n = N("ShaderNodeMath"); n.operation = op; n.location = loc; n.label = nm
        if x is not None: n.inputs[0].default_value = x
        if y is not None: n.inputs[1].default_value = y
        return n

    def VM(op, loc=(0, 0), nm=""):
        n = N("ShaderNodeVectorMath"); n.operation = op
        n.location = loc; n.label = nm
        return n

    return N, L, M, VM


def _satellites(g, S, lib, gate, y=1400):
    """A clustered shell of instanced modules.

    Points come from a UV sphere, are thinned by a spatial noise rather than by
    pure chance -- real orbital traffic bunches into planes and altitude shells
    -- and are pushed to a spread of radii so they do not all sit on one
    sphere.
    """
    N, L, M, VM = _mathfns(g)
    sph = N("GeometryNodeMeshUVSphere"); sph.location = (-1900, y)
    sockin(sph, "Segments").default_value = 64
    sockin(sph, "Rings").default_value = 32
    sr = M('MULTIPLY', y=1.16, loc=(-2100, y - 120)); L(S["Radius"], sr.inputs[0])
    L(sr.outputs[0], sockin(sph, "Radius"))
    m2p = N("GeometryNodeMeshToPoints"); m2p.location = (-1700, y)
    L(sockout(sph, "Mesh"), sockin(m2p, "Mesh"))

    pos = N("GeometryNodeInputPosition"); pos.location = (-1900, y - 300)
    csc = M('MULTIPLY', y=0.0011, loc=(-1900, y - 420))
    L(S["Cluster Scale"], csc.inputs[0])
    cv = VM('SCALE', (-1720, y - 320), "cluster coord")
    L(sockout(pos, "Position"), cv.inputs[0])
    L(csc.outputs[0], sockin(cv, "Scale"))
    cn = N("ShaderNodeTexNoise"); cn.location = (-1540, y - 320); cn.label = "clusters"
    cn.noise_dimensions = '4D'; cn.noise_type = 'FBM'
    sockin(cn, "Detail").default_value = 3.0
    sockin(cn, "Scale").default_value = 1.0
    L(sockout(cv, "Vector"), sockin(cn, "Vector"))
    L(S["Seed"], sockin(cn, "W"))
    # FBM Fac clusters tightly around 0.5, so thresholding it directly keeps
    # almost nothing -- Satellite Density 0.34 gave 24 satellites out of ~2000
    # candidate points. Spread the useful part of the distribution across 0..1
    # first, so the density value means what it says.
    spread = N("ShaderNodeMapRange"); spread.location = (-1540, y - 380)
    spread.clamp = True; spread.label = "density spread"
    for i, v in ((1, 0.36), (2, 0.64), (3, 0.0), (4, 1.0)):
        spread.inputs[i].default_value = v
    L(sockout(cn, "Fac"), spread.inputs[0])
    thr = M('SUBTRACT', x=1.0, loc=(-1540, y - 460))
    L(S["Satellite Density"], thr.inputs[1])
    keep = M('GREATER_THAN', loc=(-1360, y - 380), nm="in cluster")
    L(spread.outputs["Result"], keep.inputs[0]); L(thr.outputs[0], keep.inputs[1])
    inv = N("FunctionNodeBooleanMath"); inv.operation = 'NOT'
    inv.location = (-1180, y - 380)
    L(keep.outputs[0], inv.inputs[0])
    dele = N("GeometryNodeDeleteGeometry"); dele.location = (-1000, y)
    dele.domain = 'POINT'
    L(sockout(m2p, "Points"), sockin(dele, "Geometry"))
    L(sockout(inv, "Boolean"), sockin(dele, "Selection"))

    # spread over a shell of finite depth
    rnd_r = N("FunctionNodeRandomValue"); rnd_r.location = (-1000, y - 260)
    rnd_r.data_type = 'FLOAT'
    sockin(rnd_r, "Min").default_value = -0.5
    sockin(rnd_r, "Max").default_value = 0.5
    L(S["Seed"], sockin(rnd_r, "Seed"))
    sh = M('MULTIPLY', loc=(-820, y - 300)); L(rnd_r.outputs[0], sh.inputs[0])
    L(S["Shell Thickness"], sh.inputs[1])
    shr = M('MULTIPLY', loc=(-660, y - 300)); L(sh.outputs[0], shr.inputs[0])
    L(S["Radius"], shr.inputs[1])
    nrm = VM('NORMALIZE', (-820, y - 460))
    pos2 = N("GeometryNodeInputPosition"); pos2.location = (-1000, y - 460)
    L(sockout(pos2, "Position"), nrm.inputs[0])
    off = VM('SCALE', (-500, y - 380))
    L(sockout(nrm, "Vector"), off.inputs[0]); L(shr.outputs[0], sockin(off, "Scale"))
    sp = N("GeometryNodeSetPosition"); sp.location = (-320, y)
    L(sockout(dele, "Geometry"), sockin(sp, "Geometry"))
    L(sockout(off, "Vector"), sockin(sp, "Offset"))

    # ---- orbits ---------------------------------------------------------
    #
    # Each satellite gets a great circle of its own. The orbit plane must pass
    # through the planet centre, so the random axis is projected perpendicular
    # to the position first -- rotating about an arbitrary axis keeps the
    # radius but traces a small circle whose plane misses the centre, which
    # would have every satellite quietly orbiting a point in empty space.
    #
    # The rate is Kepler: T(r) = 84.5 min * (r/R)^1.5. At the 1.02 to 1.16 R
    # this shell occupies that is 88 to 110 minutes, so at Timelapse a
    # satellite crosses the visible disc in about forty seconds while the
    # surface below it has barely moved. That difference in speed is the whole
    # reason low orbit reads as low orbit.
    opos = N("GeometryNodeInputPosition"); opos.location = (-780, y + 620)
    olen = VM('LENGTH', (-620, y + 620), "orbit radius")
    L(sockout(opos, "Position"), olen.inputs[0])
    orad = M('DIVIDE', loc=(-460, y + 620), nm="r over R")
    L(olen.outputs["Value"], orad.inputs[0]); L(S["Radius"], orad.inputs[1])
    ophase = _anim.geo_orbit_rad(g, orad.outputs["Value"],
                                 loc=(-300, y + 760), label="satellite phase")

    oax = N("FunctionNodeRandomValue"); oax.location = (-780, y + 440)
    oax.data_type = 'FLOAT_VECTOR'
    sockin(oax, "Min").default_value = (-1.0, -1.0, -1.0)
    sockin(oax, "Max").default_value = (1.0, 1.0, 1.0)
    oaseed = M('ADD', y=307.0, loc=(-960, y + 440)); L(S["Seed"], oaseed.inputs[0])
    L(oaseed.outputs[0], sockin(oax, "Seed"))
    ophat = VM('NORMALIZE', (-620, y + 300))
    L(sockout(opos, "Position"), ophat.inputs[0])
    odot = VM('DOT_PRODUCT', (-460, y + 380))
    L(oax.outputs[0], odot.inputs[0]); L(sockout(ophat, "Vector"), odot.inputs[1])
    oproj = VM('SCALE', (-300, y + 380))
    L(sockout(ophat, "Vector"), oproj.inputs[0])
    L(odot.outputs["Value"], sockin(oproj, "Scale"))
    operp = VM('SUBTRACT', (-140, y + 440))
    L(oax.outputs[0], operp.inputs[0]); L(sockout(oproj, "Vector"), operp.inputs[1])
    oaxis = VM('NORMALIZE', (20, y + 440), "orbit axis")
    L(sockout(operp, "Vector"), oaxis.inputs[0])

    oph0 = N("FunctionNodeRandomValue"); oph0.location = (-780, y + 200)
    oph0.data_type = 'FLOAT'
    sockin(oph0, "Min").default_value = 0.0
    sockin(oph0, "Max").default_value = 6.283185307
    opseed = M('ADD', y=613.0, loc=(-960, y + 200)); L(S["Seed"], opseed.inputs[0])
    L(opseed.outputs[0], sockin(oph0, "Seed"))
    oang = M('ADD', loc=(180, y + 620), nm="satellite angle")
    L(ophase, oang.inputs[0]); L(oph0.outputs[0], oang.inputs[1])

    orot = N("ShaderNodeVectorRotate"); orot.location = (340, y + 440)
    orot.rotation_type = 'AXIS_ANGLE'; orot.label = "orbit step"
    L(sockout(opos, "Position"), orot.inputs["Vector"])
    L(sockout(oaxis, "Vector"), orot.inputs["Axis"])
    L(oang.outputs[0], orot.inputs["Angle"])
    osp = N("GeometryNodeSetPosition"); osp.location = (520, y)
    L(sockout(sp, "Geometry"), sockin(osp, "Geometry"))
    L(sockout(orot, "Vector"), sockin(osp, "Position"))

    # Orientation: nose along the velocity, one face toward the planet. A
    # satellite tumbling on a random Euler is the other half of why the old
    # shell read as debris rather than as hardware.
    ovel = VM('CROSS_PRODUCT', (520, y + 440), "velocity")
    L(sockout(oaxis, "Vector"), ovel.inputs[0]); L(sockout(orot, "Vector"), ovel.inputs[1])
    onad = VM('SCALE', (520, y + 300), "nadir")
    L(sockout(orot, "Vector"), onad.inputs[0])
    sockin(onad, "Scale").default_value = -1.0
    oal1 = N("FunctionNodeAlignRotationToVector")
    oal1.location = (700, y + 300); oal1.label = "nadir lock"
    oal1.axis = 'Z'
    oal1.inputs["Factor"].default_value = 1.0
    L(sockout(onad, "Vector"), oal1.inputs["Vector"])
    oal2 = N("FunctionNodeAlignRotationToVector")
    oal2.location = (880, y + 380); oal2.label = "along track"
    oal2.axis = 'X'
    oal2.pivot_axis = 'Z'
    oal2.inputs["Factor"].default_value = 1.0
    L(oal1.outputs[0], oal2.inputs["Rotation"])
    L(sockout(ovel, "Vector"), oal2.inputs["Vector"])

    ion = N("GeometryNodeInstanceOnPoints"); ion.location = (1060, y)
    L(sockout(osp, "Geometry"), sockin(ion, "Points"))
    L(lib, sockin(ion, "Instance"))
    sockin(ion, "Pick Instance").default_value = True
    pick = N("FunctionNodeRandomValue"); pick.location = (-320, y - 620)
    pick.data_type = 'INT'
    sockin(pick, "Min").default_value = 0
    sockin(pick, "Max").default_value = len(MODULES) - 1
    L(S["Seed"], sockin(pick, "Seed"))
    L(pick.outputs["Value"], sockin(ion, "Instance Index"))

    L(oal2.outputs[0], sockin(ion, "Rotation"))

    scl = N("FunctionNodeRandomValue"); scl.location = (-320, y - 980)
    scl.data_type = 'FLOAT'
    sockin(scl, "Min").default_value = 0.15
    sockin(scl, "Max").default_value = 0.45
    sseed = M('ADD', y=41.0, loc=(-500, y - 980)); L(S["Seed"], sseed.inputs[0])
    L(sseed.outputs[0], sockin(scl, "Seed"))
    ms = M('MULTIPLY', loc=(-160, y - 980)); L(scl.outputs[0], ms.inputs[0])
    L(S["Module Scale"], ms.inputs[1])
    L(ms.outputs[0], sockin(ion, "Scale"))

    sw = N("GeometryNodeSwitch"); sw.location = (1300, y)
    sw.input_type = 'GEOMETRY'
    L(gate(0.5, (1060, y + 240)), sw.inputs[0])
    L(sockout(ion, "Instances"), sw.inputs[2])
    return sw.outputs[0]


def _band(g, S, lib, gate, idx, rx, ry, rscale, thresh, y):
    """One structural band: hull ring, truss lattice, greebles, hubs.

    Bay count is derived from the circumference divided by Bay Length, so the
    braces meet exactly at the bay boundaries instead of overlapping or leaving
    gaps wherever the radius changes.
    """
    N, L, M, VM = _mathfns(g)
    circ = N("GeometryNodeCurvePrimitiveCircle"); circ.location = (-1900, y)
    L(S["Band Resolution"], sockin(circ, "Resolution"))
    rr = M('MULTIPLY', y=rscale, loc=(-2100, y - 120))
    L(S["Radius"], rr.inputs[0])
    L(rr.outputs[0], sockin(circ, "Radius"))

    # main hull ring
    prof = N("GeometryNodeCurvePrimitiveQuadrilateral")
    prof.location = (-1900, y - 220)
    L(S["Band Width"], sockin(prof, "Width"))
    L(S["Band Height"], sockin(prof, "Height"))
    c2m = N("GeometryNodeCurveToMesh"); c2m.location = (-1700, y)
    L(sockout(circ, "Curve"), sockin(c2m, "Curve"))
    L(sockout(prof, "Curve"), sockin(c2m, "Profile Curve"))
    sockin(c2m, "Fill Caps").default_value = True

    # bays derived from circumference / Bay Length
    circum = M('MULTIPLY', y=6.283185307, loc=(-1900, y - 400))
    L(rr.outputs[0], circum.inputs[0])
    nbays = M('DIVIDE', loc=(-1740, y - 400), nm="bay count")
    L(circum.outputs[0], nbays.inputs[0]); L(S["Bay Length"], nbays.inputs[1])
    nbr = M('ROUND', loc=(-1580, y - 400)); L(nbays.outputs[0], nbr.inputs[0])

    c2p = N("GeometryNodeCurveToPoints"); c2p.location = (-1400, y - 400)
    c2p.mode = 'COUNT'
    L(nbr.outputs[0], sockin(c2p, "Count"))
    L(sockout(circ, "Curve"), sockin(c2p, "Curve"))

    # one bay module: a box frame with an X-brace
    bay = N("GeometryNodeMeshCube"); bay.location = (-1400, y - 620)
    bl = N("ShaderNodeCombineXYZ"); bl.location = (-1580, y - 620)
    L(S["Bay Length"], bl.inputs[0])
    L(S["Band Width"], bl.inputs[1])
    L(S["Band Height"], bl.inputs[2])
    L(sockout(bl, "Vector"), sockin(bay, "Size"))
    brace = N("GeometryNodeMeshCube"); brace.location = (-1400, y - 760)
    bw = M('MULTIPLY', y=0.10, loc=(-1580, y - 760)); L(S["Bay Length"], bw.inputs[0])
    bv = N("ShaderNodeCombineXYZ"); bv.location = (-1500, y - 860)
    diag = M('MULTIPLY', y=1.30, loc=(-1680, y - 860)); L(S["Bay Length"], diag.inputs[0])
    L(diag.outputs[0], bv.inputs[0])
    L(bw.outputs[0], bv.inputs[1])
    L(bw.outputs[0], bv.inputs[2])
    L(sockout(bv, "Vector"), sockin(brace, "Size"))
    br1 = N("GeometryNodeTransform"); br1.location = (-1220, y - 760)
    L(sockout(brace, "Mesh"), sockin(br1, "Geometry"))
    sockin(br1, "Rotation").default_value = (0.0, math.radians(38), 0.0)
    br2 = N("GeometryNodeTransform"); br2.location = (-1220, y - 900)
    L(sockout(brace, "Mesh"), sockin(br2, "Geometry"))
    sockin(br2, "Rotation").default_value = (0.0, math.radians(-38), 0.0)
    bayjoin = N("GeometryNodeJoinGeometry"); bayjoin.location = (-1020, y - 700)
    for o in (sockout(bay, "Mesh"), sockout(br1, "Geometry"), sockout(br2, "Geometry")):
        L(o, sockin(bayjoin, "Geometry"))

    bay_geo = _setmat(g, sockout(bayjoin, "Geometry"), S["Material"],
                      (-920, y - 700))
    bion = N("GeometryNodeInstanceOnPoints"); bion.location = (-820, y - 400)
    L(sockout(c2p, "Points"), sockin(bion, "Points"))
    L(bay_geo, sockin(bion, "Instance"))
    # THE dashed-ribbon fix: without the curve's Rotation every bay stays
    # world-axis-aligned and the band reads as disconnected dashes
    L(sockout(c2p, "Rotation"), sockin(bion, "Rotation"))

    # greebles: library modules riding the same ring, smaller and rotated
    gc2p = N("GeometryNodeCurveToPoints"); gc2p.location = (-1400, y - 1060)
    gc2p.mode = 'COUNT'
    gcount = M('MULTIPLY', y=2.6, loc=(-1580, y - 1060)); L(nbr.outputs[0], gcount.inputs[0])
    L(gcount.outputs[0], sockin(gc2p, "Count"))
    L(sockout(circ, "Curve"), sockin(gc2p, "Curve"))
    gion = N("GeometryNodeInstanceOnPoints"); gion.location = (-820, y - 1060)
    L(sockout(gc2p, "Points"), sockin(gion, "Points"))
    L(lib, sockin(gion, "Instance"))
    sockin(gion, "Pick Instance").default_value = True
    gpick = N("FunctionNodeRandomValue"); gpick.location = (-1020, y - 1200)
    gpick.data_type = 'INT'
    sockin(gpick, "Min").default_value = 0
    sockin(gpick, "Max").default_value = len(MODULES) - 1
    gseed = M('ADD', y=7.0 + idx * 13.0, loc=(-1200, y - 1200)); L(S["Seed"], gseed.inputs[0])
    L(gseed.outputs[0], sockin(gpick, "Seed"))
    L(gpick.outputs["Value"], sockin(gion, "Instance Index"))
    L(sockout(gc2p, "Rotation"), sockin(gion, "Rotation"))
    gscl = N("FunctionNodeRandomValue"); gscl.location = (-1020, y - 1380)
    gscl.data_type = 'FLOAT'
    sockin(gscl, "Min").default_value = 0.35
    sockin(gscl, "Max").default_value = 0.95
    L(gseed.outputs[0], sockin(gscl, "Seed"))
    gms = M('MULTIPLY', loc=(-820, y - 1380)); L(gscl.outputs[0], gms.inputs[0])
    L(S["Module Scale"], gms.inputs[1])
    L(gms.outputs[0], sockin(gion, "Scale"))

    # station hubs: a few large modules spaced around the band
    hc2p = N("GeometryNodeCurveToPoints"); hc2p.location = (-1400, y - 1540)
    hc2p.mode = 'COUNT'
    L(S["Hub Count"], sockin(hc2p, "Count"))
    L(sockout(circ, "Curve"), sockin(hc2p, "Curve"))
    hion = N("GeometryNodeInstanceOnPoints"); hion.location = (-820, y - 1540)
    L(sockout(hc2p, "Points"), sockin(hion, "Points"))
    L(lib, sockin(hion, "Instance"))
    sockin(hion, "Pick Instance").default_value = True
    hpick = N("FunctionNodeRandomValue"); hpick.location = (-1020, y - 1680)
    hpick.data_type = 'INT'
    sockin(hpick, "Min").default_value = 0
    sockin(hpick, "Max").default_value = len(MODULES) - 1
    hseed = M('ADD', y=101.0 + idx * 5.0, loc=(-1200, y - 1680)); L(S["Seed"], hseed.inputs[0])
    L(hseed.outputs[0], sockin(hpick, "Seed"))
    L(hpick.outputs["Value"], sockin(hion, "Instance Index"))
    L(sockout(hc2p, "Rotation"), sockin(hion, "Rotation"))
    hs = M('MULTIPLY', y=3.4, loc=(-820, y - 1720)); L(S["Module Scale"], hs.inputs[0])
    L(hs.outputs[0], sockin(hion, "Scale"))

    hull = _setmat(g, sockout(c2m, "Mesh"), S["Material"], (-1500, y + 120))
    jn = N("GeometryNodeJoinGeometry"); jn.location = (-560, y)
    for o in (hull, sockout(bion, "Instances"),
              sockout(gion, "Instances"), sockout(hion, "Instances")):
        L(o, sockin(jn, "Geometry"))
    # The band turns about its OWN axis, so the spin has to be applied in the
    # canonical frame and the tilt afterwards. Folding the spin into the tilt
    # transform as a Z euler would rotate the tilted ring about world Z, which
    # makes it wobble like a dropped coin instead of orbiting.
    #
    # Three physical readings of a ring this size, all of them defensible, so
    # Band Motion picks between them rather than the code deciding:
    #   0 Orbiting  - free fall at the Kepler rate for its radius
    #   1 Locked    - held over the same ground, an active-support structure
    #   2 Inertial  - fixed against the stars while the planet turns
    bphase = _anim.geo_orbit_rad(g, rscale, loc=(-1000, y + 760),
                                 label="band %d phase" % idx)
    bspin = _anim.geo_spin_deg(g)
    bspinr = M('MULTIPLY', y=0.017453292519943295, loc=(-820, y + 640))
    L(bspin, bspinr.inputs[0])
    bm0 = M('COMPARE', y=0.0, loc=(-820, y + 880)); bm0.inputs[2].default_value = 0.5
    L(S["Band Motion"], bm0.inputs[0])
    bm1 = M('COMPARE', y=1.0, loc=(-820, y + 800)); bm1.inputs[2].default_value = 0.5
    L(S["Band Motion"], bm1.inputs[0])
    bo = M('MULTIPLY', loc=(-640, y + 760))
    L(bphase, bo.inputs[0]); L(bm0.outputs[0], bo.inputs[1])
    bl = M('MULTIPLY', loc=(-640, y + 640))
    L(bspinr.outputs[0], bl.inputs[0]); L(bm1.outputs[0], bl.inputs[1])
    bang = M('ADD', loc=(-480, y + 700), nm="band %d angle" % idx)
    L(bo.outputs[0], bang.inputs[0]); L(bl.outputs[0], bang.inputs[1])
    brotv = N("ShaderNodeCombineXYZ"); brotv.location = (-480, y + 560)
    L(bang.outputs[0], brotv.inputs[2])
    spinT = N("GeometryNodeTransform"); spinT.location = (-480, y)
    spinT.label = "band %d spin" % idx
    L(sockout(jn, "Geometry"), sockin(spinT, "Geometry"))
    L(sockout(brotv, "Vector"), sockin(spinT, "Rotation"))

    tr = N("GeometryNodeTransform"); tr.location = (-340, y)
    L(sockout(spinT, "Geometry"), sockin(tr, "Geometry"))
    sockin(tr, "Rotation").default_value = (rx, ry, 0.0)
    sw = N("GeometryNodeSwitch"); sw.location = (-120, y)
    sw.input_type = 'GEOMETRY'
    L(gate(thresh, (-340, y + 200)), sw.inputs[0])
    L(sockout(tr, "Geometry"), sw.inputs[2])
    return sw.outputs[0]


def _tether(g, S, gate, y=-2200):
    """Space elevator, authored in a canonical +Z frame.

    Built straight up the Z axis and laid onto the equator by ONE final
    transform. Composing rotations part by part is how the first version ended
    up with the anchor and the ribbon disagreeing about which way was up.

    The ribbon tapers toward geostationary height because a real tether has to
    carry its own weight; a constant-section cable is the giveaway that nobody
    thought about it.
    """
    N, L, M, VM = _mathfns(g)
    line = N("GeometryNodeCurvePrimitiveLine"); line.location = (-1900, y)
    st = N("ShaderNodeCombineXYZ"); st.location = (-2100, y + 100)
    L(S["Radius"], st.inputs[2])
    en = N("ShaderNodeCombineXYZ"); en.location = (-2100, y - 100)
    orr = M('MULTIPLY', y=1.62, loc=(-2280, y - 100)); L(S["Radius"], orr.inputs[0])
    L(orr.outputs[0], en.inputs[2])
    L(sockout(st, "Vector"), sockin(line, "Start"))
    L(sockout(en, "Vector"), sockin(line, "End"))
    res = N("GeometryNodeResampleCurve"); res.location = (-1720, y)
    L(sockout(line, "Curve"), sockin(res, "Curve"))
    sockin(res, "Count").default_value = 96

    # taper, peaking at geostationary height partway up the ribbon
    try:
        sp = N("GeometryNodeSplineParameter")
    except RuntimeError:
        sp = N("GeometryNodeInputSplineParameter")
    sp.location = (-1900, y - 320)
    fac = sockout(sp, "Factor")
    pk = M('MULTIPLY', y=3.14159265, loc=(-1720, y - 320)); L(fac, pk.inputs[0])
    sn = M('SINE', loc=(-1560, y - 320)); L(pk.outputs[0], sn.inputs[0])
    tm1 = M('SUBTRACT', y=1.0, loc=(-1720, y - 440)); L(S["Tether Taper"], tm1.inputs[0])
    tsc = M('MULTIPLY', loc=(-1400, y - 380)); L(sn.outputs[0], tsc.inputs[0])
    L(tm1.outputs[0], tsc.inputs[1])
    taper = M('ADD', x=1.0, loc=(-1240, y - 380), nm="taper"); L(tsc.outputs[0], taper.inputs[1])

    tilt = N("GeometryNodeSetCurveTilt"); tilt.location = (-1540, y)
    L(sockout(res, "Curve"), sockin(tilt, "Curve"))
    tw = M('MULTIPLY', y=2.4, loc=(-1720, y - 560)); L(fac, tw.inputs[0])
    L(tw.outputs[0], sockin(tilt, "Tilt"))

    prof = N("GeometryNodeCurvePrimitiveQuadrilateral"); prof.location = (-1540, y - 200)
    sockin(prof, "Width").default_value = 9.0
    sockin(prof, "Height").default_value = 0.9
    t2m = N("GeometryNodeCurveToMesh"); t2m.location = (-1080, y)
    L(sockout(tilt, "Curve"), sockin(t2m, "Curve"))
    L(sockout(prof, "Curve"), sockin(t2m, "Profile Curve"))
    if "Scale" in t2m.inputs:
        L(taper.outputs[0], sockin(t2m, "Scale"))
        curve_for_climbers = sockout(tilt, "Curve")
    else:
        # 5.2 has Curve to Mesh > Scale, so this branch is for older builds only
        rad = N("GeometryNodeSetCurveRadius"); rad.location = (-1300, y)
        L(sockout(tilt, "Curve"), sockin(rad, "Curve"))
        L(taper.outputs[0], sockin(rad, "Radius"))
        for l in list(sockin(t2m, "Curve").links):
            g.links.remove(l)
        L(sockout(rad, "Curve"), sockin(t2m, "Curve"))
        curve_for_climbers = sockout(rad, "Curve")

    # ---- climbers riding the ribbon --------------------------------------
    #
    # The ribbon is a straight line along +Z in this canonical frame, from R to
    # 1.62 R, so a climber position is just a height: no curve sampling, no
    # resampled-curve index to go stale when Climber Count changes.
    #
    # A tether climber runs at roughly 200 km/h, which on this scale is 33.3
    # units an hour against a 0.62 R ribbon: about two and a half world days
    # from anchor to counterweight. At Timelapse that is a minute of footage,
    # which is exactly the right speed to notice without watching for it.
    #
    # WRAP rather than a modulo chain, so a climber that reaches the top
    # reappears at the anchor instead of piling up at the end.
    tlen = M('MULTIPLY', y=0.62, loc=(-1520, y - 420), nm="ribbon length")
    L(S["Radius"], tlen.inputs[0])
    crate = M('DIVIDE', x=33.333, loc=(-1360, y - 420), nm="climb rate")
    L(tlen.outputs[0], crate.inputs[1])
    ctime = _anim.geo_time(g)
    cadv = M('MULTIPLY', loc=(-1200, y - 420))
    L(ctime, cadv.inputs[0]); L(crate.outputs[0], cadv.inputs[1])

    cidx = N("GeometryNodeInputIndex"); cidx.location = (-1520, y - 560)
    ccnt = M('MAXIMUM', y=1.0, loc=(-1520, y - 640))
    L(S["Climber Count"], ccnt.inputs[0])
    cbase = M('DIVIDE', loc=(-1360, y - 560), nm="climber spacing")
    L(cidx.outputs["Index"], cbase.inputs[0]); L(ccnt.outputs[0], cbase.inputs[1])
    cf0 = M('ADD', loc=(-1040, y - 500))
    L(cbase.outputs[0], cf0.inputs[0]); L(cadv.outputs[0], cf0.inputs[1])
    cf = M('WRAP', loc=(-880, y - 500), nm="climber factor")
    cf.inputs[1].default_value = 1.0
    cf.inputs[2].default_value = 0.0
    L(cf0.outputs[0], cf.inputs[0])
    cz0 = M('MULTIPLY', loc=(-720, y - 500))
    L(cf.outputs[0], cz0.inputs[0]); L(tlen.outputs[0], cz0.inputs[1])
    cz = M('ADD', loc=(-580, y - 500), nm="climber height")
    L(S["Radius"], cz.inputs[0]); L(cz0.outputs[0], cz.inputs[1])
    cpv = N("ShaderNodeCombineXYZ"); cpv.location = (-440, y - 500)
    L(cz.outputs[0], cpv.inputs[2])

    cp = N("GeometryNodePoints"); cp.location = (-1080, y - 420)
    L(S["Climber Count"], sockin(cp, "Count"))
    L(sockout(cpv, "Vector"), sockin(cp, "Position"))

    cb = N("GeometryNodeMeshCube"); cb.location = (-1080, y - 700)
    sockin(cb, "Size").default_value = (16.0, 13.0, 9.0)
    cb_geo = _setmat(g, sockout(cb, "Mesh"), S["Material"], (-960, y - 700))
    cion = N("GeometryNodeInstanceOnPoints"); cion.location = (-300, y - 420)
    L(sockout(cp, "Points"), sockin(cion, "Points"))
    L(cb_geo, sockin(cion, "Instance"))

    # Navigation strobes. Anything this size in a traffic lane carries them,
    # and a blinking light is the cheapest possible proof that a still frame
    # is a frame of something moving. The blink itself lives in the light
    # material, which is what Light Material has been for all along.
    bcn = N("GeometryNodeMeshIcoSphere"); bcn.location = (-1080, y - 840)
    sockin(bcn, "Radius").default_value = 3.4
    sockin(bcn, "Subdivisions").default_value = 1
    bcn_geo = _setmat(g, sockout(bcn, "Mesh"), S["Light Material"], (-960, y - 840))
    bion = N("GeometryNodeInstanceOnPoints"); bion.location = (-300, y - 840)
    L(sockout(cp, "Points"), sockin(bion, "Points"))
    L(bcn_geo, sockin(bion, "Instance"))

    # anchor: tower on a wide apron at the planet surface
    tower = N("GeometryNodeMeshCone"); tower.location = (-1080, y - 760)
    sockin(tower, "Radius Bottom").default_value = 34.0
    sockin(tower, "Radius Top").default_value = 11.0
    sockin(tower, "Depth").default_value = 78.0
    sockin(tower, "Vertices").default_value = 12
    twt = N("GeometryNodeTransform"); twt.location = (-880, y - 760)
    L(sockout(tower, "Mesh"), sockin(twt, "Geometry"))
    twz = N("ShaderNodeCombineXYZ"); twz.location = (-1060, y - 900)
    az = M('ADD', y=39.0, loc=(-1240, y - 900)); L(S["Radius"], az.inputs[0])
    L(az.outputs[0], twz.inputs[2])
    L(sockout(twz, "Vector"), sockin(twt, "Translation"))
    apron = N("GeometryNodeMeshCylinder"); apron.location = (-1080, y - 1040)
    sockin(apron, "Radius").default_value = 62.0
    sockin(apron, "Depth").default_value = 6.0
    sockin(apron, "Vertices").default_value = 20
    apt = N("GeometryNodeTransform"); apt.location = (-880, y - 1040)
    L(sockout(apron, "Mesh"), sockin(apt, "Geometry"))
    apz = N("ShaderNodeCombineXYZ"); apz.location = (-1060, y - 1160)
    L(S["Radius"], apz.inputs[2])
    L(sockout(apz, "Vector"), sockin(apt, "Translation"))

    # counterweight at the far end
    cw = N("GeometryNodeMeshIcoSphere"); cw.location = (-1080, y - 1300)
    sockin(cw, "Radius").default_value = 44.0
    sockin(cw, "Subdivisions").default_value = 2
    cwt = N("GeometryNodeTransform"); cwt.location = (-880, y - 1300)
    L(sockout(cw, "Mesh"), sockin(cwt, "Geometry"))
    L(sockout(en, "Vector"), sockin(cwt, "Translation"))

    jn = N("GeometryNodeJoinGeometry"); jn.location = (-620, y)
    ribbon = _setmat(g, sockout(t2m, "Mesh"), S["Material"], (-900, y))
    for o in (sockout(bion, "Instances"),):
        L(o, sockin(jn, "Geometry"))
    for o in (ribbon, sockout(cion, "Instances"),
              _setmat(g, sockout(twt, "Geometry"), S["Material"], (-720, y - 760)),
              _setmat(g, sockout(apt, "Geometry"), S["Material"], (-720, y - 1040)),
              _setmat(g, sockout(cwt, "Geometry"), S["Material"], (-720, y - 1300))):
        L(o, sockin(jn, "Geometry"))
    # ONE transform: +Z canonical frame -> equatorial
    lay = N("GeometryNodeTransform"); lay.location = (-400, y)
    L(sockout(jn, "Geometry"), sockin(lay, "Geometry"))
    sockin(lay, "Rotation").default_value = (0.0, math.radians(90), 0.0)
    # A space elevator is anchored to a point on the surface. It has no choice
    # about this: it turns with the planet or it tears out of the ground. So
    # unlike the bands, whose motion is a design decision, the tether takes the
    # planet spin and nothing else.
    tspin = _anim.geo_spin_deg(g)
    tspinr = M('MULTIPLY', y=0.017453292519943295, loc=(-400, y + 340))
    L(tspin, tspinr.inputs[0])
    tsv = N("ShaderNodeCombineXYZ"); tsv.location = (-300, y + 340)
    L(tspinr.outputs[0], tsv.inputs[2])
    tspinT = N("GeometryNodeTransform"); tspinT.location = (-280, y)
    tspinT.label = "tether spin"
    L(sockout(lay, "Geometry"), sockin(tspinT, "Geometry"))
    L(sockout(tsv, "Vector"), sockin(tspinT, "Rotation"))

    sw = N("GeometryNodeSwitch"); sw.location = (-140, y)
    sw.input_type = 'GEOMETRY'
    L(gate(8.0, (-400, y + 200)), sw.inputs[0])
    L(sockout(tspinT, "Geometry"), sw.inputs[2])
    return sw.outputs[0]


def build(radius=1000.0, name="PLNT_OrbitalRig"):
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    _iface(g)
    N, L, M, VM = _mathfns(g)
    gi = N("NodeGroupInput"); gi.location = (-2900, 0)
    go = N("NodeGroupOutput"); go.location = (900, 0)
    S = gi.outputs

    def gate(thresh, loc):
        n = M('GREATER_THAN', y=thresh, loc=loc)
        L(S["Orbital Level"], n.inputs[0])
        return n.outputs["Value"]

    lib = build_library(g, S["Material"])
    joins = [_satellites(g, S, lib, gate, y=1400)]
    joins.append(_band(g, S, lib, gate, 0, 0.0, 0.0, 1.24, 3.0, -400))
    joins.append(_band(g, S, lib, gate, 1, math.radians(62), math.radians(18),
                       1.34, 6.0, -2600))
    joins.append(_band(g, S, lib, gate, 2, math.radians(-38), math.radians(74),
                       1.46, 6.0, -4800))
    joins.append(_tether(g, S, gate, y=-7000))

    alljoin = N("GeometryNodeJoinGeometry"); alljoin.location = (500, 0)
    for j in joins:
        L(j, sockin(alljoin, "Geometry"))
    # No Realize Instances: everything already carries its material, and
    # realizing would multiply memory by the instance count for no gain.
    L(sockout(alljoin, "Geometry"), go.inputs["Geometry"])
    ifc = {i.name: i for i in g.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'}
    ifc["Radius"].default_value = radius
    return g


def _drive_seconds(node, scene=None):
    """Seconds of footage elapsed: frame / fps. Independent of Time Scale."""
    scene = scene or bpy.context.scene
    sock = node.outputs[0]
    try:
        sock.driver_remove("default_value")
    except Exception:
        pass
    fc = sock.driver_add("default_value")
    d = fc.driver
    d.type = 'SCRIPTED'
    v = d.variables.new(); v.name = "fps"; v.type = 'SINGLE_PROP'
    t = v.targets[0]; t.id_type = 'SCENE'; t.id = scene
    t.data_path = "render.fps"
    _anim.ensure_scene_props(scene)
    v2 = d.variables.new(); v2.name = "rate"; v2.type = 'SINGLE_PROP'
    t2 = v2.targets[0]; t2.id_type = 'SCENE'; t2.id = scene
    t2.data_path = '["%s"]' % _anim.SCENE_BEACON
    d.expression = "frame / max(fps,1) * rate"
    return fc


def build_light_material(name="PLNT_OrbitalLight"):
    """Emissive material for beacons, lit panels and climber lights.

    The rig has always had a "Light Material" socket and it has always pointed
    at the structural hull, because nothing ever built the material the name
    promised. A hull at metallic 0.85 / roughness 0.30 has no emission at all,
    so every "light" on the orbital infrastructure was in fact a grey panel
    catching the sun -- which is why the bands read as a chain of white beads
    on the night side, where there is no sun to catch.
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new

    out = N("ShaderNodeOutputMaterial"); out.location = (620, 0)
    em = N("ShaderNodeEmission"); em.location = (380, 0); em.label = "beacon"
    sockin(em, "Color").default_value = (0.62, 0.80, 1.0, 1.0)
    sockin(em, "Strength").default_value = 14.0

    # Per-instance variety, so a row of beacons is not one flat value. This is
    # also the socket Phase 5's 1 Hz strobe multiplies into.
    oi = N("ShaderNodeObjectInfo"); oi.location = (-260, -160)
    var = N("ShaderNodeMapRange"); var.location = (-40, -160); var.clamp = True
    var.label = "BEACON_VAR"
    L(sockout(oi, "Random"), var.inputs[0])
    for i, v in ((1, 0.0), (2, 1.0), (3, 0.55), (4, 1.45)):
        var.inputs[i].default_value = v
    # 1 Hz of FOOTAGE, not of world time. A collision beacon blinks about once
    # a second to the eye watching it, and at Timelapse one world hour passes
    # per second, so driving the strobe from world time would run it at 3600 Hz
    # and it would render as a constant dim glow.
    sec = N("ShaderNodeValue"); sec.location = (-260, -420)
    sec.label = "PLNT_SECONDS"; sec.name = "PLNT_SECONDS"
    _drive_seconds(sec)
    off = N("ShaderNodeMath"); off.operation = 'MULTIPLY'; off.location = (-260, -560)
    off.inputs[1].default_value = 0.97       # de-synchronise neighbours
    L(sockout(oi, "Random"), off.inputs[0])
    phs = N("ShaderNodeMath"); phs.operation = 'ADD'; phs.location = (-80, -480)
    L(sec.outputs[0], phs.inputs[0]); L(off.outputs[0], phs.inputs[1])
    frac = N("ShaderNodeMath"); frac.operation = 'FRACT'; frac.location = (80, -480)
    L(phs.outputs[0], frac.inputs[0])
    blink = N("ShaderNodeMapRange"); blink.location = (240, -480); blink.clamp = True
    blink.label = "BEACON_BLINK"; blink.interpolation_type = 'SMOOTHSTEP'
    for i, v in ((1, 0.10), (2, 0.16), (3, 1.0), (4, 0.22)):
        blink.inputs[i].default_value = v
    L(frac.outputs[0], blink.inputs[0])

    gain = N("ShaderNodeMath"); gain.operation = 'MULTIPLY'; gain.location = (160, -160)
    gain.label = "BEACON_GAIN"
    gain.inputs[1].default_value = 14.0
    L(var.outputs["Result"], gain.inputs[0])
    strobe = N("ShaderNodeMath"); strobe.operation = 'MULTIPLY'
    strobe.location = (420, -160); strobe.label = "BEACON_STROBE"
    L(gain.outputs[0], strobe.inputs[0])
    L(blink.outputs["Result"], strobe.inputs[1])
    L(strobe.outputs[0], sockin(em, "Strength"))
    L(sockout(em, "Emission"), sockin(out, "Surface"))
    # A beacon is a light, not a shadow caster; letting it cast turns every
    # window into a hard black stripe across the module behind it.
    mat.cycles.emission_sampling = 'NONE'
    return mat


def build_material(name="PLNT_Orbital", light_name="PLNT_OrbitalLight"):
    """Structural hull: multi-layer insulation, gold foil, panels, radiators.

    The shipped hull was one Principled BSDF at metallic 0.85 / roughness 0.30
    over a base colour of 0.022 grey. A near-black metal with a tight specular
    lobe returns almost nothing except the sun, so at planet scale every module
    resolved to the same small white highlight and the bands read as chains of
    beads. Real orbital hardware is not one material: it is matte insulation
    blanket, gold thermal foil, bare panel and black radiator, in roughly that
    order of area, and the variety is what makes the silhouette legible.

    Each class is chosen per instance from Object Info > Random through
    CONSTANT colour ramps, which Cycles evaluates once per instance rather than
    per hit, so twelve module types become four thousand distinguishable
    objects for the cost of three ramp lookups.
    """
    mat = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new

    out = N("ShaderNodeOutputMaterial"); out.location = (1100, 0)
    bsdf = N("ShaderNodeBsdfPrincipled"); bsdf.location = (700, 160)
    sockin(bsdf, "IOR").default_value = 1.45

    oi = N("ShaderNodeObjectInfo"); oi.location = (-900, 120)
    RAND = sockout(oi, "Random")

    def ramp(label, stops, loc):
        """CONSTANT ramp: one class per band of the instance random."""
        n = N("ShaderNodeValToRGB"); n.location = loc; n.label = label
        n.color_ramp.interpolation = 'CONSTANT'
        el = n.color_ramp.elements
        el[0].position = 0.0
        el[0].color = stops[0][1]
        while len(el) > 1:
            el.remove(el[len(el) - 1])
        for pos, col in stops[1:]:
            e = el.new(pos)
            e.color = col
        L(RAND, n.inputs["Fac"])
        return n

    # 40% insulation blanket, 22% gold foil, 23% bare panel, 15% radiator
    base = ramp("hull class", [
        (0.00, (0.55, 0.55, 0.54, 1.0)),     # MLI blanket, matte off-white
        (0.40, (0.72, 0.53, 0.16, 1.0)),     # gold thermal foil
        (0.62, (0.62, 0.64, 0.66, 1.0)),     # bare aluminium panel
        (0.85, (0.045, 0.048, 0.052, 1.0)),  # radiator
    ], (-620, 320))
    metal = ramp("hull metallic", [
        (0.00, (0.0, 0.0, 0.0, 1.0)),
        (0.40, (1.0, 1.0, 1.0, 1.0)),
        (0.62, (1.0, 1.0, 1.0, 1.0)),
        (0.85, (0.15, 0.15, 0.15, 1.0)),
    ], (-620, 40))
    rough = ramp("hull roughness", [
        (0.00, (0.62, 0.62, 0.62, 1.0)),
        (0.40, (0.34, 0.34, 0.34, 1.0)),
        (0.62, (0.22, 0.22, 0.22, 1.0)),
        (0.85, (0.48, 0.48, 0.48, 1.0)),
    ], (-620, -240))

    # Panel seams and streaking, in the instance own texture space so it
    # follows the module instead of sweeping across the whole band.
    tc = N("ShaderNodeTexCoord"); tc.location = (-900, -540)
    streak = N("ShaderNodeTexNoise"); streak.location = (-700, -540)
    streak.label = "hull streaks"
    streak.noise_type = 'FBM'
    sockin(streak, "Scale").default_value = 9.0
    sockin(streak, "Detail").default_value = 4.0
    sockin(streak, "Roughness").default_value = 0.62
    L(sockout(tc, "Generated"), sockin(streak, "Vector"))
    stk = N("ShaderNodeMapRange"); stk.location = (-500, -540)
    stk.clamp = True; stk.label = "streak gain"
    for i, v in ((1, 0.30), (2, 0.70), (3, 0.82), (4, 1.06)):
        stk.inputs[i].default_value = v
    L(sockout(streak, "Fac"), stk.inputs[0])
    tint = N("ShaderNodeVectorMath"); tint.operation = 'SCALE'
    tint.location = (-260, 320); tint.label = "weathered base"
    L(base.outputs["Color"], tint.inputs[0])
    L(stk.outputs["Result"], sockin(tint, "Scale"))

    L(sockout(tint, "Vector"), sockin(bsdf, "Base Color"))
    L(metal.outputs["Color"], sockin(bsdf, "Metallic"))
    L(rough.outputs["Color"], sockin(bsdf, "Roughness"))

    # Window lights are keyed off Object Info > Random, which Cycles evaluates
    # per instance. The first version drove them from a world-space Z wave, so
    # one band of light cut across every module at an arbitrary angle no matter
    # how the module was oriented.
    lit = N("ShaderNodeMapRange"); lit.location = (-500, -180); lit.clamp = True
    lit.label = "lit modules"
    L(RAND, lit.inputs[0])
    for i, v in ((1, 0.45), (2, 0.55), (3, 0.0), (4, 1.0)):
        lit.inputs[i].default_value = v

    # window grid in the instance own space, so it follows the module
    wav = N("ShaderNodeTexWave"); wav.location = (-700, -820)
    wav.wave_type = 'BANDS'; wav.bands_direction = 'Z'
    sockin(wav, "Scale").default_value = 26.0
    sockin(wav, "Distortion").default_value = 0.0
    L(sockout(tc, "Generated"), sockin(wav, "Vector"))
    rmp = N("ShaderNodeValToRGB"); rmp.location = (-500, -820)
    L(sockout(wav, "Fac"), sockin(rmp, "Fac"))
    rmp.color_ramp.elements[0].position = 0.78
    rmp.color_ramp.elements[1].position = 0.90

    win = N("ShaderNodeMath"); win.operation = 'MULTIPLY'; win.location = (-160, -700)
    win.label = "windows"
    L(rmp.outputs["Color"], win.inputs[0])
    L(lit.outputs["Result"], win.inputs[1])

    em = N("ShaderNodeEmission"); em.location = (700, -360)
    sockin(em, "Color").default_value = (0.55, 0.82, 1.0, 1.0)
    sockin(em, "Strength").default_value = 3.2
    mix = N("ShaderNodeMixShader"); mix.location = (920, 0)
    L(win.outputs[0], mix.inputs[0])
    L(sockout(bsdf, "BSDF"), mix.inputs[1])
    L(sockout(em, "Emission"), mix.inputs[2])
    L(mix.outputs[0], sockin(out, "Surface"))
    build_light_material(light_name)
    return mat


def make_object(radius=1000.0, name="PLNT_Orbital"):
    """Create or refresh the orbital object, its rig and its materials.

    Self-contained so core/scene.py never has to reach back into the
    transitional flat plnt_orbital.py, which cannot be imported inside a
    packaged extension.
    """
    g = build(radius)
    mat = build_material()
    light = bpy.data.materials.get("PLNT_OrbitalLight") or build_light_material()
    ob = bpy.data.objects.get(name)
    if ob is None:
        me = bpy.data.meshes.new(name + "Mesh")
        ob = bpy.data.objects.new(name, me)
        bpy.context.scene.collection.objects.link(ob)
    for md in list(ob.modifiers):
        ob.modifiers.remove(md)
    mod = ob.modifiers.new(name + "Rig", 'NODES')
    mod.node_group = g
    ids = {i.name: i.identifier for i in g.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
           and i.socket_type != 'NodeSocketGeometry'}

    def st(n, v):
        if n not in ids:
            return
        slot = mod.properties.inputs[ids[n]]
        try:
            if "value" in slot.keys():
                slot["value"] = v
                return
        except Exception:
            pass
        mod.properties.inputs[ids[n]] = v

    for k, v in (("Radius", radius), ("Orbital Level", 0.0), ("Seed", 0.0),
                 ("Band Height", 38.0), ("Band Width", 16.0),
                 ("Band Resolution", 220), ("Bay Length", 46.0),
                 ("Longeron Radius", 2.6), ("Satellite Density", 0.20),
                 ("Cluster Scale", 2.6), ("Shell Thickness", 0.16),
                 ("Module Scale", 1.0), ("Hub Count", 5),
                 ("Lit Fraction", 0.55), ("Tether Taper", 5.5),
                 ("Climber Count", 7), ("Band Motion", 0),
                 ("Material", mat),
                 ("Light Material", light)):
        st(k, v)
    ob.visible_shadow = True
    return ob, mod, mat
