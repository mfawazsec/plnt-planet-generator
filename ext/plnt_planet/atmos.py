"""PLNT clouds, atmosphere and rings."""
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



def _sphere(name, radius, subdiv=6):
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    me = bpy.data.meshes.new(name + "Mesh")
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if name + "Rig" in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name + "Rig"])
    g = bpy.data.node_groups.new(name + "Rig", 'GeometryNodeTree')
    g.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    g.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    s = g.interface.new_socket(name="Radius", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = radius; s.min_value = 0.1; s.max_value = 1e6
    s2 = g.interface.new_socket(name="Subdiv", in_out='INPUT', socket_type='NodeSocketInt')
    s2.default_value = subdiv; s2.min_value = 1; s2.max_value = 9
    m = g.interface.new_socket(name="Material", in_out='INPUT', socket_type='NodeSocketMaterial')
    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-400, 0)
    go = N("NodeGroupOutput"); go.location = (600, 0)
    ico = N("GeometryNodeMeshIcoSphere"); ico.location = (-150, 0)
    L(gi.outputs["Radius"], ico.inputs["Radius"])
    L(gi.outputs["Subdiv"], ico.inputs["Subdivisions"])
    sm = N("GeometryNodeSetShadeSmooth"); sm.location = (100, 0)
    L(ico.outputs["Mesh"], sm.inputs["Geometry"])
    mt = N("GeometryNodeSetMaterial"); mt.location = (330, 0)
    L(sm.outputs["Geometry"], mt.inputs["Geometry"])
    L(gi.outputs["Material"], mt.inputs["Material"])
    L(mt.outputs["Geometry"], go.inputs["Geometry"])
    mod = ob.modifiers.new(name + "Rig", 'NODES')
    mod.node_group = g
    return ob, mod, g


def _set(mod, name, value):
    ids = {i.name: i.identifier for i in mod.node_group.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
           and i.socket_type != 'NodeSocketGeometry'}
    slot = mod.properties.inputs[ids[name]]
    try:
        if "value" in slot.keys():
            slot["value"] = value; return
    except Exception:
        pass
    mod.properties.inputs[ids[name]] = value


def build_clouds(radius=1000.0):
    name = "PLNT_CloudShader"
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

    sk("Cloud Coverage", 'INPUT', 'NodeSocketFloat', 0.56, 0.0, 1.0)
    sk("Cloud Density", 'INPUT', 'NodeSocketFloat', 1.25, 0.0, 4.0)
    sk("Cloud Seed", 'INPUT', 'NodeSocketFloat', 0.0, -10000.0, 10000.0)
    sk("Band Strength", 'INPUT', 'NodeSocketFloat', 0.55, 0.0, 1.0)
    sk("Cloud Colour", 'INPUT', 'NodeSocketColor', (1.0, 1.0, 1.0, 1))
    sk("Detail Scale", 'INPUT', 'NodeSocketFloat', 1.0, 0.05, 8.0)
    sk("Cloud Relief", 'INPUT', 'NodeSocketFloat', 0.30, 0.0, 1.0)
    sk("BSDF", 'OUTPUT', 'NodeSocketShader')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-2200, 0)
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

    def NOISE(loc, scale, detail, rough, nm):
        n = N("ShaderNodeTexNoise"); n.location = loc; n.label = nm
        n.noise_dimensions = '4D'; n.noise_type = 'FBM'
        n.inputs["Scale"].default_value = scale
        n.inputs["Detail"].default_value = detail
        n.inputs["Roughness"].default_value = rough
        return n

    tc = N("ShaderNodeTexCoord"); tc.location = (-2200, -600)
    nrm = N("ShaderNodeVectorMath"); nrm.operation = 'NORMALIZE'; nrm.location = (-2020, -600)
    L(tc.outputs["Object"], nrm.inputs[0])

    def seedw(mul, add, loc):
        a = M('MULTIPLY', y=mul, loc=loc); L(gi.outputs["Cloud Seed"], a.inputs[0])
        b = M('ADD', y=add, loc=(loc[0] + 160, loc[1])); L(a.outputs["Value"], b.inputs[0])
        return b.outputs["Value"]

    # Weather evolves. A cloud deck that only rotates is a painted globe with a
    # texture sliding over it: real systems grow, shear and die over a few
    # days. All three noises are 4D, and the fourth coordinate is exactly the
    # dimension to walk along. Advancing W by 0.02 per world hour turns the
    # pattern over in about a week, which is what a satellite loop looks like.
    ctime = _anim_mod().shader_time(g, (-2600, 900))
    drift = M('MULTIPLY', y=0.02, loc=(-2420, 900), nm="weather drift")
    L(ctime, drift.inputs[0])

    def seedwt(mul, add, loc):
        base = seedw(mul, add, loc)
        t = M('ADD', loc=(loc[0] + 320, loc[1]))
        L(base, t.inputs[0]); L(drift.outputs["Value"], t.inputs[1])
        return t.outputs["Value"]

    w1, w2, w3, w4 = (seedwt(1.0, 0.0, (-2200, 700)), seedwt(1.9, 41.3, (-2200, 560)),
                      seedwt(2.7, 97.1, (-2200, 420)), seedwt(3.3, 151.9, (-2200, 280)))

    # latitude-banded macro flow: squash Z so swirls stretch into bands
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (-1840, -600)
    L(nrm.outputs["Vector"], sep.inputs["Vector"])
    zst = M('MULTIPLY', y=4.2, loc=(-1660, -700)); L(sep.outputs["Z"], zst.inputs[0])
    comb = N("ShaderNodeCombineXYZ"); comb.location = (-1480, -600)
    L(sep.outputs["X"], comb.inputs[0]); L(sep.outputs["Y"], comb.inputs[1])
    L(zst.outputs["Value"], comb.inputs[2])

    # warp the banded coords for swirl
    wn = NOISE((-1840, -280), 2.2, 4.0, 0.5, "cloud warp")
    L(nrm.outputs["Vector"], wn.inputs["Vector"]); L(w1, wn.inputs["W"])
    ws = N("ShaderNodeVectorMath"); ws.operation = 'SUBTRACT'; ws.location = (-1660, -280)
    L(wn.outputs["Color"], ws.inputs[0]); ws.inputs[1].default_value = (0.5, 0.5, 0.5)
    wsc = N("ShaderNodeVectorMath"); wsc.operation = 'SCALE'; wsc.location = (-1480, -280)
    L(ws.outputs["Vector"], wsc.inputs[0]); wsc.inputs["Scale"].default_value = 1.15
    # shear the warp: isotropic displacement makes round blobs, but a real
    # cloud field is stretched along the zonal flow and compressed across it
    wsh = N("ShaderNodeVectorMath"); wsh.operation = 'MULTIPLY'; wsh.location = (-1390, -280)
    L(wsc.outputs["Vector"], wsh.inputs[0]); wsh.inputs[1].default_value = (1.9, 1.9, 0.30)
    Pw = N("ShaderNodeVectorMath"); Pw.operation = 'ADD'; Pw.location = (-1300, -440)
    L(comb.outputs["Vector"], Pw.inputs[0]); L(wsh.outputs["Vector"], Pw.inputs[1])

    # band 1: macro swirls (banded coords)
    b1 = NOISE((-1100, 700), 2.6, 7.0, 0.55, "macro")
    L(Pw.outputs["Vector"], b1.inputs["Vector"]); L(w2, b1.inputs["W"])
    # band 2: mid cumulus clumps (unbanded, warped)
    Pw2 = N("ShaderNodeVectorMath"); Pw2.operation = 'ADD'; Pw2.location = (-1300, -100)
    L(nrm.outputs["Vector"], Pw2.inputs[0]); L(wsh.outputs["Vector"], Pw2.inputs[1])
    b2 = NOISE((-1100, 460), 6.5, 5.0, 0.6, "cumulus")
    L(Pw2.outputs["Vector"], b2.inputs["Vector"]); L(w3, b2.inputs["W"])
    # band 3: fine wisps
    b3 = NOISE((-1100, 220), 16.0, 5.0, 0.45, "wisps")
    L(Pw2.outputs["Vector"], b3.inputs["Vector"]); L(w4, b3.inputs["W"])

    for nd, base in ((b1, 2.6), (b2, 6.5), (b3, 16.0)):
        sc = M('MULTIPLY', y=base, loc=(nd.location.x - 220, nd.location.y - 160))
        L(gi.outputs["Detail Scale"], sc.inputs[0]); L(sc.outputs["Value"], nd.inputs["Scale"])

    # weighted blend; Band Strength biases macro vs detail
    bs_inv = M('SUBTRACT', x=1.0, loc=(-880, 60)); L(gi.outputs["Band Strength"], bs_inv.inputs[1])
    t1 = M('MULTIPLY', loc=(-880, 700)); L(b1.outputs["Factor"], t1.inputs[0]); L(gi.outputs["Band Strength"], t1.inputs[1])
    t2a = M('MULTIPLY', y=0.55, loc=(-880, 460)); L(b2.outputs["Factor"], t2a.inputs[0])
    t2 = M('MULTIPLY', loc=(-700, 460)); L(t2a.outputs["Value"], t2.inputs[0]); L(bs_inv.outputs["Value"], t2.inputs[1])
    t3 = M('MULTIPLY', y=0.05, loc=(-880, 220)); L(b3.outputs["Factor"], t3.inputs[0])
    s1 = M('ADD', loc=(-520, 600)); L(t1.outputs["Value"], s1.inputs[0]); L(t2.outputs["Value"], s1.inputs[1])
    s2 = M('ADD', loc=(-340, 600)); L(s1.outputs["Value"], s2.inputs[0]); L(t3.outputs["Value"], s2.inputs[1])

    # coverage threshold: high coverage -> lower cut
    cut = MR((-520, 380), 0.0, 1.0, 0.86, 0.20, "cut"); L(gi.outputs["Cloud Coverage"], cut.inputs[0])
    # a 0.16 wide ramp thresholds the cloud field into hard binary speckle
    cutw = M("ADD", y=0.50, loc=(-340, 380)); L(cut.outputs["Result"], cutw.inputs[0])
    alpha = MR((-140, 520), None, None, 0.0, 1.0, "alpha")
    L(s2.outputs["Value"], alpha.inputs[0])
    L(cut.outputs["Result"], alpha.inputs[1]); L(cutw.outputs["Value"], alpha.inputs[2])
    dens0 = M('MULTIPLY', loc=(60, 520), nm="density raw", clamp=True)
    L(alpha.outputs["Result"], dens0.inputs[0]); L(gi.outputs["Cloud Density"], dens0.inputs[1])

    # Grazing-angle fade.
    #
    # The cloud deck is an infinitely thin sphere. Seen face-on that is a fair
    # model of a 12 km layer on a 6000 km planet; seen edge-on at the limb it
    # is a lie, because a real ray would pass through tens of times more cloud
    # and the layer would read as a soft band, not a hard edge. With the shell
    # at full opacity right up to the silhouette, its Translucent lobe fires
    # along the whole rim and draws the bright line that appears on the dark
    # limb, one of the two "lines on the horizon".
    #
    # Fading density out as the surface turns edge-on removes it. |N.I| is 1
    # face-on and 0 exactly at the silhouette.
    cg = N("ShaderNodeNewGeometry"); cg.location = (-340, 240)
    ndi = N("ShaderNodeVectorMath"); ndi.operation = 'DOT_PRODUCT'
    ndi.location = (-160, 240); ndi.label = "N.I"
    L(cg.outputs["Normal"], ndi.inputs[0]); L(cg.outputs["Incoming"], ndi.inputs[1])
    andi = M('ABSOLUTE', loc=(0, 240), nm="grazing")
    L(ndi.outputs["Value"], andi.inputs[0])
    rim = MR((160, 240), 0.0, 0.25, 0.0, 1.0, "rim fade")
    rim.interpolation_type = 'SMOOTHSTEP'
    L(andi.outputs["Value"], rim.inputs[0])
    dens = M('MULTIPLY', loc=(340, 520), nm="density", clamp=True)
    L(dens0.outputs["Value"], dens.inputs[0]); L(rim.outputs["Result"], dens.inputs[1])

    # Cheap body relief. The deck was a flat painted alpha with no shading of
    # its own, so cloud systems read as stencils rather than as anything with
    # a top. Bumping the same combined field the alpha comes from gives the
    # tops a lit side for free: no volume, no second shell.
    bump = N("ShaderNodeBump"); bump.location = (-160, 60); bump.label = "cloud relief"
    L(s2.outputs["Value"], bump.inputs["Height"])
    L(gi.outputs["Cloud Relief"], bump.inputs["Strength"])
    bump.inputs["Distance"].default_value = 0.4

    # Translucent + Diffuse gives forward glow at the terminator plus body
    tr = N("ShaderNodeBsdfTranslucent"); tr.location = (60, 180)
    L(gi.outputs["Cloud Colour"], tr.inputs["Color"])
    df = N("ShaderNodeBsdfDiffuse"); df.location = (60, 20)
    L(gi.outputs["Cloud Colour"], df.inputs["Color"])
    df.inputs["Roughness"].default_value = 0.6
    L(bump.outputs["Normal"], df.inputs["Normal"])
    body = N("ShaderNodeMixShader"); body.location = (300, 100)
    body.inputs[0].default_value = 0.45
    L(tr.outputs["BSDF"], body.inputs[1]); L(df.outputs["BSDF"], body.inputs[2])
    trans = N("ShaderNodeBsdfTransparent"); trans.location = (300, 380)
    fin = N("ShaderNodeMixShader"); fin.location = (600, 300)
    L(dens.outputs["Value"], fin.inputs[0])
    L(trans.outputs["BSDF"], fin.inputs[1]); L(body.outputs["Shader"], fin.inputs[2])
    L(fin.outputs["Shader"], go.inputs["BSDF"])
    return g


def build_atmosphere():
    name = "PLNT_AtmoShader"
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

    sk("Density", 'INPUT', 'NodeSocketFloat', 0.0080, 0.0, 3.0)
    sk("Atmo Colour", 'INPUT', 'NodeSocketColor', (0.22, 0.44, 1.0, 1))
    sk("Anisotropy", 'INPUT', 'NodeSocketFloat', 0.3, -1.0, 1.0)
    sk("Inner Radius", 'INPUT', 'NodeSocketFloat', 1000.0, 1.0, 1e6)
    sk("Outer Radius", 'INPUT', 'NodeSocketFloat', 1020.0, 1.0, 1e6)
    sk("Falloff", 'INPUT', 'NodeSocketFloat', 3.2, 0.1, 12.0)
    sk("Pollution", 'INPUT', 'NodeSocketFloat', 0.0, 0.0, 1.0)
    sk("Volume", 'OUTPUT', 'NodeSocketShader')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-1000, 0)
    go = N("NodeGroupOutput"); go.location = (700, 0)
    tc = N("ShaderNodeTexCoord"); tc.location = (-1000, -300)
    ln = N("ShaderNodeVectorMath"); ln.operation = 'LENGTH'; ln.location = (-800, -300)
    L(tc.outputs["Object"], ln.inputs[0])
    # radial falloff: dense at the surface, zero at the outer shell
    mr = N("ShaderNodeMapRange"); mr.location = (-600, -300); mr.clamp = True
    L(ln.outputs["Value"], mr.inputs[0])
    L(gi.outputs["Inner Radius"], mr.inputs[1])
    L(gi.outputs["Outer Radius"], mr.inputs[2])
    mr.inputs[3].default_value = 1.0
    mr.inputs[4].default_value = 0.0
    pw = N("ShaderNodeMath"); pw.operation = 'POWER'; pw.location = (-400, -300)
    L(mr.outputs["Result"], pw.inputs[0]); L(gi.outputs["Falloff"], pw.inputs[1])
    dn = N("ShaderNodeMath"); dn.operation = 'MULTIPLY'; dn.location = (-200, -300); dn.label = "density"
    L(pw.outputs["Value"], dn.inputs[0]); L(gi.outputs["Density"], dn.inputs[1])
    # pollution tints toward brown-yellow and thickens the haze
    poll = N("ShaderNodeMix"); poll.data_type = 'RGBA'; poll.location = (-400, 100)
    poll.blend_type = 'MIX'; poll.clamp_factor = True
    L(gi.outputs["Pollution"], poll.inputs[0])
    L(gi.outputs["Atmo Colour"], poll.inputs[6])
    poll.inputs[7].default_value = (0.62, 0.45, 0.16, 1)
    pmul = N("ShaderNodeMath"); pmul.operation = 'MULTIPLY'; pmul.location = (-200, 100)
    pmul.inputs[1].default_value = 1.7
    L(gi.outputs["Pollution"], pmul.inputs[0])
    pad = N("ShaderNodeMath"); pad.operation = 'ADD'; pad.location = (-40, 100)
    pad.inputs[0].default_value = 1.0
    L(pmul.outputs["Value"], pad.inputs[1])
    dfin = N("ShaderNodeMath"); dfin.operation = 'MULTIPLY'; dfin.location = (140, -180)
    L(dn.outputs["Value"], dfin.inputs[0]); L(pad.outputs["Value"], dfin.inputs[1])
    vs = N("ShaderNodeVolumeScatter"); vs.location = (400, 0)
    L(poll.outputs[2], vs.inputs["Color"])
    L(dfin.outputs["Value"], vs.inputs["Density"])
    L(gi.outputs["Anisotropy"], vs.inputs["Anisotropy"])
    L(vs.outputs["Volume"], go.inputs["Volume"])
    return g


def make_cloud_object(radius=1000.0):
    grp = build_clouds(radius)
    mat = bpy.data.materials.get("PLNT_Clouds") or bpy.data.materials.new("PLNT_Clouds")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    gn = nt.nodes.new("ShaderNodeGroup"); gn.node_tree = grp
    gn.name = "PLNT_CTL"; gn.label = "PLNT_CTL"; gn.location = (0, 0)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(gn.outputs["BSDF"], out.inputs["Surface"])
    ob, mod, g = _sphere("PLNT_Clouds", radius * 1.002, 7)
    _set(mod, "Radius", radius * 1.002)
    _set(mod, "Subdiv", 7)
    _set(mod, "Material", mat)
    ob.visible_shadow = True
    return ob, mat


def make_atmo_object(radius=1000.0):
    grp = build_atmosphere()
    mat = bpy.data.materials.get("PLNT_Atmosphere") or bpy.data.materials.new("PLNT_Atmosphere")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    gn = nt.nodes.new("ShaderNodeGroup"); gn.node_tree = grp
    gn.name = "PLNT_CTL"; gn.label = "PLNT_CTL"; gn.location = (0, 0)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(gn.outputs["Volume"], out.inputs["Volume"])
    gn.inputs["Inner Radius"].default_value = radius
    gn.inputs["Outer Radius"].default_value = radius * 1.02
    # subdiv 5 is 5120 faces; the rim term is non-linear enough that linear
    # normal interpolation across triangles that big is visible at the limb
    ob, mod, g = _sphere("PLNT_Atmosphere", radius * 1.02, 7)
    _set(mod, "Radius", radius * 1.02)
    _set(mod, "Subdiv", 7)
    _set(mod, "Material", mat)
    # must not darken the surface it wraps
    ob.visible_shadow = False
    return ob, mat


def build_rings(inner=1.35, outer=2.30, radius=1000.0):
    """Ring disc: radial Voronoi banding, alpha gaps, forward-scattering when backlit."""
    name = "PLNT_RingShader"
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

    sk("Inner", 'INPUT', 'NodeSocketFloat', inner * radius, 1.0, 1e6)
    sk("Outer", 'INPUT', 'NodeSocketFloat', outer * radius, 1.0, 1e6)
    sk("Band Scale", 'INPUT', 'NodeSocketFloat', 60.0, 1.0, 600.0)
    sk("Gap Amount", 'INPUT', 'NodeSocketFloat', 0.55, 0.0, 1.0)
    sk("Ring Colour", 'INPUT', 'NodeSocketColor', (0.72, 0.70, 0.65, 1))
    sk("Ring Density", 'INPUT', 'NodeSocketFloat', 1.0, 0.0, 3.0)
    sk("Ring Seed", 'INPUT', 'NodeSocketFloat', 0.0, -10000.0, 10000.0)
    sk("BSDF", 'OUTPUT', 'NodeSocketShader')

    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-1600, 0)
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

    tc = N("ShaderNodeTexCoord"); tc.location = (-1600, -400)
    sep = N("ShaderNodeSeparateXYZ"); sep.location = (-1420, -400)
    L(tc.outputs["Object"], sep.inputs["Vector"])
    # radial distance in the ring plane
    fx = M('POWER', y=2.0, loc=(-1240, -300)); L(sep.outputs["X"], fx.inputs[0])
    fy = M('POWER', y=2.0, loc=(-1240, -460)); L(sep.outputs["Y"], fy.inputs[0])
    ad = M('ADD', loc=(-1060, -380)); L(fx.outputs["Value"], ad.inputs[0]); L(fy.outputs["Value"], ad.inputs[1])
    r = M('SQRT', loc=(-880, -380), nm="radius"); L(ad.outputs["Value"], r.inputs[0])

    # annulus mask with soft inner/outer edges
    inA = MR((-680, -200), None, None, 0.0, 1.0, "inner edge")
    L(r.outputs["Value"], inA.inputs[0]); L(gi.outputs["Inner"], inA.inputs[1])
    iw = M('MULTIPLY', y=1.03, loc=(-880, -100)); L(gi.outputs["Inner"], iw.inputs[0])
    L(iw.outputs["Value"], inA.inputs[2])
    outA = MR((-680, -420), None, None, 1.0, 0.0, "outer edge")
    L(r.outputs["Value"], outA.inputs[0])
    ow = M('MULTIPLY', y=0.96, loc=(-880, -560)); L(gi.outputs["Outer"], ow.inputs[0])
    L(ow.outputs["Value"], outA.inputs[1]); L(gi.outputs["Outer"], outA.inputs[2])
    ann = M('MULTIPLY', loc=(-480, -300), nm="annulus")
    L(inA.outputs["Result"], ann.inputs[0]); L(outA.outputs["Result"], ann.inputs[1])

    # normalised radius -> 1D banding
    nr = MR((-680, 100), None, None, 0.0, 1.0, "r norm")
    L(r.outputs["Value"], nr.inputs[0])
    L(gi.outputs["Inner"], nr.inputs[1]); L(gi.outputs["Outer"], nr.inputs[2])
    bs = M('MULTIPLY', loc=(-480, 100)); L(nr.outputs["Result"], bs.inputs[0])
    L(gi.outputs["Band Scale"], bs.inputs[1])
    vor = N("ShaderNodeTexVoronoi"); vor.location = (-280, 100); vor.label = "bands"
    vor.voronoi_dimensions = '1D'; vor.feature = 'F1'
    vor.inputs["Randomness"].default_value = 1.0
    sw = M('MULTIPLY', y=3.77, loc=(-480, 280)); L(gi.outputs["Ring Seed"], sw.inputs[0])
    # offset the band coordinate by the seed, else every seed gives identical rings
    bsw = M('ADD', loc=(-340, 260), nm="band coord")
    L(bs.outputs["Value"], bsw.inputs[0]); L(sw.outputs["Value"], bsw.inputs[1])
    L(bsw.outputs["Value"], vor.inputs["W"])
    # fine dust variation on top of the cell bands
    fn = N("ShaderNodeTexNoise"); fn.location = (-280, -60); fn.label = "dust"
    fn.noise_dimensions = '1D'; fn.noise_type = 'FBM'
    fn.inputs["Detail"].default_value = 8.0
    fn.inputs["Scale"].default_value = 2.4
    L(bsw.outputs["Value"], fn.inputs["W"])
    # Voronoi 1D F1 Distance tops out near 0.5 -> normalise before thresholding
    vnorm = M('MULTIPLY', y=2.0, loc=(-140, 180)); L(vor.outputs["Distance"], vnorm.inputs[0])
    vw = M('MULTIPLY', y=0.65, loc=(20, 180)); L(vnorm.outputs["Value"], vw.inputs[0])
    dw = M('MULTIPLY', y=0.35, loc=(20, 20)); L(fn.outputs["Factor"], dw.inputs[0])
    mixb = M('ADD', loc=(180, 100), clamp=True)
    L(vw.outputs["Value"], mixb.inputs[0]); L(dw.outputs["Value"], mixb.inputs[1])
    gthr = M('MULTIPLY', y=0.62, loc=(180, 280)); L(gi.outputs["Gap Amount"], gthr.inputs[0])
    ghi = M('ADD', y=0.17, loc=(340, 280)); L(gthr.outputs["Value"], ghi.inputs[0])
    gap = MR((340, 100), None, None, 0.0, 1.0, "gaps")
    L(mixb.outputs["Value"], gap.inputs[0])
    L(gthr.outputs["Value"], gap.inputs[1])
    L(ghi.outputs["Value"], gap.inputs[2])
    a1 = M('MULTIPLY', loc=(540, 0), nm="alpha")
    L(gap.outputs["Result"], a1.inputs[0]); L(ann.outputs["Value"], a1.inputs[1])
    a2 = M('MULTIPLY', loc=(700, 0), clamp=True)
    L(a1.outputs["Value"], a2.inputs[0]); L(gi.outputs["Ring Density"], a2.inputs[1])

    # forward scattering: translucent dominates so the rings glow when backlit
    tr = N("ShaderNodeBsdfTranslucent"); tr.location = (340, -260)
    L(gi.outputs["Ring Colour"], tr.inputs["Color"])
    df = N("ShaderNodeBsdfDiffuse"); df.location = (340, -420)
    L(gi.outputs["Ring Colour"], df.inputs["Color"])
    body = N("ShaderNodeMixShader"); body.location = (560, -320)
    body.inputs[0].default_value = 0.35
    L(tr.outputs["BSDF"], body.inputs[1]); L(df.outputs["BSDF"], body.inputs[2])
    trans = N("ShaderNodeBsdfTransparent"); trans.location = (560, 200)
    fin = N("ShaderNodeMixShader"); fin.location = (740, 0)
    L(a2.outputs["Value"], fin.inputs[0])
    L(trans.outputs["BSDF"], fin.inputs[1]); L(body.outputs["Shader"], fin.inputs[2])
    L(fin.outputs["Shader"], go.inputs["BSDF"])
    return g


def make_ring_object(radius=1000.0, inner=1.35, outer=2.30):
    grp = build_rings(inner, outer, radius)
    mat = bpy.data.materials.get("PLNT_Rings") or bpy.data.materials.new("PLNT_Rings")
    mat.use_nodes = True
    nt = mat.node_tree; nt.nodes.clear()
    gn = nt.nodes.new("ShaderNodeGroup"); gn.node_tree = grp
    gn.name = "PLNT_CTL"; gn.label = "PLNT_CTL"; gn.location = (0, 0)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (300, 0)
    nt.links.new(gn.outputs["BSDF"], out.inputs["Surface"])

    name = "PLNT_Rings"
    if name in bpy.data.objects:
        bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
    me = bpy.data.meshes.new(name + "Mesh")
    ob = bpy.data.objects.new(name, me)
    bpy.context.scene.collection.objects.link(ob)
    if name + "Rig" in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name + "Rig"])
    g = bpy.data.node_groups.new(name + "Rig", 'GeometryNodeTree')
    g.interface.new_socket(name="Geometry", in_out='INPUT', socket_type='NodeSocketGeometry')
    g.interface.new_socket(name="Geometry", in_out='OUTPUT', socket_type='NodeSocketGeometry')
    s = g.interface.new_socket(name="Size", in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = outer * radius * 2.2; s.min_value = 1.0; s.max_value = 1e7
    m = g.interface.new_socket(name="Material", in_out='INPUT', socket_type='NodeSocketMaterial')
    N, L = g.nodes.new, g.links.new
    gi = N("NodeGroupInput"); gi.location = (-400, 0)
    go = N("NodeGroupOutput"); go.location = (600, 0)
    grid = N("GeometryNodeMeshGrid"); grid.location = (-150, 0)
    L(gi.outputs["Size"], grid.inputs["Size X"])
    L(gi.outputs["Size"], grid.inputs["Size Y"])
    grid.inputs["Vertices X"].default_value = 2
    grid.inputs["Vertices Y"].default_value = 2
    mt = N("GeometryNodeSetMaterial"); mt.location = (330, 0)
    L(grid.outputs["Mesh"], mt.inputs["Geometry"])
    L(gi.outputs["Material"], mt.inputs["Material"])
    L(mt.outputs["Geometry"], go.inputs["Geometry"])
    mod = ob.modifiers.new(name + "Rig", 'NODES')
    mod.node_group = g
    _set(mod, "Size", outer * radius * 2.2)
    _set(mod, "Material", mat)
    ob.visible_shadow = True
    return ob, mat
