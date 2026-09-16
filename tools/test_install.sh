#!/bin/bash
# Install the built zip into a throwaway Blender profile and confirm it enables.
#
# test_extension.py proves the package imports and registers; this proves
# Blender's own installer accepts it and the add-on turns on from a cold profile.
# Repo root, derived from this script. Never hard-code an absolute path.
B="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Newest built zip, not a pinned version: pinning the name is how the
# shipped package stayed at 2.0.0 while the sources moved on.
ZIP="${1:-$(ls -t "$B"/dist/plnt_planet-*.zip "$B"/ext/plnt_planet-*.zip 2>/dev/null | head -1)}"
[ -f "$ZIP" ] || { echo "no zip at $ZIP"; exit 1; }

${PLNT_BLENDER:-blender} -b --factory-startup \
  --python-expr "
import bpy, sys, json
res = {}
try:
    bpy.ops.extensions.package_install_files(
        filepath='$ZIP', repo='user_default', enable_on_install=True)
    res['installed'] = True
except Exception as ex:
    res['installed'] = False
    res['error'] = '%s: %s' % (type(ex).__name__, ex)
res['addons_enabled'] = [a.module for a in bpy.context.preferences.addons
                         if 'plnt' in a.module.lower()]
res['panels'] = sorted(c for c in dir(bpy.types) if c.startswith('PLNT_PT_'))
res['operators'] = sorted(c for c in dir(bpy.types) if c.startswith('PLNT_OT_'))
res['scene_prop'] = hasattr(bpy.types.Scene, 'plnt')
print('INSTALL ' + json.dumps(res, default=str))
" 2>&1 | grep "^INSTALL"
