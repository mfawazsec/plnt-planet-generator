"""PLNT_SurfaceShader: per-pixel surface shading.

Evaluates PLNT_TerrainFieldSH directly in the shader rather than reading
interpolated vertex attributes, so coastlines/rivers/ice resolve at pixel
resolution instead of being quantised to the 40k-vert base mesh.
"""
import bpy


def _anim_mod():
    """core.anim, however this file happens to have been loaded.

    The flat modules are executed by path through spec_from_file_location, so
    there is no package to import from and core/ is not on sys.path. Inside the
    built extension they are real submodules and core is a sibling package.
    Both are tried before falling back to loading the file directly.
    """
    try:
        from .core import anim as a          # packaged extension
        return a
    except ImportError:
        pass
    try:
        from core import anim as a           # project directory on sys.path
        return a
    except ImportError:
        pass
    import importlib.util
    import os
    import sys
    if "plnt_anim" in sys.modules:
        return sys.modules["plnt_anim"]
    p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "core", "anim.py")
    s = importlib.util.spec_from_file_location("plnt_anim", p)
    a = importlib.util.module_from_spec(s)
    sys.modules["plnt_anim"] = a
    s.loader.exec_module(a)
    return a

import os
import sys
import importlib.util as _ilu, sys as _sys, os as _os

_D = _os.path.dirname(_os.path.abspath(__file__))


def _tech():
    sp = _ilu.spec_from_file_location("plnt_tech", _os.path.join(_D, "plnt_tech.py"))
    m = _ilu.module_from_spec(sp); _sys.modules["plnt_tech"] = m; sp.loader.exec_module(m)
    return m

FIELD_PARAMS = ["Seed", "Continent Scale", "Continent Coverage", "Mountain Sharpness",
                "Erosion Amount", "Tectonic Belt Width", "Warp Strength", "Sea Level",
                "Polar Cap Extent"]
# params mirrored from the GN modifier onto the material (Relief Strength drives
# the residual-displacement term, so it must match the geometry exactly)
SYNC_PARAMS = FIELD_PARAMS + ["Relief Strength"]

LOOK_IN = [
    ("Vegetation Hue", 'NodeSocketColor', (0.078, 0.135, 0.042, 1), None, None),
    ("Rock Hue", 'NodeSocketColor', (0.190, 0.150, 0.115, 1), None, None),
    ("Sand Hue", 'NodeSocketColor', (0.455, 0.320, 0.168, 1), None, None),
    ("Ice Brightness", 'NodeSocketFloat', 0.80, 0.0, 2.0),
    ("Ocean Shallow", 'NodeSocketColor', (0.045, 0.215, 0.275, 1), None, None),
    ("Ocean Deep", 'NodeSocketColor', (0.0035, 0.014, 0.040, 1), None, None),
    ("Shelf Boost", 'NodeSocketFloat', 1.10, 0.0, 4.0),
    ("Slope Rock Threshold", 'NodeSocketFloat', 0.26, 0.0, 1.0),
    ("Vegetation Amount", 'NodeSocketFloat', 1.0, 0.0, 2.0),
    ("Ice Temp Threshold", 'NodeSocketFloat', 0.20, 0.0, 1.0),
    ("River Tint", 'NodeSocketFloat', 0.30, 0.0, 2.0),
    ("Patchiness", 'NodeSocketFloat', 0.35, 0.0, 1.0),
    ("Lava Emission", 'NodeSocketFloat', 0.0, 0.0, 40.0),
    ("Micro Disp Height", 'NodeSocketFloat', 2.2, 0.0, 200.0),
    ("Micro Disp Scale", 'NodeSocketFloat', 145.0, 1.0, 6000.0),
]

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


def build_surface(name="PLNT_SurfaceShader", sun_dir_obj=None, pos_attr=None):
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'ShaderNodeTree')
    I = g.interface

    def sk(n, io, st, dv=None, mn=None, mx=None):
        s = I.new_socket(name=n, in_out=io, socket_type=st)
        if dv is not None: s.default_value = dv
        if mn is not None: s.min_value = mn
        if mx is not None: s.max_value = mx
        return s

    for p in FIELD_PARAMS:
        dv, mn, mx = FIELD_DEFAULTS[p]
        sk(p, 'INPUT', 'NodeSocketFloat', dv, mn, mx)
    sk("Relief Strength", 'INPUT', 'NodeSocketFloat', 70.0, 0.0, 400.0)
    for n, st, dv, mn, mx in LOOK_IN:
        sk(n, 'INPUT', st, dv, mn, mx)
    TECH = _tech()
    for n, dv, mn, mx in TECH.TECH_IN:
        sk(n, 'INPUT', 'NodeSocketFloat', dv, mn, mx)
    sk("BSDF", 'OUTPUT', 'NodeSocketShader')
    sk("Displacement", 'OUTPUT', 'NodeSocketVector')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2600, 0)
    go = N("NodeGroupOutput"); go.location = (900, 0)

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

    def MIXF(loc, a, b, nm=""):
        n = N("ShaderNodeMix"); n.data_type = 'FLOAT'; n.location = loc
        n.label = nm; n.clamp_factor = True
        n.inputs[2].default_value = a; n.inputs[3].default_value = b
        return n

    # --- position: object space, normalised => identical domain to the geometry field
    nrm = N("ShaderNodeVectorMath"); nrm.operation = 'NORMALIZE'
    nrm.location = (-2400, -700); nrm.label = "P_UNIT"
    if pos_attr:
        # ground patch: sample position supplied by the rig as an attribute
        pa = N("ShaderNodeAttribute"); pa.location = (-2600, -700)
        pa.attribute_type = 'GEOMETRY'; pa.attribute_name = pos_attr
        L(pa.outputs["Vector"], nrm.inputs[0])
    else:
        tc = N("ShaderNodeTexCoord"); tc.location = (-2600, -700)
        L(tc.outputs["Object"], nrm.inputs[0])

    F = N("ShaderNodeGroup"); F.node_tree = bpy.data.node_groups["PLNT_TerrainFieldSH"]
    F.location = (-2150, -200); F.label = "FIELD"
    L(nrm.outputs["Vector"], F.inputs["Position"])
    for p in FIELD_PARAMS:
        L(gi.outputs[p], F.inputs[p])

    o = F.outputs

    # --- vegetation factor
    vh = MR((-1850, 700), 0.17, 0.52, 0.0, 1.0); L(o["humidity"], vh.inputs[0])
    vt = MR((-1850, 540), 0.18, 0.42, 0.0, 1.0); L(o["temperature"], vt.inputs[0])
    v1 = M('MULTIPLY', loc=(-1650, 620))
    L(vh.outputs["Result"], v1.inputs[0]); L(vt.outputs["Result"], v1.inputs[1])
    vg = M('MULTIPLY', loc=(-1470, 620), nm="veg", clamp=True)
    L(v1.outputs["Value"], vg.inputs[0]); L(gi.outputs["Vegetation Amount"], vg.inputs[1])

    # --- rock factor from slope
    rhi = M('ADD', y=0.22, loc=(-1850, 380)); L(gi.outputs["Slope Rock Threshold"], rhi.inputs[0])
    rk = MR((-1650, 380), None, None, 0.0, 1.0, "rock")
    L(o["slope"], rk.inputs[0])
    L(gi.outputs["Slope Rock Threshold"], rk.inputs[1])
    L(rhi.outputs["Value"], rk.inputs[2])

    # --- ice factor
    ilo = M('SUBTRACT', y=0.09, loc=(-1850, 200)); L(gi.outputs["Ice Temp Threshold"], ilo.inputs[0])
    ic = MR((-1650, 200), None, None, 0.0, 1.0, "ice")
    L(o["temperature"], ic.inputs[0])
    L(gi.outputs["Ice Temp Threshold"], ic.inputs[1])
    L(ilo.outputs["Value"], ic.inputs[2])
    icc = MIXC((-1650, 20), "icecol")
    icc.inputs[0].default_value = 1.0
    icc.inputs[6].default_value = (0, 0, 0, 1)
    icc.inputs[7].default_value = (0.90, 0.94, 1.0, 1)
    isc = N("ShaderNodeVectorMath"); isc.operation = 'SCALE'; isc.location = (-1450, 20)
    L(icc.outputs[2], isc.inputs[0]); L(gi.outputs["Ice Brightness"], isc.inputs["Scale"])

    # --- patchiness: large-scale albedo variation so land is not flat
    pn = N("ShaderNodeTexNoise"); pn.location = (-1850, -420); pn.label = "patch"
    pn.noise_dimensions = '4D'; pn.noise_type = 'FBM'
    pn.inputs["Detail"].default_value = 6.0
    pn.inputs["Scale"].default_value = 7.5
    L(nrm.outputs["Vector"], pn.inputs["Vector"])
    pw = M('MULTIPLY', y=2.9, loc=(-2050, -520)); L(gi.outputs["Seed"], pw.inputs[0])
    pwa = M('ADD', y=87.2, loc=(-1900, -560)); L(pw.outputs["Value"], pwa.inputs[0])
    L(pwa.outputs["Value"], pn.inputs["W"])
    pctr = M('SUBTRACT', y=0.5, loc=(-1650, -420)); L(pn.outputs["Factor"], pctr.inputs[0])
    pamt = M('MULTIPLY', loc=(-1470, -420))
    L(pctr.outputs["Value"], pamt.inputs[0]); L(gi.outputs["Patchiness"], pamt.inputs[1])
    pfac = M('ADD', x=1.0, loc=(-1290, -420), nm="patchmul"); L(pamt.outputs["Value"], pfac.inputs[1])

    # --- ALBEDO chain
    m1 = MIXC((-1250, 760), "sand>veg")
    L(vg.outputs["Value"], m1.inputs[0])
    L(gi.outputs["Sand Hue"], m1.inputs[6]); L(gi.outputs["Vegetation Hue"], m1.inputs[7])
    # rock tint variation: strata-like banding so cliffs are not flat grey
    rkn = N("ShaderNodeTexNoise"); rkn.location = (-1450, 940); rkn.label = "rockvar"
    rkn.noise_dimensions = '4D'; rkn.noise_type = 'FBM'
    rkn.inputs["Scale"].default_value = 46.0
    rkn.inputs["Detail"].default_value = 8.0
    L(nrm.outputs["Vector"], rkn.inputs["Vector"])
    rkw = M('MULTIPLY', y=1.93, loc=(-1650, 940)); L(gi.outputs["Seed"], rkw.inputs[0])
    L(rkw.outputs["Value"], rkn.inputs["W"])
    rkv = MIXC((-1250, 940), "rockcol")
    L(rkn.outputs["Factor"], rkv.inputs[0])
    L(gi.outputs["Rock Hue"], rkv.inputs[6])
    rkv.inputs[7].default_value = (0.235, 0.205, 0.180, 1)
    m2 = MIXC((-1050, 760), ">rock")
    L(rk.outputs["Result"], m2.inputs[0])
    L(m1.outputs[2], m2.inputs[6]); L(rkv.outputs[2], m2.inputs[7])
    mp = N("ShaderNodeVectorMath"); mp.operation = 'SCALE'; mp.location = (-870, 760)
    L(m2.outputs[2], mp.inputs[0]); L(pfac.outputs["Value"], mp.inputs["Scale"])
    m3 = MIXC((-690, 760), ">ice")
    L(ic.outputs["Result"], m3.inputs[0])
    L(mp.outputs["Vector"], m3.inputs[6]); L(isc.outputs["Vector"], m3.inputs[7])
    rvf = M('MULTIPLY', loc=(-1050, 560), nm="rivfac", clamp=True)
    L(o["river_mask"], rvf.inputs[0]); L(gi.outputs["River Tint"], rvf.inputs[1])
    m4 = MIXC((-490, 760), ">river")
    L(rvf.outputs["Value"], m4.inputs[0]); L(m3.outputs[2], m4.inputs[6])
    m4.inputs[7].default_value = (0.018, 0.068, 0.098, 1)

    # --- ROUGHNESS chain
    r1 = MIXF((-1250, 340), 0.72, 0.62, "rgh veg"); L(vg.outputs["Value"], r1.inputs[0])
    r2 = MIXF((-1050, 340), 0.0, 0.90, "rgh rock")
    L(rk.outputs["Result"], r2.inputs[0]); L(r1.outputs[0], r2.inputs[2])
    r3 = MIXF((-850, 340), 0.0, 0.18, "rgh ice")
    L(ic.outputs["Result"], r3.inputs[0]); L(r2.outputs[0], r3.inputs[2])
    r4 = MIXF((-650, 340), 0.0, 0.16, "rgh riv")
    L(rvf.outputs["Value"], r4.inputs[0]); L(r3.outputs[0], r4.inputs[2])

    # ---- technology layer (reuses field node F; no second field evaluation)
    if sun_dir_obj is None:
        sun_dir_obj = bpy.data.objects.get("PLNT_SunDir")
    alb_t, rgh_t, emis = TECH.add_tech_layer(
        g, F, gi, m4.outputs[2], r4.outputs[0], nrm.outputs["Vector"], sun_dir_obj)

    land = N("ShaderNodeBsdfPrincipled"); land.location = (-200, 760); land.label = "LAND"
    L(alb_t, land.inputs["Base Color"])
    L(rgh_t, land.inputs["Roughness"])
    land.inputs["IOR"].default_value = 1.45

    # --- OCEAN
    dt = MR((-1250, -120), 0.0, 0.022, 0.0, 1.0, "depth"); L(o["ocean_depth"], dt.inputs[0])
    # Shelf Boost multiplies the shallow-water colour, and Foam adds white on
    # top of it. Nothing bounded the sum, so a preset with Shelf Boost 2.4 and
    # Foam 0.85 pushed the shallows past 1.0 before AgX ever saw them, and the
    # continental shelf came back as a flat glowing halo around every coast.
    # Cap the boost at 1.2 so the shelf stays a shelf.
    shc = N("ShaderNodeMath"); shc.operation = 'MINIMUM'; shc.location = (-1430, 40)
    shc.label = "shelf cap"; shc.inputs[1].default_value = 1.2
    L(gi.outputs["Shelf Boost"], shc.inputs[0])
    sh = N("ShaderNodeVectorMath"); sh.operation = 'SCALE'; sh.location = (-1250, 40)
    L(gi.outputs["Ocean Shallow"], sh.inputs[0]); L(shc.outputs[0], sh.inputs["Scale"])
    oc = MIXC((-1000, -80), "oceancol")
    L(dt.outputs["Result"], oc.inputs[0])
    L(sh.outputs["Vector"], oc.inputs[6]); L(gi.outputs["Ocean Deep"], oc.inputs[7])
    ocean = N("ShaderNodeBsdfPrincipled"); ocean.location = (-200, -80); ocean.label = "OCEAN"
    L(oc.outputs[2], ocean.inputs["Base Color"])
    ocean.inputs["Roughness"].default_value = 0.08
    ocean.inputs["IOR"].default_value = 1.33

    mx = N("ShaderNodeMixShader"); mx.location = (400, 300); mx.label = "LAND/OCEAN"
    L(o["sea_mask"], mx.inputs[0])
    L(land.outputs["BSDF"], mx.inputs[1]); L(ocean.outputs["BSDF"], mx.inputs[2])
    # emission added over the surface so grid arcs also read on the unlit hemisphere
    # Molten sea emission: dark basalt crust broken by glowing cracks.
    # A uniform bright fill saturates to flat salmon under AgX, so the area is
    # kept mostly dark and the energy concentrated into thin hot fissures, which
    # is what survives tonemapping as actual lava.
    lw = M('MULTIPLY', y=4.61, loc=(-560, -560)); L(gi.outputs["Seed"], lw.inputs[0])
    lwa0 = M('ADD', y=173.3, loc=(-400, -560)); L(lw.outputs["Value"], lwa0.inputs[0])
    # Molten crust is not a still photograph. Walking the 4D seed of the lava
    # noises slowly re-forms the plate pattern: 0.05 per world hour gives a
    # crust that visibly reorganises over a day rather than over a frame.
    ltime = _anim_mod().shader_time(g, (-760, -760))
    ldrift = M('MULTIPLY', y=0.05, loc=(-580, -760), nm="crust drift")
    L(ltime, ldrift.inputs[0])
    lwa = M('ADD', loc=(-240, -560), nm="lava W")
    L(lwa0.outputs["Value"], lwa.inputs[0]); L(ldrift.outputs["Value"], lwa.inputs[1])
    # warp the crack field so fissures wander instead of reading as cells
    lwn = N("ShaderNodeTexNoise"); lwn.location = (-560, -400); lwn.label = "lava warp"
    lwn.noise_dimensions = '4D'; lwn.noise_type = 'FBM'
    lwn.inputs["Scale"].default_value = 5.2
    lwn.inputs["Detail"].default_value = 6.0
    L(nrm.outputs["Vector"], lwn.inputs["Vector"]); L(lwa.outputs["Value"], lwn.inputs["W"])
    lws = N("ShaderNodeVectorMath"); lws.operation = 'SUBTRACT'; lws.location = (-400, -400)
    L(lwn.outputs["Color"], lws.inputs[0]); lws.inputs[1].default_value = (0.5, 0.5, 0.5)
    lwsc = N("ShaderNodeVectorMath"); lwsc.operation = 'SCALE'; lwsc.location = (-240, -400)
    L(lws.outputs["Vector"], lwsc.inputs[0]); lwsc.inputs["Scale"].default_value = 1.15
    lwp = N("ShaderNodeVectorMath"); lwp.operation = 'ADD'; lwp.location = (-80, -400)
    L(nrm.outputs["Vector"], lwp.inputs[0]); L(lwsc.outputs["Vector"], lwp.inputs[1])

    lvn = N("ShaderNodeTexVoronoi"); lvn.location = (100, -400); lvn.label = "lava cracks"
    lvn.voronoi_dimensions = '4D'; lvn.feature = 'DISTANCE_TO_EDGE'
    lvn.inputs["Scale"].default_value = 9.5
    lvn.inputs["Randomness"].default_value = 1.0
    L(lwp.outputs["Vector"], lvn.inputs["Vector"]); L(lwa.outputs["Value"], lvn.inputs["W"])
    crack = MR((280, -400), 0.0, 0.155, 1.0, 0.0, "crack")
    L(lvn.outputs["Distance"], crack.inputs[0])
    csh = M('POWER', y=1.8, loc=(460, -400)); L(crack.outputs["Result"], csh.inputs[0])

    # regional heat: some basins molten, others crusted over
    hpn = N("ShaderNodeTexNoise"); hpn.location = (100, -600); hpn.label = "lava heat"
    hpn.noise_dimensions = '4D'; hpn.noise_type = 'FBM'
    hpn.inputs["Scale"].default_value = 5.5
    hpn.inputs["Detail"].default_value = 5.0
    L(nrm.outputs["Vector"], hpn.inputs["Vector"]); L(lwa.outputs["Value"], hpn.inputs["W"])
    hpr = MR((280, -600), 0.30, 0.70, 0.18, 1.0, "heatregion")
    L(hpn.outputs["Factor"], hpr.inputs[0])
    heat = M('MULTIPLY', loc=(640, -400), nm="heat")
    L(csh.outputs["Value"], heat.inputs[0]); L(hpr.outputs["Result"], heat.inputs[1])
    # deeper basins run hotter
    dboost = MR((460, -600), 0.0, 1.0, 0.75, 1.35, "depthheat")
    L(dt.outputs["Result"], dboost.inputs[0])
    heat2 = M('MULTIPLY', loc=(820, -400), nm="heat2", clamp=True)
    L(heat.outputs["Value"], heat2.inputs[0]); L(dboost.outputs["Result"], heat2.inputs[1])

    # crust -> deep red -> orange -> white-hot core
    lramp = N("ShaderNodeValToRGB"); lramp.location = (1000, -400); lramp.label = "lava ramp"
    L(heat2.outputs["Value"], lramp.inputs["Fac"])
    _cr = lramp.color_ramp
    _cr.elements[0].position = 0.0
    _cr.elements[0].color = (0.030, 0.006, 0.002, 1)
    _cr.elements[1].position = 1.0
    _cr.elements[1].color = (1.0, 0.90, 0.62, 1)
    for _p, _c in ((0.34, (0.62, 0.055, 0.008, 1)), (0.62, (1.0, 0.30, 0.025, 1))):
        _e = _cr.elements.new(_p); _e.color = _c

    # square the intensity so crust emits almost nothing and cores stay hot
    lint = M('POWER', y=2.1, loc=(1000, -600))
    L(heat2.outputs["Value"], lint.inputs[0])
    lavm = M('MULTIPLY', loc=(1180, -600), nm="lavamask")
    L(o["sea_mask"], lavm.inputs[0]); L(gi.outputs["Lava Emission"], lavm.inputs[1])
    lavi = M('MULTIPLY', loc=(1360, -600))
    L(lint.outputs["Value"], lavi.inputs[0]); L(lavm.outputs["Value"], lavi.inputs[1])
    lavs = N("ShaderNodeVectorMath"); lavs.operation = 'SCALE'; lavs.location = (1360, -400)
    L(lramp.outputs["Color"], lavs.inputs[0]); L(lavi.outputs["Value"], lavs.inputs["Scale"])
    emsum = N("ShaderNodeVectorMath"); emsum.operation = 'ADD'; emsum.location = (320, -140)
    L(emis, emsum.inputs[0]); L(lavs.outputs["Vector"], emsum.inputs[1])

    em = N("ShaderNodeEmission"); em.location = (400, 60); em.label = "TECH_EMIT"
    L(emsum.outputs["Vector"], em.inputs["Color"])
    em.inputs["Strength"].default_value = 1.0
    add = N("ShaderNodeAddShader"); add.location = (640, 200); add.label = "SURF+TECH"
    L(mx.outputs["Shader"], add.inputs[0]); L(em.outputs["Emission"], add.inputs[1])
    L(add.outputs["Shader"], go.inputs["BSDF"])

    # --- micro-displacement
    dn = N("ShaderNodeTexNoise"); dn.location = (-1250, -760); dn.label = "microdisp"
    dn.noise_dimensions = '4D'; dn.noise_type = 'FBM'
    dn.inputs["Detail"].default_value = 12.0
    dn.inputs["Roughness"].default_value = 0.48
    L(nrm.outputs["Vector"], dn.inputs["Vector"])
    L(gi.outputs["Micro Disp Scale"], dn.inputs["Scale"])
    dw = M('MULTIPLY', y=7.31, loc=(-1500, -900)); L(gi.outputs["Seed"], dw.inputs[0])
    dwa = M('ADD', y=311.7, loc=(-1350, -940)); L(dw.outputs["Value"], dwa.inputs[0])
    L(dwa.outputs["Value"], dn.inputs["W"])
    # second, finer octave for close-range crispness
    dn2 = N("ShaderNodeTexNoise"); dn2.location = (-1250, -1060); dn2.label = "microdisp2"
    dn2.noise_dimensions = '4D'; dn2.noise_type = 'FBM'
    dn2.inputs["Detail"].default_value = 8.0
    dn2.inputs["Roughness"].default_value = 0.5
    L(nrm.outputs["Vector"], dn2.inputs["Vector"])
    ds2 = M('MULTIPLY', y=5.5, loc=(-1430, -1140))
    L(gi.outputs["Micro Disp Scale"], ds2.inputs[0]); L(ds2.outputs["Value"], dn2.inputs["Scale"])
    L(dwa.outputs["Value"], dn2.inputs["W"])
    o1 = M('SUBTRACT', y=0.5, loc=(-1050, -760)); L(dn.outputs["Factor"], o1.inputs[0])
    o2 = M('SUBTRACT', y=0.5, loc=(-1050, -1060)); L(dn2.outputs["Factor"], o2.inputs[0])
    o2s = M('MULTIPLY', y=0.22, loc=(-880, -1060)); L(o2.outputs["Value"], o2s.inputs[0])
    osum = M('ADD', loc=(-880, -860))
    L(o1.outputs["Value"], osum.inputs[0]); L(o2s.outputs["Value"], osum.inputs[1])
    # rugged terrain gets more relief than plains; ocean stays a flat plane
    rough_amp = MR((-1050, -1240), 0.04, 0.42, 0.55, 1.15, "reliefmod")
    L(o["slope"], rough_amp.inputs[0])
    lm = MR((-1000, -1400), 0.0035, 0.0, 0.0, 1.0, "shorefade")
    L(o["ocean_depth"], lm.inputs[0])
    dh0 = M('MULTIPLY', loc=(-700, -1240))
    L(gi.outputs["Micro Disp Height"], dh0.inputs[0]); L(rough_amp.outputs["Result"], dh0.inputs[1])
    dh = M('MULTIPLY', loc=(-700, -1400), nm="dispheight")
    L(dh0.outputs["Value"], dh.inputs[0]); L(lm.outputs["Result"], dh.inputs[1])
    # micro relief converted to BU
    micro_bu = M('MULTIPLY', loc=(-500, -1060), nm="micro_bu")
    L(osum.outputs["Value"], micro_bu.inputs[0]); L(dh.outputs["Value"], micro_bu.inputs[1])

    # RESIDUAL macro displacement: the field's true elevation minus the value the
    # base mesh could carry. Recovers full-resolution terrain at dice resolution,
    # which is what makes close-ups hold up.
    ea = N("ShaderNodeAttribute"); ea.location = (-1050, -1560); ea.label = "A_elevation"
    ea.attribute_type = 'GEOMETRY'; ea.attribute_name = "elevation"
    resid = M('SUBTRACT', loc=(-820, -1560), nm="residual")
    L(o["elevation"], resid.inputs[0]); L(ea.outputs["Fac"], resid.inputs[1])
    resid_bu = M('MULTIPLY', loc=(-640, -1560), nm="residual_bu")
    L(resid.outputs["Value"], resid_bu.inputs[0]); L(gi.outputs["Relief Strength"], resid_bu.inputs[1])

    total = M('ADD', loc=(-380, -1200), nm="total_disp")
    L(micro_bu.outputs["Value"], total.inputs[0]); L(resid_bu.outputs["Value"], total.inputs[1])

    disp = N("ShaderNodeDisplacement"); disp.location = (-180, -900); disp.label = "DISP"
    disp.space = 'OBJECT'
    L(total.outputs["Value"], disp.inputs["Height"])
    disp.inputs["Midlevel"].default_value = 0.0
    disp.inputs["Scale"].default_value = 1.0
    L(disp.outputs["Displacement"], go.inputs["Displacement"])

    # Extra surface detail lives in its own module so this function stays
    # readable. It attaches by node label, and every feature is gated by a new
    # group input defaulting to 0. Cycles constant-folds a constant-zero
    # branch away entirely, so unused features cost nothing at render time.
    try:
        from core import surface_detail
    except ImportError:
        import importlib.util as _ilu
        _p = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                          "core", "surface_detail.py")
        _sp = _ilu.spec_from_file_location("surface_detail", _p)
        surface_detail = _ilu.module_from_spec(_sp)
        sys.modules["surface_detail"] = surface_detail
        _sp.loader.exec_module(surface_detail)
    surface_detail.apply_all(g)
    return g


def wire_material(matname="PLNT_Surface", groupname="PLNT_SurfaceShader", displacement=True):
    mat = bpy.data.materials.get(matname) or bpy.data.materials.new(matname)
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = bpy.data.node_groups[groupname]
    gn.location = (0, 0); gn.name = "PLNT_CTL"; gn.label = "PLNT_CTL"
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (340, 0)
    nt.links.new(gn.outputs["BSDF"], out.inputs["Surface"])
    if displacement:
        nt.links.new(gn.outputs["Displacement"], out.inputs["Displacement"])
        mat.displacement_method = 'BOTH'
    else:
        mat.displacement_method = 'BUMP'
    # Measured on shot 8, paired and thermally gated: 47 s against 64 s, a 27%
    # saving, for an image that is not different. Cycles was building light
    # sampling structures for every lit window on a whole hemisphere of
    # cities. At this scale those windows illuminate nothing, because the
    # surface they would light is the surface they are on, six thousand
    # kilometres across. They are emission to look at, not lights to sample
    # from.
    try:
        mat.cycles.emission_sampling = 'NONE'
    except Exception:
        pass
    return mat
