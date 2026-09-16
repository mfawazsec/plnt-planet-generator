"""Displacement level-of-detail modes for PLNT_SurfaceShader.

Why this is the performance lever
---------------------------------
Measured: replacing the terrain field with a constant stub takes shot 02 from
189 s to 14 s. The field is ~93% of render time, so the only changes that matter
are ones that reduce how often it is evaluated.

Cycles evaluates the displacement subtree three extra times per shading hit
(P, P+du, P+dv) to build the bump normal. That subtree reads FIELD.elevation,
FIELD.slope and FIELD.ocean_depth, so the whole field is pulled ~4x per hit.
Dropping the residual term from the bump chain is what removes that multiplier.

Everything here works by node LABEL, so plnt_surface.py is never edited and the
modes can be switched per shot at render time.

  NONE   no displacement at all. Base mesh silhouette only.
  MICRO  fine noise relief only; the field is not read by the bump chain.
  BUMP   full detail as bump. Correct silhouette from the base mesh only.
  GEOMETRY  full detail as real subdivided geometry, no bump. Measured
            10% FASTER than the shipped BOTH setting on shot 02: real
            geometry costs less here than the fake normals do.
  TRUE   full detail as real geometry plus bump. What close-ups need.
"""
import bpy

MODES = ('NONE', 'MICRO', 'BUMP', 'GEOMETRY', 'TRUE')

SHADERS = ("PLNT_SurfaceShader", "PLNT_PatchShader")
MATERIALS = ("PLNT_Surface", "PLNT_PatchSurface")


def _byl(tree, label):
    for n in tree.nodes:
        if n.label == label:
            return n
    raise KeyError("no node labelled %r in %s" % (label, tree.name))


def _relink(tree, from_node, from_socket, to_node, to_socket):
    ts = to_node.inputs[to_socket]
    for l in list(ts.links):
        tree.links.remove(l)
    tree.links.new(from_node.outputs[from_socket], ts)


def _clear_input(tree, node, socket, value=None):
    s = node.inputs[socket]
    for l in list(s.links):
        tree.links.remove(l)
    if value is not None:
        s.default_value = value


def _micro_tail(tree, micro, total):
    """The end of the micro chain, which is not `micro_bu` itself.

    core.surface_detail splices the optional relief features in FRONT of the
    node they modulate: crater bowls, dune crests, lava crust and the strata
    erosion term each insert themselves between `micro_bu` and whatever used
    to consume it, so the real micro height is the LAST node in that chain,
    not the first.

    Wiring `micro_bu` straight into `total_disp` here -- which is what this
    module used to do -- silently cut every one of those features out of the
    displacement on the next quality change, and `apply_quality` runs on every
    render. Crater Amount and Dune Amount were live sockets driving a dangling
    branch; nothing they did reached a pixel.

    Walk forward while there is exactly one consumer that is not `total`, and
    hand back whatever the walk ends on. With no detail features attached that
    is `micro_bu`, so the old behaviour is the empty case of the new one.
    """
    n = micro
    seen = {n}
    while True:
        nxt = [l.to_node for l in n.outputs[0].links if l.to_node is not total]
        if len(nxt) != 1 or nxt[0] in seen:
            return n
        n = nxt[0]
        seen.add(n)


def _snapshot(tree):
    """Remember the shipped wiring so a mode switch is reversible in-session."""
    if tree.get("plnt_lod_saved"):
        return
    tree["plnt_lod_saved"] = True


def apply_mode(mode, tree_names=SHADERS, mat_names=MATERIALS,
               attr_slope=None, attr_depth=None):
    """Rewire the displacement chain for `mode`. Returns what it did.

    attr_slope / attr_depth: names of vertex attributes carrying slope and
    ocean depth. When given, MICRO reads its modulation from those instead of
    from the field, which is what actually removes the field from the bump
    chain. Without them MICRO falls back to flat constants, still fast, but
    micro relief stops fading out over ocean.
    """
    mode = mode.upper()
    if mode not in MODES:
        raise ValueError("mode must be one of %r, got %r" % (MODES, mode))
    acted = {"mode": mode, "trees": [], "materials": []}

    for tn in tree_names:
        tree = bpy.data.node_groups.get(tn)
        if not tree:
            continue
        _snapshot(tree)
        disp = _byl(tree, "DISP")
        total = _byl(tree, "total_disp")
        micro = _byl(tree, "micro_bu")
        resid = _byl(tree, "residual_bu")
        go = next(n for n in tree.nodes if n.bl_idname == 'NodeGroupOutput')

        if mode == 'NONE':
            for l in list(disp.outputs["Displacement"].links):
                tree.links.remove(l)
        else:
            _relink(tree, disp, "Displacement", go, "Displacement")
            _relink(tree, total, "Value", disp, "Height")

        tail = _micro_tail(tree, micro, total)
        if mode == 'MICRO':
            # residual is what pulls FIELD.elevation into the bump evaluation
            _clear_input(tree, total, 0, 0.0)
            _relink(tree, tail, "Value", total, 1)
            _detach_field_modulation(tree, attr_slope, attr_depth)
        elif mode in ('BUMP', 'GEOMETRY', 'TRUE'):
            _relink(tree, resid, "Value", total, 0)
            _relink(tree, tail, "Value", total, 1)
        acted["trees"].append(tn)

    method = {'NONE': 'BUMP', 'MICRO': 'BUMP', 'BUMP': 'BUMP',
              'GEOMETRY': 'DISPLACEMENT', 'TRUE': 'BOTH'}[mode]
    for mn in mat_names:
        ma = bpy.data.materials.get(mn)
        if ma:
            ma.displacement_method = method
            acted["materials"].append((mn, method))

    # Adaptive subdivision only earns its cost when real geometry is displaced.
    globe = bpy.data.objects.get("PLNT_Globe")
    if globe:
        md = globe.modifiers.get("PLNT_Adaptive")
        if md:
            md.show_render = mode in ('GEOMETRY', 'TRUE')
            acted["subsurf_render"] = md.show_render
    return acted


def _detach_field_modulation(tree, attr_slope, attr_depth):
    """Feed reliefmod / shorefade from attributes or constants, not the field.

    reliefmod reads FIELD.slope and shorefade reads FIELD.ocean_depth. slope is
    a finite difference, so reading it forces the elevation group to run three
    times. Cutting these two links is what collapses MICRO to a single field
    evaluation; without it, MICRO still pays for the whole field.
    """
    for label, attr, fallback in (("reliefmod", attr_slope, 0.5),
                                  ("shorefade", attr_depth, 0.0)):
        node = _byl(tree, label)
        if attr:
            a = tree.nodes.new("ShaderNodeAttribute")
            a.attribute_type = 'GEOMETRY'
            a.attribute_name = attr
            a.label = "LOD_" + label
            a.location = (node.location.x - 220, node.location.y - 160)
            _relink(tree, a, "Fac", node, 0)
        else:
            _clear_input(tree, node, 0, fallback)


# --------------------------------------------------------------------------
# Performance levers. These change cost without changing what the picture is
# meant to be, which is why they sit behind the Performance dropdown rather
# than the Quality one.
# --------------------------------------------------------------------------
GLOBE = "PLNT_Globe"


def apply_subdiv(level):
    """Base subdivision of the globe.

    This is memory and interactivity, not render time: level 8 is 983,040
    quads and 2.2 seconds of geometry-nodes evaluation per parameter change,
    level 7 is 245,760 quads and 0.56 seconds. Fine relief comes from
    displacement at render time either way.
    """
    ob = bpy.data.objects.get(GLOBE)
    if not ob:
        return None
    md = ob.modifiers.get("PLNT_GlobeRig")
    if not md or not md.node_group:
        return None
    ident = None
    for it in md.node_group.interface.items_tree:
        if getattr(it, "item_type", "") == 'SOCKET' and it.in_out == 'INPUT' \
                and it.name == "Subdiv Level":
            ident = it.identifier
            break
    if ident is None:
        return None
    try:
        md.properties.inputs[ident]["value"] = int(level)
    except Exception:
        return None
    ob.update_tag()
    return int(level)


def apply_adaptive(space='OBJECT', edge=0.045, pixel=1.0):
    """How Cycles' adaptive subdivision measures a dice edge.

    PIXEL is camera-relative, so the same planet costs four times the
    micropolygon memory when the camera moves twice as close: at 2560x1440 the
    close shots reached 2.56 GB of VRAM, which is most of a 6 GB card. OBJECT
    (Blender 5.0) measures the edge in object units instead, so memory is a
    property of the model rather than of the framing, and a low-end machine can
    be given a budget it will actually keep to.
    """
    out = []
    for ob in bpy.data.objects:
        md = ob.modifiers.get("PLNT_Adaptive") if ob.modifiers else None
        if not md or md.type != 'SUBSURF':
            continue
        try:
            md.adaptive_space = space
            if space == 'OBJECT':
                md.adaptive_object_edge_length = float(edge)
            else:
                md.adaptive_pixel_size = float(pixel)
            out.append((ob.name, space,
                        round(float(edge) if space == 'OBJECT' else pixel, 4)))
        except Exception:
            continue
    return out


# Every noise texture whose octave count this scales. Reducing octaves is the
# cheapest real saving in the shader: measured -11% render time on shot 02 at
# half detail, with the difference invisible at planet scale and an
# IMPROVEMENT on shot 06, where the top octaves were reading as speckle.
_DETAIL_KEY = "plnt_detail_base"


def _detail_trees():
    seen, out = set(), []
    for g in bpy.data.node_groups:
        if g.name.startswith("PLNT") and g.name not in seen:
            seen.add(g.name)
            out.append(g)
    for m in bpy.data.materials:
        if m.name.startswith("PLNT") and m.node_tree is not None:
            out.append(m.node_tree)
    return out


def apply_detail(scale=1.0):
    """Multiply every unlinked noise Detail input by `scale`.

    The base value is stamped on the node the first time this runs, so the
    scaling is absolute rather than cumulative and 1.0 always restores exactly
    what the builder wrote. Linked Detail inputs are left alone: something else
    is already driving them.
    """
    scale = max(0.0, float(scale))
    n = 0
    for tree in _detail_trees():
        for node in tree.nodes:
            s = node.inputs.get("Detail") if hasattr(node, "inputs") else None
            if s is None or s.links or not hasattr(s, "default_value"):
                continue
            base = node.get(_DETAIL_KEY)
            if base is None:
                base = float(s.default_value)
                node[_DETAIL_KEY] = base
            try:
                s.default_value = max(0.0, float(base) * scale)
                n += 1
            except Exception:
                continue
    return {"scale": scale, "nodes": n}


def detail_scale_now():
    """The scale currently in force, inferred from one stamped node."""
    for tree in _detail_trees():
        for node in tree.nodes:
            base = node.get(_DETAIL_KEY)
            s = node.inputs.get("Detail") if hasattr(node, "inputs") else None
            if base and s is not None and not s.links and float(base) > 0:
                return round(float(s.default_value) / float(base), 3)
    return 1.0


def describe():
    return {m: d for m, d in zip(MODES, (
        "No displacement. Fastest; silhouette comes from the base mesh alone.",
        "Fine noise relief only. The terrain field is not read while building "
        "the bump normal, which is where most of the render time goes.",
        "Full terrain detail as a bump normal. No change to the silhouette.",
        "Full terrain detail as real subdivided geometry, no bump. Measured "
        "faster than Bump on this project.",
        "Full terrain detail as real subdivided geometry plus bump. Correct at "
        "the limb and in close-ups; the most expensive mode."))}
