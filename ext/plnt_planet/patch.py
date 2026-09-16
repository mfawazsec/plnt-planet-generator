"""PLNT_Patch — ground-level terrain patch.

A separate object at metre scale. Patch XY is mapped to a spherical coordinate
on the same planet and PLNT_TerrainField is sampled there, so the patch matches
the globe exactly, then local octaves the globe can never resolve are added on
top (boulder / scree / stratification).
"""
import bpy
import math

FIELD_PARAMS = ["Seed", "Continent Scale", "Continent Coverage", "Mountain Sharpness",
                "Erosion Amount", "Tectonic Belt Width", "Warp Strength", "Sea Level",
                "Polar Cap Extent"]

FIELD_DEFAULTS = {
    "Seed": (0.0, -10000.0, 10000.0),
    "Continent Scale": (1.8, 0.05, 40.0),
    "Continent Coverage": (0.42, 0.0, 1.0),
    "Mountain Sharpness": (0.55, 0.0, 2.0),
    "Erosion Amount": (0.35, 0.0, 1.0),
    "Tectonic Belt Width": (0.22, 0.01, 1.0),
    "Warp Strength": (0.45, 0.0, 2.0),
    "Sea Level": (0.0, -1.0, 1.0),
    "Polar Cap Extent": (0.18, 0.0, 0.95),
}


def build():
    name = "PLNT_PatchRig"
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    I = g.interface
    I.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    I.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    def sk(n, st, dv=None, mn=None, mx=None):
        s = I.new_socket(name=n, in_out='INPUT', socket_type=st)
        if dv is not None: s.default_value = dv
        if mn is not None: s.min_value = mn
        if mx is not None: s.max_value = mx
        return s

    sk("Patch Latitude", 'NodeSocketFloat', 18.0, -89.0, 89.0)
    sk("Patch Longitude", 'NodeSocketFloat', 40.0, -360.0, 360.0)
    sk("Patch Size KM", 'NodeSocketFloat', 6.0, 0.05, 400.0)
    sk("Patch Resolution", 'NodeSocketInt', 420, 4, 1200)
    sk("Planet Radius KM", 'NodeSocketFloat', 6000.0, 10.0, 200000.0)
    sk("Relief KM", 'NodeSocketFloat', 9.0, 0.0, 200.0)
    sk("Detail Amount", 'NodeSocketFloat', 1.0, 0.0, 4.0)
    sk("Rock Density", 'NodeSocketFloat', 1.0, 0.0, 6.0)
    for p in FIELD_PARAMS:
        dv, mn, mx = FIELD_DEFAULTS[p]
        sk(p, 'NodeSocketFloat', dv, mn, mx)
    sk("Material", 'NodeSocketMaterial')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2600, 0)
    go = N("NodeGroupOutput"); go.location = (2400, 0)

    def M(op, x=None, y=None, loc=(0, 0), nm=""):
        n = N("ShaderNodeMath"); n.operation = op; n.location = loc; n.label = nm
        if x is not None: n.inputs[0].default_value = x
        if y is not None: n.inputs[1].default_value = y
        return n

    def NOISE(loc, scale, detail, rough, nm):
        n = N("ShaderNodeTexNoise"); n.location = loc; n.label = nm
        n.noise_dimensions = '4D'; n.noise_type = 'FBM'
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n

    # ---- grid sized in metres
    size_m = M('MULTIPLY', y=1000.0, loc=(-2400, 300), nm="size_m")
    L(gi.outputs["Patch Size KM"], size_m.inputs[0])
    grid = N("GeometryNodeMeshGrid"); grid.location = (-2200, 200)
    L(size_m.outputs["Value"], grid.inputs["Size X"])
    L(size_m.outputs["Value"], grid.inputs["Size Y"])
    L(gi.outputs["Patch Resolution"], grid.inputs["Vertices X"])
    L(gi.outputs["Patch Resolution"], grid.inputs["Vertices Y"])

    pos = N("GeometryNodeInputPosition"); pos.location = (-2400, -200)
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (-2220, -200)
    L(pos.outputs["Position"], sep.inputs["Vector"])

    # ---- patch XY (metres) -> spherical coordinate on the planet
    Rm = M('MULTIPLY', y=1000.0, loc=(-2400, -420), nm="R_m")
    L(gi.outputs["Planet Radius KM"], Rm.inputs[0])
    lat0 = M('MULTIPLY', y=math.pi / 180.0, loc=(-2400, -600))
    L(gi.outputs["Patch Latitude"], lat0.inputs[0])
    lon0 = M('MULTIPLY', y=math.pi / 180.0, loc=(-2400, -760))
    L(gi.outputs["Patch Longitude"], lon0.inputs[0])

    dlat = M('DIVIDE', loc=(-2040, -300), nm="dlat")
    L(sep.outputs["Y"], dlat.inputs[0]); L(Rm.outputs["Value"], dlat.inputs[1])
    coslat0 = M('COSINE', loc=(-2220, -600)); L(lat0.outputs["Value"], coslat0.inputs[0])
    cosclamp = M('MAXIMUM', y=0.02, loc=(-2040, -600)); L(coslat0.outputs["Value"], cosclamp.inputs[0])
    denom = M('MULTIPLY', loc=(-1860, -520))
    L(Rm.outputs["Value"], denom.inputs[0]); L(cosclamp.outputs["Value"], denom.inputs[1])
    dlon = M('DIVIDE', loc=(-1860, -360), nm="dlon")
    L(sep.outputs["X"], dlon.inputs[0]); L(denom.outputs["Value"], dlon.inputs[1])
    lat = M('ADD', loc=(-1680, -300), nm="lat")
    L(lat0.outputs["Value"], lat.inputs[0]); L(dlat.outputs["Value"], lat.inputs[1])
    lon = M('ADD', loc=(-1680, -460), nm="lon")
    L(lon0.outputs["Value"], lon.inputs[0]); L(dlon.outputs["Value"], lon.inputs[1])

    cl = M('COSINE', loc=(-1500, -240)); L(lat.outputs["Value"], cl.inputs[0])
    sl = M('SINE', loc=(-1500, -400)); L(lat.outputs["Value"], sl.inputs[0])
    co = M('COSINE', loc=(-1500, -560)); L(lon.outputs["Value"], co.inputs[0])
    so = M('SINE', loc=(-1500, -720)); L(lon.outputs["Value"], so.inputs[0])
    px = M('MULTIPLY', loc=(-1320, -240)); L(cl.outputs["Value"], px.inputs[0]); L(co.outputs["Value"], px.inputs[1])
    py = M('MULTIPLY', loc=(-1320, -400)); L(cl.outputs["Value"], py.inputs[0]); L(so.outputs["Value"], py.inputs[1])
    P = N("ShaderNodeCombineXYZ"); P.location = (-1140, -320); P.label = "P_sphere"
    L(px.outputs["Value"], P.inputs[0]); L(py.outputs["Value"], P.inputs[1])
    L(sl.outputs["Value"], P.inputs[2])

    # ---- sample the SAME field the globe uses
    F = N("GeometryNodeGroup"); F.node_tree = bpy.data.node_groups["PLNT_TerrainField"]
    F.location = (-940, -200); F.label = "FIELD"
    L(P.outputs["Vector"], F.inputs["Position"])
    for p in FIELD_PARAMS:
        L(gi.outputs[p], F.inputs[p])

    relief_m = M('MULTIPLY', y=1000.0, loc=(-940, 300), nm="relief_m")
    L(gi.outputs["Relief KM"], relief_m.inputs[0])
    base_h = M('MULTIPLY', loc=(-700, 200), nm="base_h")
    L(F.outputs["elevation"], base_h.inputs[0]); L(relief_m.outputs["Value"], base_h.inputs[1])

    # ---- local octaves the globe never resolves (metre scale, on local XY)
    lp = N("ShaderNodeCombineXYZ"); lp.location = (-2040, -900)
    L(sep.outputs["X"], lp.inputs[0]); L(sep.outputs["Y"], lp.inputs[1])
    sw = M('MULTIPLY', y=13.7, loc=(-2220, -1060)); L(gi.outputs["Seed"], sw.inputs[0])

    def octave(scale_div, amp, detail, rough, y, nm):
        n = NOISE((-1700, y), 1.0, detail, rough, nm)
        sc = M('DIVIDE', x=1.0, loc=(-1880, y - 140))
        sc.inputs[0].default_value = 1.0
        sc.inputs[1].default_value = scale_div
        L(lp.outputs["Vector"], n.inputs["Vector"])
        L(sw.outputs["Value"], n.inputs["W"])
        n.inputs["Scale"].default_value = 1.0 / scale_div
        c = M('SUBTRACT', y=0.5, loc=(-1500, y)); L(n.outputs["Factor"], c.inputs[0])
        a = M('MULTIPLY', y=amp, loc=(-1320, y), nm=nm + "_amp")
        L(c.outputs["Value"], a.inputs[0])
        return a

    macro = octave(7000.0, 430.0, 6.0, 0.55, -600, "macro")   # ridge/valley scale
    large = octave(1900.0, 145.0, 7.0, 0.52, -900, "large")   # spurs
    strat = octave(520.0, 38.0, 7.0, 0.55, -1200, "strat")    # stratification
    scree = octave(62.0, 5.8, 6.0, 0.50, -1500, "scree")      # scree slopes
    bould = octave(5.0, 0.7, 4.0, 0.45, -1800, "boulder")     # boulder scale

    d0 = M('ADD', loc=(-1120, -750)); L(macro.outputs["Value"], d0.inputs[0]); L(large.outputs["Value"], d0.inputs[1])
    d1 = M('ADD', loc=(-1120, -1050)); L(d0.outputs["Value"], d1.inputs[0]); L(strat.outputs["Value"], d1.inputs[1])
    d1b = M('ADD', loc=(-1040, -1150)); L(d1.outputs["Value"], d1b.inputs[0]); L(scree.outputs["Value"], d1b.inputs[1])
    d2 = M('ADD', loc=(-940, -1050)); L(d1b.outputs["Value"], d2.inputs[0]); L(bould.outputs["Value"], d2.inputs[1])
    # mountainous regions of the globe get dramatic local relief; plains stay flat
    tmod = N("ShaderNodeMapRange"); tmod.location = (-1120, -1350); tmod.clamp = True
    tmod.label = "terrain mod"
    L(F.outputs["slope"], tmod.inputs[0])
    for _i, _v in ((1, 0.0), (2, 0.45), (3, 0.30), (4, 2.10)):
        tmod.inputs[_i].default_value = _v
    dmod = M('MULTIPLY', loc=(-860, -1250))
    L(d2.outputs["Value"], dmod.inputs[0]); L(tmod.outputs["Result"], dmod.inputs[1])
    dscale = M('MULTIPLY', loc=(-760, -1050), nm="detail_h")
    L(dmod.outputs["Value"], dscale.inputs[0]); L(gi.outputs["Detail Amount"], dscale.inputs[1])

    # distance-based falloff so far ground is cheaper/smoother
    dist = N("ShaderNodeVectorMath"); dist.operation = 'LENGTH'; dist.location = (-2040, -1700)
    L(lp.outputs["Vector"], dist.inputs[0])
    half = M('MULTIPLY', y=0.5, loc=(-2040, -1860)); L(size_m.outputs["Value"], half.inputs[0])
    fall = N("ShaderNodeMapRange"); fall.location = (-1700, -1760); fall.clamp = True
    fall.label = "detail falloff"
    L(dist.outputs["Value"], fall.inputs[0])
    fall.inputs[1].default_value = 0.0
    L(half.outputs["Value"], fall.inputs[2])
    fall.inputs[3].default_value = 1.0
    fall.inputs[4].default_value = 0.35
    dfin = M('MULTIPLY', loc=(-580, -1050))
    L(dscale.outputs["Value"], dfin.inputs[0]); L(fall.outputs["Result"], dfin.inputs[1])

    ztot = M('ADD', loc=(-380, 100), nm="z_total")
    L(base_h.outputs["Value"], ztot.inputs[0]); L(dfin.outputs["Value"], ztot.inputs[1])
    # level the patch: subtract the centre height so it sits near z=0
    offv = N("ShaderNodeCombineXYZ"); offv.location = (-200, 100)
    L(ztot.outputs["Value"], offv.inputs[2])
    sp = N("GeometryNodeSetPosition"); sp.location = (0, 100)
    L(grid.outputs["Mesh"], sp.inputs["Geometry"])
    L(offv.outputs["Vector"], sp.inputs["Offset"])

    # ---- scattered rocks
    dpf = N("GeometryNodeDistributePointsOnFaces"); dpf.location = (300, -400)
    L(sp.outputs["Geometry"], dpf.inputs["Mesh"])
    dens = M('MULTIPLY', y=0.0016, loc=(120, -500)); L(gi.outputs["Rock Density"], dens.inputs[0])
    L(dens.outputs["Value"], dpf.inputs["Density"])
    L(gi.outputs["Seed"], dpf.inputs["Seed"])
    rock = N("GeometryNodeMeshIcoSphere"); rock.location = (300, -650)
    rock.inputs["Radius"].default_value = 1.0
    rock.inputs["Subdivisions"].default_value = 3
    ion = N("GeometryNodeInstanceOnPoints"); ion.location = (540, -400)
    L(dpf.outputs["Points"], ion.inputs["Points"])
    L(rock.outputs["Mesh"], ion.inputs["Instance"])
    rrnd = N("FunctionNodeRandomValue"); rrnd.location = (300, -820)
    rrnd.data_type = 'FLOAT_VECTOR'
    rrnd.inputs[0].default_value = (0.8, 0.8, 0.55)
    rrnd.inputs[1].default_value = (4.2, 4.2, 2.6)
    L(gi.outputs["Seed"], rrnd.inputs["Seed"])
    L(rrnd.outputs[0], ion.inputs["Scale"])
    rrot = N("FunctionNodeRandomValue"); rrot.location = (300, -1000)
    rrot.data_type = 'FLOAT_VECTOR'
    rrot.inputs[0].default_value = (0.0, 0.0, 0.0)
    rrot.inputs[1].default_value = (0.4, 0.4, 6.28)
    L(gi.outputs["Seed"], rrot.inputs["Seed"])
    L(rrot.outputs[0], ion.inputs["Rotation"])
    real = N("GeometryNodeRealizeInstances"); real.location = (760, -400)
    L(ion.outputs["Instances"], real.inputs["Geometry"])

    jn = N("GeometryNodeJoinGeometry"); jn.location = (1000, 0)
    L(sp.outputs["Geometry"], jn.inputs["Geometry"])
    L(real.outputs["Geometry"], jn.inputs["Geometry"])
    sm = N("GeometryNodeSetShadeSmooth"); sm.location = (1300, 0)
    L(jn.outputs["Geometry"], sm.inputs["Geometry"])
    stp = N("GeometryNodeStoreNamedAttribute"); stp.location = (1450, 0)
    stp.data_type = 'FLOAT_VECTOR'; stp.domain = 'POINT'
    stp.inputs["Name"].default_value = "sphere_pos"
    L(sm.outputs["Geometry"], stp.inputs["Geometry"])
    L(P.outputs["Vector"], stp.inputs["Value"])
    setm = N("GeometryNodeSetMaterial"); setm.location = (1600, 0)
    L(stp.outputs["Geometry"], setm.inputs["Geometry"])
    L(gi.outputs["Material"], setm.inputs["Material"])
    L(setm.outputs["Geometry"], go.inputs["Geometry"])
    return g


def make_object():
    grp = build()
    name = "PLNT_Patch"
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    me = bpy.data.meshes.new(name + "Mesh")
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (0.0, 0.0, -40000.0)   # kept far from the globe
    mod = ob.modifiers.new(name + "Rig", 'NODES')
    mod.node_group = grp
    return ob, mod
