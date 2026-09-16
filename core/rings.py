"""Ring system: real annulus geometry, azimuthal structure, named divisions.

What was wrong with the first version
-------------------------------------
* The rings were drawn on a 2-vertex quad. The corners lie outside the annulus,
  so every ray that hit them still paid for a transparent bounce, and edge-on
  the disc was a zero-thickness aliasing line.
* `Ring Seed` was computed and never connected, so every seed gave byte-
  identical rings.
* Density varied with radius only. Perfect concentric circles are the single
  strongest "this is procedural" tell; real ring systems have spiral density
  waves at orbital resonances, azimuthal clumping, and moonlet wakes.
* Divisions came out of the same noise as the ringlets, so the Cassini
  Division moved whenever the seed changed.

Reference: the structures modelled here -- density waves at resonances,
shepherd-moon wakes with sharp-edged gaps, and stable named divisions -- are
the features Cassini resolved in Saturn's rings.
"""
import bpy

try:
    from . import anim as _anim
except ImportError:
    import anim as _anim

# Named divisions, positioned in normalised radius across [Inner, Outer].
# These are deliberately independent of the noise so ring structure stays put
# when the seed changes -- a division that wanders is not a division.
DIVISIONS = (
    ("Maxwell", 0.300, 0.008, 0.70),
    ("Cassini", 0.620, 0.055, 0.95),
    ("Huygens", 0.665, 0.006, 0.85),
    ("Encke",   0.885, 0.012, 0.98),
    ("Keeler",  0.945, 0.005, 0.90),
)

RING_IN = [
    ("Inner", 'NodeSocketFloat', 1350.0, 1.0, 1e6),
    ("Outer", 'NodeSocketFloat', 2300.0, 1.0, 1e6),
    ("Ring Density", 'NodeSocketFloat', 1.0, 0.0, 3.0),
    ("Ring Colour", 'NodeSocketColor', (0.72, 0.70, 0.65, 1.0), None, None),
    ("Ice Colour", 'NodeSocketColor', (0.86, 0.88, 0.92, 1.0), None, None),
    ("Dust Colour", 'NodeSocketColor', (0.62, 0.52, 0.40, 1.0), None, None),
    ("Rock Colour", 'NodeSocketColor', (0.34, 0.29, 0.25, 1.0), None, None),
    ("Composition Scale", 'NodeSocketFloat', 3.4, 0.1, 40.0),
    ("Band Scale", 'NodeSocketFloat', 120.0, 1.0, 900.0),
    ("Band Contrast", 'NodeSocketFloat', 1.9, 0.2, 8.0),
    ("Gap Amount", 'NodeSocketFloat', 0.55, 0.0, 1.0),
    ("Gap Softness", 'NodeSocketFloat', 0.18, 0.005, 1.0),
    ("Division Depth", 'NodeSocketFloat', 1.0, 0.0, 1.0),
    ("Spiral Arms", 'NodeSocketFloat', 7.0, 0.0, 40.0),
    ("Spiral Strength", 'NodeSocketFloat', 0.22, 0.0, 1.0),
    ("Spiral Winding", 'NodeSocketFloat', 46.0, 0.0, 400.0),
    ("Wake Strength", 'NodeSocketFloat', 0.35, 0.0, 1.0),
    ("Wake Count", 'NodeSocketFloat', 120.0, 4.0, 600.0),
    ("Clump Scale", 'NodeSocketFloat', 5.5, 0.1, 60.0),
    ("Clump Strength", 'NodeSocketFloat', 0.30, 0.0, 1.0),
    ("Forward Anisotropy", 'NodeSocketFloat', 0.62, 0.0, 0.95),
    ("Forward Gain", 'NodeSocketFloat', 2.4, 0.0, 12.0),
    ("Ring Seed", 'NodeSocketFloat', 0.0, -10000.0, 10000.0),
    # The shader needs the planet radius to know an orbital period: r/R is what
    # Kepler takes, and Inner and Outer alone cannot supply it.
    ("Planet Radius", 'NodeSocketFloat', 1000.0, 1.0, 1e6),
]


try:
    from .nodeutil import sockin, sockout
except ImportError:
    from nodeutil import sockin, sockout


def _sunvec(g, loc=(-1800, -900)):
    """Sun direction as a live vector, tracked through PLNT_SunDir.

    matrix_world is not a dependency-tracked driver path -- it silently freezes
    at whatever it was when the driver was created. PLNT_SunDir is an empty
    parented to the sun at local (0,0,1); since the sun sits at the pivot
    origin its world location IS the sun's Z axis, and TRANSFORMS/WORLD_SPACE
    location drivers do track.
    """
    n = g.nodes.new("ShaderNodeCombineXYZ")
    n.location = loc
    n.label = "SUNVEC"
    target = bpy.data.objects.get("PLNT_SunDir")
    if not target:
        n.inputs[0].default_value = 1.0
        return n
    for i, tt in enumerate(('LOC_X', 'LOC_Y', 'LOC_Z')):
        fc = n.inputs[i].driver_add("default_value")
        d = fc.driver
        d.type = 'SCRIPTED'
        v = d.variables.new()
        v.name = "p"
        v.type = 'TRANSFORMS'
        t = v.targets[0]
        t.id = target
        t.transform_type = tt
        t.transform_space = 'WORLD_SPACE'
        d.expression = "p"
    return n


def build_ring_shader(name="PLNT_RingShader", inner=1350.0, outer=2300.0):
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    I = g.interface
    for n, st, dv, mn, mx in RING_IN:
        s = I.new_socket(name=n, in_out='INPUT', socket_type=st)
        if dv is not None:
            s.default_value = dv
        if mn is not None:
            s.min_value = mn
        if mx is not None:
            s.max_value = mx
    I.new_socket(name="BSDF", in_out='OUTPUT', socket_type='NodeSocketShader')
    gin = {i.name: i for i in I.items_tree if getattr(i, "item_type", "") == 'SOCKET'}
    gin["Inner"].default_value = inner
    gin["Outer"].default_value = outer

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2400, 0)
    go = N("NodeGroupOutput"); go.location = (1800, 0)
    S = gi.outputs

    def M(op, x=None, y=None, loc=(0, 0), nm="", clamp=False):
        n = N("ShaderNodeMath"); n.operation = op; n.location = loc
        n.label = nm; n.use_clamp = clamp
        if x is not None: n.inputs[0].default_value = x
        if y is not None: n.inputs[1].default_value = y
        return n

    def MR(loc, fmin, fmax, tmin, tmax, nm="", interp='LINEAR'):
        n = N("ShaderNodeMapRange"); n.location = loc; n.label = nm
        n.clamp = True; n.interpolation_type = interp
        for i, v in ((1, fmin), (2, fmax), (3, tmin), (4, tmax)):
            if v is not None:
                n.inputs[i].default_value = v
        return n

    # ---------------- polar frame ----------------
    tc = N("ShaderNodeTexCoord"); tc.location = (-2400, -500)
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (-2220, -500)
    L(sockout(tc, "Object"), sockin(sep, "Vector"))
    x2 = M('POWER', y=2.0, loc=(-2040, -420)); L(sep.outputs["X"], x2.inputs[0])
    y2 = M('POWER', y=2.0, loc=(-2040, -580)); L(sep.outputs["Y"], y2.inputs[0])
    xy = M('ADD', loc=(-1880, -500)); L(x2.outputs[0], xy.inputs[0]); L(y2.outputs[0], xy.inputs[1])
    r = M('SQRT', loc=(-1720, -500), nm="radius"); L(xy.outputs[0], r.inputs[0])
    # ---- differential rotation -------------------------------------------
    #
    # A ring is not a disc. It is several hundred million independent bodies,
    # each on its own circular orbit, and the inner ones go round faster:
    # Saturn B ring inner edge takes about 7 hours, the outer A ring about 14.
    # Anything drawn on the ring that is a function of ANGLE therefore has to
    # shear -- clumps, spiral density waves and shepherd wakes all do -- while
    # anything that is a function of RADIUS, which is every named division,
    # must stay exactly where it is.
    #
    # Rotating the sampling angle by -w(r)t does both at once, for the cost of
    # one subtraction: theta shifts, r does not.
    rR = M('DIVIDE', loc=(-1900, -860), nm="r over R")
    L(r.outputs[0], rR.inputs[0]); L(S["Planet Radius"], rR.inputs[1])
    rsafe = M('MAXIMUM', y=1.0, loc=(-1760, -860))
    L(rR.outputs[0], rsafe.inputs[0])
    rphase = _anim.geo_orbit_rad(g, rsafe.outputs[0], loc=(-1560, -900),
                                 label="ring phase")

    # ARCTAN2 is atan2(input0, input1) -> atan2(y, x)
    th0 = M('ARCTAN2', loc=(-1720, -700), nm="theta raw")
    L(sep.outputs["Y"], th0.inputs[0]); L(sep.outputs["X"], th0.inputs[1])
    th = M('SUBTRACT', loc=(-1560, -700), nm="theta")
    L(th0.outputs[0], th.inputs[0]); L(rphase, th.inputs[1])

    nr = MR((-1520, -500), None, None, 0.0, 1.0, "nr")
    L(r.outputs[0], nr.inputs[0]); L(S["Inner"], nr.inputs[1]); L(S["Outer"], nr.inputs[2])
    NR = nr.outputs["Result"]

    # annulus mask: hard-edged, because real ring edges are sharp
    inA = MR((-1520, -220), None, None, 0.0, 1.0, "inner edge", 'SMOOTHSTEP')
    L(r.outputs[0], inA.inputs[0]); L(S["Inner"], inA.inputs[1])
    iw = M('MULTIPLY', y=1.006, loc=(-1720, -120)); L(S["Inner"], iw.inputs[0])
    L(iw.outputs[0], inA.inputs[2])
    outA = MR((-1520, -20), None, None, 1.0, 0.0, "outer edge", 'SMOOTHSTEP')
    L(r.outputs[0], outA.inputs[0])
    ow = M('MULTIPLY', y=0.994, loc=(-1720, 60)); L(S["Outer"], ow.inputs[0])
    L(ow.outputs[0], outA.inputs[1]); L(S["Outer"], outA.inputs[2])
    ann = M('MULTIPLY', loc=(-1340, -120), nm="annulus")
    L(inA.outputs["Result"], ann.inputs[0]); L(outA.outputs["Result"], ann.inputs[1])

    # ---------------- radial ringlet structure ----------------
    seedw = M('MULTIPLY', y=3.77, loc=(-1720, 400), nm="seed w")
    L(S["Ring Seed"], seedw.inputs[0])
    bs = M('MULTIPLY', loc=(-1520, 300), nm="band coord")
    L(NR, bs.inputs[0]); L(S["Band Scale"], bs.inputs[1])
    bc = M('ADD', loc=(-1360, 300)); L(bs.outputs[0], bc.inputs[0])
    L(seedw.outputs[0], bc.inputs[1])
    BC = bc.outputs[0]

    coarse = N("ShaderNodeTexVoronoi"); coarse.location = (-1180, 400)
    coarse.voronoi_dimensions = '1D'; coarse.feature = 'F1'; coarse.label = "ringlets"
    sockin(coarse, "Randomness").default_value = 1.0
    L(BC, sockin(coarse, "W"))
    fscale = M('MULTIPLY', y=4.3, loc=(-1180, 240)); L(BC, fscale.inputs[0])
    fine = N("ShaderNodeTexVoronoi"); fine.location = (-1000, 240)
    fine.voronoi_dimensions = '1D'; fine.feature = 'F1'; fine.label = "fine ringlets"
    sockin(fine, "Randomness").default_value = 1.0
    L(fscale.outputs[0], sockin(fine, "W"))
    dust = N("ShaderNodeTexNoise"); dust.location = (-1180, 60)
    dust.noise_dimensions = '1D'; dust.noise_type = 'FBM'; dust.label = "dust"
    sockin(dust, "Detail").default_value = 8.0
    sockin(dust, "Scale").default_value = 2.4
    L(BC, sockin(dust, "W"))

    # 1D Voronoi F1 distance tops out near 0.5 -> normalise before combining
    cn = M('MULTIPLY', y=2.0, loc=(-820, 400)); L(sockout(coarse, "Distance"), cn.inputs[0])
    fn = M('MULTIPLY', y=2.0, loc=(-820, 240)); L(sockout(fine, "Distance"), fn.inputs[0])
    cw = M('MULTIPLY', y=0.55, loc=(-660, 400)); L(cn.outputs[0], cw.inputs[0])
    fw = M('MULTIPLY', y=0.27, loc=(-660, 240)); L(fn.outputs[0], fw.inputs[0])
    dw = M('MULTIPLY', y=0.18, loc=(-660, 60)); L(sockout(dust, "Fac"), dw.inputs[0])
    mix1 = M('ADD', loc=(-500, 320)); L(cw.outputs[0], mix1.inputs[0]); L(fw.outputs[0], mix1.inputs[1])
    bands = M('ADD', loc=(-340, 320), clamp=True, nm="bands")
    L(mix1.outputs[0], bands.inputs[0]); L(dw.outputs[0], bands.inputs[1])
    # contrast BEFORE thresholding is what reads as ringlets rather than gradient
    contrast = M('POWER', loc=(-180, 320), nm="contrast")
    L(bands.outputs[0], contrast.inputs[0]); L(S["Band Contrast"], contrast.inputs[1])
    g["_ctx"] = 1
    return g, dict(N=N, L=L, M=M, MR=MR, gi=gi, go=go, S=S, NR=NR, TH=th.outputs[0],
                   ANN=ann.outputs[0], BC=BC, CONTRAST=contrast.outputs[0],
                   SEP=sep, R=r.outputs[0],
                   POBJ=sockout(tc, "Object"), PHASE=rphase)


def _divisions(ctx, g):
    """Stable named gaps, independent of the noise.

    Each division is a smoothstep notch on normalised radius. Because they do
    not come from the band noise, the Cassini Division stays where it is when
    the seed changes -- which is what makes it read as a division rather than
    as a wide dark ringlet.
    """
    N, L, M, MR, S, NR = ctx["N"], ctx["L"], ctx["M"], ctx["MR"], ctx["S"], ctx["NR"]
    y = 900
    product = None
    for label, centre, width, depth in DIVISIONS:
        # widen/narrow every gap together with Gap Softness
        wsoft = M('MULTIPLY', y=width, loc=(-1180, y - 60), nm=label + " w")
        L(S["Gap Softness"], wsoft.inputs[0])
        wsc = M('MULTIPLY', y=5.0, loc=(-1020, y - 60))
        L(wsoft.outputs[0], wsc.inputs[0])
        lo = M('SUBTRACT', x=centre, loc=(-860, y - 60))
        L(wsc.outputs[0], lo.inputs[1])
        hi = M('ADD', x=centre, loc=(-860, y - 140))
        L(wsc.outputs[0], hi.inputs[1])
        rise = MR((-680, y), None, None, 0.0, 1.0, label + " in", 'SMOOTHSTEP')
        L(NR, rise.inputs[0]); L(lo.outputs[0], rise.inputs[1])
        rise.inputs[2].default_value = centre
        cm = N("ShaderNodeValue"); cm.location = (-860, y + 80); cm.label = label + " c"
        cm.outputs[0].default_value = centre
        L(cm.outputs[0], rise.inputs[2])
        fall = MR((-680, y - 160), None, None, 1.0, 0.0, label + " out", 'SMOOTHSTEP')
        L(NR, fall.inputs[0]); L(cm.outputs[0], fall.inputs[1]); L(hi.outputs[0], fall.inputs[2])
        band = M('MULTIPLY', loc=(-500, y - 80), nm=label)
        L(rise.outputs["Result"], band.inputs[0]); L(fall.outputs["Result"], band.inputs[1])
        dep = M('MULTIPLY', y=depth, loc=(-340, y - 80))
        L(band.outputs[0], dep.inputs[0])
        scl = M('MULTIPLY', loc=(-180, y - 80))
        L(dep.outputs[0], scl.inputs[0]); L(S["Division Depth"], scl.inputs[1])
        keep = M('SUBTRACT', x=1.0, loc=(-20, y - 80), clamp=True)
        L(scl.outputs[0], keep.inputs[1])
        if product is None:
            product = keep.outputs[0]
        else:
            mul = M('MULTIPLY', loc=(140, y - 80))
            L(product, mul.inputs[0]); L(keep.outputs[0], mul.inputs[1])
            product = mul.outputs[0]
        y -= 320
    return product


def _azimuthal(ctx, g):
    """Spiral density waves, clumping and moonlet wakes.

    Perfect concentric circles are the strongest tell that a ring is
    procedural. Three effects break them up:

    * spiral density waves at orbital resonances. The arm count must be an
      integer or the pattern leaves a hard seam where theta wraps at +/-pi.
    * azimuthal clumping, sampled on (x, y) rather than on theta -- Cartesian
      coordinates are continuous across the wrap, so there is no seam to fix.
    * shepherd-moon wakes, localised to the outer ring edge with a Gaussian
      falloff so they read as a disturbance at one radius, not everywhere.
    """
    N, L, M, MR = ctx["N"], ctx["L"], ctx["M"], ctx["MR"]
    S, NR, TH, SEP = ctx["S"], ctx["NR"], ctx["TH"], ctx["SEP"]

    arms = M('ROUND', loc=(-1180, 1600), nm="arms")
    L(S["Spiral Arms"], arms.inputs[0])
    ta = M('MULTIPLY', loc=(-1020, 1600)); L(TH, ta.inputs[0]); L(arms.outputs[0], ta.inputs[1])
    wind = M('MULTIPLY', loc=(-1020, 1460)); L(NR, wind.inputs[0])
    L(S["Spiral Winding"], wind.inputs[1])
    ph = M('ADD', loc=(-860, 1530)); L(ta.outputs[0], ph.inputs[0]); L(wind.outputs[0], ph.inputs[1])
    sw = M('SINE', loc=(-700, 1530), nm="density wave"); L(ph.outputs[0], sw.inputs[0])
    sw01 = MR((-540, 1530), -1.0, 1.0, 0.0, 1.0, "wave01")
    L(sw.outputs[0], sw01.inputs[0])
    swa = M('MULTIPLY', loc=(-380, 1530)); L(sw01.outputs["Result"], swa.inputs[0])
    L(S["Spiral Strength"], swa.inputs[1])
    wave = M('SUBTRACT', x=1.0, loc=(-220, 1530), clamp=True, nm="wave gain")
    L(swa.outputs[0], wave.inputs[1])

    # clumping on Cartesian coords -- continuous across the theta wrap, and
    # rotated by the same orbital phase so a clump travels with its own orbit
    # instead of hanging in space while the density waves sweep through it
    rot = ctx["N"]("ShaderNodeVectorRotate")
    rot.location = (-1420, 1260); rot.label = "clump frame"
    rot.rotation_type = 'Z_AXIS'
    ctx["L"](ctx["POBJ"], rot.inputs["Vector"])
    ctx["L"](ctx["PHASE"], rot.inputs["Angle"])
    RSEP = ctx["N"]("ShaderNodeSeparateXYZ"); RSEP.location = (-1300, 1260)
    ctx["L"](rot.outputs["Vector"], RSEP.inputs["Vector"])
    cvx = M('MULTIPLY', loc=(-1180, 1300)); L(RSEP.outputs["X"], cvx.inputs[0])
    cvy = M('MULTIPLY', loc=(-1180, 1220)); L(RSEP.outputs["Y"], cvy.inputs[0])
    inv = M('MULTIPLY', y=0.0022, loc=(-1520, 1260)); L(S["Clump Scale"], inv.inputs[0])
    L(inv.outputs[0], cvx.inputs[1]); L(inv.outputs[0], cvy.inputs[1])
    cv = N("ShaderNodeCombineXYZ"); cv.location = (-1020, 1260)
    L(cvx.outputs[0], cv.inputs[0]); L(cvy.outputs[0], cv.inputs[1])
    rz = M('MULTIPLY', y=3.0, loc=(-1180, 1140)); L(NR, rz.inputs[0])
    L(rz.outputs[0], cv.inputs[2])
    cn = N("ShaderNodeTexNoise"); cn.location = (-860, 1260); cn.label = "clumps"
    cn.noise_dimensions = '3D'; cn.noise_type = 'FBM'
    sockin(cn, "Detail").default_value = 4.0
    sockin(cn, "Scale").default_value = 1.0
    L(cv.outputs["Vector"], sockin(cn, "Vector"))
    cc = MR((-700, 1260), 0.35, 0.72, 1.0, 0.0, "clump01")
    L(sockout(cn, "Fac"), cc.inputs[0])
    ca = M('MULTIPLY', loc=(-540, 1260)); L(cc.outputs["Result"], ca.inputs[0])
    L(S["Clump Strength"], ca.inputs[1])
    clump = M('SUBTRACT', x=1.0, loc=(-380, 1260), clamp=True, nm="clump gain")
    L(ca.outputs[0], clump.inputs[1])

    # shepherd-moon wakes at the outer edge (Encke analogue)
    wc = M('MULTIPLY', loc=(-1180, 1020)); L(TH, wc.inputs[0])
    L(S["Wake Count"], wc.inputs[1])
    wr = M('MULTIPLY', y=260.0, loc=(-1180, 940)); L(NR, wr.inputs[0])
    wp = M('ADD', loc=(-1020, 980)); L(wc.outputs[0], wp.inputs[0]); L(wr.outputs[0], wp.inputs[1])
    ws = M('SINE', loc=(-860, 980)); L(wp.outputs[0], ws.inputs[0])
    ws01 = MR((-700, 980), -1.0, 1.0, 0.0, 1.0); L(ws.outputs[0], ws01.inputs[0])
    # Gaussian localisation around the Encke gap edge
    wd = M('SUBTRACT', y=0.885, loc=(-1020, 860)); L(NR, wd.inputs[0])
    wd2 = M('POWER', y=2.0, loc=(-860, 860)); L(wd.outputs[0], wd2.inputs[0])
    wdn = M('MULTIPLY', y=-900.0, loc=(-700, 860)); L(wd2.outputs[0], wdn.inputs[0])
    wg = M('EXPONENT', loc=(-540, 860), nm="wake envelope"); L(wdn.outputs[0], wg.inputs[0])
    wm = M('MULTIPLY', loc=(-380, 980)); L(ws01.outputs["Result"], wm.inputs[0])
    L(wg.outputs[0], wm.inputs[1])
    wa2 = M('MULTIPLY', loc=(-220, 980)); L(wm.outputs[0], wa2.inputs[0])
    L(S["Wake Strength"], wa2.inputs[1])
    wake = M('SUBTRACT', x=1.0, loc=(-60, 980), clamp=True, nm="wake gain")
    L(wa2.outputs[0], wake.inputs[1])

    m1 = M('MULTIPLY', loc=(100, 1400)); L(wave.outputs[0], m1.inputs[0])
    L(clump.outputs[0], m1.inputs[1])
    m2 = M('MULTIPLY', loc=(260, 1400), nm="azimuthal"); L(m1.outputs[0], m2.inputs[0])
    L(wake.outputs[0], m2.inputs[1])
    return m2.outputs[0]


def _mix_rgba(g, loc, label=""):
    """ShaderNodeMix in colour mode.

    Index by integer, never by name: this node carries three sets of
    identically named sockets. For RGBA the live ones are inputs 0 (Factor),
    6 (A) and 7 (B), and output 2 (Result).
    """
    n = g.nodes.new("ShaderNodeMix")
    n.data_type = 'RGBA'
    n.location = loc
    n.label = label
    return n


def _finish(ctx, g, divisions, azimuthal):
    N, L, M, MR = ctx["N"], ctx["L"], ctx["M"], ctx["MR"]
    S, NR, go = ctx["S"], ctx["NR"], ctx["go"]

    # ---------------- alpha ----------------
    glo = M('MULTIPLY', y=0.62, loc=(20, 320)); L(S["Gap Amount"], glo.inputs[0])
    ghi = M('ADD', y=0.17, loc=(180, 320)); L(glo.outputs[0], ghi.inputs[0])
    gap = MR((340, 320), None, None, 0.0, 1.0, "gaps")
    L(ctx["CONTRAST"], gap.inputs[0])
    L(glo.outputs[0], gap.inputs[1]); L(ghi.outputs[0], gap.inputs[2])

    a1 = M('MULTIPLY', loc=(520, 320)); L(gap.outputs["Result"], a1.inputs[0])
    L(ctx["ANN"], a1.inputs[1])
    a2 = M('MULTIPLY', loc=(680, 320)); L(a1.outputs[0], a2.inputs[0])
    L(divisions, a2.inputs[1])
    a3 = M('MULTIPLY', loc=(840, 320)); L(a2.outputs[0], a3.inputs[0])
    L(azimuthal, a3.inputs[1])
    alpha = M('MULTIPLY', loc=(1000, 320), clamp=True, nm="alpha")
    L(a3.outputs[0], alpha.inputs[0]); L(S["Ring Density"], alpha.inputs[1])

    # ---------------- composition ----------------
    cs = M('MULTIPLY', loc=(20, 0)); L(NR, cs.inputs[0])
    L(S["Composition Scale"], cs.inputs[1])
    cnz = N("ShaderNodeTexNoise"); cnz.location = (180, 0); cnz.label = "composition"
    cnz.noise_dimensions = '1D'; cnz.noise_type = 'FBM'
    sockin(cnz, "Detail").default_value = 3.0
    sockin(cnz, "Scale").default_value = 1.0
    L(cs.outputs[0], sockin(cnz, "W"))
    m_id = _mix_rgba(g, (400, 40), "ice>dust")
    L(sockout(cnz, "Fac"), m_id.inputs[0])
    L(S["Ice Colour"], m_id.inputs[6]); L(S["Dust Colour"], m_id.inputs[7])
    rocky = MR((400, -160), 0.62, 0.88, 0.0, 1.0, "rocky")
    L(sockout(cnz, "Fac"), rocky.inputs[0])
    m_r = _mix_rgba(g, (620, 0), ">rock")
    L(rocky.outputs["Result"], m_r.inputs[0])
    L(m_id.outputs[2], m_r.inputs[6]); L(S["Rock Colour"], m_r.inputs[7])
    tint = g.nodes.new("ShaderNodeVectorMath"); tint.operation = 'MULTIPLY'
    tint.location = (840, 0); tint.label = "tint"
    L(m_r.outputs[2], tint.inputs[0]); L(S["Ring Colour"], tint.inputs[1])
    COL = tint.outputs["Vector"]

    # ---------------- forward scattering ----------------
    # Henyey-Greenstein, using the real sun direction. No Volume Scatter: a
    # volume on a 4600 BU disc is exactly the OptiX out-of-memory failure this
    # project has already been bitten by.
    sunv = _sunvec(g, (20, -420))
    sxf = g.nodes.new("ShaderNodeVectorTransform")
    sxf.location = (140, -420); sxf.label = "SUNVEC_OBJ"
    sxf.vector_type = 'VECTOR'
    sxf.convert_from = 'WORLD'
    sxf.convert_to = 'OBJECT'
    L(sunv.outputs["Vector"], sxf.inputs[0])
    geo = N("ShaderNodeNewGeometry"); geo.location = (20, -600)
    dot = g.nodes.new("ShaderNodeVectorMath"); dot.operation = 'DOT_PRODUCT'
    dot.location = (240, -520); dot.label = "cos phase"
    L(sockout(geo, "Incoming"), dot.inputs[0]); L(sxf.outputs[0], dot.inputs[1])
    gg = M('MULTIPLY', loc=(240, -700)); L(S["Forward Anisotropy"], gg.inputs[0])
    L(S["Forward Anisotropy"], gg.inputs[1])
    num = M('SUBTRACT', x=1.0, loc=(400, -700)); L(gg.outputs[0], num.inputs[1])
    d1 = M('ADD', x=1.0, loc=(400, -820)); L(gg.outputs[0], d1.inputs[1])
    two_g = M('MULTIPLY', y=2.0, loc=(400, -940)); L(S["Forward Anisotropy"], two_g.inputs[0])
    tgc = M('MULTIPLY', loc=(560, -940)); L(two_g.outputs[0], tgc.inputs[0])
    L(dot.outputs["Value"], tgc.inputs[1])
    den0 = M('SUBTRACT', loc=(720, -820)); L(d1.outputs[0], den0.inputs[0])
    L(tgc.outputs[0], den0.inputs[1])
    den0c = M('MAXIMUM', y=0.0015, loc=(880, -820)); L(den0.outputs[0], den0c.inputs[0])
    den = M('POWER', y=1.5, loc=(1040, -820)); L(den0c.outputs[0], den.inputs[0])
    hg = M('DIVIDE', loc=(1200, -760)); L(num.outputs[0], hg.inputs[0])
    L(den.outputs[0], hg.inputs[1])
    hgg = M('MULTIPLY', loc=(1360, -760), nm="HG gain")
    L(hg.outputs[0], hgg.inputs[0]); L(S["Forward Gain"], hgg.inputs[1])
    hgc = M('MINIMUM', y=14.0, loc=(1520, -760)); L(hgg.outputs[0], hgc.inputs[0])

    fwd = g.nodes.new("ShaderNodeVectorMath"); fwd.operation = 'SCALE'
    fwd.location = (1040, -180); fwd.label = "forward colour"
    L(COL, fwd.inputs[0]); L(hgc.outputs[0], fwd.inputs["Scale"])

    tr = N("ShaderNodeBsdfTranslucent"); tr.location = (1240, -60)
    L(fwd.outputs["Vector"], sockin(tr, "Color"))
    df = N("ShaderNodeBsdfDiffuse"); df.location = (1240, -300)
    L(COL, sockin(df, "Color"))
    surf = N("ShaderNodeMixShader"); surf.location = (1440, -150); surf.label = "scatter"
    surf.inputs[0].default_value = 0.62
    L(sockout(tr, "BSDF"), surf.inputs[1]); L(sockout(df, "BSDF"), surf.inputs[2])

    tp = N("ShaderNodeBsdfTransparent"); tp.location = (1440, 200)
    out = N("ShaderNodeMixShader"); out.location = (1640, 60); out.label = "alpha"
    L(alpha.outputs[0], out.inputs[0])
    L(sockout(tp, "BSDF"), out.inputs[1])
    L(surf.outputs[0], out.inputs[2])
    L(out.outputs[0], go.inputs["BSDF"])
    return g


def build_shader(name="PLNT_RingShader", inner=1350.0, outer=2300.0):
    g, ctx = build_ring_shader(name, inner, outer)
    div = _divisions(ctx, g)
    azi = _azimuthal(ctx, g)
    _finish(ctx, g, div, azi)
    return g


def build_geometry(name="PLNT_RingsRig", inner=1350.0, outer=2300.0):
    """A real annulus, not a quad.

    The old rings lived on a 2x2 grid whose corners sit outside the ring; every
    ray that hit a corner still paid for a transparent bounce, and edge-on the
    disc was a zero-thickness line that aliased. A polar-mapped grid is both
    cheaper and correct, and carrying a little vertical corrugation gives the
    edge-on shot an actual cross-section.
    """
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    I = g.interface
    I.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    I.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')

    def sk(n, st, dv, mn=None, mx=None, desc=""):
        s = I.new_socket(name=n, in_out='INPUT', socket_type=st)
        if dv is not None:
            s.default_value = dv
        if mn is not None:
            s.min_value = mn
        if mx is not None:
            s.max_value = mx
        s.description = desc
        return s

    sk("Inner", 'NodeSocketFloat', inner, 1.0, 1e6,
       "Inner edge of the ring annulus in Blender units")
    sk("Outer", 'NodeSocketFloat', outer, 1.0, 1e6,
       "Outer edge of the ring annulus in Blender units")
    sk("Radial Segments", 'NodeSocketInt', 384, 4, 2048,
       "Rings across the disc. Raise this if radial banding looks stepped")
    sk("Angular Segments", 'NodeSocketInt', 512, 8, 4096,
       "Segments around the disc. Raise this if the outer edge looks polygonal")
    sk("Ring Warp", 'NodeSocketFloat', 2.4, 0.0, 200.0,
       "Vertical corrugation of the ring plane. Gives the disc a cross-section "
       "when seen edge-on instead of an aliasing line")
    sk("Warp Scale", 'NodeSocketFloat', 6.0, 0.1, 60.0,
       "Feature size of the vertical corrugation")
    sk("Material", 'NodeSocketMaterial', None, None, None,
       "Material applied to the ring disc")

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-1200, 0)
    go = N("NodeGroupOutput"); go.location = (900, 0)
    S = gi.outputs

    grid = N("GeometryNodeMeshGrid"); grid.location = (-960, 0)
    sockin(grid, "Size X").default_value = 1.0
    sockin(grid, "Size Y").default_value = 1.0
    L(S["Radial Segments"], sockin(grid, "Vertices X"))
    L(S["Angular Segments"], sockin(grid, "Vertices Y"))

    pos = N("GeometryNodeInputPosition"); pos.location = (-960, -320)
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (-800, -320)
    L(sockout(pos, "Position"), sockin(sep, "Vector"))

    def M(op, x=None, y=None, loc=(0, 0), nm=""):
        n = g.nodes.new("ShaderNodeMath"); n.operation = op
        n.location = loc; n.label = nm
        if x is not None: n.inputs[0].default_value = x
        if y is not None: n.inputs[1].default_value = y
        return n

    # grid spans -0.5..0.5 on both axes -> u,v in 0..1
    u = M('ADD', y=0.5, loc=(-640, -240), nm="u"); L(sep.outputs["X"], u.inputs[0])
    v = M('ADD', y=0.5, loc=(-640, -400), nm="v"); L(sep.outputs["Y"], v.inputs[0])
    span = M('SUBTRACT', loc=(-800, 200)); L(S["Outer"], span.inputs[0])
    L(S["Inner"], span.inputs[1])
    ru = M('MULTIPLY', loc=(-480, -240)); L(u.outputs[0], ru.inputs[0])
    L(span.outputs[0], ru.inputs[1])
    rad = M('ADD', loc=(-320, -240), nm="r"); L(ru.outputs[0], rad.inputs[0])
    L(S["Inner"], rad.inputs[1])
    th = M('MULTIPLY', y=6.283185307, loc=(-480, -400), nm="theta")
    L(v.outputs[0], th.inputs[0])
    ct = M('COSINE', loc=(-320, -400)); L(th.outputs[0], ct.inputs[0])
    st = M('SINE', loc=(-320, -480)); L(th.outputs[0], st.inputs[0])
    px = M('MULTIPLY', loc=(-160, -320)); L(rad.outputs[0], px.inputs[0])
    L(ct.outputs[0], px.inputs[1])
    py = M('MULTIPLY', loc=(-160, -440)); L(rad.outputs[0], py.inputs[0])
    L(st.outputs[0], py.inputs[1])

    # vertical corrugation, sampled on Cartesian coords so there is no seam
    wv = N("ShaderNodeCombineXYZ"); wv.location = (-160, -620)
    wsx = M('MULTIPLY', y=0.0016, loc=(-320, -620)); L(px.outputs[0], wsx.inputs[0])
    wsy = M('MULTIPLY', y=0.0016, loc=(-320, -700)); L(py.outputs[0], wsy.inputs[0])
    L(wsx.outputs[0], wv.inputs[0]); L(wsy.outputs[0], wv.inputs[1])
    wn = N("ShaderNodeTexNoise"); wn.location = (0, -620); wn.label = "warp"
    wn.noise_dimensions = '3D'; wn.noise_type = 'FBM'
    sockin(wn, "Detail").default_value = 3.0
    L(S["Warp Scale"], sockin(wn, "Scale"))
    L(sockout(wv, "Vector"), sockin(wn, "Vector"))
    wc = M('SUBTRACT', y=0.5, loc=(160, -620)); L(sockout(wn, "Fac"), wc.inputs[0])
    pz = M('MULTIPLY', loc=(320, -620), nm="z"); L(wc.outputs[0], pz.inputs[0])
    L(S["Ring Warp"], pz.inputs[1])

    newp = N("ShaderNodeCombineXYZ"); newp.location = (160, -320)
    L(px.outputs[0], newp.inputs[0]); L(py.outputs[0], newp.inputs[1])
    L(pz.outputs[0], newp.inputs[2])
    sp = N("GeometryNodeSetPosition"); sp.location = (360, 0)
    L(sockout(grid, "Mesh"), sockin(sp, "Geometry"))
    L(sockout(newp, "Vector"), sockin(sp, "Position"))

    # v = 0 and v = 1 land on the same angle, leaving a duplicate seam ring
    mrg = N("GeometryNodeMergeByDistance"); mrg.location = (540, 0)
    L(sockout(sp, "Geometry"), sockin(mrg, "Geometry"))
    sockin(mrg, "Distance").default_value = 0.05

    setm = N("GeometryNodeSetMaterial"); setm.location = (720, 0)
    L(sockout(mrg, "Geometry"), sockin(setm, "Geometry"))
    L(S["Material"], sockin(setm, "Material"))
    L(sockout(setm, "Geometry"), go.inputs["Geometry"])
    return g
