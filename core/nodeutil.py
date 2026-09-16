"""Shared node-graph helpers.

Socket names are defined at runtime, not in the API reference, and several node
types carry duplicates -- Map Range has twelve inputs, four named Value;
ShaderNodeMix has three parallel sets and for RGBA the live sockets are inputs
0/6/7 and output 2. Guessing a name is how a build silently wires the wrong
thing and the mistake only shows up in a render hours later. These helpers fail
loudly with the real socket list instead.
"""


def sockin(node, *names):
    for n in names:
        if n in node.inputs:
            return node.inputs[n]
    raise KeyError("%s has no input in %r; it has %r"
                   % (node.bl_idname, names, [s.name for s in node.inputs]))


def sockout(node, *names):
    for n in names:
        if n in node.outputs:
            return node.outputs[n]
    raise KeyError("%s has no output in %r; it has %r"
                   % (node.bl_idname, names, [s.name for s in node.outputs]))


def has_in(node, name):
    return name in node.inputs


def mix_rgba(tree, loc=(0, 0), label=""):
    n = tree.nodes.new("ShaderNodeMix")
    n.data_type = 'RGBA'
    n.location = loc
    n.label = label
    return n


def new_socket(iface, name, in_out, socket_type, default=None,
               mn=None, mx=None, desc=""):
    s = iface.new_socket(name=name, in_out=in_out, socket_type=socket_type)
    if default is not None:
        s.default_value = default
    if mn is not None:
        s.min_value = mn
    if mx is not None:
        s.max_value = mx
    s.description = desc
    return s
