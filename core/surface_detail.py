"""Extra surface detail, attached to PLNT_SurfaceShader by node label.

Every feature is gated by its own group input defaulting to 0. Measured on this
project: making a shader's inputs constant let Cycles fold a 193-node graph down
to near-nothing, so a feature left at zero is eliminated at compile time rather
than costing a texture lookup per sample. That is what makes it reasonable to
ship a large optional feature surface.

Attaching by label means plnt_surface.py does not have to be restructured, and
the same code works on the ground-patch variant of the shader.
"""
import bpy

try:
    from .nodeutil import sockin, sockout
except ImportError:
    from nodeutil import sockin, sockout

# (name, default, min, max, description)
DETAIL_IN = [
    ("Glint Variation", 0.0, 0.0, 1.0,
     "Breaks up the ocean's specular highlight with wind fetch and surface "
     "slicks. At zero the sea is a uniform mirror, which is the single most "
     "obvious tell in any sunlit ocean shot"),
    ("Foam Amount", 0.0, 0.0, 1.0,
     "White water where shallow sea meets land. Coastlines are the most "
     "looked-at feature on any planet render"),
    ("Dune Amount", 0.0, 0.0, 1.0,
     "Transverse dune ridges in arid lowlands. Built by squashing the noise "
     "along one axis, which is what turns isotropic sand into wind-blown "
     "ridges running perpendicular to the prevailing wind"),
    ("Dune Scale", 260.0, 1.0, 4000.0,
     "Spacing of the dune ridges"),
    ("Strata Amount", 0.0, 0.0, 1.0,
     "Sedimentary banding in exposed rock. The layers follow lines of constant "
     "elevation rather than the noise, so they read as bedding planes and "
     "erode at different rates"),
    ("Strata Frequency", 90.0, 1.0, 1200.0,
     "Number of visible rock layers"),
    ("Ice Crack Amount", 0.0, 0.0, 1.0,
     "Crevasse and flow structure in ice sheets. The cells are stretched along "
     "one axis so they read as glacier flow lines rather than as a mosaic"),
    ("Vegetation Clumping", 0.0, 0.0, 1.0,
     "Varies vegetation hue patch by patch instead of tinting every plant on "
     "the planet the same colour"),
    ("Crater Amount", 0.0, 0.0, 1.0,
     "Impact craters with raised rims. For airless worlds and dead moons"),
    ("Crater Scale", 34.0, 1.0, 400.0,
     "How many craters there are; higher values give smaller, denser craters"),
]


def find(tree, label):
    for n in tree.nodes:
        if n.label == label:
            return n
    return None


def need(tree, label):
    n = find(tree, label)
    if n is None:
        raise KeyError("no node labelled %r in %s; labels present: %r"
                       % (label, tree.name,
                          sorted({x.label for x in tree.nodes if x.label})))
    return n


def group_input(tree):
    return next(n for n in tree.nodes if n.bl_idname == 'NodeGroupInput')


def add_inputs(tree):
    """Append the feature sockets, skipping any that already exist."""
    have = {i.name for i in tree.interface.items_tree
            if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'}
    added = []
    for name, dv, mn, mx, desc in DETAIL_IN:
        if name in have:
            continue
        s = tree.interface.new_socket(name=name, in_out='INPUT',
                                      socket_type='NodeSocketFloat')
        s.default_value = dv
        s.min_value = mn
        s.max_value = mx
        s.description = desc
        added.append(name)
    return added


def splice(tree, node, socket):
    """Detach a socket's consumers so a new node can be inserted in front."""
    s = node.outputs[socket]
    consumers = [(l.to_node, list(l.to_node.inputs).index(l.to_socket))
                 for l in s.links]
    for l in list(s.links):
        tree.links.remove(l)
    return consumers


def reconnect(tree, out_socket, consumers):
    for node, idx in consumers:
        tree.links.new(out_socket, node.inputs[idx])


class Builder(object):
    """Small node factory bound to one tree, positioned in a spare column."""

    def __init__(self, tree, x=-1600, y=-2400):
        self.t = tree
        self.x = x
        self.y = y
        self.row = 0

    def _loc(self, dx=0, dy=0):
        self.row += 1
        return (self.x + dx, self.y - self.row * 60 + dy)

    def N(self, idname, label="", loc=None):
        n = self.t.nodes.new(idname)
        n.location = loc or self._loc()
        if label:
            n.label = label
        return n

    def M(self, op, x=None, y=None, label="", clamp=False):
        n = self.N("ShaderNodeMath", label)
        n.operation = op
        n.use_clamp = clamp
        if x is not None:
            n.inputs[0].default_value = x
        if y is not None:
            n.inputs[1].default_value = y
        return n

    def MR(self, fmin, fmax, tmin, tmax, label="", interp='LINEAR'):
        n = self.N("ShaderNodeMapRange", label)
        n.clamp = True
        n.interpolation_type = interp
        for i, v in ((1, fmin), (2, fmax), (3, tmin), (4, tmax)):
            if v is not None:
                n.inputs[i].default_value = v
        return n

    def VM(self, op, label=""):
        n = self.N("ShaderNodeVectorMath", label)
        n.operation = op
        return n

    def noise(self, dims='3D', ntype='FBM', detail=6.0, label=""):
        n = self.N("ShaderNodeTexNoise", label)
        n.noise_dimensions = dims
        n.noise_type = ntype
        sockin(n, "Detail").default_value = detail
        return n

    def voronoi(self, dims='3D', feature='F1', label=""):
        n = self.N("ShaderNodeTexVoronoi", label)
        n.voronoi_dimensions = dims
        n.feature = feature
        return n

    def mix(self, label=""):
        n = self.N("ShaderNodeMix", label)
        n.data_type = 'RGBA'
        return n

    def L(self, a, b):
        return self.t.links.new(a, b)


def ocean_glint(tree, B, S, P):
    """Wind fetch and slicks on the ocean's specular roughness.

    The shipped shader gives the whole ocean a constant roughness of 0.05, so
    every sea on every planet is the same plastic mirror. Real water varies
    with wind: 0.02 in a sheltered slick, 0.12 under fetch. Shot 04 is built
    entirely around the sun glint, so this is fully exposed there.
    """
    ocean = need(tree, "OCEAN")
    wind = B.noise('4D', 'FBM', 5.0, "wind fetch")
    sockin(wind, "Scale").default_value = 4.6
    B.L(P, sockin(wind, "Vector"))
    slick = B.noise('4D', 'FBM', 3.0, "slicks")
    sockin(slick, "Scale").default_value = 17.0
    B.L(P, sockin(slick, "Vector"))
    comb = B.M('MULTIPLY', label="glint mix")
    B.L(sockout(wind, "Fac"), comb.inputs[0])
    B.L(sockout(slick, "Fac"), comb.inputs[1])
    # Floor at 0.08. Below about 0.06 a curved water surface under a distant
    # sun returns the specular highlight as a handful of single bright pixels
    # that denoising cannot resolve into anything: shot 04 showed the glint as
    # a hard white dot rather than a sheet of light. 0.08 to 0.14 keeps the
    # glint as a glint and still varies with wind.
    rng = B.MR(0.12, 0.72, 0.080, 0.140, "glint roughness")
    B.L(comb.outputs[0], rng.inputs[0])
    # blend from the shipped constant so Glint Variation = 0 is unchanged
    blend = B.MR(0.0, 1.0, 0.08, 0.0, "glint blend")
    B.L(S["Glint Variation"], blend.inputs[0])
    amt = B.M('MULTIPLY', label="glint amt")
    B.L(rng.outputs["Result"], amt.inputs[0])
    B.L(S["Glint Variation"], amt.inputs[1])
    base = B.M('MULTIPLY', label="glint base")
    B.L(blend.outputs["Result"], base.inputs[0])
    base.inputs[1].default_value = 1.0
    tot = B.M('ADD', label="ocean roughness")
    B.L(amt.outputs[0], tot.inputs[0])
    B.L(base.outputs[0], tot.inputs[1])
    for l in list(sockin(ocean, "Roughness").links):
        tree.links.remove(l)
    B.L(tot.outputs[0], sockin(ocean, "Roughness"))
    if "Anisotropic" in ocean.inputs:
        an = B.M('MULTIPLY', y=0.45, label="anisotropy")
        B.L(S["Glint Variation"], an.inputs[0])
        B.L(an.outputs[0], sockin(ocean, "Anisotropic"))
    return "ocean_glint"


def coastal_foam(tree, B, S, P, FIELD):
    """White water in the shallow band along every coast."""
    ocean = need(tree, "OCEAN")
    depth = sockout(FIELD, "ocean_depth")
    band = B.MR(0.0, 0.055, 1.0, 0.0, "foam band", 'SMOOTHSTEP')
    B.L(depth, band.inputs[0])
    brk = B.noise('4D', 'FBM', 7.0, "foam breakup")
    sockin(brk, "Scale").default_value = 62.0
    B.L(P, sockin(brk, "Vector"))
    bg = B.MR(0.42, 0.62, 0.0, 1.0, "foam gate")
    B.L(sockout(brk, "Fac"), bg.inputs[0])
    m1 = B.M('MULTIPLY', label="foam mask")
    B.L(band.outputs["Result"], m1.inputs[0])
    B.L(bg.outputs["Result"], m1.inputs[1])
    m2 = B.M('MULTIPLY', label="foam amt", clamp=True)
    B.L(m1.outputs[0], m2.inputs[0])
    B.L(S["Foam Amount"], m2.inputs[1])

    col_in = sockin(ocean, "Base Color")
    src = col_in.links[0].from_socket if col_in.links else None
    mixn = B.mix("foam colour")
    mixn.inputs[7].default_value = (0.92, 0.95, 0.97, 1.0)
    B.L(m2.outputs[0], mixn.inputs[0])
    if src:
        B.L(src, mixn.inputs[6])
    for l in list(col_in.links):
        tree.links.remove(l)
    B.L(mixn.outputs[2], col_in)

    # foam is rough, not glassy
    r_in = sockin(ocean, "Roughness")
    rsrc = r_in.links[0].from_socket if r_in.links else None
    if rsrc:
        rup = B.M('MULTIPLY', y=0.55, label="foam rough")
        B.L(m2.outputs[0], rup.inputs[0])
        radd = B.M('ADD', label="rough+foam", clamp=True)
        B.L(rsrc, radd.inputs[0])
        B.L(rup.outputs[0], radd.inputs[1])
        for l in list(r_in.links):
            tree.links.remove(l)
        B.L(radd.outputs[0], r_in)
    return "coastal_foam"


def dunes(tree, B, S, P, FIELD):
    """Transverse dune ridges, made by squashing the noise along one axis.

    Isotropic FBM reads as generic bumpy ground. Compressing the sample
    coordinate on a single axis turns the same noise into parallel ridges
    running across the wind, which is what sand actually does. Shot 06 is a
    200 mm lens pointed at desert, so this is fully exposed.
    """
    micro = need(tree, "micro_bu")
    squash = B.VM('MULTIPLY', "dune squash")
    squash.inputs[1].default_value = (1.0, 0.13, 1.0)
    B.L(P, squash.inputs[0])
    scaled = B.VM('SCALE', "dune scale")
    B.L(sockout(squash, "Vector"), scaled.inputs[0])
    B.L(S["Dune Scale"], sockin(scaled, "Scale"))
    dn = B.noise('4D', 'FBM', 4.0, "dunes")
    sockin(dn, "Scale").default_value = 1.0
    sockin(dn, "Roughness").default_value = 0.42
    B.L(sockout(scaled, "Vector"), sockin(dn, "Vector"))
    # sharpen the crests: dunes have a slip face, not a sine profile
    crest = B.MR(0.35, 0.78, 0.0, 1.0, "dune crest", 'SMOOTHSTEP')
    B.L(sockout(dn, "Fac"), crest.inputs[0])
    # only in dry lowlands
    dry = B.MR(0.55, 0.20, 0.0, 1.0, "dune dryness")
    B.L(sockout(FIELD, "humidity"), dry.inputs[0])
    land = B.M('SUBTRACT', x=1.0, label="dune land")
    B.L(sockout(FIELD, "sea_mask"), land.inputs[1])
    g1 = B.M('MULTIPLY', label="dune gate")
    B.L(crest.outputs["Result"], g1.inputs[0])
    B.L(dry.outputs["Result"], g1.inputs[1])
    g2 = B.M('MULTIPLY', label="dune gate2")
    B.L(g1.outputs[0], g2.inputs[0])
    B.L(land.outputs[0], g2.inputs[1])
    amt = B.M('MULTIPLY', label="dune amt")
    B.L(g2.outputs[0], amt.inputs[0])
    B.L(S["Dune Amount"], amt.inputs[1])
    hgt = B.M('MULTIPLY', y=2.6, label="dune height")
    B.L(amt.outputs[0], hgt.inputs[0])
    consumers = splice(tree, micro, 0)
    add = B.M('ADD', label="micro+dunes")
    B.L(micro.outputs[0], add.inputs[0])
    B.L(hgt.outputs[0], add.inputs[1])
    reconnect(tree, add.outputs[0], consumers)
    return "dunes"


def rock_strata(tree, B, S, P, FIELD):
    """Sedimentary banding that follows lines of constant elevation.

    Isotropic noise on rock reads as dirt. Real exposed rock shows bedding
    planes: layers laid down horizontally, then folded. Driving the bands off
    elevation rather than off a 3D noise is what makes them read as strata, and
    modulating the micro-relief with the same signal makes hard and soft layers
    erode differently.
    """
    rockcol = need(tree, "rockcol")
    micro = need(tree, "micro_bu")
    fold = B.noise('4D', 'FBM', 4.0, "strata fold")
    sockin(fold, "Scale").default_value = 2.1
    B.L(P, sockin(fold, "Vector"))
    fs = B.M('MULTIPLY', y=0.06, label="fold amt")
    B.L(sockout(fold, "Fac"), fs.inputs[0])
    ez = B.M('ADD', label="strata coord")
    B.L(sockout(FIELD, "elevation"), ez.inputs[0])
    B.L(fs.outputs[0], ez.inputs[1])
    fr = B.M('MULTIPLY', label="strata freq")
    B.L(ez.outputs[0], fr.inputs[0])
    B.L(S["Strata Frequency"], fr.inputs[1])
    band = B.M('FRACT', label="strata band")
    B.L(fr.outputs[0], band.inputs[0])
    sharp = B.MR(0.18, 0.62, 0.0, 1.0, "strata sharp", 'SMOOTHSTEP')
    B.L(band.outputs[0], sharp.inputs[0])
    # only where rock is exposed
    slope = B.MR(0.38, 0.78, 0.0, 1.0, "strata slope")
    B.L(sockout(FIELD, "slope"), slope.inputs[0])
    g1 = B.M('MULTIPLY', label="strata gate")
    B.L(sharp.outputs["Result"], g1.inputs[0])
    B.L(slope.outputs["Result"], g1.inputs[1])
    amt = B.M('MULTIPLY', label="strata amt")
    B.L(g1.outputs[0], amt.inputs[0])
    B.L(S["Strata Amount"], amt.inputs[1])

    consumers = splice(tree, rockcol, 2)
    tone = B.mix("strata tone")
    # a tint above ~1.15 reads as painted-on contour lines rather than bedding
    tone.inputs[7].default_value = (1.13, 1.06, 0.97, 1.0)
    B.L(amt.outputs[0], tone.inputs[0])
    B.L(rockcol.outputs[2], tone.inputs[6])
    reconnect(tree, tone.outputs[2], consumers)

    # hard and soft layers erode differently
    mconsumers = splice(tree, micro, 0)
    ero = B.MR(0.0, 1.0, 1.0, 1.55, "strata erosion")
    B.L(amt.outputs[0], ero.inputs[0])
    mm = B.M('MULTIPLY', label="micro*strata")
    B.L(micro.outputs[0], mm.inputs[0])
    B.L(ero.outputs["Result"], mm.inputs[1])
    reconnect(tree, mm.outputs[0], mconsumers)
    return "rock_strata"


def ice_cracks(tree, B, S, P, FIELD):
    """Crevasses and flow lines in ice.

    Voronoi DISTANCE_TO_EDGE gives cell boundaries; stretching the sample
    coordinate on one axis is what turns a mosaic of cells into directional
    glacier flow.
    """
    icecol = need(tree, "icecol")
    stretch = B.VM('MULTIPLY', "ice stretch")
    stretch.inputs[1].default_value = (1.0, 1.0, 4.2)
    B.L(P, stretch.inputs[0])
    vor = B.voronoi('4D', 'DISTANCE_TO_EDGE', "ice cracks")
    sockin(vor, "Scale").default_value = 46.0
    sockin(vor, "Randomness").default_value = 1.0
    B.L(sockout(stretch, "Vector"), sockin(vor, "Vector"))
    edge = B.MR(0.0, 0.030, 1.0, 0.0, "crack width")
    B.L(sockout(vor, "Distance"), edge.inputs[0])
    amt = B.M('MULTIPLY', label="crack amt")
    B.L(edge.outputs["Result"], amt.inputs[0])
    B.L(S["Ice Crack Amount"], amt.inputs[1])
    consumers = splice(tree, icecol, 2)
    dark = B.mix("crack colour")
    dark.inputs[7].default_value = (0.42, 0.52, 0.62, 1.0)
    B.L(amt.outputs[0], dark.inputs[0])
    B.L(icecol.outputs[2], dark.inputs[6])
    reconnect(tree, dark.outputs[2], consumers)
    return "ice_cracks"


def vegetation_clumping(tree, B, S, P):
    """Per-patch hue variation, so not every plant on the planet matches."""
    veg = need(tree, "sand>veg")
    vor = B.voronoi('4D', 'F1', "veg patches")
    sockin(vor, "Scale").default_value = 21.0
    sockin(vor, "Randomness").default_value = 1.0
    B.L(P, sockin(vor, "Vector"))
    consumers = splice(tree, veg, 2)
    # Voronoi Color is an unconstrained random RGB per cell, so multiplying by
    # it directly swings the hue wildly and the continents come out patched in
    # pink and olive. Pull it most of the way to white first, so cells vary in
    # tone rather than in hue, which is what real vegetation does.
    tame = B.mix("veg cell tone")
    tame.inputs[6].default_value = (1.0, 1.0, 1.0, 1.0)
    tame.inputs[0].default_value = 0.38
    B.L(sockout(vor, "Color"), tame.inputs[7])
    shift = B.VM('MULTIPLY', "veg tone shift")
    B.L(veg.outputs[2], shift.inputs[0])
    B.L(tame.outputs[2], shift.inputs[1])
    norm = B.VM('SCALE', "veg normalise")
    B.L(sockout(shift, "Vector"), norm.inputs[0])
    sockin(norm, "Scale").default_value = 1.28
    out = B.mix("veg clump")
    B.L(S["Vegetation Clumping"], out.inputs[0])
    B.L(veg.outputs[2], out.inputs[6])
    B.L(sockout(norm, "Vector"), out.inputs[7])
    reconnect(tree, out.outputs[2], consumers)
    return "vegetation_clumping"


def craters(tree, B, S, P, FIELD):
    """Impact craters: a bowl with a raised rim, fed into the micro-relief.

    Deliberately modulates the existing micro-displacement chain rather than
    adding a second displacement path, because raising displaced micropolygon
    count is the one change known to have caused out-of-memory kills here.
    """
    micro = need(tree, "micro_bu")
    vor = B.voronoi('4D', 'F1', "crater cells")
    sockin(vor, "Randomness").default_value = 0.85
    B.L(P, sockin(vor, "Vector"))
    B.L(S["Crater Scale"], sockin(vor, "Scale"))
    d = sockout(vor, "Distance")
    bowl = B.MR(0.0, 0.42, -1.0, 0.0, "crater bowl", 'SMOOTHSTEP')
    B.L(d, bowl.inputs[0])
    rim = B.MR(0.30, 0.46, 0.0, 1.0, "crater rim in", 'SMOOTHSTEP')
    B.L(d, rim.inputs[0])
    rim2 = B.MR(0.46, 0.60, 1.0, 0.0, "crater rim out", 'SMOOTHSTEP')
    B.L(d, rim2.inputs[0])
    rimm = B.M('MULTIPLY', label="crater rim")
    B.L(rim.outputs["Result"], rimm.inputs[0])
    B.L(rim2.outputs["Result"], rimm.inputs[1])
    rw = B.M('MULTIPLY', y=0.55, label="rim height")
    B.L(rimm.outputs[0], rw.inputs[0])
    prof = B.M('ADD', label="crater profile")
    B.L(bowl.outputs["Result"], prof.inputs[0])
    B.L(rw.outputs[0], prof.inputs[1])
    land = B.M('SUBTRACT', x=1.0, label="crater land")
    B.L(sockout(FIELD, "sea_mask"), land.inputs[1])
    g1 = B.M('MULTIPLY', label="crater gate")
    B.L(prof.outputs[0], g1.inputs[0])
    B.L(land.outputs[0], g1.inputs[1])
    amt = B.M('MULTIPLY', label="crater amt")
    B.L(g1.outputs[0], amt.inputs[0])
    B.L(S["Crater Amount"], amt.inputs[1])
    hgt = B.M('MULTIPLY', y=6.0, label="crater height")
    B.L(amt.outputs[0], hgt.inputs[0])
    consumers = splice(tree, micro, 0)
    add = B.M('ADD', label="micro+craters")
    B.L(micro.outputs[0], add.inputs[0])
    B.L(hgt.outputs[0], add.inputs[1])
    reconnect(tree, add.outputs[0], consumers)
    return "craters"


def apply_all(tree):
    """Attach every detail feature. Returns what was added."""
    added = add_inputs(tree)
    gi = group_input(tree)
    S = gi.outputs
    P = sockout(need(tree, "P_UNIT"), "Vector")
    FIELD = need(tree, "FIELD")
    B = Builder(tree)
    done = []
    for fn, args in ((ocean_glint, (tree, B, S, P)),
                     (coastal_foam, (tree, B, S, P, FIELD)),
                     (rock_strata, (tree, B, S, P, FIELD)),
                     (ice_cracks, (tree, B, S, P, FIELD)),
                     (vegetation_clumping, (tree, B, S, P)),
                     (dunes, (tree, B, S, P, FIELD)),
                     (craters, (tree, B, S, P, FIELD)),
                     (lava_crust, (tree, B, S, P, FIELD))):
        done.append(fn(*args))
    return {"sockets_added": added, "features": done, "nodes": len(tree.nodes)}


def lava_crust(tree, B, S, P, FIELD):
    """Give the cold basalt between fissures some surface.

    On a volcanic world the sub-sea-level surface is a magma sea, but it is
    still shaded by the OCEAN branch, whose colour is near-black. The earlier
    fix for flat salmon oceans worked by making most of that area emit almost
    nothing so the hot cores survive AgX. Correct, but it left the cold crust
    with no relief, no tonal variation and a hard coastline edge, so it reads
    as a hole rather than as basalt.

    Gated on Lava Emission rather than a new socket: if there is no molten sea
    there is no crust to texture, and Cycles folds the whole branch away.
    """
    ocean = need(tree, "OCEAN")
    micro = need(tree, "micro_bu")

    plates = B.noise('4D', 'FBM', 4.0, "crust plates")
    sockin(plates, "Scale").default_value = 11.0
    sockin(plates, "Roughness").default_value = 0.55
    B.L(P, sockin(plates, "Vector"))
    grain = B.noise('4D', 'FBM', 7.0, "crust grain")
    sockin(grain, "Scale").default_value = 74.0
    B.L(P, sockin(grain, "Vector"))
    mixn = B.M('MULTIPLY', label="crust mix")
    B.L(sockout(plates, "Fac"), mixn.inputs[0])
    B.L(sockout(grain, "Fac"), mixn.inputs[1])
    # basalt is not uniformly black: chilled crust is paler than fresh flow
    tone = B.MR(0.18, 0.62, 0.55, 1.85, "crust tone")
    B.L(mixn.outputs[0], tone.inputs[0])

    gate = B.MR(0.0, 0.35, 0.0, 1.0, "crust gate")
    B.L(S["Lava Emission"], gate.inputs[0])
    amt = B.MR(0.0, 1.0, 1.0, 0.0, "crust blend")
    B.L(gate.outputs["Result"], amt.inputs[0])
    # 1 where there is no lava (leave the ocean alone), tone where there is
    fac = B.M('ADD', label="crust factor")
    B.L(amt.outputs["Result"], fac.inputs[0])
    scaled = B.M('MULTIPLY', label="crust scaled")
    B.L(tone.outputs["Result"], scaled.inputs[0])
    B.L(gate.outputs["Result"], scaled.inputs[1])
    B.L(scaled.outputs[0], fac.inputs[1])

    col_in = sockin(ocean, "Base Color")
    src = col_in.links[0].from_socket if col_in.links else None
    if src:
        mul = B.VM('MULTIPLY', "crust colour")
        B.L(src, mul.inputs[0])
        rgb = B.N("ShaderNodeCombineXYZ", "crust rgb")
        for i in range(3):
            B.L(fac.outputs[0], rgb.inputs[i])
        B.L(sockout(rgb, "Vector"), mul.inputs[1])
        for l in list(col_in.links):
            tree.links.remove(l)
        B.L(sockout(mul, "Vector"), col_in)

    # relief on the crust, below sea level only
    sea = B.M('MULTIPLY', label="crust sea")
    B.L(sockout(FIELD, "sea_mask"), sea.inputs[0])
    B.L(gate.outputs["Result"], sea.inputs[1])
    rel = B.M('SUBTRACT', y=0.5, label="crust relief")
    B.L(mixn.outputs[0], rel.inputs[0])
    relg = B.M('MULTIPLY', label="crust relief gate")
    B.L(rel.outputs[0], relg.inputs[0])
    B.L(sea.outputs[0], relg.inputs[1])
    relh = B.M('MULTIPLY', y=3.4, label="crust relief h")
    B.L(relg.outputs[0], relh.inputs[0])
    consumers = splice(tree, micro, 0)
    add = B.M('ADD', label="micro+crust")
    B.L(micro.outputs[0], add.inputs[0])
    B.L(relh.outputs[0], add.inputs[1])
    reconnect(tree, add.outputs[0], consumers)
    return "lava_crust"
