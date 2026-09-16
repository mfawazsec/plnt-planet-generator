#!/bin/bash
# Everything that can be verified without rendering.
#
#   ./tools/check_all.sh
#
# Covers the failure modes this project has actually hit: dead nodes, sockets
# with no UI, sockets with no tooltip, inputs that cannot reach an output,
# preset bleed, a broken extension package, and a planet larger than its own
# atmosphere.
# Repo root, derived from this script -- never hard-code an absolute path.
B="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Override for a Flatpak install:
#   PLNT_BLENDER="flatpak run --command=blender org.blender.Blender"
BL="${PLNT_BLENDER:-blender}"
fail=0

run () {  # label, blend-or-empty, script, marker
  echo "--- $1"
  # keep from the marker to the end: these scripts print multi-line JSON and a
  # tail -N slices it mid-document, so the parser reads a fragment and reports
  # a failure that is entirely the harness's fault
  if [ -z "$2" ]; then
    $BL -b --factory-startup --enable-autoexec -P "$B/tools/$3" 2>&1 \
      | sed -n "/^$4/,\$p" > "$B/logs/check_$1.txt"
  else
    $BL -b "$2" --enable-autoexec -P "$B/tools/$3" 2>&1 \
      | sed -n "/^$4/,\$p" > "$B/logs/check_$1.txt"
  fi
}

run builders "" validate_build.py VALIDATE
python3 - "$B/logs/check_builders.txt" <<'PY' || fail=1
import json, sys
t = open(sys.argv[1]).read()
d, _ = json.JSONDecoder().raw_decode(t[t.index('{'):])
bad = [k for k, v in d.items() if not v.get("ok")]
dead = {k: v["value"]["dead_nodes"] for k, v in d.items()
        if v.get("ok") and isinstance(v.get("value"), dict) and v["value"].get("dead_nodes")}
print("   builders failing:", bad or "none")
print("   dead nodes:", dead or "none")
sys.exit(1 if (bad or dead) else 0)
PY

run scaffold "" test_scaffold.py SCAFFOLD
python3 - "$B/logs/check_scaffold.txt" <<'PY' || fail=1
import json, sys
t = open(sys.argv[1]).read()
d, _ = json.JSONDecoder().raw_decode(t[t.index('{'):])
a = d.get("audit", {})
print("   scaffold ok:", d.get("ok"))
print("   orphans:", len(a.get("orphans", [])), " undocumented:", len(a.get("undocumented", [])))
print("   inert inputs:", d.get("inert_inputs") or "none")
sys.exit(0 if (d.get("ok") and not a.get("orphans") and not a.get("undocumented")
               and not d.get("inert_inputs")) else 1)
PY

run extension "" test_extension.py EXTTEST
grep -q '"ok": true' "$B/logs/check_extension.txt" && echo "   extension registers: yes" || { echo "   extension FAILED"; fail=1; }

run presets "$B/PLNT_PlanetGen.blend" test_presets.py PRESETS
grep -q '"ok": true' "$B/logs/check_presets.txt" && echo "   presets bleed-free: yes" || { echo "   preset bleed DETECTED"; fail=1; }

run audit "$B/PLNT_PlanetGen.blend" audit_blend.py AUDIT
python3 - "$B/logs/check_audit.txt" <<'PY' || fail=1
import json, sys
t = open(sys.argv[1]).read()
d, _ = json.JSONDecoder().raw_decode(t[t.index('{'):])
a = d["audit"]
print("   reachable:", a["reachable"], " orphans:", len(a["orphans"]),
      " undocumented:", len(a["undocumented"]))
sys.exit(0 if not a["orphans"] and not a["undocumented"] else 1)
PY

echo
[ $fail -eq 0 ] && echo "ALL CHECKS PASSED" || echo "CHECKS FAILED"
exit $fail
