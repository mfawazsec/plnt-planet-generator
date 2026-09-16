"""Generated node groups. Regenerate with tools/dump_tree.py -- do not hand-edit.

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



def build_globerig(name='PLNT_GlobeRig'):
    """Generated from the .blend by tools/dump_tree.py. Do not hand-edit."""
    if name in bpy.data.node_groups:
        bpy.data.node_groups.remove(bpy.data.node_groups[name])
    g = bpy.data.node_groups.new(name, 'GeometryNodeTree')
    I = g.interface
    s = I.new_socket(name='Geometry', in_out='OUTPUT', socket_type='NodeSocketGeometry')
    s = I.new_socket(name='Geometry', in_out='INPUT', socket_type='NodeSocketGeometry')
    s = I.new_socket(name='Seed', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s.min_value = -10000.0
    s.max_value = 10000.0
    s = I.new_socket(name='Radius', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1000.0
    s.min_value = 1.0
    s.max_value = 100000.0
    s = I.new_socket(name='Subdiv Level', in_out='INPUT', socket_type='NodeSocketInt')
    s.default_value = 7
    s.min_value = 1
    s.max_value = 9
    s = I.new_socket(name='Continent Scale', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 1.8
    s.min_value = 0.05
    s.max_value = 40.0
    s = I.new_socket(name='Continent Coverage', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.42
    s.min_value = 0.0
    s.max_value = 1.0
    s = I.new_socket(name='Relief Strength', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 70.0
    s.min_value = 0.0
    s.max_value = 400.0
    s = I.new_socket(name='Mountain Sharpness', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.55
    s.min_value = 0.0
    s.max_value = 2.0
    s = I.new_socket(name='Erosion Amount', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.35
    s.min_value = 0.0
    s.max_value = 1.0
    s = I.new_socket(name='Sea Level', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.0
    s.min_value = -1.0
    s.max_value = 1.0
    s = I.new_socket(name='Polar Cap Extent', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.18
    s.min_value = 0.0
    s.max_value = 0.95
    s = I.new_socket(name='Tectonic Belt Width', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.22
    s.min_value = 0.01
    s.max_value = 1.0
    s = I.new_socket(name='Warp Strength', in_out='INPUT', socket_type='NodeSocketFloat')
    s.default_value = 0.45
    s.min_value = 0.0
    s.max_value = 2.0
    s = I.new_socket(name='Surface Material', in_out='INPUT', socket_type='NodeSocketMaterial')
    N = g.nodes.new
    nd = {}
    n = N('NodeGroupInput'); nd['Group Input'] = n
    n.location = (-1200.0, 0.0)
    n = N('NodeGroupOutput'); nd['Group Output'] = n
    n.location = (2820.0, 0.0)
    n = N('GeometryNodeMeshIcoSphere'); nd['Ico Sphere'] = n
    n.location = (-950.0, 200.0)
    n.inputs[0].default_value = 1.0
    n = N('GeometryNodeInputPosition'); nd['Position'] = n
    n.location = (-950.0, -260.0)
    n = N('ShaderNodeVectorMath'); nd['Vector Math'] = n
    n.location = (-770.0, -260.0)
    n.operation = 'NORMALIZE'
    n.inputs[1].default_value = (0.0, 0.0, 0.0)
    n.inputs[2].default_value = (0.0, 0.0, 0.0)
    n.inputs[3].default_value = 1.0
    n = N('GeometryNodeGroup'); nd['Group'] = n
    n.location = (-560.0, -60.0)
    n.label = 'FIELD'
    n.node_tree = bpy.data.node_groups.get('PLNT_TerrainField')
    n = N('ShaderNodeMath'); nd['Math'] = n
    n.location = (-200.0, 200.0)
    n.label = 'disp'
    n.operation = 'MULTIPLY'
    n.use_clamp = False
    n.inputs[2].default_value = 0.5
    n = N('ShaderNodeMath'); nd['Math.001'] = n
    n.location = (-20.0, 200.0)
    n.label = 'radius'
    n.operation = 'ADD'
    n.use_clamp = False
    n.inputs[2].default_value = 0.5
    n = N('ShaderNodeVectorMath'); nd['Vector Math.001'] = n
    n.location = (160.0, 200.0)
    n.operation = 'SCALE'
    n.inputs[1].default_value = (0.0, 0.0, 0.0)
    n.inputs[2].default_value = (0.0, 0.0, 0.0)
    n = N('GeometryNodeSetPosition'); nd['Set Position'] = n
    n.location = (360.0, 0.0)
    n.inputs[1].default_value = True
    n.inputs[3].default_value = (0.0, 0.0, 0.0)
    n = N('GeometryNodeStoreNamedAttribute'); nd['Store Named Attribute.007'] = n
    n.location = (1960.0, 0.0)
    n.label = 'store_habitability'
    n.data_type = 'FLOAT'
    n.domain = 'POINT'
    n.inputs[1].default_value = True
    n.inputs[2].default_value = 'habitability'
    n = N('GeometryNodeSetShadeSmooth'); nd['Set Shade Smooth'] = n
    n.location = (2360.0, 0.0)
    n.domain = 'FACE'
    n.inputs[1].default_value = True
    n.inputs[2].default_value = True
    n = N('GeometryNodeSetMaterial'); nd['Set Material'] = n
    n.location = (2580.0, 0.0)
    n.inputs[1].default_value = True
    n = N('GeometryNodeStoreNamedAttribute'); nd['Store Named Attribute'] = n
    n.location = (2140.0, -260.0)
    n.label = 'store_elevation'
    n.data_type = 'FLOAT'
    n.domain = 'POINT'
    n.inputs[1].default_value = True
    n.inputs[2].default_value = 'elevation'
    Lk = g.links.new
    Lk(nd['Group Input'].outputs[3], nd['Ico Sphere'].inputs[1])
    Lk(nd['Position'].outputs[0], nd['Vector Math'].inputs[0])
    Lk(nd['Group Input'].outputs[6], nd['Math'].inputs[1])
    Lk(nd['Group Input'].outputs[2], nd['Math.001'].inputs[0])
    Lk(nd['Math'].outputs[0], nd['Math.001'].inputs[1])
    Lk(nd['Vector Math'].outputs[0], nd['Vector Math.001'].inputs[0])
    Lk(nd['Math.001'].outputs[0], nd['Vector Math.001'].inputs[3])
    Lk(nd['Ico Sphere'].outputs[0], nd['Set Position'].inputs[0])
    Lk(nd['Vector Math.001'].outputs[0], nd['Set Position'].inputs[2])
    Lk(nd['Set Shade Smooth'].outputs[0], nd['Set Material'].inputs[0])
    Lk(nd['Set Material'].outputs[0], nd['Group Output'].inputs[0])
    Lk(nd['Group Input'].outputs[13], nd['Set Material'].inputs[2])
    Lk(nd['Set Position'].outputs[0], nd['Store Named Attribute.007'].inputs[0])
    Lk(nd['Store Named Attribute.007'].outputs[0], nd['Store Named Attribute'].inputs[0])
    Lk(nd['Store Named Attribute'].outputs[0], nd['Set Shade Smooth'].inputs[0])
    Lk(nd['Vector Math'].outputs[0], nd['Group'].inputs[0])
    Lk(nd['Group Input'].outputs[1], nd['Group'].inputs[1])
    Lk(nd['Group Input'].outputs[4], nd['Group'].inputs[2])
    Lk(nd['Group Input'].outputs[5], nd['Group'].inputs[3])
    Lk(nd['Group Input'].outputs[7], nd['Group'].inputs[4])
    Lk(nd['Group Input'].outputs[8], nd['Group'].inputs[5])
    Lk(nd['Group Input'].outputs[11], nd['Group'].inputs[6])
    Lk(nd['Group Input'].outputs[12], nd['Group'].inputs[7])
    Lk(nd['Group Input'].outputs[9], nd['Group'].inputs[8])
    Lk(nd['Group Input'].outputs[10], nd['Group'].inputs[9])
    Lk(nd['Group'].outputs[0], nd['Math'].inputs[0])
    Lk(nd['Group'].outputs[0], nd['Store Named Attribute'].inputs[3])
    Lk(nd['Group'].outputs[7], nd['Store Named Attribute.007'].inputs[3])
    return g

