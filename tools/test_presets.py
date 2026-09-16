"""Apply all 13 presets in sequence and check for bleed.

The bug this guards: after the volcanic preset set Lava Emission to 9.0, the
value persisted into five subsequent shots and gave them salmon oceans.
"""
import bpy, os, sys, json
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, "core"))
txt = bpy.data.texts.get("PLNT_presets.py")
ns = {"__name__": "plnt_presets_mod"}
exec(compile(txt.as_string(), "PLNT_presets.py", "exec"), ns)
P, apply_preset = ns["P"], ns["apply_preset"]
ctl = bpy.data.materials["PLNT_Surface"].node_tree.nodes["PLNT_CTL"]
res = {"order": [], "bleed": [], "defaults_check": ns["check_defaults"]()}


def snap():
    return {s.name: (tuple(round(float(x), 5) for x in s.default_value)
                     if hasattr(s.default_value, "__len__")
                     else round(float(s.default_value), 5))
            for s in ctl.inputs if hasattr(s, "default_value")}


# apply each preset twice in different orders; the second pass must match the
# first exactly, or something is carrying over
first = {}
for name in sorted(P):
    apply_preset(name, seed=1234)
    first[name] = snap()
    res["order"].append(name)
for name in sorted(P, reverse=True):
    apply_preset(name, seed=1234)
    now = snap()
    diff = {k: (first[name][k], now[k]) for k in now if now[k] != first[name].get(k)}
    if diff:
        res["bleed"].append({"preset": name, "differs": diff})
res["presets_tested"] = len(P)
res["ok"] = not res["bleed"] and not res["defaults_check"]["missing_from_defaults"]
print("PRESETS " + json.dumps(res, default=str), flush=True)
