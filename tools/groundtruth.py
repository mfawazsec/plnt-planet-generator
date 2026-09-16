"""Phase 0: dump every render-relevant fact from the live .blend.

  flatpak run --command=blender org.blender.Blender -b <abs.blend> \
    --enable-autoexec -P <abs>/tools/groundtruth.py

Writes logs/captured_state.json. These values exist ONLY inside the .blend and
are unrecoverable from source; this is also the reproducibility snapshot.
"""
import bpy, os, json, sys

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(D, "logs", "captured_state.json")


def rna_dump(owner, skip=()):
    """Every readable non-pointer property of an RNA struct."""
    out = {}
    for p in owner.bl_rna.properties:
        k = p.identifier
        if k in ("rna_type",) or k in skip:
            continue
        try:
            v = getattr(owner, k)
        except Exception:
            continue
        if isinstance(v, (int, float, bool, str)):
            out[k] = v
        elif hasattr(v, "__len__") and not hasattr(v, "bl_rna"):
            try:
                out[k] = list(v)
            except Exception:
                pass
    return out


res = {"blend": bpy.data.filepath, "version": bpy.app.version_string}

# ---- modifier stacks -------------------------------------------------------
objs = []
dg = bpy.context.evaluated_depsgraph_get()
for ob in bpy.data.objects:
    e = {"name": ob.name, "type": ob.type,
         "hide_render": ob.hide_render, "hide_viewport": ob.hide_viewport,
         "visible_camera": getattr(ob, "visible_camera", None),
         "visible_shadow": getattr(ob, "visible_shadow", None),
         "location": [round(c, 3) for c in ob.location],
         "scale": [round(c, 4) for c in ob.scale],
         "parent": ob.parent.name if ob.parent else None,
         "materials": [m.name if m else None for m in ob.data.materials]
                      if getattr(ob, "data", None) and hasattr(ob.data, "materials") else [],
         "modifiers": []}
    for md in ob.modifiers:
        m = {"name": md.name, "type": md.type,
             "show_render": md.show_render, "show_viewport": md.show_viewport}
        if md.type == 'SUBSURF':
            for k in ("subdivision_type", "levels", "render_levels", "quality",
                      "use_adaptive_subdivision", "adaptive_pixel_size",
                      "use_limit_surface", "uv_smooth", "boundary_smooth"):
                m[k] = getattr(md, k, "<absent>")
        if md.type == 'NODES':
            m["node_group"] = md.node_group.name if md.node_group else None
            try:
                m["inputs"] = {k: (v["value"] if isinstance(v, dict) and "value" in v
                                   else str(v))
                               for k, v in md.properties.get("inputs", {}).items()}
            except Exception as ex:
                m["inputs_error"] = str(ex)
        e["modifiers"].append(m)
    # evaluated geometry
    try:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh() if ev.type in ('MESH', 'CURVE', 'SURFACE', 'META', 'FONT') else None
        if me:
            e["eval_verts"] = len(me.vertices)
            e["eval_polys"] = len(me.polygons)
            e["eval_tris"] = sum(len(p.vertices) - 2 for p in me.polygons)
            e["eval_attrs"] = [(a.name, a.domain, a.data_type) for a in me.attributes]
            ev.to_mesh_clear()
    except Exception as ex:
        e["eval_error"] = str(ex)
    if ob.type == 'LIGHT':
        e["light"] = {"type": ob.data.type, "energy": ob.data.energy,
                      "angle": getattr(ob.data, "angle", None),
                      "color": list(ob.data.color)}
    if ob.type == 'CAMERA':
        e["camera"] = {"lens": ob.data.lens, "sensor_width": ob.data.sensor_width,
                       "clip_start": ob.data.clip_start, "clip_end": ob.data.clip_end}
    objs.append(e)
res["objects"] = objs

# ---- materials -------------------------------------------------------------
mats = []
for ma in bpy.data.materials:
    m = {"name": ma.name, "users": ma.users,
         "displacement_method": getattr(ma, "displacement_method", "<absent>"),
         "nodes": len(ma.node_tree.nodes) if ma.node_tree else 0}
    cy = getattr(ma, "cycles", None)
    if cy:
        m["cycles"] = rna_dump(cy)
    if ma.node_tree:
        out = next((n for n in ma.node_tree.nodes if n.type == 'OUTPUT_MATERIAL'), None)
        if out:
            m["output_linked"] = {s.name: bool(s.links) for s in out.inputs}
        m["groups"] = sorted({n.node_tree.name for n in ma.node_tree.nodes
                              if n.type == 'GROUP' and n.node_tree})
    mats.append(m)
res["materials"] = mats

# ---- node groups -----------------------------------------------------------
ngs = []
for ng in bpy.data.node_groups:
    g = {"name": ng.name, "type": ng.bl_idname, "users": ng.users,
         "nodes": len(ng.nodes),
         "subdiv_nodes": [n.bl_idname for n in ng.nodes
                          if 'Subdivi' in n.bl_idname or 'Subdivide' in n.bl_idname],
         "inputs": [(i.name, i.bl_socket_idname,
                     bool(getattr(i, "description", "")))
                    for i in ng.interface.items_tree
                    if getattr(i, "item_type", "") == 'SOCKET'
                    and getattr(i, "in_out", "") == 'INPUT']}
    ngs.append(g)
res["node_groups"] = ngs
res["total_shader_nodes_PLNT_Surface"] = next(
    (m["nodes"] for m in mats if m["name"] == "PLNT_Surface"), None)

# ---- scene / cycles --------------------------------------------------------
sc = bpy.context.scene
res["render"] = rna_dump(sc.render, skip=("stamp_note_text",))
res["cycles"] = rna_dump(sc.cycles)
res["cycles_dicing_camera"] = sc.cycles.dicing_camera.name if sc.cycles.dicing_camera else None
res["scene_camera"] = sc.camera.name if sc.camera else None
res["view_transform"] = sc.view_settings.view_transform
res["look"] = sc.view_settings.look
res["world"] = {"name": sc.world.name if sc.world else None,
                "nodes": len(sc.world.node_tree.nodes) if sc.world and sc.world.node_tree else 0}

# ---- devices ---------------------------------------------------------------
try:
    prefs = bpy.context.preferences.addons["cycles"].preferences
    prefs.refresh_devices()
    res["compute_device_type"] = prefs.compute_device_type
    res["devices"] = [(d.name, d.type, d.use) for d in prefs.devices]
except Exception as ex:
    res["devices_error"] = str(ex)

# ---- the two gate questions ------------------------------------------------
subsurf = [(o["name"], m) for o in objs for m in o["modifiers"] if m["type"] == 'SUBSURF']
res["GATE_subsurf_modifiers"] = subsurf
res["GATE_subsurf_present"] = bool(subsurf)
res["GATE_adaptive_active"] = any(m.get("use_adaptive_subdivision") for _, m in subsurf)
surf = next((m for m in mats if m["name"] == "PLNT_Surface"), None)
res["GATE_surface_emission_sampling"] = (surf or {}).get("cycles", {}).get("emission_sampling")
res["GATE_surface_displacement_method"] = (surf or {}).get("displacement_method")
res["GATE_globe_tris"] = next((o.get("eval_tris") for o in objs if o["name"] == "PLNT_Globe"), None)

os.makedirs(os.path.dirname(OUT), exist_ok=True)
with open(OUT, "w") as f:
    json.dump(res, f, indent=1, default=str)

print("GT_GATE " + json.dumps({k: v for k, v in res.items() if k.startswith("GATE_")}), flush=True)
print("GT_WROTE " + OUT, flush=True)
