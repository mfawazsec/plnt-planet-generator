"""Central parameter registry: the single source of truth for how every socket
is presented.

Why this exists
---------------
The old panels hand-listed socket names (GLOBE_PARAMS, LOOK_PARAMS, TECH_PARAMS).
Anything not on a list was simply unreachable -- which is how every ring
parameter, all eight patch parameters, the orbital structural parameters and the
sun/starfield settings ended up with no UI at all. The UI now enumerates node
group interfaces directly and consults this table only for grouping, ordering,
tier and help text. A socket missing from this table still appears (under
Advanced); it can never be orphaned.

Keys are (owner, socket_name). `owner` is needed because names collide across
subsystems: "Seed" exists on the globe, the rings and the orbital rig; "Density"
means atmospheric density on the atmosphere and ring opacity on the rings.

TIERS
  BASIC     the handful of controls that change the planet's identity
  ADVANCED  everything else -- shown when the user asks for it
"""

PANELS = [
    ("preset",  "Preset",          'PRESET'),
    ("terrain", "Terrain",         'WORLD'),
    ("surface", "Surface Look",    'MATERIAL'),
    ("ocean",   "Ocean & Ice",     'MOD_FLUIDSIM'),
    ("civ",     "Civilisation",    'HOME'),
    ("clouds",  "Clouds",          'OUTLINER_DATA_VOLUME'),
    ("atmo",    "Atmosphere",      'FORCE_FORCE'),
    ("rings",   "Rings",           'MESH_CIRCLE'),
    ("orbital", "Orbital",         'MOD_ARRAY'),
    ("mega",    "Megastructures",  'MOD_BUILD'),
    ("sky",     "Sun & Sky",       'LIGHT_SUN'),
    ("patch",   "Ground Patch",    'MESH_GRID'),
    ("camera",  "Camera",          'CAMERA_DATA'),
]
# Thirteen sibling sub-panels under one header is a wall, and the order they
# happen to be declared in is not an order anyone reads. Four groups, named
# after the thing being built rather than after the code that builds it.
GROUPS = [
    ("planet", "Planet",       'WORLD'),
    ("sky",    "Sky",          'OUTLINER_DATA_VOLUME'),
    ("civ",    "Civilisation", 'HOME'),
    ("scene",  "Scene",        'SCENE_DATA'),
]
GROUP_LABEL = {g[0]: g[1] for g in GROUPS}
GROUP_ICON = {g[0]: g[2] for g in GROUPS}
GROUP_ORDER = {g[0]: i for i, g in enumerate(GROUPS)}

PANEL_GROUP = {
    "terrain": "planet", "surface": "planet", "ocean": "planet",
    "patch":   "planet",
    "clouds":  "sky",    "atmo":    "sky",    "sky":   "sky",
    "civ":     "civ",    "orbital": "civ",    "mega":  "civ",
    "rings":   "scene",  "camera":  "scene",  "render": "scene",
}


def group_of(panel_id):
    return PANEL_GROUP.get(panel_id, "scene")


PANEL_ORDER = {p[0]: i for i, p in enumerate(PANELS)}
PANEL_LABEL = {p[0]: p[1] for p in PANELS}
PANEL_ICON = {p[0]: p[2] for p in PANELS}

DEFAULT_PANEL = "surface"
DEFAULT_TIER = 'ADVANCED'

# (owner, socket) -> (panel, order, tier, description)
# Descriptions are written to be read in a tooltip: what it does first, then the
# practical consequence of turning it up.
SPEC = {}


def _add(owner, rows):
    for name, panel, order, tier, desc in rows:
        SPEC[(owner, name)] = (panel, order, tier, desc)


# --------------------------------------------------------------------------
# Terrain -- shared by the globe rig, the surface shader and the ground patch.
# --------------------------------------------------------------------------
_TERRAIN = [
    ("Seed", "terrain", 10, 'BASIC',
     "Master random seed. Every noise in the terrain, clouds and cities derives "
     "from this, so changing it gives a completely different planet with the same "
     "settings"),
    ("Continent Scale", "terrain", 20, 'BASIC',
     "Number of continents. Low values give one or two supercontinents; high "
     "values break the land into many small island chains"),
    ("Continent Coverage", "terrain", 30, 'BASIC',
     "Fraction of the surface above sea level, before Sea Level is applied. "
     "Raise for a land world, lower for an ocean world"),
    ("Sea Level", "terrain", 40, 'BASIC',
     "Height of the waterline in the elevation field. Raising it floods "
     "lowlands and turns coastal plains into shelf sea"),
    ("Relief Strength", "terrain", 50, 'BASIC',
     "Vertical exaggeration of the terrain, in Blender units of displacement. "
     "This is what makes mountains read as mountains at the limb"),
    ("Mountain Sharpness", "terrain", 60, 'ADVANCED',
     "Ridge sharpness of mountain belts. Low is rolling and worn, high is "
     "knife-edged alpine ridgelines"),
    ("Erosion Amount", "terrain", 70, 'ADVANCED',
     "How strongly high ground is worn down toward the valleys. Raising it "
     "widens valleys and flattens summits"),
    ("Tectonic Belt Width", "terrain", 80, 'ADVANCED',
     "Width of the mountain-building belts. Narrow gives long thin cordilleras; "
     "wide gives broad plateau uplift"),
    ("Warp Strength", "terrain", 90, 'ADVANCED',
     "Domain warping applied to the noise coordinates. This is what stops the "
     "terrain looking like isotropic noise and gives coastlines their folded, "
     "non-repeating character. Zero looks obviously procedural"),
    ("Polar Cap Extent", "terrain", 100, 'ADVANCED',
     "How far the ice caps reach from the poles toward the equator"),
    ("Subdiv Level", "terrain", 110, 'ADVANCED',
     "Base mesh subdivision of the globe. This carries the large-scale shape; "
     "fine detail comes from displacement at render time. Raising it costs "
     "memory, not render time"),
    ("Radius", "terrain", 120, 'ADVANCED',
     "Planet radius in Blender units. Cameras and rings are placed relative to "
     "this, so changing it rescales the whole system"),
    ("Surface Material", "terrain", 130, 'ADVANCED',
     "Material applied to the generated globe. Geometry Nodes output carries no "
     "material of its own, so this must be set or the planet renders white"),
]
_add("globe", _TERRAIN)
_add("surface", _TERRAIN)
_add("patch", _TERRAIN)


# --------------------------------------------------------------------------
# Surface look
# --------------------------------------------------------------------------
_add("surface", [
    ("Vegetation Amount", "surface", 10, 'BASIC',
     "How much of the habitable land is covered in vegetation. Zero gives a "
     "sterile rock world even where the climate would allow life"),
    ("Vegetation Hue", "surface", 20, 'BASIC',
     "Colour of vegetation. Earth greens are the obvious choice; reds, teals "
     "and violets read immediately as an alien biosphere"),
    ("Rock Hue", "surface", 30, 'BASIC',
     "Base colour of exposed rock, used on steep slopes and barren ground"),
    ("Sand Hue", "surface", 40, 'BASIC',
     "Colour of arid lowland ground -- desert, dust and dry plains"),
    ("Slope Rock Threshold", "surface", 50, 'ADVANCED',
     "Steepness at which ground stops being soil and becomes bare rock. Lower "
     "values expose rock on gentler slopes, which reads as a younger, "
     "less-weathered world"),
    ("Patchiness", "surface", 60, 'ADVANCED',
     "Breaks the biome colours up with a mottling noise so terrain does not "
     "read as flat painted regions"),
    ("River Tint", "surface", 70, 'ADVANCED',
     "Strength of the river network's colour on the surface. The river geometry "
     "is always present; this controls how visible it is"),
    ("Micro Disp Height", "surface", 80, 'ADVANCED',
     "Amplitude of fine surface relief added at render time, below the "
     "resolution of the base mesh. This is what holds up in close-ups"),
    ("Micro Disp Scale", "surface", 90, 'ADVANCED',
     "Feature size of the fine surface relief. High values give sand-grade "
     "texture, low values give hill-grade texture"),
    ("Glint Variation", "ocean", 5, 'BASIC',
     "Breaks up the ocean's specular highlight with wind fetch and slicks. At "
     "zero the sea is a uniform mirror, the most obvious tell in a sunlit "
     "ocean shot"),
    ("Foam Amount", "ocean", 6, 'BASIC',
     "White water where shallow sea meets land"),
    ("Dune Amount", "surface", 110, 'BASIC',
     "Transverse dune ridges in arid lowlands"),
    ("Dune Scale", "surface", 112, 'ADVANCED',
     "Spacing of the dune ridges"),
    ("Strata Amount", "surface", 120, 'BASIC',
     "Sedimentary banding in exposed rock, following lines of constant "
     "elevation so it reads as bedding planes"),
    ("Strata Frequency", "surface", 122, 'ADVANCED',
     "Number of visible rock layers"),
    ("Ice Crack Amount", "ocean", 60, 'ADVANCED',
     "Crevasse and glacier-flow structure in ice sheets"),
    ("Vegetation Clumping", "surface", 25, 'ADVANCED',
     "Varies vegetation hue patch by patch instead of tinting every plant on "
     "the planet identically"),
    ("Crater Amount", "surface", 130, 'BASIC',
     "Impact craters with raised rims, for airless worlds"),
    ("Crater Scale", "surface", 132, 'ADVANCED',
     "Crater density; higher values give smaller, denser craters"),
    ("Lava Emission", "surface", 100, 'BASIC',
     "Brightness of molten rock in fissures below sea level. Above zero the "
     "ocean basins become a magma sea that lights the planet's night side"),
])

# --------------------------------------------------------------------------
# Ocean and ice
# --------------------------------------------------------------------------
_add("surface", [
    ("Ocean Shallow", "ocean", 10, 'BASIC',
     "Water colour over the continental shelf, where light reaches the bottom "
     "and scatters back"),
    ("Ocean Deep", "ocean", 20, 'BASIC',
     "Water colour in the deep basins, where almost nothing returns"),
    ("Shelf Boost", "ocean", 30, 'ADVANCED',
     "How strongly shallow water brightens toward the coast. This is the "
     "turquoise fringe that makes coastlines legible from orbit"),
    ("Ice Brightness", "ocean", 40, 'BASIC',
     "Albedo of polar and high-altitude ice. Ice is the brightest thing on the "
     "planet, so this strongly affects overall exposure"),
    ("Ice Temp Threshold", "ocean", 50, 'ADVANCED',
     "Temperature below which surface ice forms. Raising it grows the caps and "
     "puts ice on mountain ranges at lower latitudes"),
])

# --------------------------------------------------------------------------
# Civilisation
# --------------------------------------------------------------------------
_add("surface", [
    ("Tech Level", "civ", 10, 'BASIC',
     "Master civilisation control, 0-10. Zero is a pristine world with no trace "
     "of habitation. Each step unlocks the next layer: settlements, roads, "
     "agriculture, night lights, power grids, then megastructures. The "
     "individual sliders below scale within whatever this allows"),
    ("Urban Density", "civ", 20, 'BASIC',
     "How much land the settlements cover. Low gives isolated outposts, high "
     "gives continuous urban sprawl along the habitable belts"),
    ("Night Light Intensity", "civ", 30, 'BASIC',
     "Brightness of city lights on the unlit side. These are area-limited, not "
     "brightness-limited -- if they are hard to see, raise Urban Density rather "
     "than pushing this higher"),
    ("Light Colour Temp", "civ", 40, 'ADVANCED',
     "Colour of the night lights, from warm sodium (an early industrial world) "
     "to cold blue-white (a high-technology one)"),
    ("Road Network Visibility", "civ", 50, 'ADVANCED',
     "Visibility of surface transport links between settlements"),
    ("Agriculture Coverage", "civ", 60, 'ADVANCED',
     "Extent of cultivated land around settlements. Reads as regular tinted "
     "blocks in the habitable zones"),
    ("Grid Network Intensity", "civ", 70, 'ADVANCED',
     "Brightness of the planet-spanning geometric energy grid. This is a "
     "high-technology feature and looks wrong on a low Tech Level"),
    ("Megastructure Scale", "civ", 80, 'ADVANCED',
     "Size of surface megastructures. Below the activation threshold no "
     "geometry appears at all"),
])


# --------------------------------------------------------------------------
# Clouds / atmosphere
# --------------------------------------------------------------------------
_add("cloud", [
    ("Cloud Coverage", "clouds", 10, 'BASIC',
     "Fraction of the sky filled with cloud. At zero the surface is fully "
     "exposed; near one the planet is permanently overcast"),
    ("Cloud Density", "clouds", 20, 'BASIC',
     "Opacity of the cloud deck. Thin cloud lets surface colour through and "
     "reads as haze; dense cloud reads as solid white weather systems"),
    ("Band Strength", "clouds", 30, 'ADVANCED',
     "How strongly cloud is organised into latitude bands by planetary "
     "rotation. High values give a banded gas-giant look; zero gives "
     "unstructured cloud"),
    ("Detail Scale", "clouds", 40, 'ADVANCED',
     "Feature size of cloud structure. Higher values give finer, wispier "
     "systems"),
    ("Cloud Colour", "clouds", 50, 'ADVANCED',
     "Tint of the cloud deck. Off-white for water vapour, ochre for dust, "
     "yellow-green for a toxic atmosphere"),
    ("Cloud Seed", "clouds", 60, 'ADVANCED',
     "Random seed for the weather pattern only. Change it to reroll the "
     "clouds while keeping the same continents"),
    ("Cloud Relief", "clouds", 70, 'ADVANCED',
     "Shading relief on the cloud tops. The deck is a single thin shell, so "
     "without this it reads as a flat stencil; raising it gives the systems a "
     "lit side and a shadowed side"),
])
_add("atmo", [
    ("Density", "atmo", 10, 'BASIC',
     "Thickness of the atmosphere. This drives the bright limb halo -- the "
     "single strongest cue that the planet has air"),
    ("Atmo Colour", "atmo", 20, 'BASIC',
     "Colour of atmospheric scattering. Blue for an Earth-like nitrogen-oxygen "
     "atmosphere, orange or green for exotic chemistry"),
    ("Falloff", "atmo", 30, 'ADVANCED',
     "How quickly the atmosphere thins with altitude. Sharp falloff gives a "
     "tight bright rim, soft falloff gives a broad diffuse glow"),
    ("Anisotropy", "atmo", 40, 'ADVANCED',
     "Directional bias of scattering. Positive values scatter light forward, "
     "so the atmosphere flares brightly when the planet is backlit"),
    ("Pollution", "atmo", 50, 'ADVANCED',
     "Industrial haze mixed into the atmosphere -- desaturates and warms it. "
     "Pairs with a high Tech Level"),
    ("Inner Radius", "atmo", 60, 'ADVANCED',
     "Altitude at which the atmosphere begins. Should sit at the planet "
     "surface"),
    ("Night Glow", "atmo", 55, 'ADVANCED',
     "Residual brightness on the unlit side, so the terminator does not end in "
     "a hard black edge"),
    ("Intensity", "atmo", 15, 'BASIC',
     "Overall brightness of atmospheric scattering"),
    ("Outer Radius", "atmo", 70, 'ADVANCED',
     "Top of the atmosphere. The gap between this and Inner Radius is the "
     "depth of the visible shell"),
])

# --------------------------------------------------------------------------
# Rings
# --------------------------------------------------------------------------
_add("ring", [
    ("Inner", "rings", 10, 'BASIC',
     "Inner edge of the ring system, in planet radii. Below about 1.2 the "
     "rings intersect the atmosphere"),
    ("Outer", "rings", 20, 'BASIC',
     "Outer edge of the ring system, in planet radii"),
    ("Ring Density", "rings", 30, 'BASIC',
     "Overall opacity of the ring material. Low values give a faint dust ring, "
     "high values a solid bright band"),
    ("Ring Colour", "rings", 40, 'BASIC',
     "Tint of the ring particles -- clean ice, or dirty ice reddened by rock "
     "and organics"),
    ("Band Scale", "rings", 50, 'ADVANCED',
     "Number of distinct ringlets across the system. Real ring systems have "
     "hundreds, so high values read as more authentic"),
    ("Gap Amount", "rings", 60, 'ADVANCED',
     "How much empty space is cut between ringlets. This is what turns a "
     "smooth disc into visibly separated bands"),
    ("Ring Seed", "rings", 70, 'ADVANCED',
     "Random seed for ring structure, independent of the planet seed"),
])
_add("ring", [
    ("Band Contrast", "rings", 55, 'ADVANCED',
     "Sharpness of the ringlet edges. Applied before the gaps are cut, which "
     "is what makes the result read as hundreds of distinct ringlets rather "
     "than a smooth radial gradient"),
    ("Gap Softness", "rings", 62, 'ADVANCED',
     "How sharp the named divisions are. Real ring gaps have very sharp edges, "
     "so low values are the realistic choice"),
    ("Division Depth", "rings", 64, 'BASIC',
     "How completely the named divisions (Cassini, Encke, Keeler and the rest) "
     "are cleared out. At zero they disappear entirely"),
    ("Spiral Arms", "rings", 100, 'ADVANCED',
     "Number of spiral density waves, driven by orbital resonances with the "
     "moons. Rounded to a whole number, because a fractional arm count leaves "
     "a visible seam where the rings wrap around"),
    ("Spiral Strength", "rings", 102, 'ADVANCED',
     "Contrast of the spiral density waves. This is the main thing that stops "
     "the rings reading as perfect concentric circles"),
    ("Spiral Winding", "rings", 104, 'ADVANCED',
     "How tightly the density waves wind. High values give many tight turns "
     "across the ring; low values give lazy open spirals"),
    ("Wake Strength", "rings", 110, 'ADVANCED',
     "Strength of the wake a shepherd moon carves at a gap edge -- the "
     "propeller-shaped disturbance Cassini photographed at the Encke gap"),
    ("Wake Count", "rings", 112, 'ADVANCED',
     "Number of wake ripples around the circumference"),
    ("Clump Scale", "rings", 120, 'ADVANCED',
     "Size of the azimuthal clumping. Ring particles bunch up rather than "
     "spreading evenly around each orbit"),
    ("Clump Strength", "rings", 122, 'ADVANCED',
     "How pronounced the azimuthal clumping is"),
    ("Ice Colour", "rings", 130, 'ADVANCED',
     "Colour of the icy ring material, which dominates the bright bands"),
    ("Dust Colour", "rings", 132, 'ADVANCED',
     "Colour of the dusty component, usually reddened by organics"),
    ("Rock Colour", "rings", 134, 'ADVANCED',
     "Colour of the rocky component, which reads as the dark bands"),
    ("Composition Scale", "rings", 136, 'ADVANCED',
     "How rapidly composition changes with radius. Low values give a few broad "
     "compositional zones; high values give rapid ice/rock alternation"),
    ("Forward Anisotropy", "rings", 140, 'ADVANCED',
     "How sharply the ring particles scatter light forward. This is what makes "
     "the rings flare when the planet is between you and the sun"),
    ("Forward Gain", "rings", 142, 'ADVANCED',
     "Brightness of the forward-scattering flare"),
    ("Radial Segments", "rings", 150, 'ADVANCED',
     "Mesh resolution across the ring. Raise if radial banding looks stepped"),
    ("Angular Segments", "rings", 152, 'ADVANCED',
     "Mesh resolution around the ring. Raise if the outer edge looks polygonal"),
    ("Ring Warp", "rings", 154, 'ADVANCED',
     "Vertical corrugation of the ring plane. Gives the disc a real "
     "cross-section when seen edge-on instead of an aliasing line"),
    ("Warp Scale", "rings", 156, 'ADVANCED',
     "Feature size of the vertical corrugation"),
])
_add("ringrig", [
    ("Inner", "rings", 10, 'BASIC', "Inner edge of the ring annulus"),
    ("Outer", "rings", 20, 'BASIC', "Outer edge of the ring annulus"),
    ("Radial Segments", "rings", 150, 'ADVANCED',
     "Mesh resolution across the ring"),
    ("Angular Segments", "rings", 152, 'ADVANCED',
     "Mesh resolution around the ring"),
    ("Ring Warp", "rings", 154, 'ADVANCED',
     "Vertical corrugation of the ring plane"),
    ("Warp Scale", "rings", 156, 'ADVANCED',
     "Feature size of the vertical corrugation"),
])
_add("ringrig", [
    ("Size", "rings", 80, 'ADVANCED',
     "Extent of the mesh the rings are drawn on. Must comfortably exceed the "
     "outer radius or the rings will be clipped"),
])

# --------------------------------------------------------------------------
# Orbital infrastructure
# --------------------------------------------------------------------------
_add("orbital", [
    ("Orbital Level", "orbital", 10, 'BASIC',
     "Amount of orbital infrastructure, 0-10. Above 0.5 scattered satellites "
     "appear, above 3 a structural band, above 6 three intersecting bands, and "
     "above 8 an equatorial space elevator"),
    ("Band Height", "orbital", 20, 'ADVANCED',
     "Cross-section height of the orbital bands. Larger bands read as "
     "habitats rather than as trusses"),
    ("Radius", "orbital", 30, 'ADVANCED',
     "Planet radius the orbital structures are placed around. Should match the "
     "globe's radius"),
    ("Seed", "orbital", 40, 'ADVANCED',
     "Random seed for satellite placement and structural detail"),
    ("Material", "orbital", 50, 'ADVANCED',
     "Material applied to the orbital structures"),
])

_add("orbital", [
    ("Band Width", "orbital", 22, 'ADVANCED',
     "Cross-section width of the orbital bands"),
    ("Band Resolution", "orbital", 24, 'ADVANCED',
     "Segments around each band. Raise if the band looks polygonal"),
    ("Bay Length", "orbital", 30, 'ADVANCED',
     "Length of one truss bay. The bay count is derived from the "
     "circumference, so braces meet exactly instead of overlapping"),
    ("Longeron Radius", "orbital", 32, 'ADVANCED',
     "Thickness of the rails running the length of the truss"),
    ("Satellite Density", "orbital", 40, 'BASIC',
     "How many orbital slots carry a satellite"),
    ("Cluster Scale", "orbital", 42, 'ADVANCED',
     "Size of the clusters satellites gather into. Real orbital traffic "
     "bunches into planes and altitude shells rather than spreading evenly"),
    ("Shell Thickness", "orbital", 44, 'ADVANCED',
     "Depth of the orbital shell, so satellites sit at a spread of altitudes "
     "instead of all on one sphere"),
    ("Module Scale", "orbital", 46, 'BASIC',
     "Overall size of the instanced structures"),
    ("Hub Count", "orbital", 50, 'ADVANCED',
     "Number of large station hubs spaced around the main band"),
    ("Lit Fraction", "orbital", 60, 'ADVANCED',
     "Fraction of modules whose windows are lit"),
    ("Light Colour", "orbital", 62, 'ADVANCED',
     "Colour of the structures' own lighting"),
    ("Light Material", "orbital", 64, 'ADVANCED',
     "Emissive material for lit panels and windows"),
    ("Tether Taper", "orbital", 70, 'ADVANCED',
     "How much wider the space elevator ribbon is at geostationary height "
     "than at the anchor. A real tether must taper to carry its own weight"),
    ("Climber Count", "orbital", 72, 'ADVANCED',
     "Number of climbers riding the tether"),
])

# --------------------------------------------------------------------------
# Megastructures
# --------------------------------------------------------------------------
_add("mega", [
    ("Mega Scale", "mega", 10, 'BASIC',
     "Overall size of the orbital megastructures. Below the activation "
     "threshold no geometry is built at all"),
    ("Mirror Orbit", "mega", 20, 'ADVANCED',
     "Orbital radius of the solar mirror array, in planet radii"),
    ("Mirror Count", "mega", 22, 'ADVANCED',
     "Number of mirrors in the equatorial belt"),
    ("Mirror Size", "mega", 24, 'ADVANCED',
     "Size of an individual mirror panel"),
    ("Ring Orbit", "mega", 30, 'ADVANCED',
     "Orbital radius of the partial ringworld arcs"),
    ("Ring Sweep", "mega", 32, 'ADVANCED',
     "How far around the planet each ringworld arc reaches, in degrees"),
    ("Ring Width", "mega", 34, 'ADVANCED',
     "Width of the ringworld habitat band"),
    ("Arc Count", "mega", 36, 'ADVANCED',
     "Number of separate ringworld arcs"),
    ("Habitat Glow", "mega", 40, 'ADVANCED',
     "Brightness of the inhabited inner face of the ringworld arcs"),
    ("Swarm Count", "mega", 50, 'ADVANCED',
     "Number of collectors in the Dyson swarm"),
    ("Radius", "mega", 60, 'ADVANCED',
     "Planet radius the megastructures are placed around; should match the "
     "globe's radius"),
    ("Seed", "mega", 62, 'ADVANCED',
     "Random seed for megastructure placement"),
    ("Material", "mega", 70, 'ADVANCED',
     "Structural material for the ringworld arcs"),
    ("Mirror Material", "mega", 72, 'ADVANCED',
     "Reflective material for mirror panels and swarm collectors. Its "
     "roughness is deliberately not zero: a perfect mirror on a large curved "
     "panel throws fireflies that survive denoising"),
    ("Glow Material", "mega", 74, 'ADVANCED',
     "Emissive material for the inhabited inner face of the ringworld arcs"),
])

# --------------------------------------------------------------------------
# Ground patch -- a square of terrain rendered at ground level
# --------------------------------------------------------------------------
_add("patch", [
    ("Patch Latitude", "patch", 10, 'BASIC',
     "Latitude on the planet the ground patch is sampled from, in degrees"),
    ("Patch Longitude", "patch", 20, 'BASIC',
     "Longitude on the planet the ground patch is sampled from, in degrees"),
    ("Patch Size KM", "patch", 30, 'BASIC',
     "Width of the ground patch in kilometres. Small patches show individual "
     "landforms; large ones show whole ranges"),
    ("Patch Resolution", "patch", 40, 'ADVANCED',
     "Grid subdivision of the patch. This is the single most expensive setting "
     "in the file -- it is what makes the patch evaluate to millions of "
     "triangles"),
    ("Planet Radius KM", "patch", 50, 'ADVANCED',
     "Real planet radius in kilometres, used to convert the patch position and "
     "relief into the terrain field's coordinates"),
    ("Relief KM", "patch", 60, 'ADVANCED',
     "Vertical scale of the patch terrain in kilometres"),
    ("Detail Amount", "patch", 70, 'ADVANCED',
     "Strength of small-scale surface detail added on top of the terrain field"),
    ("Rock Density", "patch", 80, 'ADVANCED',
     "How many scattered rocks and boulders sit on the patch surface"),
    ("Material", "patch", 90, 'ADVANCED',
     "Material applied to the ground patch"),
])
_add("globe", [("Material", "terrain", 131, 'ADVANCED', "Material applied to the globe")])
_add("mega", [
    ("Arc Motion", "mega", 75, 'ADVANCED',
     "How the ringworld arcs move. Orbiting (0) puts them in free fall at the "
     "Kepler rate for their radius, Locked (1) turns them with the planet, "
     "Inertial (2) holds them fixed against the stars"),
])
_add("ring", [
    ("Planet Radius", "rings", 95, 'ADVANCED',
     "Radius of the planet the rings orbit. The shader needs it to work out "
     "an orbital period at each ring radius, which is what makes the inner "
     "ring shear past the outer one instead of turning as a solid disc"),
])
_add("orbital", [
    ("Band Motion", "orbital", 75, 'ADVANCED',
     "How the orbital bands move. Orbiting (0) puts each band in free fall at "
     "the Kepler rate for its altitude, which is what an unpowered ring does. "
     "Locked (1) holds them over the same ground, the active-support ring of "
     "the fiction. Inertial (2) fixes them against the stars while the planet "
     "turns beneath"),
])
_add("cloud", [("Material", "clouds", 90, 'ADVANCED', "Material applied to the cloud shell")])
_add("atmo", [("Material", "atmo", 90, 'ADVANCED', "Material applied to the atmosphere shell")])
_add("ringrig", [("Material", "rings", 90, 'ADVANCED', "Material applied to the ring disc")])
for _o in ("cloud", "atmo", "ringrig"):
    _add(_o, [("Radius", "clouds" if _o == "cloud" else "atmo", 95, 'ADVANCED',
               "Shell radius in Blender units"),
              ("Subdiv", "clouds" if _o == "cloud" else "atmo", 96, 'ADVANCED',
               "Subdivision of the shell mesh")])


# --------------------------------------------------------------------------
# The patch rig carries its own copy of every terrain socket, kept in sync with
# the globe by the presets. Showing them twice would be confusing, so they are
# demoted to the MIRROR tier: visible only under "All".
# --------------------------------------------------------------------------
for _n, _p, _o, _t, _d in _TERRAIN:
    if ("patch", _n) in SPEC:
        SPEC[("patch", _n)] = (_p, _o, 'MIRROR', _d + " (mirrors the globe)")

TIERS = ('BASIC', 'ADVANCED', 'MIRROR')
TIER_VISIBLE = {'BASIC': ('BASIC',),
                'ADVANCED': ('BASIC', 'ADVANCED'),
                'ALL': ('BASIC', 'ADVANCED', 'MIRROR')}

# node group name -> owner id. Trailing .001 etc is stripped before lookup, so a
# duplicated datablock still resolves.
OWNER_OF_GROUP = {
    "PLNT_GlobeRig": "globe",
    "PLNT_SurfaceShader": "surface",
    "PLNT_PatchRig": "patch",
    "PLNT_CloudShader": "cloud",
    "PLNT_CloudsRig": "cloud",
    "PLNT_AtmoShader": "atmo",
    "PLNT_AtmosphereRig": "atmo",
    "PLNT_RingShader": "ring",
    "PLNT_RingsRig": "ringrig",
    "PLNT_OrbitalRig": "orbital",
    "PLNT_MegaRig": "mega",
}
# Internal plumbing: real node groups, but never surfaced in the UI. They are
# driven entirely by the groups above.
INTERNAL_GROUPS = {"PLNT_TerrainField", "PLNT_TerrainFieldSH",
                   "PLNT_Elevation", "PLNT_ElevationSH", "PLNT_CloudField",
                   # the ground patch carries its own copy of the surface
                   # shader, kept in step with the globe's. Exposing both
                   # would show every look parameter twice.
                   "PLNT_PatchShader"}

# Sockets that are plumbing rather than art direction, wherever they appear.
NEVER_SHOW = {"Geometry", "Position", "Instance", "Selection"}

# Sockets Randomise must never touch, wherever they appear.
#
# These set the SIZE and TOPOLOGY of the system rather than its look, and their
# interface ranges are legal-range rather than artistic-range: Radius is
# 1..100000, so a midpoint roll gave a planet of radius ~50000 sitting inside
# a 1060-unit atmosphere -- the planet vanished and the panel looked broken.
# Seeds are excluded for a different reason: they are driven by the one master
# Seed field, and rolling them per panel desynchronises the geometry from the
# shading.
NEVER_RANDOMISE = {
    # scale of the system
    "Radius", "Inner", "Outer", "Inner Radius", "Outer Radius",
    "Planet Radius KM", "Patch Size KM", "Patch Latitude", "Patch Longitude",
    "Mirror Orbit", "Ring Orbit",
    # mesh topology / cost
    "Subdiv", "Subdiv Level", "Radial Segments", "Angular Segments",
    "Band Resolution", "Patch Resolution", "Planet Radius",
    # motion modes are a choice between three physical readings, not a dial
    "Band Motion", "Arc Motion",
    # seeds
    "Seed", "Cloud Seed", "Ring Seed",
}


def randomisable(owner, socket_name):
    """May Randomise Section roll this socket?

    Name-based rather than a per-entry flag, because the same socket means the
    same thing on every rig that carries it and a table of 159 booleans would
    drift out of step with the builders.
    """
    return socket_name not in NEVER_RANDOMISE


def base_name(group_name):
    """Strip Blender's .001 duplicate suffix."""
    if len(group_name) > 4 and group_name[-4] == "." and group_name[-3:].isdigit():
        return group_name[:-4]
    return group_name


def owner_of(group_name):
    return OWNER_OF_GROUP.get(base_name(group_name))


def is_internal(group_name):
    return base_name(group_name) in INTERNAL_GROUPS


def lookup(owner, socket_name):
    """(panel, order, tier, description) for a socket, always resolving.

    An unknown socket is not dropped -- it lands in the owner's panel under
    ADVANCED, so a socket added later can never become unreachable.
    """
    hit = SPEC.get((owner, socket_name))
    if hit:
        return hit
    panel = _OWNER_DEFAULT_PANEL.get(owner, DEFAULT_PANEL)
    return (panel, 9000, DEFAULT_TIER, "")


_OWNER_DEFAULT_PANEL = {
    "globe": "terrain", "surface": "surface", "patch": "patch",
    "cloud": "clouds", "atmo": "atmo", "ring": "rings", "ringrig": "rings",
    "orbital": "orbital", "mega": "mega",
}


def sockets_of(group):
    """Yield (socket_interface_item, panel, order, tier, desc) for one node group."""
    owner = owner_of(group.name)
    if owner is None or is_internal(group.name):
        return
    for it in group.interface.items_tree:
        if getattr(it, "item_type", "") != 'SOCKET' or it.in_out != 'INPUT':
            continue
        if it.name in NEVER_SHOW or it.bl_socket_idname == 'NodeSocketGeometry':
            continue
        panel, order, tier, desc = lookup(owner, it.name)
        yield it, panel, order, tier, desc


def apply_descriptions(node_groups):
    """Write every registered description onto the live socket.

    Blender shows interface descriptions as the tooltip on the modifier and
    group-node fields, so this is what turns 174 unlabelled sliders into
    something a person can actually use.
    """
    done = missing = 0
    undocumented = []
    for g in node_groups:
        owner = owner_of(g.name)
        if owner is None or is_internal(g.name):
            continue
        for it in g.interface.items_tree:
            if getattr(it, "item_type", "") != 'SOCKET' or it.in_out != 'INPUT':
                continue
            if it.name in NEVER_SHOW or it.bl_socket_idname == 'NodeSocketGeometry':
                continue
            _, _, _, desc = lookup(owner, it.name)
            if desc:
                it.description = desc
                done += 1
            else:
                missing += 1
                undocumented.append((g.name, it.name))
    return {"described": done, "undocumented": missing, "which": undocumented}


def validate():
    """Every SPEC entry must name a real panel. Cheap import-time guard."""
    bad = [k for k, v in SPEC.items() if v[0] not in PANEL_ORDER]
    assert not bad, "SPEC entries with unknown panel: %r" % bad
    return {"entries": len(SPEC), "panels": len(PANELS)}


validate()
