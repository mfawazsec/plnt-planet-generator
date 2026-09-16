"""Count instanced geometry properly: to_mesh() cannot see instances."""
import bpy, os, sys, json, traceback
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, "core"))
res = {}
try:
    import orbital, mega, nodeutil
    orbital.make_object(1000.0)
    ob = bpy.data.objects["PLNT_Orbital"]
    md = ob.modifiers[0]
    ids = {i.name: i.identifier for i in md.node_group.interface.items_tree
           if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
           and i.socket_type != 'NodeSocketGeometry'}

    def setv(n, v):
        slot = md.properties.inputs[ids[n]]
        try:
            if "value" in slot.keys():
                slot["value"] = v; return
        except Exception:
            pass
        md.properties.inputs[ids[n]] = v

    out = {}
    for level in (0.0, 1.0, 4.0, 7.0, 9.5):
        setv("Orbital Level", level)
        bpy.context.view_layer.update()
        dg = bpy.context.evaluated_depsgraph_get()
        inst = 0
        real_tris = 0
        for oi in dg.object_instances:
            if oi.is_instance and oi.parent and oi.parent.original.name == "PLNT_Orbital":
                inst += 1
        ev = ob.evaluated_get(dg)
        me = ev.to_mesh()
        if me:
            real_tris = sum(len(p.vertices) - 2 for p in me.polygons)
            ev.to_mesh_clear()
        out[level] = {"instances": inst, "real_tris": real_tris}
    res["orbital_by_level"] = out
    res["readback"] = md.properties.inputs[ids["Orbital Level"]]["value"]
    res["ok"] = True
except Exception as ex:
    res["ok"] = False
    res["error"] = "%s: %s" % (type(ex).__name__, ex)
    res["trace"] = traceback.format_exc().splitlines()[-8:]
print("ORBTEST " + json.dumps(res, default=str), flush=True)
