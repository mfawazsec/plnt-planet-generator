"""PLNT technology-level layer.

Appended into PLNT_SurfaceShader so it reuses the already-evaluated field node
instead of paying for a second per-pixel field evaluation.

Master `Tech Level` (0-10) gates everything; each slider is a 0-2 multiplier
defaulting to 1.0, so Tech Level alone drives the whole civilisation, and any
slider can independently override. Tech Level 0 => every term is exactly zero.
"""
import bpy

TECH_IN = [
    ("Tech Level", 0.0, 0.0, 10.0),
    ("Urban Density", 1.0, 0.0, 2.0),
    ("Night Light Intensity", 1.0, 0.0, 4.0),
    ("Light Colour Temp", 0.5, 0.0, 1.0),
    ("Road Network Visibility", 1.0, 0.0, 2.0),
    ("Agriculture Coverage", 1.0, 0.0, 2.0),
    ("Grid Network Intensity", 1.0, 0.0, 2.0),
    ("Megastructure Scale", 1.0, 0.0, 2.0),
]

SODIUM = (1.0, 0.52, 0.16, 1.0)
MERCURY = (0.86, 0.92, 0.78, 1.0)      # older mercury-vapour and metal halide
COOLWHITE = (0.70, 0.86, 1.0, 1.0)     # modern LED
GRIDCOL = (0.42, 0.88, 1.0, 1.0)


def add_tech_layer(g, F, gi, albedo_sock, rough_sock, nrm_sock, sun_dir_obj):
    """Returns (albedo, roughness, emission_colour) sockets."""
    N, L = g.nodes.new, g.links.new
    o = F.outputs

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

    def MIXC(loc, nm=""):
        n = N("ShaderNodeMix"); n.data_type = 'RGBA'; n.location = loc
        n.label = nm; n.blend_type = 'MIX'; n.clamp_factor = True
        return n

    def VOR(loc, feature, dims='4D', nm=""):
        n = N("ShaderNodeTexVoronoi"); n.location = loc; n.label = nm
        n.voronoi_dimensions = dims; n.feature = feature
        n.inputs["Randomness"].default_value = 1.0
        return n

    X0 = 1400

    # ---------- master gate ----------
    t01 = M('DIVIDE', y=10.0, loc=(X0, 1200), nm="tech01", clamp=True)
    L(gi.outputs["Tech Level"], t01.inputs[0])

    def gated(slider, y, nm, curve=None):
        base = t01.outputs["Value"]
        if curve is not None:
            c = MR((X0 + 160, y), curve[0], curve[1], 0.0, 1.0)
            L(base, c.inputs[0]); base = c.outputs["Result"]
        m = M('MULTIPLY', loc=(X0 + 340, y), nm=nm)
        L(base, m.inputs[0]); L(gi.outputs[slider], m.inputs[1])
        return m.outputs["Value"]

    urban = gated("Urban Density", 1040, "urban")
    lights = gated("Night Light Intensity", 900, "lights")
    roads_a = gated("Road Network Visibility", 760, "roads")
    agri_a = gated("Agriculture Coverage", 620, "agri")
    # Tech 8 and up. Below that the arcs used to fade in over Tech 5.5-9.5 as
    # a faint scratch that read as a render artefact rather than as orbital
    # engineering, on presets that have no business having one.
    grid_a = gated("Grid Network Intensity", 480, "grid", curve=(0.80, 1.0))
    mega_a = gated("Megastructure Scale", 340, "mega", curve=(0.72, 1.0))

    # ---------- sun direction + night mask ----------
    sv = N("ShaderNodeCombineXYZ"); sv.location = (X0, 100); sv.label = "SUNVEC"
    for i, tt in enumerate(('LOC_X', 'LOC_Y', 'LOC_Z')):
        fc = sv.inputs[i].driver_add("default_value")
        d = fc.driver; d.type = 'SCRIPTED'
        v = d.variables.new(); v.name = "p"; v.type = 'TRANSFORMS'
        t = v.targets[0]; t.id = sun_dir_obj
        t.transform_type = tt; t.transform_space = 'WORLD_SPACE'
        d.expression = "p"
    # World to object. nrm_sock is the object-space unit position, and the
    # driven sun vector is in world space: dotting them directly is only
    # correct while the planet never turns. With the transform in place the
    # terminator stays put in world space and the surface rotates under it,
    # which is the whole point of a day.
    svt = N("ShaderNodeVectorTransform"); svt.location = (X0 + 180, 100)
    svt.label = "SUNVEC_OBJ"
    svt.vector_type = 'VECTOR'
    svt.convert_from = 'WORLD'
    svt.convert_to = 'OBJECT'
    L(sv.outputs["Vector"], svt.inputs[0])
    dot = N("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'; dot.location = (X0 + 360, 20)
    L(nrm_sock, dot.inputs[0]); L(svt.outputs[0], dot.inputs[1])
    night = MR((X0 + 540, 20), 0.06, -0.16, 0.0, 1.0, "night")
    L(dot.outputs["Value"], night.inputs[0])

    # ---------- settlement mask: cores on habitable land only ----------
    habg = MR((X0, -300), 0.025, 0.18, 0.0, 1.0, "habgate")
    L(o["habitability"], habg.inputs[0])
    cs = M('MULTIPLY', y=60.0, loc=(X0, -460)); cs.inputs[0].default_value = 2.6
    cv = VOR((X0 + 200, -300), 'F1', '4D', "citycells")
    # 27 cells across the sphere put roughly a dozen cities on a visible
    # hemisphere, which reads as a scatter of isolated dots rather than as a
    # settled world. 40 is about 90 sites globally: still countable, but dense
    # enough that neighbouring cores and their roads form clusters.
    cv.inputs["Scale"].default_value = 40.0
    L(nrm_sock, cv.inputs["Vector"])
    csw = M('MULTIPLY', y=5.13, loc=(X0, -620)); L(gi.outputs["Seed"], csw.inputs[0])
    cswa = M('ADD', y=23.9, loc=(X0 + 160, -620)); L(csw.outputs["Value"], cswa.inputs[0])
    L(cswa.outputs["Value"], cv.inputs["W"])
    csep = N("ShaderNodeSeparateXYZ"); csep.location = (X0 + 420, -480)
    L(cv.outputs["Color"], csep.inputs["Vector"])
    # Per-cell extent. Every city used to be exactly 0.30 cells across with a
    # linear edge, so a night side was a field of identical discs. The cell
    # random colour gives each one its own size, and SMOOTHSTEP stops the edge
    # reading as a drawn circle.
    crad = MR((X0 + 420, -160), 0.0, 1.0, 0.10, 0.42, "cityradius")
    L(csep.outputs["Y"], crad.inputs[0])
    core = MR((X0 + 600, -300), 0.0, None, 1.0, 0.0, "citycore")
    core.interpolation_type = 'SMOOTHSTEP'
    L(cv.outputs["Distance"], core.inputs[0])
    L(crad.outputs["Result"], core.inputs[2])
    # higher urban density -> more cells qualify as cities
    cthr = MR((X0 + 600, -480), 0.0, 1.0, 0.94, 0.42, "citythr")
    L(urban, cthr.inputs[0])
    iscity = M('GREATER_THAN', loc=(X0 + 780, -480), nm="iscity")
    L(csep.outputs["X"], iscity.inputs[0]); L(cthr.outputs["Result"], iscity.inputs[1])
    # sprawl granularity so cities are not smooth blobs
    spn = N("ShaderNodeTexNoise"); spn.location = (X0 + 420, -660); spn.label = "sprawl"
    spn.noise_dimensions = '4D'; spn.noise_type = 'FBM'
    spn.inputs["Scale"].default_value = 260.0
    spn.inputs["Detail"].default_value = 6.0
    L(nrm_sock, spn.inputs["Vector"]); L(cswa.outputs["Value"], spn.inputs["W"])
    spg = MR((X0 + 600, -660), 0.35, 0.75, 0.25, 1.0, "sprawlg")
    L(spn.outputs["Factor"], spg.inputs[0])
    # Capitals: the strongest few cells get a brighter core. Derived from the
    # same Voronoi rather than a second one, so a capital is by construction a
    # big city and not an unrelated bright dot somewhere else.
    capthr = MR((X0 + 780, -620), 0.0, 1.0, 0.985, 0.80, "capthr")
    L(urban, capthr.inputs[0])
    iscap = M('GREATER_THAN', loc=(X0 + 960, -620), nm="iscapital")
    L(csep.outputs["X"], iscap.inputs[0]); L(capthr.outputs["Result"], iscap.inputs[1])
    capb = M('MULTIPLY', y=1.6, loc=(X0 + 1140, -620), nm="capboost")
    L(iscap.outputs["Value"], capb.inputs[0])
    capg = M('ADD', x=1.0, loc=(X0 + 1320, -620)); L(capb.outputs["Value"], capg.inputs[1])

    s1 = M('MULTIPLY', loc=(X0 + 960, -300))
    L(core.outputs["Result"], s1.inputs[0]); L(iscity.outputs["Value"], s1.inputs[1])
    s2 = M('MULTIPLY', loc=(X0 + 1140, -300))
    L(s1.outputs["Value"], s2.inputs[0]); L(habg.outputs["Result"], s2.inputs[1])
    s3 = M('MULTIPLY', loc=(X0 + 1320, -300))
    L(s2.outputs["Value"], s3.inputs[0]); L(spg.outputs["Result"], s3.inputs[1])
    s4 = M('MULTIPLY', loc=(X0 + 1500, -300))
    L(s3.outputs["Value"], s4.inputs[0]); L(urban, s4.inputs[1])
    settle = M('MULTIPLY', loc=(X0 + 1680, -300), nm="settlement", clamp=True)
    L(s4.outputs["Value"], settle.inputs[0]); L(capg.outputs["Value"], settle.inputs[1])

    # ---------- roads: the line between two neighbouring cities -------------
    #
    # The old network was the EDGE SET of a Voronoi diagram (feature
    # DISTANCE_TO_EDGE) belonging to a different, finer Voronoi than the
    # cities. That draws the boundaries BETWEEN territories: closed polygons
    # meeting at three-way knots, running through empty land and arriving
    # nowhere. On the night side it read as a wireframe laid over the dark
    # hemisphere, which is exactly what it was.
    #
    # A road joins two settlements. F1 and F2 of the CITY Voronoi give the two
    # nearest city sites to this point, and the distance from the point to the
    # segment between them is small only along the corridor that joins them.
    # That is the Delaunay dual of the same diagram, the graph of which city
    # neighbours which, and it produces a network that starts and ends at
    # cities.
    rv2 = VOR((X0 + 200, -900), 'F2', '4D', "citycells_f2")
    rv2.inputs["Scale"].default_value = 27.0
    L(nrm_sock, rv2.inputs["Vector"]); L(cswa.outputs["Value"], rv2.inputs["W"])

    def VMath(op, loc, nm=""):
        n = N("ShaderNodeVectorMath"); n.operation = op
        n.location = loc; n.label = nm
        return n

    # a = P - P1 (to the nearest city), b = P2 - P1 (nearest to second nearest)
    va = VMath('SUBTRACT', (X0 + 420, -900), "a")
    L(nrm_sock, va.inputs[0]); L(cv.outputs["Position"], va.inputs[1])
    vb = VMath('SUBTRACT', (X0 + 420, -1040), "b")
    L(rv2.outputs["Position"], vb.inputs[0]); L(cv.outputs["Position"], vb.inputs[1])
    ab = VMath('DOT_PRODUCT', (X0 + 600, -900), "a.b")
    L(va.outputs["Vector"], ab.inputs[0]); L(vb.outputs["Vector"], ab.inputs[1])
    bb = VMath('DOT_PRODUCT', (X0 + 600, -1040), "b.b")
    L(vb.outputs["Vector"], bb.inputs[0]); L(vb.outputs["Vector"], bb.inputs[1])
    bbs = M('MAXIMUM', y=1e-6, loc=(X0 + 760, -1040))
    L(bb.outputs["Value"], bbs.inputs[0])
    tpar = M('DIVIDE', loc=(X0 + 920, -900), nm="t", clamp=True)
    L(ab.outputs["Value"], tpar.inputs[0]); L(bbs.outputs["Value"], tpar.inputs[1])
    tb = VMath('SCALE', (X0 + 1100, -1040), "t*b")
    L(vb.outputs["Vector"], tb.inputs[0])
    L(tpar.outputs["Value"], tb.inputs["Scale"])
    dv = VMath('SUBTRACT', (X0 + 1280, -900), "a - t*b")
    L(va.outputs["Vector"], dv.inputs[0]); L(tb.outputs["Vector"], dv.inputs[1])
    dlen = VMath('LENGTH', (X0 + 1460, -900), "road distance")
    L(dv.outputs["Vector"], dlen.inputs[0])

    # A dead-straight line between every pair is a giveaway. The sprawl noise
    # is already evaluated for the cities, so reusing it to wander the corridor
    # costs nothing.
    wob = M('SUBTRACT', y=0.5, loc=(X0 + 780, -660)); L(spn.outputs["Factor"], wob.inputs[0])
    wobs = M('MULTIPLY', y=0.0028, loc=(X0 + 960, -660), nm="road wobble")
    L(wob.outputs["Value"], wobs.inputs[0])
    dwob = M('ADD', loc=(X0 + 1640, -900))
    L(dlen.outputs["Value"], dwob.inputs[0]); L(wobs.outputs["Value"], dwob.inputs[1])
    rline = MR((X0 + 1820, -900), 0.0, 0.0045, 1.0, 0.0, "roadline")
    rline.interpolation_type = 'SMOOTHSTEP'
    L(dwob.outputs["Value"], rline.inputs[0])

    # Traffic thins in the middle of a long haul: 4t(1-t) peaks at the midpoint
    tm = M('SUBTRACT', x=1.0, loc=(X0 + 1100, -760)); L(tpar.outputs["Value"], tm.inputs[1])
    tmid = M('MULTIPLY', loc=(X0 + 1280, -760))
    L(tpar.outputs["Value"], tmid.inputs[0]); L(tm.outputs["Value"], tmid.inputs[1])
    tmid4 = M('MULTIPLY', y=4.0, loc=(X0 + 1460, -760))
    L(tmid.outputs["Value"], tmid4.inputs[0])
    fade = MR((X0 + 1640, -760), 0.0, 1.0, 1.0, 0.45, "road fade")
    L(tmid4.outputs["Value"], fade.inputs[0])

    # Both ends must be real cities, or the corridor runs between two empty
    # cells. This is the gate an earlier prototype set far too strict, which
    # made the whole network vanish at Tech 3.
    c2sep = N("ShaderNodeSeparateXYZ"); c2sep.location = (X0 + 420, -1200)
    L(rv2.outputs["Color"], c2sep.inputs["Vector"])
    rthr = MR((X0 + 600, -1200), 0.0, 1.0, 0.90, 0.36, "roadthr")
    L(urban, rthr.inputs[0])
    e1c = M('GREATER_THAN', loc=(X0 + 780, -1160))
    L(csep.outputs["X"], e1c.inputs[0]); L(rthr.outputs["Result"], e1c.inputs[1])
    e2c = M('GREATER_THAN', loc=(X0 + 780, -1280))
    L(c2sep.outputs["X"], e2c.inputs[0]); L(rthr.outputs["Result"], e2c.inputs[1])
    ends = M('MULTIPLY', loc=(X0 + 960, -1220), nm="both ends")
    L(e1c.outputs["Value"], ends.inputs[0]); L(e2c.outputs["Value"], ends.inputs[1])

    land = M('SUBTRACT', x=1.0, loc=(X0 + 420, -1340)); L(o["sea_mask"], land.inputs[1])
    rh = MR((X0 + 600, -1340), 0.06, 0.40, 0.0, 1.0)
    L(o["habitability"], rh.inputs[0])
    r0 = M('MULTIPLY', loc=(X0 + 2000, -900))
    L(rline.outputs["Result"], r0.inputs[0]); L(fade.outputs["Result"], r0.inputs[1])
    r1 = M('MULTIPLY', loc=(X0 + 2180, -900))
    L(r0.outputs["Value"], r1.inputs[0]); L(ends.outputs["Value"], r1.inputs[1])
    r2 = M('MULTIPLY', loc=(X0 + 2360, -900))
    L(r1.outputs["Value"], r2.inputs[0]); L(land.outputs["Value"], r2.inputs[1])
    r3 = M('MULTIPLY', loc=(X0 + 2540, -900))
    L(r2.outputs["Value"], r3.inputs[0]); L(rh.outputs["Result"], r3.inputs[1])
    road = M('MULTIPLY', loc=(X0 + 2720, -900), nm="road", clamp=True)
    L(r3.outputs["Value"], road.inputs[0]); L(roads_a, road.inputs[1])

    # ---------- planetary grid: great circles + ring nodes, ignores terrain ----------
    rot = N("ShaderNodeVectorRotate"); rot.location = (X0 + 200, -1300); rot.label = "gridrot"
    rot.rotation_type = 'EULER_XYZ'
    L(nrm_sock, rot.inputs["Vector"])
    gseed = M('MULTIPLY', y=0.7919, loc=(X0, -1460)); L(gi.outputs["Seed"], gseed.inputs[0])
    gcomb = N("ShaderNodeCombineXYZ"); gcomb.location = (X0, -1620)
    L(gseed.outputs["Value"], gcomb.inputs[0])
    gs2 = M('MULTIPLY', y=1.317, loc=(X0 - 180, -1700)); L(gi.outputs["Seed"], gs2.inputs[0])
    L(gs2.outputs["Value"], gcomb.inputs[1])
    L(gcomb.outputs["Vector"], rot.inputs["Rotation"])

    # Five great circles plus three small ones is eight full rings wrapped
    # round the globe, and on a night side that reads as a wireframe cage
    # drawn over the cities rather than as orbital engineering above them.
    # Three and two leave the same idea legible with the surface still
    # visible through it.
    AXES = [(1, 0, 0), (0, 1, 0), (0.577, 0.577, 0.577)]
    prev = None
    yy = -1300
    for i, ax in enumerate(AXES):
        av = N("ShaderNodeCombineXYZ"); av.location = (X0 + 380, yy)
        for k in range(3): av.inputs[k].default_value = ax[k]
        dp = N("ShaderNodeVectorMath"); dp.operation = 'DOT_PRODUCT'; dp.location = (X0 + 560, yy)
        L(rot.outputs["Vector"], dp.inputs[0]); L(av.outputs["Vector"], dp.inputs[1])
        ab = M('ABSOLUTE', loc=(X0 + 740, yy))
        L(dp.outputs["Value"], ab.inputs[0])
        # 0.0011 of a unit sphere is about 7 km wide: thinner than one pixel at
        # every hero framing, so the arcs aliased into dashes. 0.004 is roughly
        # 24 km, wide enough to survive sampling, and SMOOTHSTEP gives it an
        # edge instead of a staircase.
        arc = MR((X0 + 900, yy), 0.0, 0.004, 1.0, 0.0, f"arc{i}")
        arc.interpolation_type = 'SMOOTHSTEP'
        L(ab.outputs["Value"], arc.inputs[0])
        if prev is None:
            prev = arc.outputs["Result"]
        else:
            mx = M('MAXIMUM', loc=(X0 + 1080, yy))
            L(prev, mx.inputs[0]); L(arc.outputs["Result"], mx.inputs[1])
            prev = mx.outputs["Value"]
        yy -= 170

    # ring nodes: small circles at fixed polar angles
    for j, c in enumerate((0.35, 0.72)):
        av = N("ShaderNodeCombineXYZ"); av.location = (X0 + 380, yy)
        av.inputs[0].default_value = 0.577; av.inputs[1].default_value = -0.577
        av.inputs[2].default_value = 0.577
        dp = N("ShaderNodeVectorMath"); dp.operation = 'DOT_PRODUCT'; dp.location = (X0 + 560, yy)
        L(rot.outputs["Vector"], dp.inputs[0]); L(av.outputs["Vector"], dp.inputs[1])
        sb = M('SUBTRACT', y=c, loc=(X0 + 740, yy)); L(dp.outputs["Value"], sb.inputs[0])
        ab = M('ABSOLUTE', loc=(X0 + 900, yy)); L(sb.outputs["Value"], ab.inputs[0])
        rr = MR((X0 + 1060, yy), 0.0, 0.0035, 1.0, 0.0, f"ring{j}")
        rr.interpolation_type = 'SMOOTHSTEP'
        L(ab.outputs["Value"], rr.inputs[0])
        mx = M('MAXIMUM', loc=(X0 + 1240, yy))
        L(prev, mx.inputs[0]); L(rr.outputs["Result"], mx.inputs[1])
        prev = mx.outputs["Value"]
        yy -= 170

    grid = M('MULTIPLY', loc=(X0 + 1440, -1300), nm="gridmask", clamp=True)
    L(prev, grid.inputs[0]); L(grid_a, grid.inputs[1])

    # ---------- agriculture: quantised cells on flat, temperate, humid land ----------
    av2 = VOR((X0 + 200, -2400), 'F1', '4D', "agricells")
    av2.inputs["Scale"].default_value = 420.0
    L(nrm_sock, av2.inputs["Vector"]); L(cswa.outputs["Value"], av2.inputs["W"])
    asep = N("ShaderNodeSeparateXYZ"); asep.location = (X0 + 420, -2400)
    L(av2.outputs["Color"], asep.inputs["Vector"])
    aq = M('SNAP', y=0.25, loc=(X0 + 600, -2400), nm="agriquant")
    L(asep.outputs["Y"], aq.inputs[0])
    aflat = MR((X0 + 420, -2560), 0.22, 0.05, 0.0, 1.0)
    L(o["slope"], aflat.inputs[0])
    ahum = MR((X0 + 420, -2720), 0.20, 0.55, 0.0, 1.0)
    L(o["humidity"], ahum.inputs[0])
    ag1 = M('MULTIPLY', loc=(X0 + 780, -2560))
    L(aflat.outputs["Result"], ag1.inputs[0]); L(ahum.outputs["Result"], ag1.inputs[1])
    ag2 = M('MULTIPLY', loc=(X0 + 960, -2560))
    L(ag1.outputs["Value"], ag2.inputs[0]); L(habg.outputs["Result"], ag2.inputs[1])
    ag3 = M('MULTIPLY', loc=(X0 + 1140, -2560))
    L(ag2.outputs["Value"], ag3.inputs[0]); L(agri_a, ag3.inputs[1])
    agri = M('MULTIPLY', loc=(X0 + 1320, -2560), nm="agri", clamp=True)
    L(ag3.outputs["Value"], agri.inputs[0]); L(aq.outputs["Value"], agri.inputs[1])

    # ---------- albedo modification: roads darken, agriculture tints ----------
    agcol = MIXC((X0 + 1500, -2560), "agricol")
    L(agri.outputs["Value"], agcol.inputs[0])
    L(albedo_sock, agcol.inputs[6])
    agcol.inputs[7].default_value = (0.175, 0.170, 0.055, 1)
    rdcol = MIXC((X0 + 1700, -2560), "roadcol")
    rdday = M('MULTIPLY', y=0.55, loc=(X0 + 1500, -2720)); L(road.outputs["Value"], rdday.inputs[0])
    L(rdday.outputs["Value"], rdcol.inputs[0])
    L(agcol.outputs[2], rdcol.inputs[6])
    rdcol.inputs[7].default_value = (0.055, 0.050, 0.048, 1)
    # megastructure: homogenise biomes toward engineered grey-green
    megcol = MIXC((X0 + 1900, -2560), "megacol")
    megf = M('MULTIPLY', y=0.55, loc=(X0 + 1700, -2720)); L(mega_a, megf.inputs[0])
    L(megf.outputs["Value"], megcol.inputs[0])
    L(rdcol.outputs[2], megcol.inputs[6])
    megcol.inputs[7].default_value = (0.115, 0.125, 0.110, 1)

    rgh = N("ShaderNodeMix"); rgh.data_type = 'FLOAT'; rgh.location = (X0 + 1700, -2900)
    rgh.clamp_factor = True; rgh.inputs[3].default_value = 0.42
    L(agri.outputs["Value"], rgh.inputs[0]); L(rough_sock, rgh.inputs[2])

    # ---------- emission: city lights + road glow + grid arcs ----------
    # One city is not lit like the next. Light Colour Temp sets where the
    # planet sits on the sodium-to-LED transition; the third channel of the
    # cell colour scatters individual cities either side of it, so a night
    # side shows the mixture a real one does instead of one global tint.
    ctv = M('SUBTRACT', y=0.5, loc=(X0 + 1340, 1040)); L(csep.outputs["Z"], ctv.inputs[0])
    ctj = M('MULTIPLY', y=0.42, loc=(X0 + 1520, 1040)); L(ctv.outputs["Value"], ctj.inputs[0])
    ctmp = M('ADD', loc=(X0 + 1700, 1040), nm="cell temp", clamp=True)
    L(gi.outputs["Light Colour Temp"], ctmp.inputs[0]); L(ctj.outputs["Value"], ctmp.inputs[1])
    lramp = N("ShaderNodeValToRGB"); lramp.location = (X0 + 1880, 1040)
    lramp.label = "lightcol"
    L(ctmp.outputs["Value"], lramp.inputs["Fac"])
    _el = lramp.color_ramp.elements
    _el[0].position = 0.0; _el[0].color = SODIUM
    _el[1].position = 1.0; _el[1].color = COOLWHITE
    _mid = lramp.color_ramp.elements.new(0.5); _mid.color = MERCURY
    lcol = MIXC((X0 + 2060, 900), "lightcol mix")
    lcol.inputs[0].default_value = 0.0
    L(lramp.outputs["Color"], lcol.inputs[6])
    lcol.inputs[7].default_value = COOLWHITE
    cityn = M('MULTIPLY', loc=(X0 + 1700, 700))
    L(settle.outputs["Value"], cityn.inputs[0]); L(night.outputs["Result"], cityn.inputs[1])
    cityl = M('MULTIPLY', loc=(X0 + 1880, 700), nm="citylight")
    L(cityn.outputs["Value"], cityl.inputs[0]); L(lights, cityl.inputs[1])
    cgain = M('MULTIPLY', y=26.0, loc=(X0 + 2060, 700)); L(cityl.outputs["Value"], cgain.inputs[0])
    cem = N("ShaderNodeVectorMath"); cem.operation = 'SCALE'; cem.location = (X0 + 2240, 800)
    L(lcol.outputs[2], cem.inputs[0]); L(cgain.outputs["Value"], cem.inputs["Scale"])

    rn2 = M('MULTIPLY', loc=(X0 + 1700, 500))
    L(road.outputs["Value"], rn2.inputs[0]); L(night.outputs["Result"], rn2.inputs[1])
    rgain = M('MULTIPLY', y=1.1, loc=(X0 + 1880, 500)); L(rn2.outputs["Value"], rgain.inputs[0])
    rem = N("ShaderNodeVectorMath"); rem.operation = 'SCALE'; rem.location = (X0 + 2060, 500)
    L(lcol.outputs[2], rem.inputs[0]); L(rgain.outputs["Value"], rem.inputs["Scale"])

    # grid is visible on the unlit hemisphere too, and ignores land/ocean
    gnight = M('MULTIPLY', y=0.55, loc=(X0 + 1700, 300)); L(night.outputs["Result"], gnight.inputs[0])
    gbase = M('ADD', y=0.45, loc=(X0 + 1880, 300)); L(gnight.outputs["Value"], gbase.inputs[0])
    gg = M('MULTIPLY', loc=(X0 + 2060, 300))
    L(grid.outputs["Value"], gg.inputs[0]); L(gbase.outputs["Value"], gg.inputs[1])
    # A city core is a handful of pixels; an arc is an unbroken line around
    # the whole planet. At the same nominal gain the arcs carry many times the
    # integrated light and win the frame outright, so they are gained well
    # below the 26.0 the city cores get.
    ggain = M('MULTIPLY', y=2.4, loc=(X0 + 2240, 300)); L(gg.outputs["Value"], ggain.inputs[0])
    gem = N("ShaderNodeVectorMath"); gem.operation = 'SCALE'; gem.location = (X0 + 2420, 300)
    gcol = N("ShaderNodeRGB"); gcol.location = (X0 + 2240, 140)
    gcol.outputs[0].default_value = GRIDCOL
    L(gcol.outputs[0], gem.inputs[0]); L(ggain.outputs["Value"], gem.inputs["Scale"])

    e1 = N("ShaderNodeVectorMath"); e1.operation = 'ADD'; e1.location = (X0 + 2600, 650)
    L(cem.outputs["Vector"], e1.inputs[0]); L(rem.outputs["Vector"], e1.inputs[1])
    e2 = N("ShaderNodeVectorMath"); e2.operation = 'ADD'; e2.location = (X0 + 2780, 650)
    L(e1.outputs["Vector"], e2.inputs[0]); L(gem.outputs["Vector"], e2.inputs[1])

    return megcol.outputs[2], rgh.outputs[0], e2.outputs["Vector"]
