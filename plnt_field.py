"""PLNT terrain field builder.

Emits the SAME field graph into either a GeometryNodeTree (for displacement)
or a ShaderNodeTree (for per-pixel surface evaluation). Node types used here
exist in both tree types, so one source of truth guarantees the shader field
and the geometry field agree exactly.
"""
import bpy

EPS = 0.0045


def _shader(tree):
    name = tree if isinstance(tree, str) else tree.bl_idname
    return name == 'ShaderNodeTree'


def _grp(tree):
    return "ShaderNodeGroup" if _shader(tree) else "GeometryNodeGroup"


def _new(tree, name):
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    return bpy.data.node_groups.new(name, tree)


def _sk(g, n, io, st, dv=None, mn=None, mx=None):
    s = g.interface.new_socket(name=n, in_out=io, socket_type=st)
    if dv is not None:
        s.default_value = dv
    if mn is not None:
        s.min_value = mn
    if mx is not None:
        s.max_value = mx
    return s


ELEV_IN = [
    ("Position", 'NodeSocketVector', None, None, None),
    ("Seed", 'NodeSocketFloat', 0.0, -10000.0, 10000.0),
    ("Continent Scale", 'NodeSocketFloat', 1.8, 0.05, 40.0),
    ("Continent Coverage", 'NodeSocketFloat', 0.42, 0.0, 1.0),
    ("Mountain Sharpness", 'NodeSocketFloat', 0.55, 0.0, 2.0),
    ("Erosion Amount", 'NodeSocketFloat', 0.35, 0.0, 1.0),
    ("Tectonic Belt Width", 'NodeSocketFloat', 0.22, 0.01, 1.0),
    ("Warp Strength", 'NodeSocketFloat', 0.45, 0.0, 2.0),
    ("Sea Level", 'NodeSocketFloat', 0.0, -1.0, 1.0),
]
ELEV_PASS = [n for n, *_ in ELEV_IN if n != "Position"]

FIELD_IN = ELEV_IN + [("Polar Cap Extent", 'NodeSocketFloat', 0.18, 0.0, 0.95)]
FIELD_OUT = ["elevation", "slope", "latitude", "temperature", "humidity",
             "sea_mask", "river_mask", "habitability", "biome_id", "ocean_depth"]


def build_elevation(tree_type, name):
    g = _new(tree_type, name)
    for n, st, dv, mn, mx in ELEV_IN:
        _sk(g, n, 'INPUT', st, dv, mn, mx)
    for n in ("Elevation", "Raw Elevation", "Continent", "River"):
        _sk(g, n, 'OUTPUT', 'NodeSocketFloat')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2200, 0)
    go = N("NodeGroupOutput"); go.location = (2400, 0)

    def M(op, x=None, y=None, loc=(0, 0), nm="", clamp=False):
        n = N("ShaderNodeMath"); n.operation = op; n.location = loc
        n.label = nm; n.use_clamp = clamp
        if x is not None: n.inputs[0].default_value = x
        if y is not None: n.inputs[1].default_value = y
        return n

    def VM(op, loc=(0, 0), nm=""):
        n = N("ShaderNodeVectorMath"); n.operation = op; n.location = loc; n.label = nm
        return n

    def NOISE(loc, detail=6.0, rough=0.5, ntype='FBM', nm=""):
        n = N("ShaderNodeTexNoise"); n.location = loc
        n.noise_dimensions = '4D'; n.noise_type = ntype; n.label = nm
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n

    def seedw(mul, add, loc):
        a = M('MULTIPLY', y=mul, loc=loc)
        L(gi.outputs["Seed"], a.inputs[0])
        b = M('ADD', y=add, loc=(loc[0] + 170, loc[1]))
        L(a.outputs["Value"], b.inputs[0])
        return b.outputs["Value"]

    w_warp = seedw(1.000, 0.00, (-2050, 700))
    w_cont = seedw(1.713, 13.37, (-2050, 520))
    w_ridge = seedw(2.391, 71.90, (-2050, 340))
    w_micro = seedw(3.117, 137.40, (-2050, 160))
    w_vor = seedw(0.911, 202.50, (-2050, -20))

    # domain warp
    wn = NOISE((-1700, 900), 3.0, 0.5, 'FBM', "warp")
    wn.inputs["Scale"].default_value = 1.15
    L(gi.outputs["Position"], wn.inputs["Vector"])
    L(w_warp, wn.inputs["W"])
    ws = VM('SUBTRACT', (-1500, 900)); L(wn.outputs["Color"], ws.inputs[0])
    ws.inputs[1].default_value = (0.5, 0.5, 0.5)
    wa = M('MULTIPLY', y=2.0, loc=(-1700, 1080))
    L(gi.outputs["Warp Strength"], wa.inputs[0])
    wsc = VM('SCALE', (-1320, 900))
    L(ws.outputs["Vector"], wsc.inputs[0]); L(wa.outputs["Value"], wsc.inputs["Scale"])
    Pw = VM('ADD', (-1130, 780), "P_warped")
    L(gi.outputs["Position"], Pw.inputs[0]); L(wsc.outputs["Vector"], Pw.inputs[1])

    # continents
    cn = NOISE((-900, 640), 6.0, 0.52, 'FBM', "continents")
    L(Pw.outputs["Vector"], cn.inputs["Vector"])
    L(gi.outputs["Continent Scale"], cn.inputs["Scale"])
    L(w_cont, cn.inputs["W"])
    thr = N("ShaderNodeMapRange"); thr.location = (-900, 400); thr.clamp = True
    L(gi.outputs["Continent Coverage"], thr.inputs[0])
    for i, v in ((1, 0.0), (2, 1.0), (3, 0.72), (4, 0.30)):
        thr.inputs[i].default_value = v
    csig = M('SUBTRACT', loc=(-650, 560), nm="csig")
    L(cn.outputs["Factor"], csig.inputs[0]); L(thr.outputs["Result"], csig.inputs[1])

    # tectonic belts hugging coastlines
    rn = NOISE((-650, 260), 7.0, 0.52, 'RIDGED_MULTIFRACTAL', "ridges")
    rn.inputs["Lacunarity"].default_value = 2.1
    L(Pw.outputs["Vector"], rn.inputs["Vector"]); L(w_ridge, rn.inputs["W"])
    rsc = M('MULTIPLY', y=3.4, loc=(-880, 120))
    L(gi.outputs["Continent Scale"], rsc.inputs[0]); L(rsc.outputs["Value"], rn.inputs["Scale"])
    cab = M('ABSOLUTE', loc=(-430, 120)); L(csig.outputs["Value"], cab.inputs[0])
    cdv = M('DIVIDE', loc=(-250, 120), clamp=True)
    L(cab.outputs["Value"], cdv.inputs[0]); L(gi.outputs["Tectonic Belt Width"], cdv.inputs[1])
    belt = M('SUBTRACT', x=1.0, loc=(-70, 120), clamp=True)
    L(cdv.outputs["Value"], belt.inputs[1])
    # smooth land gate: a hard step here puts vertical cliffs in the geometry
    landg = N("ShaderNodeMapRange"); landg.location = (-250, -60); landg.clamp = True
    landg.label = "is_land"
    for _i, _v in ((1, 0.0), (2, 0.020), (3, 0.0), (4, 1.0)):
        landg.inputs[_i].default_value = _v
    L(csig.outputs["Value"], landg.inputs[0])
    bl = M('MULTIPLY', loc=(110, 120))
    L(belt.outputs["Value"], bl.inputs[0]); L(landg.outputs["Result"], bl.inputs[1])
    r1 = M('MULTIPLY', loc=(110, 300))
    L(rn.outputs["Factor"], r1.inputs[0]); L(bl.outputs["Value"], r1.inputs[1])
    rf = M('MULTIPLY', y=0.95, loc=(110, 470))
    L(gi.outputs["Mountain Sharpness"], rf.inputs[0])
    ridge = M('MULTIPLY', loc=(300, 300), nm="ridge")
    L(r1.outputs["Value"], ridge.inputs[0]); L(rf.outputs["Value"], ridge.inputs[1])

    # erosion channels: cell edges = thin dendritic rivers
    # second, finer warp so channel edges wander instead of reading as polygons
    rwn = NOISE((-1100, -120), 7.0, 0.62, 'FBM', "river warp")
    rwn.inputs["Scale"].default_value = 7.4
    L(Pw.outputs["Vector"], rwn.inputs["Vector"]); L(w_vor, rwn.inputs["W"])
    rws = VM('SUBTRACT', (-940, -120)); L(rwn.outputs["Color"], rws.inputs[0])
    rws.inputs[1].default_value = (0.5, 0.5, 0.5)
    rwsc = VM('SCALE', (-800, -120)); L(rws.outputs["Vector"], rwsc.inputs[0])
    rwsc.inputs["Scale"].default_value = 1.35
    rwp = VM('ADD', (-660, -120)); L(Pw.outputs["Vector"], rwp.inputs[0])
    L(rwsc.outputs["Vector"], rwp.inputs[1])

    vd = N("ShaderNodeTexVoronoi"); vd.location = (-650, -260)
    vd.voronoi_dimensions = '4D'; vd.feature = 'DISTANCE_TO_EDGE'
    vd.inputs["Randomness"].default_value = 1.0
    L(rwp.outputs["Vector"], vd.inputs["Vector"]); L(w_vor, vd.inputs["W"])
    vsc = M('MULTIPLY', y=23.0, loc=(-880, -300))
    L(gi.outputs["Continent Scale"], vsc.inputs[0]); L(vsc.outputs["Value"], vd.inputs["Scale"])
    riv = N("ShaderNodeMapRange"); riv.location = (-430, -260); riv.clamp = True
    L(vd.outputs["Distance"], riv.inputs[0])
    for i, v in ((1, 0.0), (2, 0.010), (3, 1.0), (4, 0.0)):
        riv.inputs[i].default_value = v
    rvl = M('MULTIPLY', loc=(-150, -260), nm="river")
    L(riv.outputs["Result"], rvl.inputs[0]); L(landg.outputs["Result"], rvl.inputs[1])
    ea = M('MULTIPLY', y=0.075, loc=(-150, -440))
    L(gi.outputs["Erosion Amount"], ea.inputs[0])
    ero = M('MULTIPLY', loc=(110, -260))
    L(rvl.outputs["Value"], ero.inputs[0]); L(ea.outputs["Value"], ero.inputs[1])

    # micro relief
    mn = NOISE((300, -520), 8.0, 0.5, 'FBM', "micro")
    L(Pw.outputs["Vector"], mn.inputs["Vector"]); L(w_micro, mn.inputs["W"])
    ms = M('MULTIPLY', y=14.0, loc=(80, -560))
    L(gi.outputs["Continent Scale"], ms.inputs[0]); L(ms.outputs["Value"], mn.inputs["Scale"])
    mc = M('SUBTRACT', y=0.5, loc=(500, -520)); L(mn.outputs["Factor"], mc.inputs[0])
    ma = M('MULTIPLY', y=0.028, loc=(680, -520)); L(mc.outputs["Value"], ma.inputs[0])

    s1 = M('ADD', loc=(700, 400))
    L(csig.outputs["Value"], s1.inputs[0]); L(ridge.outputs["Value"], s1.inputs[1])
    s2 = M('SUBTRACT', loc=(880, 400))
    L(s1.outputs["Value"], s2.inputs[0]); L(ero.outputs["Value"], s2.inputs[1])
    raw = M('ADD', loc=(1060, 400), nm="raw")
    L(s2.outputs["Value"], raw.inputs[0]); L(ma.outputs["Value"], raw.inputs[1])
    elev = M('MAXIMUM', loc=(1300, 400), nm="elev")
    L(raw.outputs["Value"], elev.inputs[0]); L(gi.outputs["Sea Level"], elev.inputs[1])

    L(elev.outputs["Value"], go.inputs["Elevation"])
    L(raw.outputs["Value"], go.inputs["Raw Elevation"])
    L(csig.outputs["Value"], go.inputs["Continent"])
    L(rvl.outputs["Value"], go.inputs["River"])
    return g


def build_field(tree_type, name, elev_group):
    """Wraps build_elevation, adding slope (3-tap finite difference) and derived scalars."""
    g = _new(tree_type, name)
    for n, st, dv, mn, mx in FIELD_IN:
        _sk(g, n, 'INPUT', st, dv, mn, mx)
    for n in FIELD_OUT:
        _sk(g, n, 'OUTPUT', 'NodeSocketFloat')

    N, L = g.nodes.new, g.links.new
    GT = _grp(tree_type)
    gi = N("NodeGroupInput"); gi.location = (-1800, 0)
    go = N("NodeGroupOutput"); go.location = (3000, 400)

    def M(op, x=None, y=None, loc=(0, 0), nm="", clamp=False):
        n = N("ShaderNodeMath"); n.operation = op; n.location = loc
        n.label = nm; n.use_clamp = clamp
        if x is not None: n.inputs[0].default_value = x
        if y is not None: n.inputs[1].default_value = y
        return n

    def MR(loc, fmin, fmax, tmin, tmax, nm=""):
        n = N("ShaderNodeMapRange"); n.location = loc; n.label = nm; n.clamp = True
        for i, v in ((1, fmin), (2, fmax), (3, tmin), (4, tmax)):
            if v is not None: n.inputs[i].default_value = v
        return n

    def VM(op, loc):
        n = N("ShaderNodeVectorMath"); n.operation = op; n.location = loc
        return n

    # two tangents on the unit sphere (CombineXYZ works in both tree types)
    zc = N("ShaderNodeCombineXYZ"); zc.location = (-1600, -400)
    zc.inputs[0].default_value = 0.0
    zc.inputs[1].default_value = 0.0
    zc.inputs[2].default_value = 1.0
    c1 = VM('CROSS_PRODUCT', (-1400, -300))
    L(gi.outputs["Position"], c1.inputs[0]); L(zc.outputs["Vector"], c1.inputs[1])
    n1 = VM('NORMALIZE', (-1220, -300)); L(c1.outputs["Vector"], n1.inputs[0])
    c2 = VM('CROSS_PRODUCT', (-1040, -420))
    L(gi.outputs["Position"], c2.inputs[0]); L(n1.outputs["Vector"], c2.inputs[1])
    n2 = VM('NORMALIZE', (-860, -420)); L(c2.outputs["Vector"], n2.inputs[0])

    def offset(tangent, y):
        sc = VM('SCALE', (-660, y))
        L(tangent, sc.inputs[0]); sc.inputs["Scale"].default_value = EPS
        ad = VM('ADD', (-480, y))
        L(gi.outputs["Position"], ad.inputs[0]); L(sc.outputs["Vector"], ad.inputs[1])
        nm = VM('NORMALIZE', (-300, y)); L(ad.outputs["Vector"], nm.inputs[0])
        return nm.outputs["Vector"]

    P_u, P_v = offset(n1.outputs["Vector"], -300), offset(n2.outputs["Vector"], -560)

    def call(pos, loc, lab):
        n = N(GT); n.node_tree = elev_group; n.location = loc; n.label = lab
        L(pos, n.inputs["Position"])
        for p in ELEV_PASS:
            L(gi.outputs[p], n.inputs[p])
        return n

    E0 = call(gi.outputs["Position"], (-60, 200), "E0")
    Eu = call(P_u, (-60, -100), "Eu")
    Ev = call(P_v, (-60, -400), "Ev")

    # slope
    du = M('SUBTRACT', loc=(200, -100))
    L(Eu.outputs["Elevation"], du.inputs[0]); L(E0.outputs["Elevation"], du.inputs[1])
    dv = M('SUBTRACT', loc=(200, -260))
    L(Ev.outputs["Elevation"], dv.inputs[0]); L(E0.outputs["Elevation"], dv.inputs[1])
    su = M('POWER', y=2.0, loc=(380, -100)); L(du.outputs["Value"], su.inputs[0])
    sv = M('POWER', y=2.0, loc=(380, -260)); L(dv.outputs["Value"], sv.inputs[0])
    ss = M('ADD', loc=(560, -180))
    L(su.outputs["Value"], ss.inputs[0]); L(sv.outputs["Value"], ss.inputs[1])
    sq = M('SQRT', loc=(740, -180)); L(ss.outputs["Value"], sq.inputs[0])
    gr = M('DIVIDE', y=EPS, loc=(920, -180)); L(sq.outputs["Value"], gr.inputs[0])
    slope = MR((1100, -180), 0.0, 4.0, 0.0, 1.0, "slope")
    L(gr.outputs["Value"], slope.inputs[0])

    # latitude
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (200, -560)
    L(gi.outputs["Position"], sep.inputs["Vector"])
    lat = M('ABSOLUTE', loc=(380, -560), nm="lat"); L(sep.outputs["Z"], lat.inputs[0])

    # elevation above sea
    ab = M('SUBTRACT', loc=(200, 380))
    L(E0.outputs["Elevation"], ab.inputs[0]); L(gi.outputs["Sea Level"], ab.inputs[1])
    abv = M('MAXIMUM', y=0.0, loc=(380, 380), nm="above")
    L(ab.outputs["Value"], abv.inputs[0])

    # temperature
    pc = M('MULTIPLY', y=0.8, loc=(380, -760)); L(gi.outputs["Polar Cap Extent"], pc.inputs[0])
    ps = M('SUBTRACT', x=1.0, loc=(560, -760)); L(pc.outputs["Value"], ps.inputs[1])
    pm = M('MAXIMUM', y=0.15, loc=(740, -760)); L(ps.outputs["Value"], pm.inputs[0])
    ln = M('DIVIDE', loc=(920, -620))
    L(lat.outputs["Value"], ln.inputs[0]); L(pm.outputs["Value"], ln.inputs[1])
    lp = M('POWER', y=1.6, loc=(1100, -620)); L(ln.outputs["Value"], lp.inputs[0])
    t1 = M('SUBTRACT', x=1.0, loc=(1280, -620)); L(lp.outputs["Value"], t1.inputs[1])
    lap = M('MULTIPLY', y=1.5, loc=(560, 380)); L(abv.outputs["Value"], lap.inputs[0])
    temp = M('SUBTRACT', loc=(1460, -620), nm="temp", clamp=True)
    L(t1.outputs["Value"], temp.inputs[0]); L(lap.outputs["Value"], temp.inputs[1])

    # humidity
    hn = N("ShaderNodeTexNoise"); hn.location = (200, -900)
    hn.noise_dimensions = '4D'; hn.noise_type = 'FBM'
    hn.inputs["Detail"].default_value = 5.0
    L(gi.outputs["Position"], hn.inputs["Vector"])
    hw = M('MULTIPLY', y=4.77, loc=(20, -1060)); L(gi.outputs["Seed"], hw.inputs[0])
    ha = M('ADD', y=59.3, loc=(200, -1060)); L(hw.outputs["Value"], ha.inputs[0])
    L(ha.outputs["Value"], hn.inputs["W"])
    hs = M('MULTIPLY', y=2.1, loc=(20, -1220))
    L(gi.outputs["Continent Scale"], hs.inputs[0]); L(hs.outputs["Value"], hn.inputs["Scale"])
    op = MR((560, 180), 0.0, 0.26, 1.0, 0.42, "oprox"); L(abv.outputs["Value"], op.inputs[0])
    hum = M('MULTIPLY', loc=(740, -900), nm="hum", clamp=True)
    L(hn.outputs["Factor"], hum.inputs[0]); L(op.outputs["Result"], hum.inputs[1])

    # sea / river / depth
    #
    # LESS_THAN gives a 0-or-1 sea mask, and the land/ocean MixShader that
    # consumes it therefore switches between two entirely different BSDFs at a
    # single micropolygon boundary. At planet scale that reads as a coastline
    # drawn with a hard pen, and on the volcanic preset, where the "ocean" is
    # glowing lava, it punches black holes out of the crust wherever the
    # elevation crosses the line. A smoothstep a few thousandths wide gives
    # every shore a surf zone instead, and costs one node.
    shore = M('MULTIPLY', y=0.004, loc=(380, 560), nm="shore width")
    shore.inputs[0].default_value = 1.0
    slo = M('SUBTRACT', loc=(380, 680), nm="shore lo")
    L(gi.outputs["Sea Level"], slo.inputs[0]); L(shore.outputs["Value"], slo.inputs[1])
    shi = M('ADD', loc=(380, 440), nm="shore hi")
    L(gi.outputs["Sea Level"], shi.inputs[0]); L(shore.outputs["Value"], shi.inputs[1])
    sea = MR((560, 560), None, None, 1.0, 0.0, "sea")
    sea.interpolation_type = 'SMOOTHSTEP'
    L(E0.outputs["Raw Elevation"], sea.inputs[0])
    L(slo.outputs["Value"], sea.inputs[1]); L(shi.outputs["Value"], sea.inputs[2])
    land = M('SUBTRACT', x=1.0, loc=(740, 560), nm="land"); L(sea.outputs["Result"], land.inputs[1])
    rv = M('MULTIPLY', loc=(740, 720), nm="river")
    L(E0.outputs["River"], rv.inputs[0]); L(land.outputs["Value"], rv.inputs[1])
    d1 = M('SUBTRACT', loc=(560, 900))
    L(gi.outputs["Sea Level"], d1.inputs[0]); L(E0.outputs["Raw Elevation"], d1.inputs[1])
    dep = M('MAXIMUM', y=0.0, loc=(740, 900), nm="depth"); L(d1.outputs["Value"], dep.inputs[0])

    # habitability
    sok = MR((1300, -180), 0.0, 0.35, 1.0, 0.0); L(slope.outputs["Result"], sok.inputs[0])
    td = M('SUBTRACT', y=0.62, loc=(1640, -620)); L(temp.outputs["Value"], td.inputs[0])
    ta = M('ABSOLUTE', loc=(1820, -620)); L(td.outputs["Value"], ta.inputs[0])
    tsc = M('MULTIPLY', y=2.6, loc=(2000, -620)); L(ta.outputs["Value"], tsc.inputs[0])
    tmp = M('SUBTRACT', x=1.0, loc=(2180, -620), clamp=True); L(tsc.outputs["Value"], tmp.inputs[1])
    nw = M('MAXIMUM', loc=(920, 720))
    L(op.outputs["Result"], nw.inputs[0]); L(rv.outputs["Value"], nw.inputs[1])
    aok = MR((740, 380), 0.06, 0.20, 1.0, 0.0); L(abv.outputs["Value"], aok.inputs[0])
    h1 = M('MULTIPLY', loc=(2360, -380)); L(sok.outputs["Result"], h1.inputs[0]); L(tmp.outputs["Value"], h1.inputs[1])
    h2 = M('MULTIPLY', loc=(2360, -220)); L(h1.outputs["Value"], h2.inputs[0]); L(nw.outputs["Value"], h2.inputs[1])
    h3 = M('MULTIPLY', loc=(2360, -60)); L(h2.outputs["Value"], h3.inputs[0]); L(aok.outputs["Result"], h3.inputs[1])
    hab = M('MULTIPLY', loc=(2360, 100), nm="hab", clamp=True)
    L(h3.outputs["Value"], hab.inputs[0]); L(land.outputs["Value"], hab.inputs[1])

    # biome id via math-node lerps (avoids ShaderNodeMix duplicate-socket hazard)
    val = N("ShaderNodeValue"); val.location = (900, 1100)
    val.outputs[0].default_value = 2.0
    cur = val.outputs[0]
    x = [1080]

    def lerp(const, fac):
        d = M('SUBTRACT', x=const, loc=(x[0], 1100)); L(cur[0] if isinstance(cur, tuple) else cur, d.inputs[1])
        m = M('MULTIPLY', loc=(x[0], 940))
        L(d.outputs["Value"], m.inputs[0]); L(fac, m.inputs[1])
        a = M('ADD', loc=(x[0], 1260))
        L(cur[0] if isinstance(cur, tuple) else cur, a.inputs[0]); L(m.outputs["Value"], a.inputs[1])
        x[0] += 200
        return a.outputs["Value"]

    g1 = M('GREATER_THAN', y=0.30, loc=(900, 780)); L(hum.outputs["Value"], g1.inputs[0])
    cur = lerp(3.0, g1.outputs["Value"])
    g2 = M('GREATER_THAN', y=0.55, loc=(900, 620)); L(hum.outputs["Value"], g2.inputs[0])
    cur = lerp(4.0, g2.outputs["Value"])
    g3 = M('GREATER_THAN', y=0.45, loc=(900, 460)); L(slope.outputs["Result"], g3.inputs[0])
    cur = lerp(5.0, g3.outputs["Value"])
    g4 = M('LESS_THAN', y=0.22, loc=(900, 300)); L(temp.outputs["Value"], g4.inputs[0])
    cur = lerp(1.0, g4.outputs["Value"])
    cur = lerp(0.0, sea.outputs["Result"])

    L(E0.outputs["Elevation"], go.inputs["elevation"])
    L(slope.outputs["Result"], go.inputs["slope"])
    L(lat.outputs["Value"], go.inputs["latitude"])
    L(temp.outputs["Value"], go.inputs["temperature"])
    L(hum.outputs["Value"], go.inputs["humidity"])
    L(sea.outputs["Result"], go.inputs["sea_mask"])
    L(rv.outputs["Value"], go.inputs["river_mask"])
    L(hab.outputs["Value"], go.inputs["habitability"])
    L(cur, go.inputs["biome_id"])
    L(dep.outputs["Value"], go.inputs["ocean_depth"])
    return g


def build_all():
    ge = build_elevation('GeometryNodeTree', "PLNT_Elevation")
    gf = build_field('GeometryNodeTree', "PLNT_TerrainField", ge)
    se = build_elevation('ShaderNodeTree', "PLNT_ElevationSH")
    sf = build_field('ShaderNodeTree', "PLNT_TerrainFieldSH", se)
    return {"geo_elev": ge.name, "geo_field": gf.name,
            "sh_elev": se.name, "sh_field": sf.name,
            "nodes": {ge.name: len(ge.nodes), gf.name: len(gf.nodes),
                      se.name: len(se.nodes), sf.name: len(sf.nodes)}}
