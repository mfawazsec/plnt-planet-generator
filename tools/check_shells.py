import bpy, json
res = {}
for n in ("PLNT_Clouds", "PLNT_Atmosphere", "PLNT_Rings", "PLNT_Globe"):
    ob = bpy.data.objects.get(n)
    if not ob:
        res[n] = "MISSING"
        continue
    e = {"hide_render": ob.hide_render, "hide_viewport": ob.hide_viewport,
         "visible_camera": getattr(ob, "visible_camera", None),
         "mesh_materials": [m.name if m else None for m in ob.data.materials],
         "mods": [(m.name, m.type, m.node_group.name if getattr(m, "node_group", None) else None,
                   m.show_render) for m in ob.modifiers]}
    for m in ob.modifiers:
        if m.type == 'NODES' and m.node_group:
            ids = {i.name: i.identifier for i in m.node_group.interface.items_tree
                   if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
                   and i.socket_type != 'NodeSocketGeometry'}
            vals = {}
            for k, ident in ids.items():
                try:
                    slot = m.properties.inputs[ident]
                    vals[k] = slot["value"] if hasattr(slot, "keys") and "value" in slot.keys() else str(slot)
                except Exception as ex:
                    vals[k] = "ERR:%s" % ex
            e["inputs"] = {k: (v.name if hasattr(v, "name") else v) for k, v in vals.items()}
    dg = bpy.context.evaluated_depsgraph_get()
    try:
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        e["eval_tris"] = sum(len(p.vertices) - 2 for p in me.polygons) if me else 0
        e["eval_mats"] = [m.name if m else None for m in me.materials] if me else []
        if me:
            ev.to_mesh_clear()
    except Exception as ex:
        e["eval_error"] = str(ex)
    res[n] = e
for mn in ("PLNT_Clouds", "PLNT_Atmosphere"):
    ma = bpy.data.materials.get(mn)
    if ma and ma.node_tree:
        ctl = ma.node_tree.nodes.get("PLNT_CTL")
        res["MAT_" + mn] = {
            "group": ctl.node_tree.name if ctl and ctl.node_tree else None,
            "inputs": {s.name: (list(s.default_value) if hasattr(s.default_value, "__len__")
                                else s.default_value)
                       for s in ctl.inputs if hasattr(s, "default_value")} if ctl else None,
            "emission_sampling": getattr(ma.cycles, "emission_sampling", None),
            "output_links": {s.name: bool(s.links) for n2 in ma.node_tree.nodes
                             if n2.type == 'OUTPUT_MATERIAL' for s in n2.inputs},
        }
print("SHELLS " + json.dumps(res, default=str), flush=True)
