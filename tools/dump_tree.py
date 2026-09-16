"""Emit Python that rebuilds a node group, so it stops living only in the .blend.

PLNT_GlobeRig, the sun rig, the cameras and the world exist nowhere in source.
If the .blend were lost the system could not be rebuilt, and `rebuild()` only
regenerates node groups onto objects that already exist. This dumps a group to
a source module.

Links are emitted by socket INDEX, never by name: Map Range has four inputs
called Value and ShaderNodeMix has three parallel sets, so a name-based
round-trip silently reconnects the wrong socket.

  blender -b <blend> -P tools/dump_tree.py -- --group PLNT_GlobeRig --out core/gen_globe.py
"""
import bpy, os, sys

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []


def arg(n, d=None):
    return argv[argv.index(n) + 1] if n in argv else d


# node properties worth preserving, by attribute name. Only emitted when the
# node actually has the attribute.
NODE_PROPS = (
    "operation", "data_type", "domain", "mode", "input_type", "clamp",
    "use_clamp", "interpolation_type", "noise_dimensions", "noise_type",
    "voronoi_dimensions", "feature", "distance", "wave_type", "bands_direction",
    "rings_direction", "wave_profile", "gradient_type", "attribute_type",
    "attribute_name", "vector_type", "rotation_type", "blend_type",
    "invert", "hide_value", "component", "axis", "pivot_axis", "operation_type",
    "resolution_mode", "poll_instance", "scale_elements_mode", "legacy_behavior",
)


def pyrepr(v):
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, bool):
        return repr(v)
    if isinstance(v, (int,)):
        return repr(v)
    if isinstance(v, float):
        return repr(round(v, 6))
    if hasattr(v, "__len__"):
        return "(" + ", ".join(pyrepr(x) for x in v) + ")"
    return repr(v)


def dump(group, fn_name):
    L = []
    w = L.append
    tt = group.bl_idname
    w('def %s(name=%r):' % (fn_name, group.name))
    w('    """Generated from the .blend by tools/dump_tree.py. Do not hand-edit."""')
    w('    if name in bpy.data.node_groups:')
    w('        bpy.data.node_groups.remove(bpy.data.node_groups[name])')
    w('    g = bpy.data.node_groups.new(name, %r)' % tt)
    w('    I = g.interface')
    for it in group.interface.items_tree:
        if getattr(it, "item_type", "") != 'SOCKET':
            continue
        w('    s = I.new_socket(name=%r, in_out=%r, socket_type=%r)'
          % (it.name, it.in_out, it.bl_socket_idname))
        if hasattr(it, "default_value") and it.bl_socket_idname not in (
                'NodeSocketGeometry', 'NodeSocketShader', 'NodeSocketMaterial',
                'NodeSocketObject', 'NodeSocketCollection', 'NodeSocketImage',
                'NodeSocketTexture'):
            try:
                w('    s.default_value = %s' % pyrepr(it.default_value))
            except Exception:
                pass
        for a in ("min_value", "max_value"):
            if hasattr(it, a):
                try:
                    w('    s.%s = %s' % (a, pyrepr(getattr(it, a))))
                except Exception:
                    pass
        if getattr(it, "description", ""):
            w('    s.description = %r' % it.description)
        if getattr(it, "subtype", None) not in (None, 'NONE'):
            w('    s.subtype = %r' % it.subtype)
    w('    N = g.nodes.new')
    w('    nd = {}')
    for n in group.nodes:
        w('    n = N(%r); nd[%r] = n' % (n.bl_idname, n.name))
        w('    n.location = %s' % pyrepr(tuple(n.location)))
        if n.label:
            w('    n.label = %r' % n.label)
        if n.mute:
            w('    n.mute = True')
        for p in NODE_PROPS:
            if not hasattr(n, p):
                continue
            try:
                v = getattr(n, p)
            except Exception:
                continue
            if isinstance(v, (str, bool, int, float)):
                w('    n.%s = %s' % (p, pyrepr(v)))
        if getattr(n, "node_tree", None) is not None:
            w('    n.node_tree = bpy.data.node_groups.get(%r)' % n.node_tree.name)
        if n.bl_idname == 'ShaderNodeValToRGB':
            w('    _ramp(n, %s)' % pyrepr([(e.position, tuple(e.color))
                                           for e in n.color_ramp.elements]))
        for i, s in enumerate(n.inputs):
            if s.links or not hasattr(s, "default_value"):
                continue
            try:
                w('    n.inputs[%d].default_value = %s' % (i, pyrepr(s.default_value)))
            except Exception:
                pass
    w('    Lk = g.links.new')
    for lk in group.links:
        fi = list(lk.from_node.outputs).index(lk.from_socket)
        ti = list(lk.to_node.inputs).index(lk.to_socket)
        w('    Lk(nd[%r].outputs[%d], nd[%r].inputs[%d])'
          % (lk.from_node.name, fi, lk.to_node.name, ti))
    w('    return g')
    return "\n".join(L)


HEADER = '''"""Generated node groups. Regenerate with tools/dump_tree.py -- do not hand-edit.

These structures previously existed only inside PLNT_PlanetGen.blend, which
meant the system could not be rebuilt from source if the file were lost.
"""
import bpy


def _ramp(node, stops):
    cr = node.color_ramp
    while len(cr.elements) > 1:
        cr.elements.remove(cr.elements[-1])
    for i, (pos, col) in enumerate(stops):
        e = cr.elements[0] if i == 0 else cr.elements.new(pos)
        e.position = pos
        e.color = col


'''

names = (arg("--group") or "").split(",")
out = arg("--out")
parts = [HEADER]
made = []
for nm in names:
    g = bpy.data.node_groups.get(nm)
    if not g:
        print("DUMP_MISS " + nm, flush=True)
        continue
    fn = "build_" + nm.replace("PLNT_", "").lower()
    parts.append(dump(g, fn) + "\n\n")
    made.append((nm, fn, len(g.nodes)))
open(out, "w").write("\n".join(parts))
print("DUMP_OK " + repr(made) + " -> " + out, flush=True)
