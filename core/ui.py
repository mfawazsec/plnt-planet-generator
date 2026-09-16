"""Data-driven UI.

The panels enumerate node group interfaces and consult core.params only for
grouping, ordering, tier and help text. Nothing is hand-listed, so a socket
added later cannot become unreachable, which is how every ring parameter, all
eight patch parameters and the whole sun/starfield setup ended up with no UI at
all in the first version.

Node sockets stay the single source of truth. Drawing the real socket means
Blender gives us its description as the tooltip, its min/max as the drag range,
its subtype as the units, and undo for free.
"""
import bpy

try:
    from . import params
except ImportError:                     # running as a loose script
    import params

GLOBE = "PLNT_Globe"
GLOBE_MOD = "PLNT_GlobeRig"
SURF = "PLNT_Surface"
PATCH_SURF = "PLNT_PatchSurface"
CLOUDS = "PLNT_Clouds"
ATMO = "PLNT_Atmosphere"
RINGS = "PLNT_Rings"
ORBITAL = "PLNT_Orbital"
PATCH = "PLNT_Patch"
MEGA = "PLNT_Mega"

# panel id -> ordered list of ('mod', object, modifier) / ('ctl', material)
SOURCES = {
    "terrain": [("mod", GLOBE, GLOBE_MOD)],
    "surface": [("ctl", SURF)],
    "ocean":   [("ctl", SURF)],
    "civ":     [("ctl", SURF)],
    "clouds":  [("ctl", CLOUDS), ("mod", CLOUDS, "PLNT_CloudsRig")],
    "atmo":    [("ctl", ATMO), ("mod", ATMO, "PLNT_AtmosphereRig")],
    "rings":   [("ctl", RINGS), ("mod", RINGS, "PLNT_RingsRig")],
    "orbital": [("mod", ORBITAL, "PLNT_OrbitalRig")],
    "mega":    [("mod", MEGA, "PLNT_MegaRig")],
    "patch":   [("mod", PATCH, "PLNT_PatchRig")],
}

# Sockets whose value must be mirrored from the globe rig onto every shader and
# rig that carries its own copy, or the geometry and the shading disagree: drag
# Continent Scale and the coastline moves while the terrain does not.
SHARED_TERRAIN = ("Seed", "Continent Scale", "Continent Coverage",
                  "Mountain Sharpness", "Erosion Amount", "Tectonic Belt Width",
                  "Warp Strength", "Sea Level", "Polar Cap Extent",
                  "Relief Strength")
MIRROR_TARGETS = [("ctl", SURF), ("ctl", PATCH_SURF), ("mod", PATCH, "PLNT_PatchRig")]


def _ids(ng):
    return {i.name: i.identifier for i in ng.interface.items_tree
            if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
            and i.socket_type != 'NodeSocketGeometry'}


def _mod(obj_name, mod_name):
    ob = bpy.data.objects.get(obj_name)
    if not ob:
        return None
    md = ob.modifiers.get(mod_name)
    return md if md and md.node_group else None


def _ctl_node(mat_name):
    m = bpy.data.materials.get(mat_name)
    if not m or not m.node_tree:
        return None
    return m.node_tree.nodes.get("PLNT_CTL")


def resolve(source):
    """('mod', obj, mod) or ('ctl', mat) -> (kind, holder, node_group) or None."""
    if source[0] == "mod":
        md = _mod(source[1], source[2])
        return ("mod", md, md.node_group) if md else None
    node = _ctl_node(source[1])
    return ("ctl", node, node.node_tree) if node and node.node_tree else None


def visible_sockets(panel_id, tier, search):
    """[(kind, holder, socket_item, identifier, order)] for one panel."""
    allowed = params.TIER_VISIBLE.get(tier, params.TIER_VISIBLE['ADVANCED'])
    needle = (search or "").strip().lower()
    out = []
    for src in SOURCES.get(panel_id, ()):
        r = resolve(src)
        if not r:
            continue
        kind, holder, ng = r
        ids = _ids(ng) if kind == "mod" else None
        for it, panel, order, t, _desc in params.sockets_of(ng):
            if panel != panel_id:
                continue
            if needle:
                if needle not in it.name.lower():
                    continue
            elif t not in allowed:
                continue
            ident = ids.get(it.name) if ids else None
            if kind == "mod" and ident is None:
                continue
            out.append((kind, holder, it, ident, order))
    out.sort(key=lambda r: (r[4], r[2].name))
    return out


def mod_slot(holder, ident):
    """The drawable struct behind one Geometry Nodes modifier input.

    Blender 5.x stores a modifier input as an ID property GROUP per socket,
    {value, type, attribute_name}, reached through `md.properties.inputs`.
    Drawing `inputs['["Socket_4"]']` therefore draws the group itself, and the
    panel reads "ID Property Group" with no usable widget: every rig slider in
    this add-on was dead on 5.2 for exactly that reason. `path_resolve` hands
    the group back as a real struct whose "value" key is the thing to drag.
    """
    try:
        return holder.properties.inputs.path_resolve('["%s"]' % ident)
    except Exception:
        return None


def draw_socket(layout, kind, holder, item, ident):
    if kind == "mod":
        slot = mod_slot(holder, ident)
        if slot is not None:
            layout.prop(slot, '["value"]', text=item.name)
    else:
        sock = holder.inputs.get(item.name)
        if sock is not None:
            layout.prop(sock, "default_value", text=item.name)


# Interface ranges and tooltips do not travel with the value. An ID property
# starts life with the full float range and no description, so without this
# every rig slider drags from -3.4e38 to +3.4e38 and has nothing to say for
# itself, while the socket it mirrors carries 0..1 and a paragraph of help.
_UI_NUMERIC = {"NodeSocketFloat", "NodeSocketFloatFactor", "NodeSocketFloatDistance",
               "NodeSocketFloatAngle", "NodeSocketInt"}


def apply_socket_ui(report=False):
    """Push each node group interface's range, default and tooltip onto the
    matching modifier slot. Cheap, idempotent, and only needs running when the
    rigs are rebuilt; the values are saved in the .blend."""
    done_n = 0
    notes = []
    for panel_id, srcs in SOURCES.items():
        for src in srcs:
            if src[0] != "mod":
                continue
            md = _mod(src[1], src[2])
            if not md:
                continue
            for it in md.node_group.interface.items_tree:
                if getattr(it, "item_type", "") != 'SOCKET' or it.in_out != 'INPUT':
                    continue
                if it.socket_type == 'NodeSocketGeometry':
                    continue
                slot = mod_slot(md, it.identifier)
                if slot is None:
                    continue
                try:
                    ui = slot.id_properties_ui("value")
                except Exception:
                    continue
                kw = {}
                desc = getattr(it, "description", "") or ""
                if desc:
                    kw["description"] = desc
                if it.socket_type in _UI_NUMERIC:
                    cast = int if it.socket_type == 'NodeSocketInt' else float
                    for key, attr in (("min", "min_value"), ("max", "max_value"),
                                      ("soft_min", "min_value"), ("soft_max", "max_value"),
                                      ("default", "default_value")):
                        v = getattr(it, attr, None)
                        if v is not None:
                            kw[key] = cast(v)
                if not kw:
                    continue
                try:
                    ui.update(**kw)
                    done_n += 1
                except Exception as ex:
                    notes.append("%s/%s: %s" % (md.name, it.name, str(ex)[:60]))
    out = {"slots": done_n}
    if notes:
        out["problems"] = notes
    return out if report else done_n


def tag_update(*objects):
    """Tag objects so Geometry Nodes actually re-evaluates.

    Writing a value through `mod.properties.inputs[...]["value"]` does not mark
    the depsgraph dirty, so Blender keeps handing back the previous evaluation.
    Dragging a slider in a panel tags it for you; an operator writing the same
    value does not, so every operator here has to tag explicitly or the change
    silently does nothing on screen.
    """
    names = objects or (GLOBE, CLOUDS, ATMO, RINGS, ORBITAL, PATCH, MEGA)
    n = 0
    for nm in names:
        ob = bpy.data.objects.get(nm) if isinstance(nm, str) else nm
        if ob:
            ob.update_tag()
            n += 1
    return n


def sync_shared_terrain():
    """Push the globe rig's terrain values onto every mirror copy.

    Called from a depsgraph handler. Cheap: ten float comparisons against at
    most three targets, and it only writes when a value actually differs, so it
    cannot loop.
    """
    md = _mod(GLOBE, GLOBE_MOD)
    if not md:
        return 0
    ids = _ids(md.node_group)
    written = 0
    for name in SHARED_TERRAIN:
        if name not in ids:
            continue
        try:
            src = md.properties.inputs[ids[name]]["value"]
        except Exception:
            continue
        for tgt in MIRROR_TARGETS:
            r = resolve(tgt)
            if not r:
                continue
            kind, holder, ng = r
            if kind == "ctl":
                s = holder.inputs.get(name)
                if s is not None and abs(s.default_value - src) > 1e-9:
                    s.default_value = src
                    written += 1
            else:
                tids = _ids(ng)
                if name not in tids:
                    continue
                slot = holder.properties.inputs[tids[name]]
                try:
                    if abs(slot["value"] - src) > 1e-9:
                        slot["value"] = src
                        written += 1
                        ob = bpy.data.objects.get(tgt[1])
                        if ob:
                            ob.update_tag()
                except Exception:
                    pass
    return written


# --------------------------------------------------------------------------
# Preset table lookup. During the transition the presets still live in a text
# datablock inside the .blend; once packaged they are a real module. Try the
# module first, fall back to the text, and cache either way: exec on every
# redraw would make the panel unusable.
# --------------------------------------------------------------------------
_NS_CACHE = {}


def presets_ns(force=False):
    if _NS_CACHE and not force:
        return _NS_CACHE
    ns = None
    try:
        import importlib as _il
        _p = _il.import_module(".presets", __package__.rsplit(".", 1)[0]) \
            if __package__ and "." in __package__ else None
        if _p is None:
            from . import presets as _p
        ns = _p.__dict__
    except Exception:
        txt = bpy.data.texts.get("PLNT_presets.py")
        if txt:
            ns = {"__name__": "plnt_presets_mod"}
            try:
                exec(compile(txt.as_string(), "PLNT_presets.py", "exec"), ns)
            except Exception:
                ns = None
    _NS_CACHE.clear()
    if ns:
        _NS_CACHE.update(ns)
    return _NS_CACHE


def preset_items(self=None, context=None):
    ns = presets_ns()
    P = ns.get("P") or {}
    if not P:
        return [('NONE', "(no presets loaded)", "")]
    return [(k, k.replace("_", " ").title(), (v.get("note") or "")[:180])
            for k, v in sorted(P.items())]


# --------------------------------------------------------------------------
# State messages. A panel that silently does nothing is the main way a tool
# like this wastes someone's afternoon.
# --------------------------------------------------------------------------
def quality_estimate(quality, performance):
    """One line saying what the chosen tier is likely to cost.

    An estimate people can see beats a render they have to sit through to find
    out. The seconds come from the measured table, overwritten by this
    machine own numbers once it has rendered anything.
    """
    try:
        R = _render_mod()
        secs = R.measured_times().get(quality)
        if not secs:
            return ""
        cfg = R.PERFORMANCE.get(performance, {})
        # Low trades detail for memory and lands slightly faster; High dices
        # per pixel and lands slower. Both are small next to the quality tier.
        factor = {'LOW': 0.88, 'BALANCED': 1.0, 'HIGH': 1.18}.get(performance, 1.0)
        secs = secs * factor
        if secs < 90:
            t = "%d s" % round(secs)
        else:
            t = "%d min %02d s" % (int(secs // 60), int(secs - 60 * (secs // 60)))
        pct = R.PRESETS[quality]["resolution_percentage"]
        w = int(round(2560 * pct / 100.0))
        h = int(round(1440 * pct / 100.0))
        return "About %s a frame at %dx%d - %s" % (t, w, h, cfg.get("note", ""))
    except Exception:
        return ""


def device_notes(context):
    """Say it out loud when the render will be slow for a reason."""
    notes = []
    try:
        cy = context.scene.cycles
    except Exception:
        return notes
    if getattr(cy, "device", "CPU") == 'CPU':
        notes.append(("Rendering on CPU - expect roughly 14x longer", 'ERROR'))
    try:
        R = _render_mod()
        vram = R.gpu_vram_gb()
        p = props(context)
        if vram is not None and vram < 7.0 and p and p.quality == 'ARCHIVE':
            notes.append(("Archive at %.0f GB of VRAM may run out of memory"
                          % vram, 'ERROR'))
    except Exception:
        pass
    return notes


def state_notes(panel_id):
    notes = []
    if not bpy.data.objects.get(GLOBE):
        return [("No planet in this scene - use Create Planet System", 'ERROR')]
    ctl = _ctl_node(SURF)
    if panel_id == "civ" and ctl and "Tech Level" in ctl.inputs:
        if ctl.inputs["Tech Level"].default_value <= 0.0:
            notes.append(("Tech Level is 0 - civilisation is switched off", 'INFO'))
    if panel_id == "rings":
        r = bpy.data.objects.get(RINGS)
        if r is not None and r.hide_render:
            notes.append(("Rings are hidden for this preset", 'INFO'))
    if panel_id == "orbital":
        md = _mod(ORBITAL, "PLNT_OrbitalRig")
        if md:
            ids = _ids(md.node_group)
            if "Orbital Level" in ids:
                try:
                    if md.properties.inputs[ids["Orbital Level"]]["value"] < 0.5:
                        notes.append(("Orbital Level below 0.5 - nothing is built",
                                      'INFO'))
                except Exception:
                    pass
    if panel_id == "mega" and not bpy.data.objects.get(MEGA):
        notes.append(("No megastructures in this scene", 'INFO'))
    if panel_id == "patch":
        p = bpy.data.objects.get(PATCH)
        if p is not None and p.hide_render:
            notes.append(("Ground patch is hidden - enable it to render from "
                          "the surface", 'INFO'))
    return notes


# (panel, socket, short label). The short label matters: "Road Network
# Visibility" in a 200 px N-panel column leaves no room for the slider itself.
QUICK = [("terrain", "Seed", "Seed"),
         ("terrain", "Continent Coverage", "Land"),
         ("terrain", "Sea Level", "Sea Level"),
         ("terrain", "Relief Strength", "Relief"),
         ("civ", "Tech Level", "Tech Level"),
         ("clouds", "Cloud Coverage", "Cloud"),
         ("atmo", "Density", "Atmosphere"),
         ("orbital", "Orbital Level", "Orbital")]


def draw_quick(layout):
    """The eight controls that change a planet's identity, at top level."""
    col = layout.column(align=True)
    for panel_id, sock, label in QUICK:
        for src in SOURCES.get(panel_id, ()):
            r = resolve(src)
            if not r:
                continue
            kind, holder, ng = r
            if kind == "mod":
                ids = _ids(ng)
                if sock in ids:
                    slot = mod_slot(holder, ids[sock])
                    if slot is not None:
                        col.prop(slot, '["value"]', text=label or sock)
                    break
            else:
                s = holder.inputs.get(sock)
                if s is not None:
                    col.prop(s, "default_value", text=label or sock)
                    break


# --------------------------------------------------------------------------
# Scene properties
# --------------------------------------------------------------------------
def _render_mod():
    try:
        from . import render as _r
    except ImportError:
        import render as _r
    return _r


def _quality_update(self, context):
    try:
        _render_mod().apply_quality(self.quality, context.scene)
    except Exception:
        pass


def _performance_update(self, context):
    try:
        _render_mod().apply_performance(self.performance, context.scene)
        tag_update()
    except Exception:
        pass


def _time_update(self, context):
    try:
        from . import anim as _a
    except ImportError:
        try:
            import anim as _a
        except ImportError:
            return
    try:
        _a.sync(context.scene)
    except Exception:
        pass


def _sun_update(self, context):
    ns = presets_ns()
    fn = ns.get("sun")
    if fn:
        try:
            fn(self.sun_azimuth, self.sun_elevation)
        except Exception:
            pass


class PLNT_Props(bpy.types.PropertyGroup):
    preset: bpy.props.EnumProperty(
        name="Preset", items=preset_items,
        description="Starting point for a planet. Applying a preset resets "
                    "every look setting first, so presets never bleed into "
                    "one another")
    seed: bpy.props.IntProperty(
        name="Seed", default=2291, min=0, max=99999,
        description="Master seed. Same settings, different seed, completely "
                    "different planet")
    tier: bpy.props.EnumProperty(
        name="Detail", default='BASIC',
        items=[('BASIC', "Basic", "The controls that change the planet's identity"),
               ('ADVANCED', "Advanced", "Everything with an artistic effect"),
               ('ALL', "All", "Including values kept in sync automatically")],
        description="How many controls to show")
    search: bpy.props.StringProperty(
        name="Search", options={'TEXTEDIT_UPDATE'},
        description="Filter every panel by parameter name. Overrides the "
                    "Basic/Advanced setting while it has text in it")
    quality: bpy.props.EnumProperty(
        name="Quality", default='FAST',
        items=[('DRAFT', "Draft", "1280x720, 64 samples. Framing and colour"),
               ('FAST', "Fast", "1920x1080, 96 samples. A shareable frame in "
                                "well under a minute"),
               ('PREVIEW', "Preview", "1920x1080, 192 samples. For judging detail"),
               ('FINAL', "Final", "2560x1440, 512 adaptive samples. The "
                                  "delivery setting"),
               ('ARCHIVE', "Archive", "2048 samples and full dicing. Reference "
                                      "stills; wants more than 6 GB of VRAM")],
        update=_quality_update,
        description="What the picture is worth: resolution, samples and "
                    "displacement. Separate from Performance, which is what "
                    "the machine can afford")
    performance: bpy.props.EnumProperty(
        name="Performance", default='BALANCED',
        items=[('LOW', "Low", "Laptops and 4 GB cards. Coarser base mesh, "
                              "object-space dicing, fewer noise octaves"),
               ('BALANCED', "Balanced", "The tested setting on a 6 GB card"),
               ('HIGH', "High", "8 GB or more. Camera-relative dicing, every "
                                "octave, GPU denoising")],
        update=_performance_update,
        description="What this machine can afford. Changes cost, not intent")
    time_scale: bpy.props.FloatProperty(
        name="Time Scale", default=1.0, min=0.0, max=240.0,
        precision=4, update=_time_update,
        description="Hours of world time per second of footage. 0 freezes the "
                    "system; 1 turns the planet once in 24 seconds and takes a "
                    "satellite round its orbit in about 90")
    day_length_h: bpy.props.FloatProperty(
        name="Day Length", default=24.0, min=0.5, max=2000.0,
        unit='NONE', update=_time_update,
        description="Length of one rotation in hours. Everything else in the "
                    "system keeps its own real period, so a slow day gives a "
                    "sky full of fast-moving traffic")
    beacon_rate: bpy.props.FloatProperty(
        name="Beacon Rate", default=1.0, min=0.0, max=8.0,
        description="Navigation strobes per second of FOOTAGE, not of world "
                    "time. Around 1 Hz is what real collision beacons run at; "
                    "zero holds them steady on")
    motion_blur: bpy.props.BoolProperty(
        name="Motion Blur", default=False, update=_time_update,
        description="Shutter blur on everything that moves. Off by default: "
                    "at these speeds it costs real time and the stills do not "
                    "need it")
    disp_mode: bpy.props.EnumProperty(
        name="Displacement", default='GEOMETRY',
        items=[('NONE', "None", "No displacement. Fastest"),
               ('MICRO', "Micro", "Fine relief only; skips the terrain field "
                                  "while building the bump normal"),
               ('BUMP', "Bump", "Full detail as bump; silhouette unchanged"),
               ('GEOMETRY', "Geometry", "Full detail as real subdivided "
                                        "geometry, no bump. Measured 26% "
                                        "faster than True on this project, "
                                        "for an indistinguishable image"),
               ('TRUE', "True", "Full detail as real geometry plus bump. The "
                                "most expensive mode; only close-ups need it")],
        description="How surface relief is produced. This is the main "
                    "speed/quality trade-off")
    sun_azimuth: bpy.props.FloatProperty(
        name="Sun Azimuth", default=120.0, min=-360.0, max=360.0,
        update=_sun_update,
        description="Direction the sun comes from, in degrees around the planet")
    sun_elevation: bpy.props.FloatProperty(
        name="Sun Elevation", default=20.0, min=-90.0, max=90.0,
        update=_sun_update,
        description="Height of the sun above the planet's equator, in degrees. "
                    "Low angles give long terminators and raking light")
    shot: bpy.props.IntProperty(
        name="Shot", default=2, min=1, max=10,
        description="Which of the ten hero shots to frame up")
    clipboard: bpy.props.StringProperty(
        name="Settings JSON",
        description="Every current setting as JSON. Copy this to share a "
                    "planet; paste one in and press Paste to load it")
    # The preset dropdown is a CHOICE, not a report: it keeps showing
    # "earthlike" after forty edits, after a Randomise, and after loading
    # someone else's settings JSON, so it cannot be read as what is on screen.
    # These two say what actually is.
    applied_preset: bpy.props.StringProperty(
        name="Applied Preset", default="",
        description="The preset this planet was last built from")
    applied_hash: bpy.props.StringProperty(name="Applied Fingerprint", default="")
    modified: bpy.props.BoolProperty(
        name="Modified", default=False,
        description="Something has been changed since the preset was applied")


def props(context):
    return getattr(context.scene, "plnt", None)


# --------------------------------------------------------------------------
# Panels. Generated from params.PANELS so a new panel is one table entry.
# --------------------------------------------------------------------------
class PLNT_PT_main(bpy.types.Panel):
    bl_label = "PLNT Planet"
    bl_idname = "PLNT_PT_main"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PLNT Planet"

    def draw(self, context):
        lay = self.layout
        p = props(context)
        if p is None:
            lay.label(text="Add-on not fully registered", icon='ERROR')
            return
        if not bpy.data.objects.get(GLOBE):
            box = lay.box()
            box.label(text="No planet in this scene", icon='INFO')
            box.operator("plnt.create_system", icon='WORLD')
            return
        row = lay.row(align=True)
        row.prop(p, "preset", text="")
        row.prop(p, "seed", text="")
        row = lay.row(align=True)
        row.operator("plnt.apply_preset", icon='CHECKMARK')
        row.operator("plnt.randomize", icon='FILE_REFRESH')
        if p.applied_preset:
            lay.label(
                text="In scene: %s%s" % (p.applied_preset.replace("_", " ").title(),
                                         " (modified)" if p.modified else ""),
                icon='DOT' if p.modified else 'CHECKMARK')
        else:
            lay.label(text="In scene: unknown - press Apply", icon='QUESTION')
        lay.separator()
        box = lay.box()
        col = box.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        col.prop(p, "quality")
        col.prop(p, "performance")
        col.prop(p, "time_scale")
        est = quality_estimate(p.quality, p.performance)
        if est:
            box.label(text=est, icon='TIME')
        for text, ic in device_notes(context):
            box.label(text=text, icon=ic)

        lay.separator()
        lay.label(text="Quick")
        draw_quick(lay)
        lay.separator()
        row = lay.row(align=True)
        row.prop(p, "tier", expand=True)
        lay.prop(p, "search", icon='VIEWZOOM', text="")
        row = lay.row(align=True)
        row.operator("plnt.save_preset", icon='FILE_TICK')
        row.operator("plnt.load_preset", icon='FILE_FOLDER')


def _make_group(group_id, label, icon):
    """One parent panel per entry in params.GROUPS."""
    def draw(self, context):
        pass

    return type("PLNT_PT_g_" + group_id, (bpy.types.Panel,), {
        "bl_label": label,
        "bl_idname": "PLNT_PT_g_" + group_id,
        "bl_parent_id": "PLNT_PT_main",
        "bl_space_type": 'VIEW_3D',
        "bl_region_type": 'UI',
        "bl_category": "PLNT Planet",
        "bl_options": {'DEFAULT_CLOSED'},
        "draw": draw,
    })


GROUP_PANELS = [_make_group(gid, label, icon) for gid, label, icon in params.GROUPS]


def _make_panel(panel_id, label, icon):
    """One Panel class per entry in params.PANELS."""
    def draw(self, context):
        lay = self.layout
        p = props(context)
        for text, ic in state_notes(panel_id):
            lay.label(text=text, icon=ic)
        tier = 'ALL' if (p and p.search) else (p.tier if p else 'ADVANCED')
        rows = visible_sockets(panel_id, tier, p.search if p else "")
        if not rows:
            lay.label(text="Nothing matches" if (p and p.search)
                      else "Nothing to configure here", icon='DOT')
            return
        col = lay.column(align=True)
        col.use_property_split = True
        col.use_property_decorate = False
        for kind, holder, item, ident, _order in rows:
            draw_socket(col, kind, holder, item, ident)
        lay.separator()
        r = lay.row(align=True)
        op = r.operator("plnt.randomize_section", text="Randomise")
        op.panel = panel_id
        op = r.operator("plnt.reset_section", text="Reset")
        op.panel = panel_id

    return type("PLNT_PT_" + panel_id, (bpy.types.Panel,), {
        "bl_label": label,
        "bl_idname": "PLNT_PT_" + panel_id,
        "bl_parent_id": "PLNT_PT_g_" + params.group_of(panel_id),
        "bl_space_type": 'VIEW_3D',
        "bl_region_type": 'UI',
        "bl_category": "PLNT Planet",
        "bl_options": {'DEFAULT_CLOSED'},
        "draw": draw,
    })


GENERATED = [_make_panel(pid, label, icon) for pid, label, icon in params.PANELS
             if pid in SOURCES]


class PLNT_PT_sky(bpy.types.Panel):
    bl_label = "Sun & Sky"
    bl_idname = "PLNT_PT_sky"
    bl_parent_id = "PLNT_PT_g_sky"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PLNT Planet"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        lay = self.layout
        p = props(context)
        sun = bpy.data.objects.get("PLNT_Sun")
        if not sun:
            lay.label(text="No sun in this scene", icon='ERROR')
            return
        col = lay.column(align=True)
        col.use_property_split = True
        col.prop(p, "sun_azimuth")
        col.prop(p, "sun_elevation")
        col.separator()
        col.prop(p, "day_length_h")
        col.prop(p, "time_scale")
        col.prop(p, "beacon_rate")
        col.prop(p, "motion_blur")
        col.separator()
        col.operator("plnt.time_preset", text="Frozen").scale = 0.0
        row2 = col.row(align=True)
        row2.operator("plnt.time_preset", text="Real").scale = 0.000277778
        row2.operator("plnt.time_preset", text="Slow").scale = 0.1
        row2.operator("plnt.time_preset", text="Timelapse").scale = 1.0
        row2.operator("plnt.time_preset", text="Fast").scale = 6.0
        col.separator()
        col.prop(sun.data, "energy", text="Strength")
        col.prop(sun.data, "angle", text="Angular Size")
        col.prop(sun.data, "color", text="Colour")
        world = context.scene.world
        if world and world.node_tree:
            col.separator()
            col.label(text="Starfield")
            for n in world.node_tree.nodes:
                if n.label in ("STAR_SCALE", "STAR_GAIN", "NEBULA"):
                    for s in n.inputs:
                        if not s.links and hasattr(s, "default_value"):
                            col.prop(s, "default_value", text=n.label.title())
                            break


class PLNT_PT_camera(bpy.types.Panel):
    bl_label = "Camera"
    bl_idname = "PLNT_PT_camera"
    bl_parent_id = "PLNT_PT_g_scene"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = "PLNT Planet"
    bl_options = {'DEFAULT_CLOSED'}

    def draw(self, context):
        lay = self.layout
        p = props(context)
        row = lay.row(align=True)
        row.prop(p, "shot")
        row.operator("plnt.apply_shot", text="Frame")
        cam = context.scene.camera
        if cam and cam.type == 'CAMERA':
            col = lay.column(align=True)
            col.prop(cam.data, "lens")
            col.prop(cam.data, "clip_end")
        lay.operator("plnt.quick_render", icon='RENDER_STILL')


class PLNT_PT_render(bpy.types.Panel):
    """Render settings belong with render settings, not in the N-panel."""
    bl_label = "PLNT Planet"
    bl_idname = "PLNT_PT_render"
    bl_space_type = 'PROPERTIES'
    bl_region_type = 'WINDOW'
    bl_context = "render"

    def draw(self, context):
        lay = self.layout
        p = props(context)
        if p is None:
            return
        col = lay.column(align=True)
        col.prop(p, "quality")
        col.prop(p, "performance")
        col.prop(p, "disp_mode")
        est = quality_estimate(p.quality, p.performance)
        if est:
            col.label(text=est, icon='TIME')
        col.separator()
        col.operator("plnt.apply_quality", icon='CHECKMARK')
        col.separator()
        rd = context.scene.render
        col.prop(rd, "resolution_x", text="Resolution X")
        col.prop(rd, "resolution_y", text="Y")
        col.prop(context.scene.cycles, "samples")
        col.prop(context.scene.cycles, "dicing_rate")
        col.prop(rd, "filepath", text="Output")


# --------------------------------------------------------------------------
# Operators. All REGISTER|UNDO so every tweak is undoable.
# --------------------------------------------------------------------------
import json as _json
import random as _random


class _Base(bpy.types.Operator):
    bl_options = {'REGISTER', 'UNDO'}


class PLNT_OT_apply_preset(_Base):
    bl_idname = "plnt.apply_preset"
    bl_label = "Apply"
    bl_description = "Apply the selected preset at the current seed"

    def execute(self, context):
        p = props(context)
        fn = presets_ns().get("apply_preset")
        if not fn:
            self.report({'ERROR'}, "Preset table not found")
            return {'CANCELLED'}
        try:
            fn(p.preset, seed=p.seed)
        except Exception as ex:
            self.report({'ERROR'}, "Preset failed: %s" % ex)
            return {'CANCELLED'}
        sync_shared_terrain()
        tag_update()
        mark_applied(p, p.preset)
        self.report({'INFO'}, "%s @ seed %d" % (p.preset, p.seed))
        return {'FINISHED'}


class PLNT_OT_randomize(_Base):
    bl_idname = "plnt.randomize"
    bl_label = "Randomise"
    bl_description = "Roll a new seed and a new preset"

    def execute(self, context):
        p = props(context)
        fn = presets_ns().get("randomize")
        if not fn:
            self.report({'ERROR'}, "Preset table not found")
            return {'CANCELLED'}
        p.seed = _random.randint(0, 99999)
        name = fn(p.seed)
        sync_shared_terrain()
        tag_update()
        # randomize() jitters the terrain on top of the preset, so the scene
        # legitimately does not match the preset it started from
        mark_applied(p, name)
        p.modified = True
        self.report({'INFO'}, "%s @ seed %d" % (name, p.seed))
        return {'FINISHED'}


class PLNT_OT_randomize_section(_Base):
    bl_idname = "plnt.randomize_section"
    bl_label = "Randomise Section"
    bl_description = ("Randomise only this panel's parameters, within their "
                      "own ranges. Everything else is left alone")
    panel: bpy.props.StringProperty()

    def execute(self, context):
        n = held = 0
        for kind, holder, item, ident, _o in visible_sockets(self.panel, 'ALL', ""):
            if not params.randomisable(None, item.name):
                held += 1
                continue
            lo = getattr(item, "min_value", None)
            hi = getattr(item, "max_value", None)
            if lo is None or hi is None or item.bl_socket_idname != 'NodeSocketFloat':
                continue
            # Roll around the socket's OWN default, not the midpoint of its
            # range. Interface min/max are the legal range, not an artistic
            # one: Relief Strength is 0..400 with a default near 68, so a
            # midpoint roll produced 200-unit mountains on every planet and
            # made Randomise useless as a starting point.
            lo2, hi2 = max(lo, -1e6), min(hi, 1e6)
            base = getattr(item, "default_value", None)
            try:
                base = float(base)
            except (TypeError, ValueError):
                base = (lo2 + hi2) * 0.5
            base = max(lo2, min(hi2, base))
            span = (hi2 - lo2) * 0.20
            v = max(lo2, min(hi2, _random.uniform(base - span, base + span)))
            if kind == "mod":
                try:
                    holder.properties.inputs[ident]["value"] = v
                except Exception:
                    continue
            else:
                s = holder.inputs.get(item.name)
                if s is None:
                    continue
                s.default_value = v
            n += 1
        sync_shared_terrain()
        tag_update()
        msg = "Randomised %d parameters in %s" % (n, self.panel)
        if held:
            msg += " (%d structural values left alone)" % held
        self.report({'INFO'}, msg)
        return {'FINISHED'}


class PLNT_OT_reset_section(_Base):
    bl_idname = "plnt.reset_section"
    bl_label = "Reset Section"
    bl_description = "Put this panel back to the current preset's values"
    panel: bpy.props.StringProperty()

    def execute(self, context):
        p = props(context)
        ns = presets_ns()
        fn = ns.get("apply_preset")
        if not fn:
            self.report({'ERROR'}, "Preset table not found")
            return {'CANCELLED'}
        keep = snapshot_all()
        fn(p.preset, seed=p.seed)
        restore_all(keep, skip_panel=self.panel)
        sync_shared_terrain()
        tag_update()
        self.report({'INFO'}, "%s reset to %s" % (self.panel, p.preset))
        return {'FINISHED'}


def snapshot_all():
    """Every reachable parameter value, keyed by (panel, source, socket)."""
    out = {}
    for panel_id in SOURCES:
        for si, src in enumerate(SOURCES[panel_id]):
            r = resolve(src)
            if not r:
                continue
            kind, holder, ng = r
            ids = _ids(ng) if kind == "mod" else None
            for it, panel, _o, _t, _d in params.sockets_of(ng):
                if panel != panel_id:
                    continue
                key = "%s|%d|%s" % (panel_id, si, it.name)
                if kind == "mod":
                    ident = ids.get(it.name)
                    if ident is None:
                        continue
                    try:
                        v = holder.properties.inputs[ident]["value"]
                    except Exception:
                        continue
                else:
                    s = holder.inputs.get(it.name)
                    if s is None or not hasattr(s, "default_value"):
                        continue
                    v = s.default_value
                if hasattr(v, "__len__") and not isinstance(v, str):
                    v = list(v)
                if isinstance(v, (int, float, bool, list, str)):
                    out[key] = v
    return out


def snapshot_hash():
    """Stable fingerprint of every reachable parameter value.

    Rounded before hashing so that float noise from a depsgraph round-trip
    does not read as an edit.
    """
    import hashlib

    def norm(v):
        if isinstance(v, float):
            return round(v, 6)
        if isinstance(v, list):
            return [round(x, 6) if isinstance(x, float) else x for x in v]
        return v

    blob = _json.dumps({k: norm(v) for k, v in snapshot_all().items()},
                       sort_keys=True, separators=(",", ":"))
    return hashlib.md5(blob.encode("utf-8")).hexdigest()[:16]


def mark_applied(p, preset_name):
    """Record that the scene now matches `preset_name` exactly."""
    if p is None:
        return
    p.applied_preset = preset_name or ""
    p.applied_hash = snapshot_hash()
    p.modified = False


def refresh_modified(p):
    if p is None or not p.applied_hash:
        return
    now = snapshot_hash() != p.applied_hash
    if now != p.modified:
        p.modified = now


def restore_all(snap, skip_panel=None):
    written = 0
    for key, v in snap.items():
        panel_id, si, name = key.split("|", 2)
        if skip_panel and panel_id == skip_panel:
            continue
        try:
            src = SOURCES[panel_id][int(si)]
        except (KeyError, IndexError, ValueError):
            continue
        r = resolve(src)
        if not r:
            continue
        kind, holder, ng = r
        if kind == "mod":
            ident = _ids(ng).get(name)
            if ident is None:
                continue
            try:
                holder.properties.inputs[ident]["value"] = v
                written += 1
            except Exception:
                pass
        else:
            s = holder.inputs.get(name)
            if s is None:
                continue
            try:
                s.default_value = v
                written += 1
            except Exception:
                pass
    return written


class PLNT_OT_copy(_Base):
    bl_idname = "plnt.copy_settings"
    bl_label = "Copy"
    bl_description = "Write every current setting into the text box as JSON"

    def execute(self, context):
        p = props(context)
        p.clipboard = _json.dumps(snapshot_all(), separators=(",", ":"))
        self.report({'INFO'}, "Copied %d settings" % len(snapshot_all()))
        return {'FINISHED'}


class PLNT_OT_paste(_Base):
    bl_idname = "plnt.paste_settings"
    bl_label = "Paste"
    bl_description = "Load settings from the JSON in the text box"

    def execute(self, context):
        p = props(context)
        try:
            snap = _json.loads(p.clipboard)
        except Exception as ex:
            self.report({'ERROR'}, "Not valid settings JSON: %s" % ex)
            return {'CANCELLED'}
        n = restore_all(snap)
        sync_shared_terrain()
        tag_update()
        self.report({'INFO'}, "Applied %d settings" % n)
        return {'FINISHED'}


def user_preset_dir():
    """Where a saved planet lives.

    bpy.utils.extension_path_user is the only writable place an extension is
    allowed to use, and the manifest already asks for the files permission for
    exactly this. Falls back to the Blender config directory when running as
    loose scripts rather than as an installed extension.
    """
    import os
    try:
        d = bpy.utils.extension_path_user(__package__, path="presets",
                                          create=True)
        if d:
            return d
    except Exception:
        pass
    d = os.path.join(bpy.utils.user_resource('CONFIG', create=True),
                     "plnt_presets")
    os.makedirs(d, exist_ok=True)
    return d


def _safe_name(s):
    keep = "-_ ()"
    out = "".join(c for c in (s or "") if c.isalnum() or c in keep).strip()
    return out or "planet"


class PLNT_OT_save_preset(_Base):
    bl_idname = "plnt.save_preset"
    bl_label = "Save"
    bl_description = ("Save every current setting as a named preset on disk, "
                      "so it comes back in any scene and any file")
    name: bpy.props.StringProperty(name="Name", default="My Planet")

    def invoke(self, context, event):
        p = props(context)
        if p and p.applied_preset:
            self.name = p.applied_preset.replace("_", " ").title()
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        import os
        p = props(context)
        path = os.path.join(user_preset_dir(), _safe_name(self.name) + ".json")
        doc = {"name": self.name,
               "base": (p.applied_preset if p else ""),
               "seed": (p.seed if p else 0),
               "settings": snapshot_all()}
        try:
            with open(path, "w") as f:
                _json.dump(doc, f, indent=1, sort_keys=True)
        except Exception as ex:
            self.report({'ERROR'}, "Could not save: %s" % ex)
            return {'CANCELLED'}
        self.report({'INFO'}, "Saved %s" % path)
        return {'FINISHED'}


def _user_preset_items(self, context):
    import os
    try:
        d = user_preset_dir()
        names = sorted(f[:-5] for f in os.listdir(d) if f.endswith(".json"))
    except Exception:
        names = []
    if not names:
        return [('NONE', "(no saved planets)", "")]
    return [(n, n, "Load %s" % n) for n in names]


class PLNT_OT_load_preset(_Base):
    bl_idname = "plnt.load_preset"
    bl_label = "Load"
    bl_description = "Load a planet saved with Save"
    which: bpy.props.EnumProperty(name="Saved Planet", items=_user_preset_items)

    def invoke(self, context, event):
        return context.window_manager.invoke_props_dialog(self)

    def execute(self, context):
        import os
        if self.which in ("", "NONE"):
            self.report({'ERROR'}, "Nothing saved yet")
            return {'CANCELLED'}
        path = os.path.join(user_preset_dir(), self.which + ".json")
        try:
            with open(path) as f:
                doc = _json.load(f)
        except Exception as ex:
            self.report({'ERROR'}, "Could not load: %s" % ex)
            return {'CANCELLED'}
        n = restore_all(doc.get("settings") or {})
        p = props(context)
        if p is not None:
            if doc.get("seed"):
                p.seed = int(doc["seed"])
            mark_applied(p, doc.get("name") or self.which)
            p.modified = True
        sync_shared_terrain()
        tag_update()
        self.report({'INFO'}, "Loaded %s (%d settings)" % (self.which, n))
        return {'FINISHED'}


class PLNT_OT_time_preset(_Base):
    bl_idname = "plnt.time_preset"
    bl_label = "Time"
    bl_description = "Set Time Scale to a named speed"
    scale: bpy.props.FloatProperty(default=1.0)

    def execute(self, context):
        p = props(context)
        p.time_scale = self.scale
        self.report({'INFO'}, "%g world hours per second" % self.scale)
        return {'FINISHED'}


class PLNT_OT_apply_performance(_Base):
    bl_idname = "plnt.apply_performance"
    bl_label = "Apply Performance"
    bl_description = "Apply the chosen performance tier to this scene"

    def execute(self, context):
        p = props(context)
        info = _render_mod().apply_performance(p.performance, context.scene)
        tag_update()
        self.report({'INFO'}, "%s: subdiv %s, dicing %s, detail %s"
                    % (info["level"], info.get("subdiv"),
                       (info.get("adaptive") or [("", "", "")])[0][1],
                       (info.get("detail") or {}).get("scale")))
        return {'FINISHED'}


class PLNT_OT_apply_quality(_Base):
    bl_idname = "plnt.apply_quality"
    bl_label = "Apply Render Settings"
    bl_description = "Apply the chosen quality preset and displacement mode"

    def execute(self, context):
        p = props(context)
        try:
            from . import render as _r, lod as _l
        except ImportError:
            import render as _r
            import lod as _l
        info = _r.apply_quality(p.quality, context.scene,
                                displacement=p.disp_mode)
        _r.apply_performance(p.performance, context.scene)
        tag_update()
        self.report({'INFO'}, "%s at %s performance, displacement %s, %d samples"
                    % (p.quality, p.performance, p.disp_mode, info["samples"]))
        return {'FINISHED'}


class PLNT_OT_apply_shot(_Base):
    bl_idname = "plnt.apply_shot"
    bl_label = "Frame"
    bl_description = "Frame the camera using one of the ten hero shots"

    def execute(self, context):
        try:
            import importlib as _il
            _s = _il.import_module(".shots", __package__.rsplit(".", 1)[0]) \
                if __package__ and "." in __package__ else None
            if _s is None:
                from . import shots as _s
        except Exception:
            self.report({'ERROR'}, "Shot definitions not available")
            return {'CANCELLED'}
        p = props(context)
        shot = next((s for s in _s.SHOTS if s["n"] == p.shot), None)
        if not shot:
            self.report({'ERROR'}, "No shot %d" % p.shot)
            return {'CANCELLED'}
        info = _s.apply_shot(shot)
        self.report({'INFO'}, "Shot %d: %s" % (p.shot, info))
        return {'FINISHED'}


class PLNT_OT_quick_render(_Base):
    bl_idname = "plnt.quick_render"
    bl_label = "Quick Render"
    bl_description = ("Render a small preview to the Image Editor. Everything "
                      "else here is render-only, so this is how you see what a "
                      "slider actually did")

    def execute(self, context):
        sc = context.scene
        keep = (sc.render.resolution_x, sc.render.resolution_y,
                sc.render.resolution_percentage, sc.cycles.samples,
                sc.cycles.use_denoising)
        sc.render.resolution_x, sc.render.resolution_y = 480, 270
        sc.render.resolution_percentage = 100
        sc.cycles.samples = 32
        sc.cycles.use_denoising = True
        try:
            bpy.ops.render.render('INVOKE_DEFAULT', write_still=False)
        finally:
            (sc.render.resolution_x, sc.render.resolution_y,
             sc.render.resolution_percentage, sc.cycles.samples,
             sc.cycles.use_denoising) = keep
        return {'FINISHED'}


class PLNT_OT_create_system(_Base):
    bl_idname = "plnt.create_system"
    bl_label = "Create Planet System"
    bl_description = ("Build a complete planet in this scene: globe, clouds, "
                      "atmosphere, rings, orbital infrastructure, sun rig, "
                      "cameras and starfield")
    preset: bpy.props.StringProperty(default="earthlike")
    seed: bpy.props.IntProperty(default=2291)

    def execute(self, context):
        try:
            from . import scene as _sc
        except ImportError:
            try:
                import scene as _sc
            except ImportError:
                self.report({'ERROR'}, "Scene builder not installed")
                return {'CANCELLED'}
        try:
            info = _sc.build_scene_scaffold(preset=self.preset, seed=self.seed)
        except Exception as ex:
            # a half-built scene is worse than none: say what broke
            self.report({'ERROR'}, "Build failed: %s" % ex)
            return {'CANCELLED'}
        _NS_CACHE.clear()
        sync_shared_terrain()
        p = props(context)
        if p is not None:
            p.preset = self.preset
            p.seed = self.seed
        mark_applied(p, self.preset)
        self.report({'INFO'}, "Planet system created: %s" % info)
        return {'FINISHED'}


class PLNT_OT_remove_system(_Base):
    bl_idname = "plnt.remove_system"
    bl_label = "Remove Planet System"
    bl_description = "Delete every PLNT object, node group and material"

    def execute(self, context):
        # core.scene.remove_system also clears lights, cameras and the world,
        # which this copy did not, so "Remove" used to leave the sun rig,
        # both cameras and the starfield behind and Create rebuilt on top.
        try:
            from . import scene as _sc
        except ImportError:
            import scene as _sc
        removed = _sc.remove_system()
        _NS_CACHE.clear()
        self.report({'INFO'}, "Removed %d datablocks" % removed)
        return {'FINISHED'}


# --------------------------------------------------------------------------
# Registration
# --------------------------------------------------------------------------
_depsgraph_guard = {"busy": False}


def _on_depsgraph(scene, depsgraph):
    """Keep the terrain values the globe rig and the shaders share in step.

    Without this, dragging Continent Scale moves the geometry while the
    coastline stays where it was, because the two evaluate the same field from
    separate copies of the parameters.
    """
    if _depsgraph_guard["busy"]:
        return
    _depsgraph_guard["busy"] = True
    try:
        sync_shared_terrain()
        refresh_modified(getattr(scene, "plnt", None))
    except Exception:
        pass
    finally:
        _depsgraph_guard["busy"] = False


# Parent panels must register before the children that name them.
CLASSES = ([PLNT_Props, PLNT_PT_main] + GROUP_PANELS + GENERATED +
           [PLNT_PT_sky, PLNT_PT_camera, PLNT_PT_render,
            PLNT_OT_apply_preset, PLNT_OT_randomize, PLNT_OT_randomize_section,
            PLNT_OT_reset_section, PLNT_OT_copy, PLNT_OT_paste,
            PLNT_OT_save_preset, PLNT_OT_load_preset,
            PLNT_OT_apply_performance, PLNT_OT_time_preset,
            PLNT_OT_apply_quality, PLNT_OT_apply_shot, PLNT_OT_quick_render,
            PLNT_OT_create_system, PLNT_OT_remove_system])


def register():
    for c in CLASSES:
        try:
            bpy.utils.register_class(c)
        except Exception:
            pass
    bpy.types.Scene.plnt = bpy.props.PointerProperty(type=PLNT_Props)
    if _on_depsgraph not in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.append(_on_depsgraph)


def unregister():
    if _on_depsgraph in bpy.app.handlers.depsgraph_update_post:
        bpy.app.handlers.depsgraph_update_post.remove(_on_depsgraph)
    for c in reversed(CLASSES):
        try:
            bpy.utils.unregister_class(c)
        except Exception:
            pass
    if hasattr(bpy.types.Scene, "plnt"):
        del bpy.types.Scene.plnt


def audit():
    """Usability acceptance check: no orphaned sockets, no missing tooltips.

    Returns {"scene": False} when there is no planet to inspect, rather than
    reporting every socket as an orphan: an empty scene is not a UI defect.
    """
    if not bpy.data.objects.get(GLOBE):
        return {"scene": False, "reachable": 0, "orphans": [], "undocumented": []}
    reachable, orphan, undocumented = set(), [], []
    for panel_id in SOURCES:
        for src in SOURCES[panel_id]:
            r = resolve(src)
            if not r:
                continue
            _kind, _holder, ng = r
            for it, panel, _o, _t, desc in params.sockets_of(ng):
                reachable.add((ng.name, it.name))
                if panel not in SOURCES:
                    orphan.append((ng.name, it.name, panel))
                if not desc:
                    undocumented.append((ng.name, it.name))
    for ng in bpy.data.node_groups:
        if params.owner_of(ng.name) is None or params.is_internal(ng.name):
            continue
        for it, _p, _o, _t, _d in params.sockets_of(ng):
            if (ng.name, it.name) not in reachable:
                orphan.append((ng.name, it.name, "<no panel draws this>"))
    return {"scene": True, "reachable": len(reachable), "orphans": orphan,
            "undocumented": undocumented}
