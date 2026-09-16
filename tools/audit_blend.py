"""Run the usability audit against the real .blend, not a fresh scaffold."""
import bpy, os, sys, json
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(D, "core"))
import ui, params
res = {}
ui.register()
res["audit"] = ui.audit()
# what a person actually sees in each panel at each tier
res["panel_counts"] = {}
for pid, label, _icon in params.PANELS:
    if pid not in ui.SOURCES:
        continue
    res["panel_counts"][label] = {
        t: len(ui.visible_sockets(pid, t, "")) for t in ("BASIC", "ADVANCED", "ALL")}
res["search_example"] = len(ui.visible_sockets("rings", "ALL", "spiral"))
res["preset_items"] = len(ui.preset_items())
ui.unregister()
print("AUDIT " + json.dumps(res, default=str), flush=True)
