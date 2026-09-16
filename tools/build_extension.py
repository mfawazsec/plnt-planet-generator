"""Assemble the shippable extension from the working modules.

The working tree still uses flat top-level modules loaded by path, which cannot
work inside an extension: the package name is bl_ext.<repo>.<id>, and
sys.modules["plnt_tech"] would collide with anything else on the machine using
that name. This rewrites the loaders into real relative imports.

  python3 tools/build_extension.py
  blender --command extension build --source-dir ext/plnt_planet
"""
import os
import re
import shutil
import sys

D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EXT = os.path.join(D, "ext", "plnt_planet")
CORE = os.path.join(EXT, "core")

CORE_MODULES = ["nodeutil", "params", "ui", "lod", "render", "rings", "orbital",
                "mega", "atmosphere", "surface_detail", "scene", "gen_groups",
                "anim", "compositing"]
# transitional flat modules that become package submodules
FLAT = {"plnt_field": "field", "plnt_surface": "surface", "plnt_tech": "tech",
        "plnt_atmos": "atmos", "plnt_patch": "patch", "plnt_shots": "shots",
        "PLNT_presets": "presets"}


def rewrite(src, name):
    """Turn path-based loaders into relative imports."""
    out = src
    # `from core import X` / `import X` for our own modules
    out = re.sub(r'^from core import (\w+)$', r'from . import \1', out, flags=re.M)
    # The flat modules resolve core.anim at call time through _anim_mod(),
    # which already tries the packaged layout first, so nothing to rewrite.
    for flat, mod in FLAT.items():
        out = out.replace('_load_flat("%s", directory)' % flat,
                          '_import_sub("%s")' % mod)
        out = out.replace('load("%s")' % flat, '_import_sub("%s")' % mod)
    # output paths must not land in the install directory, which is read-only
    out = out.replace('os.path.dirname(os.path.abspath(__file__)), "renders"',
                      'bpy.app.tempdir, "plnt_renders"')
    return out


def main():
    os.makedirs(CORE, exist_ok=True)
    written = []
    for m in CORE_MODULES:
        src = os.path.join(D, "core", m + ".py")
        if not os.path.exists(src):
            print("  missing core/%s.py" % m)
            continue
        text = rewrite(open(src).read(), m)
        open(os.path.join(CORE, m + ".py"), "w").write(text)
        written.append("core/%s.py" % m)
    open(os.path.join(CORE, "__init__.py"), "w").write(
        '"""Generator internals."""\n')

    for flat, mod in FLAT.items():
        src = os.path.join(D, flat + ".py")
        if not os.path.exists(src):
            print("  missing %s.py" % flat)
            continue
        text = rewrite(open(src).read(), mod)
        open(os.path.join(EXT, mod + ".py"), "w").write(text)
        written.append(mod + ".py")

    # ui.py stays inside core/. Copying it to the package root would give it
    # a second identity whose `from . import params` resolves to the wrong
    # package and fails at registration.
    print("EXT_BUILT %d files -> %s" % (len(written), EXT))
    for w in sorted(written):
        print("   ", w)
    return 0


if __name__ == "__main__":
    sys.exit(main())
