"""Build the new node groups on a factory-default scene and report.

Runs against --factory-startup so it cannot touch PLNT_PlanetGen.blend or the
in-flight benchmark. Nothing is saved.
"""
import bpy, os, sys, json, traceback

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, "core"))

res = {}


def try_step(name, fn):
    try:
        res[name] = {"ok": True, "value": fn()}
    except Exception as ex:
        res[name] = {"ok": False, "error": "%s: %s" % (type(ex).__name__, ex),
                     "trace": traceback.format_exc().splitlines()[-6:]}


import params
try_step("params.validate", lambda: params.validate())

import rings


def build_ring_shader():
    g = rings.build_shader()
    kinds = {}
    for n in g.nodes:
        kinds[n.bl_idname] = kinds.get(n.bl_idname, 0) + 1
    unlinked_out = [s.name for n in g.nodes
                    if n.bl_idname == 'NodeGroupOutput' for s in n.inputs
                    if not s.links and s.name != ""]
    dead = [n.label or n.name for n in g.nodes
            if n.bl_idname not in ('NodeGroupOutput',)
            and not any(s.links for s in n.outputs)]
    return {"nodes": len(g.nodes),
            "inputs": len([i for i in g.interface.items_tree
                           if getattr(i, "item_type", "") == 'SOCKET'
                           and i.in_out == 'INPUT']),
            "group_output_unlinked": unlinked_out,
            "dead_nodes": dead,
            "voronoi": kinds.get('ShaderNodeTexVoronoi', 0),
            "noise": kinds.get('ShaderNodeTexNoise', 0)}


def build_ring_geo():
    g = rings.build_geometry()
    dead = [n.label or n.name for n in g.nodes
            if n.bl_idname != 'NodeGroupOutput'
            and not any(s.links for s in n.outputs)]
    return {"nodes": len(g.nodes), "dead_nodes": dead}


try_step("rings.build_shader", build_ring_shader)
try_step("rings.build_geometry", build_ring_geo)


import orbital


def build_orbital():
    g = orbital.build(1000.0)
    dead = [n.label or n.name for n in g.nodes
            if n.bl_idname not in ('NodeGroupOutput',)
            and not any(s.links for s in n.outputs)]
    unlinked = [s.name for n in g.nodes if n.bl_idname == 'NodeGroupOutput'
                for s in n.inputs if not s.links and s.name != ""]
    kinds = {}
    for n in g.nodes:
        kinds[n.bl_idname] = kinds.get(n.bl_idname, 0) + 1
    return {"nodes": len(g.nodes),
            "inputs": len([i for i in g.interface.items_tree
                           if getattr(i, "item_type", "") == 'SOCKET'
                           and i.in_out == 'INPUT']),
            "dead_nodes": dead, "group_output_unlinked": unlinked,
            "realize_instances": kinds.get('GeometryNodeRealizeInstances', 0),
            "set_material": kinds.get('GeometryNodeSetMaterial', 0),
            "instance_on_points": kinds.get('GeometryNodeInstanceOnPoints', 0)}


try_step("orbital.build", build_orbital)
try_step("orbital.material", lambda: orbital.build_material().name)


import mega


def build_mega():
    g = mega.build(1000.0)
    dead = [n.label or n.name for n in g.nodes
            if n.bl_idname not in ('NodeGroupOutput',)
            and not any(s.links for s in n.outputs)]
    unlinked = [s.name for n in g.nodes if n.bl_idname == 'NodeGroupOutput'
                for s in n.inputs if not s.links and s.name != ""]
    return {"nodes": len(g.nodes),
            "inputs": len([i for i in g.interface.items_tree
                           if getattr(i, "item_type", "") == 'SOCKET'
                           and i.in_out == 'INPUT']),
            "dead_nodes": dead, "group_output_unlinked": unlinked}


try_step("mega.build", build_mega)
try_step("mega.materials", lambda: [m.name for m in mega.build_materials()])


import atmosphere as ATM


def build_atmo():
    g = ATM.build()
    dead = [n.label or n.name for n in g.nodes
            if n.bl_idname not in ('NodeGroupOutput',)
            and not any(s.links for s in n.outputs)]
    unlinked = [s.name for n in g.nodes if n.bl_idname == 'NodeGroupOutput'
                for s in n.inputs if not s.links and s.name != ""]
    kinds = {}
    for n in g.nodes:
        kinds[n.bl_idname] = kinds.get(n.bl_idname, 0) + 1
    return {"nodes": len(g.nodes),
            "inputs": len([i for i in g.interface.items_tree
                           if getattr(i, "item_type", "") == 'SOCKET'
                           and i.in_out == 'INPUT']),
            "dead_nodes": dead, "group_output_unlinked": unlinked,
            "volume_nodes": kinds.get('ShaderNodeVolumeScatter', 0)
                            + kinds.get('ShaderNodeVolumeAbsorption', 0)
                            + kinds.get('ShaderNodeVolumePrincipled', 0),
            "outputs": [i.name for i in g.interface.items_tree
                        if getattr(i, "item_type", "") == 'SOCKET'
                        and i.in_out == 'OUTPUT']}


try_step("atmosphere.build", build_atmo)
try_step("atmosphere.material", lambda: ATM.make_material().name)

# lod / render modules must at least import and expose what the UI calls
import lod
import render as rmod
try_step("lod.describe", lambda: sorted(lod.describe().keys()))
try_step("render.presets", lambda: sorted(rmod.PRESETS.keys()))

# UI: registration is the real test -- a bad property or panel fails here
import ui
try_step("ui.register", lambda: (ui.register(), "registered")[1])
try_step("ui.audit", lambda: ui.audit())
try_step("ui.unregister", lambda: (ui.unregister(), "unregistered")[1])

print("VALIDATE " + json.dumps(res, indent=1, default=str), flush=True)
