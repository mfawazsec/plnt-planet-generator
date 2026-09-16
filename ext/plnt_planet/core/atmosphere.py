"""Atmosphere: analytic surface scattering instead of a ray-marched volume.

Why
---
Measured on shot 02: hiding the atmosphere takes the frame from 93.6 s to
42.9 s. The volumetric shell is 54% of total render time -- more than the
surface shader, displacement and subdivision combined. Cycles ray-marches it
with volume_max_steps up to 1024 on a 1030-unit sphere, for every camera ray
and every shadow ray.

None of that marching is buying anything a closed form cannot. The shell is a
uniform spherical atmosphere: the optical path along a ray is a chord, and a
chord through a sphere has an exact expression. So instead of stepping through
the volume, evaluate the path length directly on the shell surface.

Geometry, in the shell's object space with the planet at the origin:

    P   shading point on the shell
    d   direction of travel (-Incoming, normalised)
    b   impact parameter, the ray's closest approach to the centre,
        b = |P x d|   because |P| sin(angle between P and d) is exactly that
    t   half-chord inside a sphere of radius R:  sqrt(R^2 - b^2)

If b < R_planet the ray is blocked by the planet, so only the near half of the
shell contributes. Otherwise the ray passes through the whole shell and we get
the full chord -- which is why the limb is bright: grazing rays travel much
further through air than rays aimed at the middle of the disc.

Cost: about forty math nodes, evaluated once per hit, with no stepping.
"""
import bpy
import math

try:
    from .nodeutil import sockin, sockout, new_socket
except ImportError:
    from nodeutil import sockin, sockout, new_socket

ATMO_IN = [
    ("Density", 'NodeSocketFloat', 0.008, 0.0, 1.0,
     "Thickness of the atmosphere. Drives the bright limb halo, which is the "
     "strongest single cue that the planet has air"),
    ("Atmo Colour", 'NodeSocketColor', (0.22, 0.44, 1.0, 1.0), None, None,
     "Colour of atmospheric scattering. Blue for nitrogen-oxygen, orange or "
     "green for exotic chemistry"),
    ("Anisotropy", 'NodeSocketFloat', 0.30, -0.95, 0.95,
     "Directional bias of scattering. Positive values scatter light forward, "
     "so the atmosphere flares when the planet is backlit"),
    ("Inner Radius", 'NodeSocketFloat', 1000.0, 1.0, 1e6,
     "Altitude at which the atmosphere begins; should sit at the surface"),
    ("Outer Radius", 'NodeSocketFloat', 1030.0, 1.0, 1e6,
     "Top of the atmosphere. The gap to Inner Radius is the shell depth"),
    ("Falloff", 'NodeSocketFloat', 3.2, 0.1, 20.0,
     "How quickly the air thins with altitude. Sharp falloff gives a tight "
     "bright rim, soft falloff a broad diffuse glow"),
    ("Pollution", 'NodeSocketFloat', 0.0, 0.0, 1.0,
     "Industrial haze: desaturates and warms the atmosphere"),
    ("Night Glow", 'NodeSocketFloat', 0.004, 0.0, 1.0,
     "Residual brightness on the unlit side, so the terminator does not end in "
     "a hard black edge"),
    ("Intensity", 'NodeSocketFloat', 1.0, 0.0, 20.0,
     "Overall brightness of the scattering"),
]


def _sunvec(g, loc=(-1900, -900)):
    """Sun direction, tracked via PLNT_SunDir.

    matrix_world is not a dependency-tracked driver path and silently freezes.
    PLNT_SunDir is parented to the sun at local (0,0,1), so its world location
    is the sun's Z axis, and TRANSFORMS/WORLD_SPACE drivers do track it.
    """
    n = g.nodes.new("ShaderNodeCombineXYZ")
    n.location = loc
    n.label = "SUNVEC"
    target = bpy.data.objects.get("PLNT_SunDir")
    if not target:
        n.inputs[2].default_value = 1.0
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


# See the long comment at `density cal` in _finish_surface. Measured, not
# guessed: 0.11 restores the optical depth the presets were authored against
# after two corrections to the chord model.
DENSITY_CALIBRATION = 0.11


def build_surface_atmo(name="PLNT_AtmoShader"):
    """Analytic atmosphere as a surface shader. Outputs BSDF, not Volume."""
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    I = g.interface
    for nm, st, dv, mn, mx, desc in ATMO_IN:
        new_socket(I, nm, 'INPUT', st, dv, mn, mx, desc)
    I.new_socket(name="BSDF", in_out='OUTPUT', socket_type='NodeSocketShader')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2400, 0)
    go = N("NodeGroupOutput"); go.location = (1600, 0)
    S = gi.outputs

    def M(op, x=None, y=None, loc=(0, 0), nm="", clamp=False):
        n = N("ShaderNodeMath"); n.operation = op; n.location = loc
        n.label = nm; n.use_clamp = clamp
        if x is not None:
            n.inputs[0].default_value = x
        if y is not None:
            n.inputs[1].default_value = y
        return n

    def VM(op, loc=(0, 0), nm=""):
        n = N("ShaderNodeVectorMath"); n.operation = op
        n.location = loc; n.label = nm
        return n

    def MR(loc, fmin, fmax, tmin, tmax, nm="", interp='LINEAR'):
        n = N("ShaderNodeMapRange"); n.location = loc; n.label = nm
        n.clamp = True; n.interpolation_type = interp
        for i, v in ((1, fmin), (2, fmax), (3, tmin), (4, tmax)):
            if v is not None:
                n.inputs[i].default_value = v
        return n

    # ---- ray geometry in the shell's object space --------------------------
    tc = N("ShaderNodeTexCoord"); tc.location = (-2400, -400)
    P = sockout(tc, "Object")
    geo = N("ShaderNodeNewGeometry"); geo.location = (-2400, -640)
    dvec = VM('SCALE', (-2200, -640), "d = -Incoming")
    L(sockout(geo, "Incoming"), dvec.inputs[0])
    sockin(dvec, "Scale").default_value = -1.0
    dn = VM('NORMALIZE', (-2020, -640))
    L(sockout(dvec, "Vector"), dn.inputs[0])

    # impact parameter b = |P x d|
    crs = VM('CROSS_PRODUCT', (-1840, -520), "P x d")
    L(P, crs.inputs[0]); L(sockout(dn, "Vector"), crs.inputs[1])
    blen = VM('LENGTH', (-1660, -520), "b")
    L(sockout(crs, "Vector"), blen.inputs[0])
    B = sockout(blen, "Value")

    # half-chords: sqrt(R^2 - b^2), clamped at zero outside the sphere
    def halfchord(radius_socket, loc, nm):
        r2 = M('POWER', y=2.0, loc=(loc[0], loc[1] + 80))
        L(radius_socket, r2.inputs[0])
        b2 = M('POWER', y=2.0, loc=(loc[0], loc[1] - 80))
        L(B, b2.inputs[0])
        dif = M('SUBTRACT', loc=(loc[0] + 170, loc[1]))
        L(r2.outputs[0], dif.inputs[0]); L(b2.outputs[0], dif.inputs[1])
        pos = M('MAXIMUM', y=0.0, loc=(loc[0] + 330, loc[1]))
        L(dif.outputs[0], pos.inputs[0])
        sq = M('SQRT', loc=(loc[0] + 490, loc[1]), nm=nm)
        L(pos.outputs[0], sq.inputs[0])
        return sq.outputs[0]

    t_out = halfchord(S["Outer Radius"], (-1500, 300), "t_outer")
    t_in = halfchord(S["Inner Radius"], (-1500, -60), "t_inner")

    # Path through air. Rays that miss the planet cross the whole shell twice
    # over: 2*(t_outer - t_inner). Rays that hit the planet are stopped by it,
    # so only the near portion counts.
    shell = M('SUBTRACT', loc=(-880, 300), nm="shell path")
    L(t_out, shell.inputs[0]); L(t_in, shell.inputs[1])
    full = M('MULTIPLY', y=2.0, loc=(-720, 300))
    L(shell.outputs[0], full.inputs[0])
    # a hard LESS_THAN here puts a visible ring at the planet edge, so the
    # blocked/unblocked transition is smoothstepped instead
    lim = MR((-720, 120), None, None, 1.0, 0.0, "planet edge", 'SMOOTHSTEP')
    L(B, lim.inputs[0])
    iw = M('MULTIPLY', y=0.985, loc=(-880, -40)); L(S["Inner Radius"], iw.inputs[0])
    L(iw.outputs[0], lim.inputs[1]); L(S["Inner Radius"], lim.inputs[2])
    near = M('SUBTRACT', loc=(-560, 160), nm="near path")
    L(t_out, near.inputs[0]); L(t_in, near.inputs[1])
    mixpath = N("ShaderNodeMix"); mixpath.location = (-380, 240)
    mixpath.data_type = 'FLOAT'; mixpath.label = "path"
    L(lim.outputs["Result"], mixpath.inputs[0])
    L(full.outputs[0], mixpath.inputs[2])
    L(near.outputs[0], mixpath.inputs[3])
    PATH = mixpath.outputs[0]
    return g, dict(N=N, L=L, M=M, VM=VM, MR=MR, S=S, go=go, P=P, B=B,
                   PATH=PATH, DN=sockout(dn, "Vector"), geo=geo,
                   LIM=lim.outputs["Result"])


def _finish_surface(g, C):
    """Extinction, sun illumination, phase function, and the output shader."""
    N, L, M, VM, MR, S = C["N"], C["L"], C["M"], C["VM"], C["MR"], C["S"]

    # ---- altitude falloff --------------------------------------------------
    # Air thins with height; weight the path by how low the ray's closest
    # approach sits inside the shell.
    span = M('SUBTRACT', loc=(-880, -220))
    L(S["Outer Radius"], span.inputs[0]); L(S["Inner Radius"], span.inputs[1])
    above = M('SUBTRACT', loc=(-880, -320))
    L(C["B"], above.inputs[0]); L(S["Inner Radius"], above.inputs[1])
    hnorm = M('DIVIDE', loc=(-720, -270), clamp=True)
    L(above.outputs[0], hnorm.inputs[0]); L(span.outputs[0], hnorm.inputs[1])
    inv = M('SUBTRACT', x=1.0, loc=(-560, -270), clamp=True)
    L(hnorm.outputs[0], inv.inputs[1])
    dens = M('POWER', loc=(-400, -270), nm="altitude density")
    L(inv.outputs[0], dens.inputs[0]); L(S["Falloff"], dens.inputs[1])

    # ---- optical depth and extinction --------------------------------------
    tau0 = M('MULTIPLY', loc=(-220, 120), nm="path*density")
    L(C["PATH"], tau0.inputs[0]); L(dens.outputs[0], tau0.inputs[1])
    # Density recalibration.
    #
    # Two corrections in v3 each roughly doubled how much atmosphere a ray
    # that hits the planet sees: illumination moved to the chord closest
    # approach (which is far more sunlit than the shell hit point was), and
    # the per-face alpha split stopped being applied to rays that cross the
    # shell only once. Both are right. Together they made the disc carry four
    # times the veil it used to, and every preset Density was tuned against
    # the old, wrong number.
    #
    # Measured on shot 05 with the planet replaced by flat grey: the
    # atmosphere contributed 0.153 in the delivered v2 scene and 0.600 after
    # the corrections; 0.25 brought that to 0.343 and 0.11 lands on 0.15,
    # because alpha saturates and the relationship is not linear in Density.
    # The constant below is what puts it back, so preset
    # Density values keep the magnitudes they were authored with.
    dcal = M('MULTIPLY', y=DENSITY_CALIBRATION, loc=(-220, 40), nm="density cal")
    L(S["Density"], dcal.inputs[0])
    tau = M('MULTIPLY', loc=(-60, 120), nm="tau")
    L(tau0.outputs[0], tau.inputs[0]); L(dcal.outputs[0], tau.inputs[1])
    negt = M('MULTIPLY', y=-1.0, loc=(100, 120))
    L(tau.outputs[0], negt.inputs[0])
    ext = M('EXPONENT', loc=(260, 120)); L(negt.outputs[0], ext.inputs[0])
    alpha = M('SUBTRACT', x=1.0, loc=(420, 120), clamp=True, nm="alpha")
    L(ext.outputs[0], alpha.inputs[1])

    # ---- sun illumination --------------------------------------------------
    sun = _sunvec(g, (-2400, -1000))
    sxf = g.nodes.new("ShaderNodeVectorTransform")
    sxf.location = (-2320, -1000); sxf.label = "SUNVEC_OBJ"
    sxf.vector_type = 'VECTOR'
    sxf.convert_from = 'WORLD'
    sxf.convert_to = 'OBJECT'
    L(sockout(sun, "Vector"), sxf.inputs[0])
    sn = VM('NORMALIZE', (-2200, -1000))
    L(sxf.outputs[0], sn.inputs[0])
    SUN = sockout(sn, "Vector")
    # Where along the ray to ask "is this air in sunlight?".
    #
    # Asking at the hit point P is what put a hard bright hairline along the
    # lit limb. Near the limb the shell is hit almost tangentially, so P sits
    # far around the curve from the air the ray actually travels through: two
    # adjacent pixels sample sun angles that differ by tens of degrees, and the
    # terminator smoothstep turns that into a one-pixel step in brightness.
    #
    # The closest-approach point C = P - (P.d)d is the deepest, densest point
    # of the chord and the honest place to evaluate illumination. It varies
    # smoothly across the limb, so the hairline has nothing to form from.
    pdd = VM('DOT_PRODUCT', (-2380, -1160), "P.d")
    L(C["P"], pdd.inputs[0]); L(C["DN"], pdd.inputs[1])
    step = VM('SCALE', (-2380, -1300), "(P.d)d")
    L(C["DN"], step.inputs[0])
    L(pdd.outputs["Value"], sockin(step, "Scale"))
    capprox = VM('SUBTRACT', (-2280, -1230), "closest approach")
    L(C["P"], capprox.inputs[0]); L(sockout(step, "Vector"), capprox.inputs[1])
    pn = VM('NORMALIZE', (-2200, -1160))
    L(sockout(capprox, "Vector"), pn.inputs[0])
    lam = VM('DOT_PRODUCT', (-2020, -1080), "sun dot")
    L(sockout(pn, "Vector"), lam.inputs[0]); L(SUN, lam.inputs[1])
    # soft terminator: the day/night edge on air is gradual, not a hard line.
    # Narrower than the original -0.35..0.30 now that the sun angle is sampled
    # at a point that moves smoothly -- the wide ramp was compensating for a
    # discontinuity that is no longer there, and it washed the terminator out.
    lit = MR((-1840, -1080), -0.20, 0.25, 0.0, 1.0, "lit", 'SMOOTHSTEP')
    L(lam.outputs["Value"], lit.inputs[0])
    night = M('MULTIPLY', loc=(-1660, -1200), nm="night floor")
    L(S["Night Glow"], night.inputs[0])
    night.inputs[1].default_value = 1.0
    illum = M('MAXIMUM', loc=(-1500, -1140), nm="illumination")
    L(lit.outputs["Result"], illum.inputs[0]); L(night.outputs[0], illum.inputs[1])

    # ---- Henyey-Greenstein phase -------------------------------------------
    cosang = VM('DOT_PRODUCT', (-2020, -1320), "phase cos")
    L(C["DN"], cosang.inputs[0]); L(SUN, cosang.inputs[1])
    gg = M('MULTIPLY', loc=(-1840, -1400))
    L(S["Anisotropy"], gg.inputs[0]); L(S["Anisotropy"], gg.inputs[1])
    num = M('SUBTRACT', x=1.0, loc=(-1680, -1400)); L(gg.outputs[0], num.inputs[1])
    d1 = M('ADD', x=1.0, loc=(-1680, -1500)); L(gg.outputs[0], d1.inputs[1])
    twog = M('MULTIPLY', y=2.0, loc=(-1680, -1600)); L(S["Anisotropy"], twog.inputs[0])
    tgc = M('MULTIPLY', loc=(-1520, -1600))
    L(twog.outputs[0], tgc.inputs[0]); L(cosang.outputs["Value"], tgc.inputs[1])
    den0 = M('SUBTRACT', loc=(-1360, -1500))
    L(d1.outputs[0], den0.inputs[0]); L(tgc.outputs[0], den0.inputs[1])
    denc = M('MAXIMUM', y=0.002, loc=(-1200, -1500)); L(den0.outputs[0], denc.inputs[0])
    den = M('POWER', y=1.5, loc=(-1040, -1500)); L(denc.outputs[0], den.inputs[0])
    hg = M('DIVIDE', loc=(-880, -1440)); L(num.outputs[0], hg.inputs[0])
    L(den.outputs[0], hg.inputs[1])
    hgc = M('MINIMUM', y=6.0, loc=(-720, -1440), nm="phase")
    L(hg.outputs[0], hgc.inputs[0])

    # ---- colour ------------------------------------------------------------
    poll = N("ShaderNodeMix"); poll.data_type = 'RGBA'
    poll.location = (-720, -700); poll.label = "pollution"
    L(S["Pollution"], poll.inputs[0])
    L(S["Atmo Colour"], poll.inputs[6])
    poll.inputs[7].default_value = (0.52, 0.44, 0.30, 1.0)

    gain = M('MULTIPLY', loc=(-380, -1100), nm="gain")
    L(illum.outputs[0], gain.inputs[0]); L(hgc.outputs[0], gain.inputs[1])
    gain2 = M('MULTIPLY', loc=(-220, -1100))
    L(gain.outputs[0], gain2.inputs[0]); L(S["Intensity"], gain2.inputs[1])
    col = VM('SCALE', (-40, -800), "scatter colour")
    L(poll.outputs[2], col.inputs[0])
    L(gain2.outputs[0], sockin(col, "Scale"))

    em = N("ShaderNodeEmission"); em.location = (700, -80)
    L(sockout(col, "Vector"), sockin(em, "Color"))
    sockin(em, "Strength").default_value = 1.0
    tp = N("ShaderNodeBsdfTransparent"); tp.location = (700, 160)

    # A camera ray crosses the shell twice, so the full-chord alpha has to be
    # split between the two hits. Gating on Backfacing looked right but depends
    # on the generated normals pointing outward -- and when they do not, the
    # near face is zeroed and the atmosphere disappears entirely, which is
    # exactly what happened on the first render.
    #
    # Splitting as a_face = 1 - sqrt(1 - a_total) is orientation-independent
    # and composes back exactly: (1 - a_face)^2 = 1 - a_total.
    inv_a = M('SUBTRACT', x=1.0, loc=(700, 300), nm="1-alpha")
    L(alpha.outputs[0], inv_a.inputs[1])
    root = M('SQRT', loc=(860, 300)); L(inv_a.outputs[0], root.inputs[0])
    a2 = M('SUBTRACT', x=1.0, loc=(1020, 300), clamp=True, nm="alpha per face")
    L(root.outputs[0], a2.inputs[1])

    # ...but only for rays that MISS the planet. A ray that hits the planet is
    # stopped by it and crosses the shell once, so splitting its alpha halves
    # the atmosphere exactly over the disc and leaves a brighter rim outside
    # it: the second of the two lines visible along the horizon. `planet edge`
    # is 1 when the planet blocks the ray, so it selects the unsplit alpha.
    afac = N("ShaderNodeMix"); afac.location = (1180, 300)
    afac.data_type = 'FLOAT'; afac.label = "alpha faces"
    L(C["LIM"], afac.inputs[0])
    L(a2.outputs[0], afac.inputs[2])
    L(alpha.outputs[0], afac.inputs[3])

    mix = N("ShaderNodeMixShader"); mix.location = (1340, 60); mix.label = "atmo"
    L(afac.outputs[0], mix.inputs[0])
    L(sockout(tp, "BSDF"), mix.inputs[1])
    L(sockout(em, "Emission"), mix.inputs[2])
    L(mix.outputs[0], C["go"].inputs["BSDF"])
    return g


def build(name="PLNT_AtmoShader"):
    g, C = build_surface_atmo(name)
    return _finish_surface(g, C)


def make_material(matname="PLNT_Atmosphere", groupname="PLNT_AtmoShader",
                  radius=1000.0):
    """Wire the analytic shader as a SURFACE, replacing the volume output."""
    mat = bpy.data.materials.get(matname) or bpy.data.materials.new(matname)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = bpy.data.node_groups[groupname]
    gn.name = "PLNT_CTL"; gn.label = "PLNT_CTL"; gn.location = (0, 0)
    gn.inputs["Inner Radius"].default_value = radius
    gn.inputs["Outer Radius"].default_value = radius * 1.03
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (320, 0)
    nt.links.new(gn.outputs["BSDF"], out.inputs["Surface"])
    # nothing is connected to Volume any more: that is the whole point.
    #
    # The scattering is an Emission shader on a 1030-unit sphere, which would
    # otherwise enter the light tree as an enormous mesh light and cost more
    # than the volume it replaced. This is the case emission_sampling='NONE'
    # exists for: the atmosphere is something you look at, not something that
    # lights the scene. (It is the wrong setting for the lava and city lights,
    # which ARE the light source in shots 05, 07 and 08.)
    try:
        mat.cycles.emission_sampling = 'NONE'
    except Exception:
        pass
    return mat
