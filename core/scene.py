"""Build a complete planet system in an empty scene.

This is the reproducibility fix. PLNT_GlobeRig, the sun rig, the four cameras
and the starfield world previously existed only inside PLNT_PlanetGen.blend --
`rebuild()` regenerates node groups onto objects that must already exist, and
raises KeyError on an empty scene. If the .blend were lost the system could not
be rebuilt at all.

Order matters: the sun rig must exist before the surface shader is built,
because the technology layer creates drivers that target PLNT_SunDir.
"""
import bpy
import math

try:
    from .nodeutil import sockin, sockout
except ImportError:
    from nodeutil import sockin, sockout

RADIUS = 1000.0
SUN_ANGLE = math.radians(0.526)     # the Sun's angular diameter from Earth
SUN_ENERGY = 4.0

CAMERAS = [
    # name, lens, location, clip_start, clip_end, tracks planet
    ("PLNT_CAM_Orbital", 55.0, (1807.33, -3705.58, 801.40), 0.01, 100000.0, True),
    ("PLNT_CAM_Limb", 50.0, (1320.0, 0.0, 210.0), 0.01, 100000.0, True),
    ("PLNT_CAM_Night", 85.0, (-4280.44, 3591.71, -1393.17), 0.01, 100000.0, True),
    ("PLNT_CAM_Ground", 40.0, (-1200.0, -2900.0, -38821.27), 1.0, 200000.0, False),
]


def _rm(coll, name):
    d = coll.get(name)
    if d:
        try:
            coll.remove(d, do_unlink=True)
        except TypeError:
            coll.remove(d)


def build_sun_rig(radius=RADIUS):
    """Sun on an orbitable pivot, plus the direction empty the drivers read.

    PLNT_SunDir is parented to the sun at local (0, 0, 1). Because the sun sits
    at the pivot origin, that empty's world location IS the sun's Z axis. This
    exists because matrix_world is not a dependency-tracked driver path: a
    driver reading it silently freezes at its creation value, whereas
    TRANSFORMS/WORLD_SPACE location drivers do track.
    """
    for n in ("PLNT_SunDir", "PLNT_Sun", "PLNT_SunPivot"):
        _rm(bpy.data.objects, n)
    _rm(bpy.data.lights, "PLNT_SunData")

    pivot = bpy.data.objects.new("PLNT_SunPivot", None)
    pivot.empty_display_size = radius * 0.25
    bpy.context.scene.collection.objects.link(pivot)

    ld = bpy.data.lights.new("PLNT_SunData", 'SUN')
    ld.energy = SUN_ENERGY
    ld.angle = SUN_ANGLE
    ld.color = (1.0, 0.98, 0.95)
    sun = bpy.data.objects.new("PLNT_Sun", ld)
    bpy.context.scene.collection.objects.link(sun)
    sun.parent = pivot
    sun.location = (0.0, 0.0, 0.0)

    d = bpy.data.objects.new("PLNT_SunDir", None)
    d.empty_display_size = radius * 0.05
    bpy.context.scene.collection.objects.link(d)
    d.parent = sun
    d.location = (0.0, 0.0, 1.0)
    return {"pivot": pivot.name, "sun": sun.name, "dir": d.name}


SUN_BASE_ROT = (0.0, math.pi * 0.5, 0.0)


def set_sun(azimuth_deg=120.0, elevation_deg=20.0):
    """Point the sun rig. ONE convention, written in both places.

    There were two, and they disagree by 90 degrees about azimuth:

      presets.sun   pivot = (0, -elevation, azimuth), sun object untouched,
                    relying on the sun already carrying a base rotation of
                    (0, 90, 0) so that its +Z points along the pivot +X.
      scene.set_sun pivot = (0, 0, azimuth), sun = (90 - elevation, 0, 0).

    Both produce a plausible sun, so nothing ever looked broken. Which one you
    got depended on which function had touched the rig last, and the shipped
    .blend happened to have been left by the presets one, so every hero shot
    was framed and lit against that convention. Rebuilding the scene from the
    builders ended with set_sun instead, rotated the lighting by 90 degrees on
    all ten shots, and turned the night-heavy frames into day.

    The presets convention wins because the shot table was authored against it.
    Both functions now write BOTH objects, so neither can inherit a stale base
    rotation from the other.
    """
    p = bpy.data.objects.get("PLNT_SunPivot")
    s = bpy.data.objects.get("PLNT_Sun")
    if not p or not s:
        return None
    p.rotation_euler = (0.0, math.radians(-elevation_deg), math.radians(azimuth_deg))
    s.rotation_euler = SUN_BASE_ROT
    bpy.context.view_layer.update()
    return (azimuth_deg, elevation_deg)


def build_cameras(radius=RADIUS):
    made = []
    for name, lens, loc, cs, ce, track in CAMERAS:
        _rm(bpy.data.objects, name)
        _rm(bpy.data.cameras, name + "Data")
        cd = bpy.data.cameras.new(name + "Data")
        cd.lens = lens
        cd.sensor_width = 36.0
        cd.clip_start = cs
        cd.clip_end = ce
        ob = bpy.data.objects.new(name, cd)
        bpy.context.scene.collection.objects.link(ob)
        ob.location = loc
        if track:
            from mathutils import Vector
            q = (Vector(loc) - Vector((0.0, 0.0, 0.0))).to_track_quat('Z', 'Y')
            ob.rotation_mode = 'QUATERNION'
            ob.rotation_quaternion = q
        else:
            ob.rotation_euler = (math.radians(88.0), 0.0, 0.0)
        made.append(name)
    sc = bpy.context.scene
    sc.camera = bpy.data.objects.get("PLNT_CAM_Orbital")
    # was saved pointing at the ground camera, 40 km from the planet
    sc.cycles.dicing_camera = sc.camera
    return made


def build_world(name="PLNT_World", star_scale=900.0, star_gain=1.0,
                nebula=0.0625):
    """Procedural starfield: no image textures anywhere in this project.

    Stars come from a high-frequency Voronoi thresholded hard, so most of the
    sky is black and a small fraction is a point. A noise-driven nebula sits
    underneath at low intensity. The named nodes are what the Sun & Sky panel
    finds to expose scale, gain and nebula strength.
    """
    _rm(bpy.data.worlds, name)
    w = bpy.data.worlds.new(name)
    w.use_nodes = True
    nt = w.node_tree
    nt.nodes.clear()
    N, L = nt.nodes.new, nt.links.new

    tc = N("ShaderNodeTexCoord"); tc.location = (-1200, 0)
    sc = N("ShaderNodeVectorMath"); sc.operation = 'SCALE'
    sc.location = (-1000, 0); sc.label = "STAR_SCALE"
    L(sockout(tc, "Generated"), sc.inputs[0])
    sockin(sc, "Scale").default_value = star_scale

    vor = N("ShaderNodeTexVoronoi"); vor.location = (-800, 0); vor.label = "stars"
    vor.voronoi_dimensions = '3D'
    vor.feature = 'F1'
    sockin(vor, "Randomness").default_value = 1.0
    sockin(vor, "Scale").default_value = 1.0
    L(sockout(sc, "Vector"), sockin(vor, "Vector"))

    # hard threshold: a star is a point, not a gradient
    thr = N("ShaderNodeMapRange"); thr.location = (-600, 0); thr.clamp = True
    thr.label = "star cut"
    L(sockout(vor, "Distance"), thr.inputs[0])
    for i, v in ((1, 0.0), (2, 0.055), (3, 1.0), (4, 0.0)):
        thr.inputs[i].default_value = v
    pw = N("ShaderNodeMath"); pw.operation = 'POWER'; pw.location = (-420, 0)
    L(thr.outputs["Result"], pw.inputs[0])
    pw.inputs[1].default_value = 4.0

    # per-star brightness and colour temperature variation
    cvar = N("ShaderNodeTexVoronoi"); cvar.location = (-800, -260)
    cvar.voronoi_dimensions = '3D'
    cvar.feature = 'F1'
    sockin(cvar, "Scale").default_value = 1.0
    L(sockout(sc, "Vector"), sockin(cvar, "Vector"))
    tint = N("ShaderNodeMix"); tint.data_type = 'RGBA'; tint.location = (-420, -260)
    tint.label = "star colour"
    tint.inputs[6].default_value = (0.62, 0.74, 1.0, 1.0)
    tint.inputs[7].default_value = (1.0, 0.82, 0.62, 1.0)
    L(sockout(cvar, "Color"), tint.inputs[0])

    gain = N("ShaderNodeMath"); gain.operation = 'MULTIPLY'
    gain.location = (-240, 0); gain.label = "STAR_GAIN"
    L(pw.outputs[0], gain.inputs[0])
    gain.inputs[1].default_value = star_gain
    starcol = N("ShaderNodeVectorMath"); starcol.operation = 'SCALE'
    starcol.location = (-60, -120)
    L(tint.outputs[2], starcol.inputs[0])
    L(gain.outputs[0], sockin(starcol, "Scale"))

    neb = N("ShaderNodeTexNoise"); neb.location = (-800, -520); neb.label = "nebula noise"
    neb.noise_dimensions = '3D'
    neb.noise_type = 'FBM'
    sockin(neb, "Scale").default_value = 1.6
    sockin(neb, "Detail").default_value = 6.0
    L(sockout(tc, "Generated"), sockin(neb, "Vector"))
    nramp = N("ShaderNodeValToRGB"); nramp.location = (-600, -520)
    L(sockout(neb, "Fac"), sockin(nramp, "Fac"))
    nramp.color_ramp.elements[0].position = 0.42
    nramp.color_ramp.elements[0].color = (0.0, 0.0, 0.0, 1.0)
    nramp.color_ramp.elements[1].position = 0.78
    nramp.color_ramp.elements[1].color = (0.10, 0.06, 0.22, 1.0)
    nmul = N("ShaderNodeVectorMath"); nmul.operation = 'SCALE'
    nmul.location = (-380, -520); nmul.label = "NEBULA"
    L(nramp.outputs["Color"], nmul.inputs[0])
    # 0.0625, not 0.25.
    #
    # The nebula is a full-sphere emitter, so it is not scenery: it is the
    # ambient fill for the whole scene, and at 0.25 it was the DOMINANT light.
    # Measured on shot 05 with the planet replaced by flat grey: sun alone
    # gives 0.035, the starfield adds nothing measurable (0.26193 against
    # 0.26172 with the stars off), and the nebula alone took it to 0.262 --
    # seven times the sun. Every night side in the set was being lit by the
    # sky rather than by anything in the scene, and the volcanic frame, whose
    # whole subject is lava being the only light, came back as a pale sphere.
    #
    # 0.0625 puts the sky contribution at 0.114, matching the delivered v2
    # scene (0.113) whose world predates this builder. Stars stay exactly as
    # bright: they were never the problem.
    sockin(nmul, "Scale").default_value = nebula

    add = N("ShaderNodeVectorMath"); add.operation = 'ADD'; add.location = (140, -240)
    L(sockout(starcol, "Vector"), add.inputs[0])
    L(sockout(nmul, "Vector"), add.inputs[1])

    bg = N("ShaderNodeBackground"); bg.location = (360, -240)
    L(sockout(add, "Vector"), sockin(bg, "Color"))
    sockin(bg, "Strength").default_value = 1.0
    out = N("ShaderNodeOutputWorld"); out.location = (560, -240)
    L(sockout(bg, "Background"), sockin(out, "Surface"))
    bpy.context.scene.world = w
    return w


def build_render_settings(scene=None, quality='FINAL'):
    scene = scene or bpy.context.scene
    scene.render.engine = 'CYCLES'
    scene.view_settings.view_transform = 'AgX'
    scene.render.resolution_x = 2560
    scene.render.resolution_y = 1440
    scene.render.film_transparent = False
    try:
        from . import render as _r
    except ImportError:
        import render as _r
    dev = _r.setup_device(scene)
    q = _r.apply_quality(quality, scene)
    return {"device": dev, "quality": q}


# Maps the transitional flat module names to their packaged submodule names.
_SUBMODULES = {"field": "plnt_field", "surface": "plnt_surface",
               "tech": "plnt_tech", "atmos": "plnt_atmos",
               "patch": "plnt_patch", "shots": "plnt_shots",
               "presets": "PLNT_presets"}


def _import_sub(name):
    """Import a generator submodule.

    Inside the packaged extension these are real siblings of core/, so a
    relative import works. In the working tree they are still flat top-level
    files loaded by path. Path loaders cannot be used inside an extension:
    the package is bl_ext.<repo>.<id> and sys.modules["plnt_tech"] would
    collide globally, so the relative import is tried first.
    """
    import importlib
    import os
    try:
        return importlib.import_module("..%s" % name, __name__)
    except Exception:
        directory = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return _load_flat(_SUBMODULES.get(name, name), directory)


def _load_flat(modname, directory):
    """Import one of the transitional top-level modules by path."""
    import importlib.util
    import os
    import sys
    p = os.path.join(directory, modname + ".py")
    spec = importlib.util.spec_from_file_location(modname, p)
    m = importlib.util.module_from_spec(spec)
    sys.modules[modname] = m
    spec.loader.exec_module(m)
    return m


def _set_mod_inputs(md, values):
    if not md or not md.node_group:
        return 0
    ids = {i.name: i.identifier for i in md.node_group.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
           and i.socket_type != 'NodeSocketGeometry'}
    n = 0
    for k, v in values.items():
        if k not in ids:
            continue
        try:
            slot = md.properties.inputs[ids[k]]
            if "value" in slot.keys():
                slot["value"] = v
            else:
                md.properties.inputs[ids[k]] = v
            n += 1
        except Exception:
            try:
                md.properties.inputs[ids[k]] = v
                n += 1
            except Exception:
                pass
    return n


def _build_rings(rg, radius):
    """Rings from core/rings: a real annulus, not a two-vertex quad."""
    inner, outer = radius * 1.35, radius * 2.30
    shader = rg.build_shader("PLNT_RingShader", inner, outer)
    geo = rg.build_geometry("PLNT_RingsRig", inner, outer)
    mat = bpy.data.materials.get("PLNT_Rings") or bpy.data.materials.new("PLNT_Rings")
    mat.use_nodes = True
    nt = mat.node_tree
    nt.nodes.clear()
    gn = nt.nodes.new("ShaderNodeGroup")
    gn.node_tree = shader
    gn.name = "PLNT_CTL"; gn.label = "PLNT_CTL"; gn.location = (0, 0)
    out = nt.nodes.new("ShaderNodeOutputMaterial"); out.location = (320, 0)
    nt.links.new(gn.outputs["BSDF"], out.inputs["Surface"])
    _rm(bpy.data.objects, "PLNT_Rings")
    _rm(bpy.data.meshes, "PLNT_RingsMesh")
    me = bpy.data.meshes.new("PLNT_RingsMesh")
    ob = bpy.data.objects.new("PLNT_Rings", me)
    bpy.context.scene.collection.objects.link(ob)
    md = ob.modifiers.new("PLNT_RingsRig", 'NODES')
    md.node_group = geo
    _set_mod_inputs(md, {"Inner": inner, "Outer": outer,
                         "Radial Segments": 384, "Angular Segments": 512,
                         "Ring Warp": radius * 0.0024, "Warp Scale": 6.0,
                         "Material": mat})
    ob.visible_shadow = True
    return ob


def build_scene_scaffold(preset="earthlike", seed=2291, radius=RADIUS,
                         subdiv=8, quality='FINAL', directory=None,
                         atmo_mode="surface"):
    """Empty scene -> complete planet system. The 'few clicks' entry point.

    The order below is load-bearing: the sun rig must exist before the surface
    shader is built, because the technology layer creates drivers targeting
    PLNT_SunDir, and a driver created against a missing object never recovers.
    """
    import os
    directory = directory or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    steps = {}

    steps["render"] = build_render_settings(quality=quality)
    steps["sun"] = build_sun_rig(radius)          # before build_surface
    steps["world"] = build_world().name
    steps["cameras"] = build_cameras(radius)

    field = _load_flat("plnt_field", directory)
    field.build_all()
    steps["field"] = ["PLNT_TerrainField", "PLNT_TerrainFieldSH"]

    try:
        from . import gen_groups
    except ImportError:
        try:
            gen_groups = _load_flat("gen_groups",
                                    os.path.join(directory, "core"))
        except Exception as ex:
            raise RuntimeError(
                "core/gen_groups.py is missing; regenerate it with "
                "tools/dump_tree.py --group PLNT_GlobeRig. Without it the "
                "globe rig cannot be built from source. (%s)" % ex)
    globe_rig = gen_groups.build_globerig()
    steps["globe_rig"] = globe_rig.name

    surface = _load_flat("plnt_surface", directory)
    surface.build_surface(sun_dir_obj=bpy.data.objects.get("PLNT_SunDir"))
    mat = surface.wire_material()
    steps["surface"] = mat.name

    # globe object
    _rm(bpy.data.objects, "PLNT_Globe")
    _rm(bpy.data.meshes, "PLNT_GlobeMesh")
    me = bpy.data.meshes.new("PLNT_GlobeMesh")
    ob = bpy.data.objects.new("PLNT_Globe", me)
    bpy.context.scene.collection.objects.link(ob)
    md = ob.modifiers.new("PLNT_GlobeRig", 'NODES')
    md.node_group = globe_rig
    ids = {i.name: i.identifier for i in globe_rig.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
           and i.socket_type != 'NodeSocketGeometry'}

    def gset(name, value):
        if name not in ids:
            return
        slot = md.properties.inputs[ids[name]]
        try:
            if "value" in slot.keys():
                slot["value"] = value
                return
        except Exception:
            pass
        md.properties.inputs[ids[name]] = value

    gset("Radius", radius)
    gset("Subdiv Level", subdiv)
    gset("Seed", float(seed))
    gset("Surface Material", mat)
    sub = ob.modifiers.new("PLNT_Adaptive", 'SUBSURF')
    sub.subdivision_type = 'SIMPLE'
    sub.use_adaptive_subdivision = True
    sub.adaptive_pixel_size = 1.0
    sub.levels = 1
    sub.render_levels = 2
    steps["globe"] = ob.name

    # shells and structures
    atmos = _import_sub("atmos")
    atmos.make_cloud_object(radius)
    # Analytic surface atmosphere by default. The ray-marched volume measured
    # 54% of total render time on shot 02; the optical path through a spherical
    # shell has a closed form, so there is nothing to march.
    atmos.make_atmo_object(radius)          # builds the shell mesh and rig
    if atmo_mode == "surface":
        try:
            from . import atmosphere as _atm
        except ImportError:
            _atm = _load_flat("atmosphere", os.path.join(directory, "core"))
        _atm.build("PLNT_AtmoShader")
        amat = _atm.make_material("PLNT_Atmosphere", "PLNT_AtmoShader", radius)
        aob = bpy.data.objects.get("PLNT_Atmosphere")
        if aob and aob.data and hasattr(aob.data, "materials"):
            aob.data.materials.clear()
            aob.data.materials.append(amat)
        if aob and aob.modifiers:
            _set_mod_inputs(aob.modifiers[0], {"Material": amat})
            aob.visible_shadow = False
    try:
        from . import rings as _rg
    except ImportError:
        _rg = _load_flat("rings", os.path.join(directory, "core"))
    _build_rings(_rg, radius)
    _set_ring_radius(radius)
    steps["shells"] = ["PLNT_Clouds", "PLNT_Atmosphere", "PLNT_Rings"]

    try:
        from . import orbital as _orb
    except ImportError:
        _orb = _load_flat("orbital", os.path.join(directory, "core"))
    _orb.make_object(radius)
    steps["orbital"] = "PLNT_Orbital"

    # Megastructures. Until v3 this object was only ever created by
    # tools/apply_v2.py, so a planet built through Create Planet System had no
    # mirror belt, no ringworld arcs and no Dyson swarm. The Megastructures
    # panel simply reported "No megastructures in this scene" forever.
    try:
        from . import mega as _mg
    except ImportError:
        _mg = _load_flat("mega", os.path.join(directory, "core"))
    _build_mega(_mg, radius)
    steps["mega"] = "PLNT_Mega"

    patch = _import_sub("patch")
    patch.make_object()          # build() returns the node group, not an object
    surface.build_surface(name="PLNT_PatchShader",
                          sun_dir_obj=bpy.data.objects.get("PLNT_SunDir"),
                          pos_attr="sphere_pos")
    pmat = surface.wire_material(matname="PLNT_PatchSurface",
                                 groupname="PLNT_PatchShader",
                                 displacement=False)
    p = bpy.data.objects.get("PLNT_Patch")
    if p and p.modifiers:
        _set_mod_inputs(p.modifiers[0], {"Material": pmat})
    if p:
        p.hide_render = True
        # ~20.7M triangles; leaving it visible makes every depsgraph update crawl
        p.hide_viewport = True
    steps["patch"] = "PLNT_Patch"

    # descriptions on every socket, then the preset
    try:
        from . import params as _pm
    except ImportError:
        _pm = _load_flat("params", os.path.join(directory, "core"))
    steps["descriptions"] = _pm.apply_descriptions(bpy.data.node_groups)["described"]

    presets = _load_flat("PLNT_presets", directory)
    presets.apply_preset(preset, seed=seed)
    steps["preset"] = preset
    set_sun(120.0, 20.0)

    # Socket ranges and tooltips do not travel with a modifier value: without
    # this every rig slider drags over the full float range with no tooltip.
    try:
        from . import ui as _ui
    except ImportError:
        _ui = _load_flat("ui", os.path.join(directory, "core"))
    try:
        steps["socket_ui"] = _ui.apply_socket_ui()
    except Exception as ex:
        steps["socket_ui_error"] = str(ex)[:120]

    # One clock for everything that moves.
    try:
        from . import anim as _an
    except ImportError:
        _an = _load_flat("anim", os.path.join(directory, "core"))
    try:
        steps["motion"] = _an.apply_object_motion()
        steps["clock"] = _an.sync()
    except Exception as ex:
        steps["motion_error"] = str(ex)[:160]
    return steps


def _set_ring_radius(radius):
    """The ring shader needs the planet radius to work out orbital periods."""
    m = bpy.data.materials.get("PLNT_Rings")
    n = m.node_tree.nodes.get("PLNT_CTL") if (m and m.node_tree) else None
    if n and "Planet Radius" in n.inputs:
        n.inputs["Planet Radius"].default_value = float(radius)
    return radius


def _build_mega(mg, radius):
    """PLNT_Mega + its rig and materials, idempotently."""
    g = mg.build(radius)
    mir, glow = mg.build_materials()
    struct = bpy.data.materials.get("PLNT_Orbital") or mir
    ob = bpy.data.objects.get("PLNT_Mega")
    if ob is None:
        me = bpy.data.meshes.new("PLNT_MegaMesh")
        ob = bpy.data.objects.new("PLNT_Mega", me)
        bpy.context.scene.collection.objects.link(ob)
    for md in list(ob.modifiers):
        ob.modifiers.remove(md)
    md = ob.modifiers.new("PLNT_MegaRig", 'NODES')
    md.node_group = g
    _set_mod_inputs(md, {
        "Radius": radius, "Mega Scale": 0.0, "Seed": 0.0,
        "Mirror Orbit": 1.9, "Mirror Count": 90, "Mirror Size": 62.0,
        "Ring Orbit": 2.7, "Ring Sweep": 130.0, "Ring Width": 120.0,
        "Arc Count": 3, "Habitat Glow": 1.0, "Swarm Count": 240,
        "Arc Motion": 0,
        "Material": struct, "Mirror Material": mir, "Glow Material": glow,
    })
    ob.visible_shadow = True
    # Mega Scale 0 builds nothing; the preset turns it on where it belongs
    ob.hide_render = True
    ob.hide_viewport = True
    return ob


def remove_system():
    n = 0
    for coll in (bpy.data.objects, bpy.data.node_groups, bpy.data.materials,
                 bpy.data.meshes, bpy.data.lights, bpy.data.cameras,
                 bpy.data.worlds):
        for d in list(coll):
            if d.name.startswith("PLNT"):
                try:
                    coll.remove(d, do_unlink=True)
                    n += 1
                except Exception:
                    pass
    return n
