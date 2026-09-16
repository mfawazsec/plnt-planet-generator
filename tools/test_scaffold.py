"""Build a whole planet system from an empty scene and report what happened.

Runs on --factory-startup so it cannot touch PLNT_PlanetGen.blend. Nothing is
saved. This is the acceptance test for "few clicks and have a planet".
"""
import bpy, os, sys, json, traceback

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, "core"))
res = {}

try:
    import scene
    # ringed_ice so the new annulus geometry is actually exercised; earthlike
    # hides the rings, which makes them evaluate to nothing.
    res["steps"] = scene.build_scene_scaffold(preset="ringed_ice", seed=5514,
                                              subdiv=7, quality='DRAFT',
                                              directory=D)
    res["ok"] = True
except Exception as ex:
    res["ok"] = False
    res["error"] = "%s: %s" % (type(ex).__name__, ex)
    res["trace"] = traceback.format_exc().splitlines()[-12:]

if res.get("ok"):
    dg = bpy.context.evaluated_depsgraph_get()
    objs = {}
    for ob in bpy.data.objects:
        if not ob.name.startswith("PLNT"):
            continue
        e = {"type": ob.type, "hide_render": ob.hide_render,
             "mods": [(m.name, m.type) for m in ob.modifiers]}
        try:
            ev = ob.evaluated_get(dg)
            if ev.type == 'MESH':
                me = ev.to_mesh()
                if me:
                    e["verts"] = len(me.vertices)
                    e["tris"] = sum(len(p.vertices) - 2 for p in me.polygons)
                    ev.to_mesh_clear()
        except Exception as ex:
            e["eval_error"] = str(ex)
        objs[ob.name] = e
    res["objects"] = objs
    res["materials"] = sorted(m.name for m in bpy.data.materials
                              if m.name.startswith("PLNT"))
    res["node_groups"] = len([g for g in bpy.data.node_groups
                              if g.name.startswith("PLNT")])
    # the driver hazard: SCRIPTED drivers need autoexec unless they are simple
    drv = []
    for mat in bpy.data.materials:
        if not mat.node_tree or not mat.node_tree.animation_data:
            continue
        for fc in mat.node_tree.animation_data.drivers:
            drv.append({"path": fc.data_path,
                        "type": fc.driver.type,
                        "simple": getattr(fc.driver, "is_simple_expression", None),
                        "valid": not fc.driver.is_valid
                        if hasattr(fc.driver, "is_valid") else None})
    res["drivers"] = {"count": len(drv), "sample": drv[:3],
                      "all_simple": all(d["simple"] for d in drv) if drv else None}
    # dead-node / unlinked-output sweep across every generated group. This is
    # the class of bug that left Ring Seed computed and never connected.
    hygiene = {}
    for g in bpy.data.node_groups:
        if not g.name.startswith("PLNT"):
            continue
        dead = [n.label or n.name for n in g.nodes
                if n.bl_idname not in ('NodeGroupOutput',)
                and not any(sk.links for sk in n.outputs)]
        unl = [sk.name for n in g.nodes if n.bl_idname == 'NodeGroupOutput'
               for sk in n.inputs if not sk.links and sk.name != ""]
        if dead or unl:
            hygiene[g.name] = {"dead": dead, "unlinked_outputs": unl}
    res["hygiene"] = hygiene
    res["group_sizes"] = {g.name: len(g.nodes) for g in bpy.data.node_groups
                          if g.name.startswith("PLNT")}

    # Inert inputs: a group input that cannot reach the group output does
    # nothing at all. This is the generalisation of the Ring Seed bug, where
    # the seed was computed into a node whose output was never connected, so
    # every seed produced identical rings.
    inert = {}
    for g in bpy.data.node_groups:
        if not g.name.startswith("PLNT"):
            continue
        fwd = {}
        for lk in g.links:
            fwd.setdefault(lk.from_node.name, set()).add(lk.to_node.name)
        outs = [n.name for n in g.nodes if n.bl_idname == 'NodeGroupOutput']
        gi_nodes = [n for n in g.nodes if n.bl_idname == 'NodeGroupInput']
        dead_names = []
        for gi in gi_nodes:
            for sk in gi.outputs:
                if not sk.name or not sk.enabled:
                    continue
                if not sk.links:
                    continue
                seen, stack = set(), [lk.to_node.name for lk in sk.links]
                reached = False
                while stack:
                    cur = stack.pop()
                    if cur in seen:
                        continue
                    seen.add(cur)
                    if cur in outs:
                        reached = True
                        break
                    stack.extend(fwd.get(cur, ()))
                if not reached:
                    dead_names.append(sk.name)
        if dead_names:
            inert[g.name] = sorted(set(dead_names))
    res["inert_inputs"] = inert

    # open the gates so ring and orbital geometry can be counted
    try:
        import importlib.util as _i
        for ob_name, mod_name, vals in (
                ("PLNT_Orbital", "PLNT_OrbitalRig", {"Orbital Level": 9.0}),
                ("PLNT_Mega", "PLNT_MegaRig", {"Mega Scale": 9.5})):
            ob = bpy.data.objects.get(ob_name)
            if ob and ob.modifiers:
                scene._set_mod_inputs(ob.modifiers[0], vals)
        r = bpy.data.objects.get("PLNT_Rings")
        if r:
            r.hide_viewport = False
        bpy.context.view_layer.update()
        dg2 = bpy.context.evaluated_depsgraph_get()
        gated = {}
        for n in ("PLNT_Rings", "PLNT_Orbital"):
            ob = bpy.data.objects.get(n)
            if not ob:
                continue
            ev = ob.evaluated_get(dg2)
            me = ev.to_mesh()
            gated[n] = {"verts": len(me.vertices) if me else 0,
                        "tris": sum(len(p.vertices) - 2 for p in me.polygons)
                        if me else 0}
            if me:
                ev.to_mesh_clear()
        res["gated"] = gated
    except Exception as ex:
        res["gated"] = {"error": str(ex)}

    # UI reachability audit with a real scene present
    try:
        import ui
        ui.register()
        res["audit"] = ui.audit()
        ui.unregister()
    except Exception as ex:
        res["audit"] = {"error": str(ex)}

    # ---- v3 regressions ---------------------------------------------------
    # Each of these is a bug that shipped once. They are cheap to check and
    # expensive to find again.
    v3 = {}

    # 1. Every rig slider must resolve to a draggable value. On 5.x a Geometry
    #    Nodes modifier input is an ID property GROUP, so the panel drew the
    #    group and every slider in the add-on read "ID Property Group".
    try:
        import ui as _ui
        bad = []
        checked = 0
        for panel_id, srcs in _ui.SOURCES.items():
            for src in srcs:
                if src[0] != "mod":
                    continue
                md = _ui._mod(src[1], src[2])
                if not md:
                    continue
                for it in md.node_group.interface.items_tree:
                    if getattr(it, "item_type", "") != 'SOCKET' or it.in_out != 'INPUT':
                        continue
                    if it.socket_type == 'NodeSocketGeometry':
                        continue
                    slot = _ui.mod_slot(md, it.identifier)
                    checked += 1
                    if slot is None or "value" not in slot.keys():
                        bad.append("%s/%s" % (md.name, it.name))
        v3["drawable_sliders"] = {"checked": checked, "broken": bad}
    except Exception as ex:
        v3["drawable_sliders"] = {"error": str(ex)}

    # 2. apply_preset never wrote the megastructure rig, so the "megastructure"
    #    preset built no megastructures.
    try:
        import importlib.util as _iu
        sp = _iu.spec_from_file_location("plnt_presets", os.path.join(D, "PLNT_presets.py"))
        pm = _iu.module_from_spec(sp)
        sys.modules["plnt_presets"] = pm
        sp.loader.exec_module(pm)
        pm.apply_preset("megastructure", seed=6690)
        mm = bpy.data.objects["PLNT_Mega"].modifiers["PLNT_MegaRig"]
        ids = {i.name: i.identifier for i in mm.node_group.interface.items_tree
               if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'}
        v3["mega_written"] = {
            "mega_scale": mm.properties.inputs[ids["Mega Scale"]]["value"],
            "hidden": bpy.data.objects["PLNT_Mega"].hide_render}
    except Exception as ex:
        v3["mega_written"] = {"error": str(ex)}

    # 3. The night-side road network is segments between cities now, not the
    #    edge set of an unrelated Voronoi.
    try:
        sg = bpy.data.node_groups["PLNT_SurfaceShader"]
        labels = {n.label for n in sg.nodes if n.label}
        v3["roads"] = {"segment_model": "citycells_f2" in labels,
                       "old_cell_edges": "roadcells" in labels}
    except Exception as ex:
        v3["roads"] = {"error": str(ex)}

    # 4. Every shader that asks whether a point is in daylight must transform
    #    the sun vector into the space its coordinates are in, or the planet
    #    cannot turn without taking the terminator with it.
    try:
        want = {}
        for gn in ("PLNT_SurfaceShader", "PLNT_PatchShader", "PLNT_AtmoShader",
                   "PLNT_RingShader"):
            g2 = bpy.data.node_groups.get(gn)
            if not g2:
                continue
            want[gn] = any(n.bl_idname == 'ShaderNodeVectorTransform'
                           for n in g2.nodes)
        v3["sun_in_object_space"] = want
    except Exception as ex:
        v3["sun_in_object_space"] = {"error": str(ex)}

    # 5. The clock has to reach both shading and geometry, and the drivers must
    #    read scene ID properties so a headless render still animates.
    try:
        clocks = {}
        for g2 in bpy.data.node_groups:
            for n in g2.nodes:
                if n.label in ("PLNT_TIME", "PLNT_TS", "PLNT_SPIN"):
                    clocks.setdefault(n.label, []).append(g2.name)
        paths = set()
        for coll in (bpy.data.node_groups, bpy.data.materials, bpy.data.objects):
            for dblock in coll:
                tree = dblock if hasattr(dblock, "nodes") else getattr(dblock, "node_tree", None)
                for holder in (tree, dblock):
                    ad = getattr(holder, "animation_data", None) if holder else None
                    if not ad:
                        continue
                    for fc in ad.drivers:
                        for var in fc.driver.variables:
                            for tgt in var.targets:
                                if tgt.data_path:
                                    paths.add(tgt.data_path)
        v3["clock"] = {"nodes": {k: len(v) for k, v in clocks.items()},
                       "driver_paths": sorted(paths),
                       "no_addon_dependency":
                           not any(p.startswith("plnt.") for p in paths)}
    except Exception as ex:
        v3["clock"] = {"error": str(ex)}

    # 6. The sun vector is DRIVEN. Every group that carries a SUNVEC node must
    #    still have three drivers pointing at PLNT_SunDir. This is here because
    #    adding the animation clock wiped them: _drive_time called
    #    animation_data_clear() on node.id_data, which is the whole node group,
    #    and the frames came back uniformly lit with nothing in the graph
    #    looking wrong.
    try:
        sun = {}
        for g2 in bpy.data.node_groups:
            if not any(n.label == "SUNVEC" for n in g2.nodes):
                continue
            ad = g2.animation_data
            sun[g2.name] = len(ad.drivers) if ad else 0
        v3["sunvec_drivers"] = sun
        v3["sunvec_ok"] = all(v >= 3 for v in sun.values()) and bool(sun)
    except Exception as ex:
        v3["sunvec_drivers"] = {"error": str(ex)}

    # 7. One sun convention. PLNT_Sun must be left at its base rotation of
    #    (0, 90, 0); the elevation lives on the pivot. Two functions used to
    #    disagree about this by 90 degrees of azimuth.
    try:
        import math as _m
        s = bpy.data.objects.get("PLNT_Sun")
        r = [round(x, 4) for x in s.rotation_euler] if s else None
        v3["sun_base_rot"] = r
        v3["sun_convention_ok"] = bool(
            r and abs(r[0]) < 1e-3 and abs(r[1] - _m.pi * 0.5) < 1e-3
            and abs(r[2]) < 1e-3)
    except Exception as ex:
        v3["sun_base_rot"] = {"error": str(ex)}

    # 8. The sky must not out-light the sun. The nebula is a full-sphere
    #    emitter; at its old strength it was seven times the sun and lit every
    #    night side in the set.
    try:
        w = bpy.context.scene.world
        neb = None
        if w and w.node_tree:
            for n in w.node_tree.nodes:
                if n.label == "NEBULA":
                    neb = round(float(n.inputs["Scale"].default_value), 5)
        v3["nebula_scale"] = neb
        v3["nebula_ok"] = neb is not None and neb <= 0.08
    except Exception as ex:
        v3["nebula_scale"] = {"error": str(ex)}

    res["v3"] = v3

print("SCAFFOLD " + json.dumps(res, indent=1, default=str), flush=True)
