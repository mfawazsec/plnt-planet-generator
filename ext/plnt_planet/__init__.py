"""PLNT Procedural Planet.

Registration only. Everything else lives in submodules, because an add-on that
does work at import time cannot be reloaded cleanly.

No bl_info: extensions declare metadata in blender_manifest.toml, and a stale
bl_info block silently overrides it.
"""
from .core import ui


def register():
    ui.register()


def unregister():
    ui.unregister()
