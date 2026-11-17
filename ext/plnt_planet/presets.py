"""PLNT_presets: preset library, randomiser and N-panel UI.

Lives as a text datablock inside the .blend. Run it once (Text Editor > Run
Script, or it auto-registers on load if `Register` is ticked) to add the
"PLNT Planet" tab to the 3D viewport N-panel.

  apply_preset("earthlike")
  randomize(seed=42, tech_level=6.0)
"""
import bpy
import random

GLOBE = "PLNT_Globe"
MOD = "PLNT_GlobeRig"
SURF = "PLNT_Surface"
PATCHSURF = "PLNT_PatchSurface"
CLOUDS = "PLNT_Clouds"
ATMO = "PLNT_Atmosphere"
RINGS = "PLNT_Rings"
ORBITAL = "PLNT_Orbital"


# ---------------------------------------------------------------- plumbing
def _ids(ng):
    return {i.name: i.identifier for i in ng.interface.items_tree
            if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
            and i.socket_type != 'NodeSocketGeometry'}


def gset(mod, name, value):
    ids = _ids(mod.node_group)
    if name not in ids:
        return False
    slot = mod.properties.inputs[ids[name]]
    try:
        if "value" in slot.keys():
            slot["value"] = value
            return True
    except Exception:
        pass
    mod.properties.inputs[ids[name]] = value
    return True


def gget(mod, name):
    ids = _ids(mod.node_group)
    if name not in ids:
        return None
    slot = mod.properties.inputs[ids[name]]
    try:
        return slot["value"]
    except Exception:
        return slot


def _ctl(matname):
    m = bpy.data.materials.get(matname)
    if not m or not m.node_tree:
        return None
    return m.node_tree.nodes.get("PLNT_CTL")


def _set_ctl(matname, params):
    n = _ctl(matname)
    if not n:
        return
    for k, v in params.items():
        if k in n.inputs:
            try:
                n.inputs[k].default_value = v
            except Exception:
                pass


def _obj(name):
    return bpy.data.objects.get(name)


# ---------------------------------------------------------------- presets
# globe: terrain     surface: palette + tech     clouds/atmo: sky     orbital: level
P = {}

P["pristine_alien"] = dict(
    globe=dict(**{"Continent Scale": 2.1, "Continent Coverage": 0.46, "Relief Strength": 26.0,
                  "Mountain Sharpness": 0.72, "Erosion Amount": 0.62, "Sea Level": 0.0,
                  "Polar Cap Extent": 0.12, "Tectonic Belt Width": 0.26, "Warp Strength": 0.62}),
    surface={"Vegetation Hue": (0.230, 0.020, 0.075, 1), "Rock Hue": (0.145, 0.055, 0.058, 1),
             "Sand Hue": (0.330, 0.105, 0.090, 1), "Ice Brightness": 0.75,
             # Teal-violet rather than Earth blue. The vegetation here is
             # crimson, so a nitrogen-blue ocean underneath it reads as Earth
             # with the land recoloured; shifting the water green in the
             # shallows and indigo in the deeps makes the whole world foreign
             # and separates it from the earthlike preset at a glance.
             "Ocean Shallow": (0.030, 0.215, 0.205, 1), "Ocean Deep": (0.012, 0.010, 0.052, 1),
             "Shelf Boost": 0.420, "Vegetation Amount": 1.35, "River Tint": 0.95,
             "Ice Temp Threshold": 0.16, "Patchiness": 0.45, "Tech Level": 0.0, "Vegetation Clumping": 0.85, "Foam Amount": 0.160, "Glint Variation": 0.6, "Strata Amount": 0.3},
    clouds={"Cloud Coverage": 0.34, "Cloud Density": 1.1, "Band Strength": 0.42, "Detail Scale": 1.2},
    atmo={"Density": 0.0336, "Atmo Colour": (0.36, 0.34, 1.0, 1), "Falloff": 3.0, "Pollution": 0.0},
    rings=False, orbital=0.0)

P["earthlike"] = dict(
    globe={"Continent Scale": 1.75, "Continent Coverage": 0.40, "Relief Strength": 22.7,
           "Mountain Sharpness": 0.58, "Erosion Amount": 0.38, "Sea Level": 0.0,
           "Polar Cap Extent": 0.20, "Tectonic Belt Width": 0.22, "Warp Strength": 0.46},
    surface={"Vegetation Hue": (0.072, 0.128, 0.040, 1), "Rock Hue": (0.190, 0.150, 0.115, 1),
             "Sand Hue": (0.455, 0.320, 0.168, 1), "Ice Brightness": 0.85,
             "Ocean Shallow": (0.045, 0.215, 0.275, 1), "Ocean Deep": (0.0030, 0.013, 0.038, 1),
             "Shelf Boost": 0.386, "Vegetation Amount": 1.15, "River Tint": 0.55,
             "Ice Temp Threshold": 0.21, "Patchiness": 0.35, "Tech Level": 0.0, "Glint Variation": 0.75, "Foam Amount": 0.195, "Vegetation Clumping": 0.55, "Strata Amount": 0.28, "Ice Crack Amount": 0.35},
    clouds={"Cloud Coverage": 0.62, "Cloud Density": 1.35, "Band Strength": 0.52, "Detail Scale": 1.25},
    atmo={"Density": 0.0300, "Atmo Colour": (0.22, 0.44, 1.0, 1), "Falloff": 3.2, "Pollution": 0.0},
    rings=False, orbital=0.0)

P["colonial_outpost"] = dict(
    globe={"Continent Scale": 1.9, "Continent Coverage": 0.38, "Relief Strength": 24.0,
           "Mountain Sharpness": 0.60, "Erosion Amount": 0.40, "Sea Level": 0.0,
           "Polar Cap Extent": 0.24, "Tectonic Belt Width": 0.20, "Warp Strength": 0.50},
    surface={"Vegetation Hue": (0.070, 0.108, 0.048, 1), "Rock Hue": (0.180, 0.148, 0.118, 1),
             "Sand Hue": (0.420, 0.305, 0.172, 1), "Ice Brightness": 0.85,
             "Ocean Shallow": (0.042, 0.200, 0.260, 1), "Ocean Deep": (0.0030, 0.013, 0.038, 1),
             "Shelf Boost": 0.370, "Vegetation Amount": 1.0, "River Tint": 0.60,
             "Patchiness": 0.35, "Tech Level": 3.0, "Light Colour Temp": 0.12,
             "Urban Density": 1.65, "Night Light Intensity": 3.8,
             "Road Network Visibility": 1.1, "Agriculture Coverage": 0.9, "Glint Variation": 0.55, "Foam Amount": 0.137, "Vegetation Clumping": 0.4, "Strata Amount": 0.35, "Dune Amount": 0.25},
    clouds={"Cloud Coverage": 0.50, "Cloud Density": 1.2, "Band Strength": 0.50, "Detail Scale": 1.2},
    atmo={"Density": 0.0300, "Atmo Colour": (0.24, 0.44, 1.0, 1), "Falloff": 3.2, "Pollution": 0.05},
    rings=False, orbital=1.5)

P["industrial_world"] = dict(
    globe={"Continent Scale": 1.7, "Continent Coverage": 0.47, "Relief Strength": 20.7,
           "Mountain Sharpness": 0.50, "Erosion Amount": 0.34, "Sea Level": 0.0,
           "Polar Cap Extent": 0.16, "Tectonic Belt Width": 0.20, "Warp Strength": 0.44},
    surface={"Vegetation Hue": (0.078, 0.092, 0.044, 1), "Rock Hue": (0.170, 0.140, 0.115, 1),
             "Sand Hue": (0.400, 0.300, 0.180, 1), "Ice Brightness": 0.72,
             "Ocean Shallow": (0.052, 0.170, 0.190, 1), "Ocean Deep": (0.006, 0.014, 0.030, 1),
             "Shelf Boost": 0.353, "Vegetation Amount": 0.60, "River Tint": 0.50,
             "Patchiness": 0.30, "Tech Level": 6.0, "Light Colour Temp": 0.35,
             "Urban Density": 1.35, "Night Light Intensity": 1.5,
             "Road Network Visibility": 1.4, "Agriculture Coverage": 1.2, "Glint Variation": 0.45, "Foam Amount": 0.115, "Strata Amount": 0.4},
    clouds={"Cloud Coverage": 0.58, "Cloud Density": 1.3, "Band Strength": 0.55, "Detail Scale": 1.1},
    atmo={"Density": 0.0493, "Atmo Colour": (0.34, 0.36, 0.62, 1), "Falloff": 2.6, "Pollution": 0.62},
    rings=False, orbital=4.0)

P["hyperdeveloped"] = dict(
    globe={"Continent Scale": 1.8, "Continent Coverage": 0.42, "Relief Strength": 19.3,
           "Mountain Sharpness": 0.45, "Erosion Amount": 0.30, "Sea Level": 0.0,
           "Polar Cap Extent": 0.18, "Tectonic Belt Width": 0.18, "Warp Strength": 0.46},
    surface={"Vegetation Hue": (0.060, 0.085, 0.058, 1), "Rock Hue": (0.140, 0.140, 0.140, 1),
             "Sand Hue": (0.300, 0.260, 0.200, 1), "Ice Brightness": 0.70,
             "Ocean Shallow": (0.030, 0.130, 0.180, 1), "Ocean Deep": (0.002, 0.008, 0.026, 1),
             "Shelf Boost": 0.336, "Vegetation Amount": 0.55, "River Tint": 0.35,
             "Patchiness": 0.18, "Tech Level": 9.0, "Light Colour Temp": 0.85,
             "Urban Density": 1.9, "Night Light Intensity": 2.6,
             "Road Network Visibility": 1.4,
             "Grid Network Intensity": 0.70, "Megastructure Scale": 1.2, "Glint Variation": 0.4, "Foam Amount": 0.092, "Strata Amount": 0.25},
    clouds={"Cloud Coverage": 0.36, "Cloud Density": 1.0, "Band Strength": 0.5, "Detail Scale": 1.1},
    atmo={"Density": 0.0347, "Atmo Colour": (0.26, 0.44, 0.95, 1), "Falloff": 3.0, "Pollution": 0.28},
    rings=False, orbital=6.5,
    mega={"Mega Scale": 7.0, "Mirror Count": 140, "Mirror Size": 54.0,
          "Arc Count": 2, "Ring Sweep": 95.0, "Habitat Glow": 1.6,
          "Swarm Count": 320})

P["megastructure"] = dict(
    globe={"Continent Scale": 1.85, "Continent Coverage": 0.44, "Relief Strength": 18.3,
           "Mountain Sharpness": 0.42, "Erosion Amount": 0.28, "Sea Level": 0.0,
           "Polar Cap Extent": 0.16, "Tectonic Belt Width": 0.18, "Warp Strength": 0.48},
    surface={"Vegetation Hue": (0.055, 0.080, 0.062, 1), "Rock Hue": (0.130, 0.132, 0.136, 1),
             "Sand Hue": (0.270, 0.245, 0.205, 1), "Ice Brightness": 0.68,
             "Ocean Shallow": (0.026, 0.120, 0.170, 1), "Ocean Deep": (0.002, 0.007, 0.024, 1),
             "Shelf Boost": 0.336, "Vegetation Amount": 0.45, "River Tint": 0.30,
             "Patchiness": 0.14, "Tech Level": 10.0, "Light Colour Temp": 0.95,
             "Urban Density": 1.6, "Night Light Intensity": 2.0,
             "Grid Network Intensity": 0.7, "Megastructure Scale": 1.6, "Glint Variation": 0.4, "Foam Amount": 0.080},
    clouds={"Cloud Coverage": 0.32, "Cloud Density": 0.95, "Band Strength": 0.5, "Detail Scale": 1.1},
    atmo={"Density": 0.0329, "Atmo Colour": (0.28, 0.46, 1.0, 1), "Falloff": 3.0, "Pollution": 0.20},
    rings=False, orbital=10.0,
    mega={"Mega Scale": 9.5, "Mirror Count": 260, "Mirror Size": 72.0,
          "Arc Count": 4, "Ring Sweep": 165.0, "Ring Width": 180.0,
          "Habitat Glow": 2.4, "Swarm Count": 900})

P["ringed_ice"] = dict(
    globe={"Continent Scale": 1.6, "Continent Coverage": 0.34, "Relief Strength": 20.0,
           "Mountain Sharpness": 0.55, "Erosion Amount": 0.30, "Sea Level": 0.0,
           "Polar Cap Extent": 0.62, "Tectonic Belt Width": 0.22, "Warp Strength": 0.42},
    surface={"Vegetation Hue": (0.070, 0.100, 0.090, 1), "Rock Hue": (0.180, 0.185, 0.200, 1),
             "Sand Hue": (0.330, 0.330, 0.345, 1), "Ice Brightness": 1.25,
             "Ocean Shallow": (0.090, 0.230, 0.300, 1), "Ocean Deep": (0.006, 0.026, 0.060, 1),
             "Shelf Boost": 0.437, "Vegetation Amount": 0.25, "River Tint": 0.40,
             "Ice Temp Threshold": 0.46, "Patchiness": 0.24, "Tech Level": 0.0, "Ice Crack Amount": 0.9, "Foam Amount": 0.069, "Strata Amount": 0.2},
    clouds={"Cloud Coverage": 0.55, "Cloud Density": 1.15, "Band Strength": 0.62, "Detail Scale": 1.0,
            "Cloud Colour": (0.94, 0.97, 1.0, 1)},
    atmo={"Density": 0.0292, "Atmo Colour": (0.30, 0.52, 1.0, 1), "Falloff": 3.2, "Pollution": 0.0},
    rings=True, orbital=0.0,
    ring={"Gap Amount": 0.78, "Band Scale": 170.0, "Ring Density": 1.0,
          "Ring Colour": (0.80, 0.82, 0.86, 1),
          # bright, clean, sharply divided ice rings
          "Ice Colour": (0.90, 0.92, 0.96, 1), "Dust Colour": (0.66, 0.62, 0.58, 1),
          "Rock Colour": (0.30, 0.28, 0.27, 1), "Composition Scale": 4.2,
          "Band Contrast": 2.3, "Gap Softness": 0.10, "Division Depth": 1.0,
          "Spiral Arms": 9.0, "Spiral Strength": 0.26, "Spiral Winding": 58.0,
          "Wake Strength": 0.45, "Wake Count": 150.0,
          "Clump Scale": 6.5, "Clump Strength": 0.32,
          "Forward Anisotropy": 0.70, "Forward Gain": 3.1})

P["volcanic"] = dict(
    globe={"Continent Scale": 2.3, "Continent Coverage": 0.66, "Relief Strength": 32.0,
           "Mountain Sharpness": 1.05, "Erosion Amount": 0.20, "Sea Level": 0.0,
           "Polar Cap Extent": 0.05, "Tectonic Belt Width": 0.40, "Warp Strength": 0.58},
    surface={"Vegetation Hue": (0.150, 0.030, 0.008, 1), "Rock Hue": (0.055, 0.040, 0.038, 1),
             "Sand Hue": (0.110, 0.070, 0.055, 1), "Ice Brightness": 0.0,
             "Ocean Shallow": (0.520, 0.130, 0.020, 1), "Ocean Deep": (0.240, 0.035, 0.004, 1),
             "Shelf Boost": 0.806, "Vegetation Amount": 0.0, "River Tint": 1.6,
             "Ice Temp Threshold": 0.0, "Patchiness": 0.50, "Tech Level": 0.0,
             "Lava Emission": 24.0, "Strata Amount": 0.7, "Crater Amount": 0.25, "Dune Amount": 0.2},
    clouds={"Cloud Coverage": 0.30, "Cloud Density": 1.5, "Band Strength": 0.45,
            "Detail Scale": 1.4, "Cloud Colour": (0.32, 0.24, 0.20, 1)},
    atmo={"Density": 0.0548, "Atmo Colour": (0.62, 0.26, 0.10, 1), "Falloff": 2.4, "Pollution": 0.45},
    rings=False, orbital=0.0)

P["frozen"] = dict(
    globe={"Continent Scale": 1.7, "Continent Coverage": 0.44, "Relief Strength": 22.0,
           "Mountain Sharpness": 0.62, "Erosion Amount": 0.26, "Sea Level": 0.0,
           "Polar Cap Extent": 0.62, "Tectonic Belt Width": 0.24, "Warp Strength": 0.44},
    surface={"Vegetation Hue": (0.080, 0.100, 0.105, 1), "Rock Hue": (0.170, 0.178, 0.195, 1),
             "Sand Hue": (0.320, 0.330, 0.350, 1), "Ice Brightness": 1.05,
             "Ocean Shallow": (0.120, 0.250, 0.310, 1), "Ocean Deep": (0.010, 0.035, 0.075, 1),
             "Shelf Boost": 0.470, "Vegetation Amount": 0.0, "River Tint": 0.30,
             "Ice Temp Threshold": 0.50, "Patchiness": 0.18, "Tech Level": 0.0, "Ice Crack Amount": 0.85, "Strata Amount": 0.3},
    clouds={"Cloud Coverage": 0.48, "Cloud Density": 1.0, "Band Strength": 0.68, "Detail Scale": 0.9},
    atmo={"Density": 0.0256, "Atmo Colour": (0.34, 0.56, 1.0, 1), "Falloff": 3.4, "Pollution": 0.0},
    rings=False, orbital=0.0)

P["desert"] = dict(
    globe={"Continent Scale": 1.55, "Continent Coverage": 0.80, "Relief Strength": 24.7,
           "Mountain Sharpness": 0.66, "Erosion Amount": 0.50, "Sea Level": 0.0,
           "Polar Cap Extent": 0.08, "Tectonic Belt Width": 0.30, "Warp Strength": 0.54},
    surface={"Vegetation Hue": (0.150, 0.130, 0.055, 1), "Rock Hue": (0.235, 0.150, 0.092, 1),
             "Sand Hue": (0.560, 0.395, 0.205, 1), "Ice Brightness": 0.55,
             "Ocean Shallow": (0.080, 0.190, 0.190, 1), "Ocean Deep": (0.010, 0.028, 0.045, 1),
             "Shelf Boost": 0.403, "Vegetation Amount": 0.16, "River Tint": 0.75,
             "Ice Temp Threshold": 0.10, "Patchiness": 0.48, "Tech Level": 2.0,
             "Light Colour Temp": 0.15, "Urban Density": 0.7, "Dune Amount": 0.95, "Dune Scale": 300.0, "Strata Amount": 0.32, "Crater Amount": 0.15},
    # The deck is dust, not water. Mars' storms organise into latitude bands
    # and lift enough material that the limb haze stays bright to ~20 km and
    # stratifies above it, so coverage and density both go up, the colour goes
    # to suspended ochre, and a little Belt Contrast gives the storm fronts
    # somewhere to sit.
    clouds={"Cloud Coverage": 0.44, "Cloud Density": 1.7, "Band Strength": 0.72, "Detail Scale": 1.7,
            "Cloud Colour": (0.88, 0.66, 0.42, 1), "Belt Contrast": 0.30,
            "Belt Frequency": 9.0, "Belt Colour": (0.62, 0.40, 0.24, 1)},
    atmo={"Density": 0.0760, "Atmo Colour": (0.66, 0.40, 0.24, 1), "Falloff": 2.2, "Pollution": 0.55},
    rings=False, orbital=0.5)

P["ocean_world"] = dict(
    globe={"Continent Scale": 1.45, "Continent Coverage": 0.11, "Relief Strength": 17.3,
           "Mountain Sharpness": 0.50, "Erosion Amount": 0.30, "Sea Level": 0.0,
           "Polar Cap Extent": 0.22, "Tectonic Belt Width": 0.20, "Warp Strength": 0.50},
    surface={"Vegetation Hue": (0.062, 0.120, 0.055, 1), "Rock Hue": (0.170, 0.145, 0.115, 1),
             "Sand Hue": (0.470, 0.360, 0.210, 1), "Ice Brightness": 0.90,
             "Ocean Shallow": (0.040, 0.235, 0.300, 1), "Ocean Deep": (0.0020, 0.010, 0.034, 1),
             "Shelf Boost": 0.504, "Vegetation Amount": 1.2, "River Tint": 0.50,
             "Patchiness": 0.30, "Tech Level": 1.0, "Light Colour Temp": 0.3, "Glint Variation": 1.0, "Foam Amount": 0.229, "Vegetation Clumping": 0.3},
    clouds={"Cloud Coverage": 0.55, "Cloud Density": 1.2, "Band Strength": 0.58, "Detail Scale": 1.2},
    atmo={"Density": 0.0311, "Atmo Colour": (0.20, 0.44, 1.0, 1), "Falloff": 3.2, "Pollution": 0.0},
    rings=False, orbital=0.6)

P["dead_moon"] = dict(
    globe={"Continent Scale": 2.0, "Continent Coverage": 0.95, "Relief Strength": 29.3,
           "Mountain Sharpness": 0.85, "Erosion Amount": 0.10, "Sea Level": -1.0,
           "Polar Cap Extent": 0.0, "Tectonic Belt Width": 0.34, "Warp Strength": 0.40},
    surface={"Vegetation Hue": (0.10, 0.10, 0.10, 1), "Rock Hue": (0.115, 0.112, 0.108, 1),
             "Sand Hue": (0.185, 0.180, 0.172, 1), "Ice Brightness": 0.0,
             "Ocean Shallow": (0.05, 0.05, 0.05, 1), "Ocean Deep": (0.02, 0.02, 0.02, 1),
             "Shelf Boost": 0.336, "Vegetation Amount": 0.0, "River Tint": 0.0,
             "Ice Temp Threshold": 0.0, "Patchiness": 0.42, "Tech Level": 0.0,
             # Matched against LRO: bright highlands saturated with impacts,
             # dark basalt seas over roughly a fifth of the surface carrying a
             # fraction of the craters, and rays off the youngest few. Strata
             # drops right down -- bedding planes are a sedimentary feature and
             # an airless basalt moon has no business showing them.
             "Micro Disp Height": 0.534, "Crater Amount": 0.95, "Crater Scale": 26.0,
             "Maria Amount": 0.90, "Maria Scale": 1.4, "Crater Ray Amount": 0.75,
             "Strata Amount": 0.08},
    clouds={"Cloud Coverage": 0.0, "Cloud Density": 0.0, "Band Strength": 0.5, "Detail Scale": 1.0},
    atmo={"Density": 0.0022, "Atmo Colour": (0.5, 0.5, 0.5, 1), "Falloff": 4.0, "Pollution": 0.0},
    rings=False, orbital=0.0)

P["gas_giant"] = dict(
    globe={"Continent Scale": 1.2, "Continent Coverage": 0.02, "Relief Strength": 0.7,
           "Mountain Sharpness": 0.2, "Erosion Amount": 0.0, "Sea Level": 0.0,
           "Polar Cap Extent": 0.30, "Tectonic Belt Width": 0.2, "Warp Strength": 0.9},
    surface={"Vegetation Hue": (0.30, 0.22, 0.14, 1), "Rock Hue": (0.34, 0.26, 0.18, 1),
             "Sand Hue": (0.42, 0.32, 0.22, 1), "Ice Brightness": 0.4,
             "Ocean Shallow": (0.46, 0.36, 0.26, 1), "Ocean Deep": (0.30, 0.22, 0.15, 1),
             "Shelf Boost": 0.336, "Vegetation Amount": 0.0, "River Tint": 0.0,
             "Ice Temp Threshold": 0.0, "Patchiness": 0.2, "Tech Level": 0.0,
             "Micro Disp Height": 0.000},
    # gas giants read through their cloud deck: heavy banding, full coverage
    # Zones pale, belts dark: the colour alternation is the planet, and
    # coverage is pulled off the ceiling so the bands have somewhere to end.
    # Colour comes off Juno imagery rather than off the memory of a textbook
    # illustration: the zones are pale and faintly BLUE, not cream, and the
    # belts are rust. Putting a warm cream against a warm brown is what made
    # this planet one colour with stripes in it.
    clouds={"Cloud Coverage": 0.96, "Cloud Density": 2.4, "Band Strength": 1.0,
            "Detail Scale": 0.55, "Cloud Colour": (0.72, 0.77, 0.82, 1),
            "Belt Contrast": 1.0, "Belt Frequency": 23.0,
            "Belt Colour": (0.33, 0.18, 0.09, 1),
            # Boundaries as vortex trains, convective cells across the whole
            # disc, and a scattering of white ovals.
            "Belt Turbulence": 0.75, "Eddy Scale": 11.0, "Storm Amount": 0.70},
    atmo={"Density": 0.0658, "Atmo Colour": (0.56, 0.53, 0.50, 1), "Falloff": 2.2, "Pollution": 0.0},
    rings=True, orbital=0.0,
    ring={"Gap Amount": 0.52, "Band Scale": 170.0, "Ring Density": 1.45,
          "Ring Colour": (0.74, 0.70, 0.62, 1),
          # dustier, warmer, less sharply divided than the ice rings
          "Ice Colour": (0.80, 0.78, 0.74, 1), "Dust Colour": (0.60, 0.48, 0.34, 1),
          "Rock Colour": (0.36, 0.30, 0.24, 1), "Composition Scale": 2.8,
          "Band Contrast": 2.3, "Gap Softness": 0.16, "Division Depth": 0.95,
          "Spiral Arms": 7.0, "Spiral Strength": 0.30, "Spiral Winding": 52.0,
          "Wake Strength": 0.48, "Wake Count": 150.0,
          "Clump Scale": 4.5, "Clump Strength": 0.38,
          "Forward Anisotropy": 0.58, "Forward Gain": 2.2})

PRESET_NAMES = list(P.keys())

# Every look/tech parameter is reset to these before a preset is applied.
# Without this, any value a preset sets (e.g. volcanic's Lava Emission) leaks
# into every preset applied afterwards, because presets only write their own keys.
LOOK_DEFAULTS = {
    "Vegetation Hue": (0.078, 0.135, 0.042, 1), "Rock Hue": (0.190, 0.150, 0.115, 1),
    "Sand Hue": (0.455, 0.320, 0.168, 1), "Ice Brightness": 0.80,
    "Ocean Shallow": (0.045, 0.215, 0.275, 1), "Ocean Deep": (0.0035, 0.014, 0.040, 1),
    "Shelf Boost": 0.370, "Slope Rock Threshold": 0.26, "Vegetation Amount": 1.0,
    "Ice Temp Threshold": 0.20, "River Tint": 0.30, "Patchiness": 0.35,
    "Lava Emission": 0.0, "Micro Disp Height": 0.345, "Micro Disp Scale": 300,
    "Tech Level": 0.0, "Urban Density": 1.0, "Night Light Intensity": 1.0,
    "Light Colour Temp": 0.5, "Road Network Visibility": 1.0,
    "Agriculture Coverage": 1.0, "Grid Network Intensity": 1.0,
    "Megastructure Scale": 1.0,
    # surface detail features. Every one of these MUST be listed here even
    # though it defaults to 0: apply_preset writes this whole dict before each
    # preset, and any socket missing from it keeps whatever the previous
    # preset left behind. That is the bug that put a salmon ocean on five
    # consecutive shots after the volcanic preset set Lava Emission to 9.
    "Glint Variation": 0.0, "Foam Amount": 0.000,
    "Dune Amount": 0.0, "Dune Scale": 260.0,
    "Strata Amount": 0.0, "Strata Frequency": 90.0,
    "Ice Crack Amount": 0.0, "Vegetation Clumping": 0.0,
    "Crater Amount": 0.0, "Crater Scale": 34.0,
    "Maria Amount": 0.0, "Maria Scale": 2.2, "Crater Ray Amount": 0.0,
}
CLOUD_DEFAULTS = {"Cloud Coverage": 0.55, "Cloud Density": 1.25, "Band Strength": 0.52,
                  "Detail Scale": 1.2, "Cloud Colour": (1.0, 1.0, 1.0, 1),
                  "Cloud Relief": 0.30, "Belt Contrast": 0.0,
                  "Belt Frequency": 16.0, "Belt Colour": (0.55, 0.42, 0.30, 1)}
ATMO_DEFAULTS = {"Density": 0.0292, "Atmo Colour": (0.22, 0.44, 1.0, 1),
                 "Anisotropy": 0.3, "Falloff": 3.2, "Pollution": 0.0,
                 # 0.02 lifted the whole night hemisphere into a visible
                 # blue-grey veil that flattened the city lights against it.
                 # Real airglow is a few thousandths of daylight.
                 "Night Glow": 0.004, "Intensity": 1.0}
# apply_preset never wrote the megastructure rig at all, so the ringworld,
# the mirror belt and the Dyson swarm stayed at Mega Scale 0 on every preset
# including "megastructure". Shot 10 was built from the orbital rig alone.
MEGA_DEFAULTS = {
    "Mega Scale": 0.0, "Mirror Orbit": 1.9, "Mirror Count": 90,
    "Mirror Size": 62.0, "Ring Orbit": 2.7, "Ring Sweep": 130.0,
    "Ring Width": 120.0, "Arc Count": 3, "Habitat Glow": 1.0,
    "Swarm Count": 240, "Arc Motion": 0,
}
RING_DEFAULTS = {
    "Ring Density": 1.0, "Ring Colour": (0.72, 0.70, 0.65, 1),
    "Ice Colour": (0.86, 0.88, 0.92, 1), "Dust Colour": (0.62, 0.52, 0.40, 1),
    "Rock Colour": (0.34, 0.29, 0.25, 1), "Composition Scale": 3.4,
    "Band Scale": 120.0, "Band Contrast": 1.9, "Gap Amount": 0.55,
    "Gap Softness": 0.18, "Division Depth": 1.0,
    "Spiral Arms": 7.0, "Spiral Strength": 0.22, "Spiral Winding": 46.0,
    "Wake Strength": 0.35, "Wake Count": 120.0,
    "Clump Scale": 5.5, "Clump Strength": 0.30,
    "Forward Anisotropy": 0.62, "Forward Gain": 2.4,
    "Planet Radius": 1000.0,
}


def check_defaults(node_group_name="PLNT_SurfaceShader", defaults=None):
    """Every writable interface input must appear in the defaults dict.

    Import-time guard against the preset-bleed bug returning as new sockets are
    added: a socket the presets never reset keeps the previous preset's value.
    """
    import bpy as _b
    ng = _b.data.node_groups.get(node_group_name)
    if not ng:
        return {"skipped": "no %s" % node_group_name}
    defaults = LOOK_DEFAULTS if defaults is None else defaults
    skip = {"Seed", "Relief Strength", "Continent Scale", "Continent Coverage",
            "Mountain Sharpness", "Erosion Amount", "Tectonic Belt Width",
            "Warp Strength", "Sea Level", "Polar Cap Extent"}
    missing = [i.name for i in ng.interface.items_tree
               if getattr(i, "item_type", "") == 'SOCKET' and i.in_out == 'INPUT'
               and i.name not in skip and i.name not in defaults]
    return {"missing_from_defaults": missing}


# ---------------------------------------------------------------- apply
def _tag_all():
    """Modifier writes do not dirty the depsgraph on their own."""
    for n in ("PLNT_Globe", "PLNT_Clouds", "PLNT_Atmosphere", "PLNT_Rings",
              "PLNT_Orbital", "PLNT_Patch", "PLNT_Mega"):
        ob = bpy.data.objects.get(n)
        if ob:
            ob.update_tag()


def apply_preset(name, seed=None):
    if name not in P:
        raise KeyError("unknown preset %r (have: %s)" % (name, ", ".join(PRESET_NAMES)))
    d = P[name]
    ob = _obj(GLOBE)
    if ob is None:
        raise RuntimeError("PLNT_Globe not found")
    mod = ob.modifiers[MOD]
    for k, v in d["globe"].items():
        gset(mod, k, v)
    if seed is not None:
        gset(mod, "Seed", float(seed))

    surf = dict(LOOK_DEFAULTS)
    surf.update(d["surface"])
    if seed is not None:
        surf["Seed"] = float(seed)
    # mirror geometry params onto both materials
    for k in ("Seed", "Continent Scale", "Continent Coverage", "Mountain Sharpness",
              "Erosion Amount", "Tectonic Belt Width", "Warp Strength", "Sea Level",
              "Polar Cap Extent", "Relief Strength"):
        v = gget(mod, k)
        if v is not None:
            surf.setdefault(k, v)
            surf[k] = v
    for mname in (SURF, PATCHSURF):
        _set_ctl(mname, surf)

    cl = dict(CLOUD_DEFAULTS)
    cl.update(d["clouds"])
    if seed is not None:
        cl["Cloud Seed"] = float(seed) * 1.7 + 11.0
    _set_ctl(CLOUDS, cl)
    atm = dict(ATMO_DEFAULTS); atm.update(d["atmo"])
    _set_ctl(ATMO, atm)

    r = _obj(RINGS)
    if r:
        r.hide_render = not d.get("rings", False)
        r.hide_viewport = not d.get("rings", False)
        # full reset before the preset's own overrides, same reason as
        # LOOK_DEFAULTS: without it ring settings bleed between presets
        rng = dict(RING_DEFAULTS)
        rng.update(d.get("ring") or {})
        _set_ctl(RINGS, rng)

    orb = _obj(ORBITAL)
    if orb:
        om = orb.modifiers.get("PLNT_OrbitalRig")
        if om:
            gset(om, "Orbital Level", float(d.get("orbital", 0.0)))
            if seed is not None:
                gset(om, "Seed", float(seed))

    meg = _obj("PLNT_Mega")
    if meg:
        mm = meg.modifiers.get("PLNT_MegaRig")
        if mm:
            mg = dict(MEGA_DEFAULTS)
            mg.update(d.get("mega") or {})
            for k, v in mg.items():
                gset(mm, k, v)
            if seed is not None:
                gset(mm, "Seed", float(seed) * 0.31 + 7.0)
            # below 0.5 the rig builds nothing, so hide it outright rather
            # than leaving an empty object in the outliner
            on = mg.get("Mega Scale", 0.0) >= 0.5
            meg.hide_render = not on
            meg.hide_viewport = not on

    patch = _obj("PLNT_Patch")
    if patch:
        pm = patch.modifiers.get("PLNT_PatchRig")
        if pm:
            for k, v in d["globe"].items():
                gset(pm, k, v)
            if seed is not None:
                gset(pm, "Seed", float(seed))
    return name


def randomize(seed, tech_level=None):
    """Pick a preset deterministically from the seed and jitter its terrain."""
    rng = random.Random(int(seed))
    name = rng.choice(PRESET_NAMES)
    apply_preset(name, seed=seed)
    ob = _obj(GLOBE)
    mod = ob.modifiers[MOD]
    jit = {
        "Continent Scale": (0.75, 1.35),
        "Continent Coverage": (0.80, 1.20),
        "Relief Strength": (0.80, 1.30),
        "Mountain Sharpness": (0.75, 1.35),
        "Erosion Amount": (0.70, 1.35),
        "Warp Strength": (0.80, 1.30),
        "Tectonic Belt Width": (0.80, 1.25),
    }
    for k, (lo, hi) in jit.items():
        v = gget(mod, k)
        if v is not None:
            gset(mod, k, float(v) * rng.uniform(lo, hi))
    if tech_level is not None:
        for mname in (SURF, PATCHSURF):
            _set_ctl(mname, {"Tech Level": float(tech_level)})
        orb = _obj(ORBITAL)
        if orb and orb.modifiers.get("PLNT_OrbitalRig"):
            gset(orb.modifiers["PLNT_OrbitalRig"], "Orbital Level", float(tech_level))
    # keep materials in step with the jittered geometry
    surf = {}
    for k in ("Seed", "Continent Scale", "Continent Coverage", "Mountain Sharpness",
              "Erosion Amount", "Tectonic Belt Width", "Warp Strength", "Sea Level",
              "Polar Cap Extent", "Relief Strength"):
        v = gget(mod, k)
        if v is not None:
            surf[k] = v
    for mname in (SURF, PATCHSURF):
        _set_ctl(mname, surf)
    return name


def sun(azimuth_deg, elevation_deg=0.0):
    """Point the sun rig. Must stay identical to core.scene.set_sun.

    This used to set the pivot only, relying on PLNT_Sun already carrying a
    base rotation of (0, 90, 0). core.scene.set_sun used a different convention
    and wrote the sun object too, so whichever ran last decided what the
    azimuth meant, a 90 degree difference that never looked broken and
    relit every hero shot the first time the scene was rebuilt from the
    builders rather than patched.
    """
    import math
    piv = _obj("PLNT_SunPivot")
    s = _obj("PLNT_Sun")
    if piv:
        piv.rotation_euler = (0.0, math.radians(-elevation_deg),
                              math.radians(azimuth_deg))
    if s:
        s.rotation_euler = (0.0, math.pi * 0.5, 0.0)
    return True


# ---------------------------------------------------------------- UI
# The panels, operators and PLNT_Props that used to live here were v1's UI.
# They are gone: core/ui.py owns the interface now, and this file is also
# embedded as a text datablock inside the .blend, so the two registered the
# SAME bl_idname ("PLNT_PT_main"). Whichever ran last won, which is why the
# N-panel could come back as the old four-panel layout with none of the ring,
# orbital, megastructure, patch or sky controls in it.
#
# What stays here is the data and the plumbing that writes it: P, the
# *_DEFAULTS tables, apply_preset, randomize and sun.
