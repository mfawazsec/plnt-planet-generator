# PLNT -- Procedural Sci-Fi Planet Generator

> **Development log.** This is the working record kept while PLNT was built:
> architecture, the API traps hit along the way, measured costs and the
> defect log. For installation and usage start at the
> [repository README](../README.md). Some things referenced here -- `logs/`,
> `renders*/`, the benchmark harness, the demo `.blend` -- are not part of
> this repository.

Blender 5.2.1 LTS · Cycles · OptiX GPU (RTX 2060) · AgX

Paths below are relative to the repository root; `$PLNT` stands for wherever
you cloned it.
Developed on Linux under Flatpak, moved to Windows on 2026-09-12; the `.sh`
tooling was ported to PowerShell that day and the originals left in place. See
`DELIVERABLES.md` for the command mapping.

**Current version: v3.** What changed and why is in `V3_REPORT.md`; the audit it
answers is `AUDIT_2026-09-12.md`. The headline is that every rig slider was dead
on Blender 5.x, the night-side road network was the edge set of the wrong
Voronoi, and nothing in the scene was animated. All three are fixed, and the
system now moves from one Time Scale control.

---

## Files

| Path | What it is |
|---|---|
| `PLNT_PlanetGen.blend` | The scene. Self-contained; survives Append into a fresh file. |
| `ext/plnt_planet-3.0.0.zip` | The installable extension. Built and validated with Blender's own `extension build`. |
| `ext/plnt_planet/` | Extension source (manifest + package). |
| `core/scene.py` | **Builds a whole planet system in an empty scene.** The reproducibility fix. |
| `core/gen_groups.py` | `PLNT_GlobeRig` dumped to source; it previously existed only in the .blend. |
| `core/atmosphere.py` | Analytic surface atmosphere. Replaces the ray-marched volume. |
| `core/rings.py` | Ring shader + real polar annulus geometry. |
| `core/orbital.py` | Instanced module library, truss bands, space elevator. |
| `core/mega.py` | Mirror belts, ringworld arcs, Dyson swarm. |
| `core/surface_detail.py` | Glint, foam, dunes, strata, ice cracks, vegetation, craters. |
| `core/params.py` | Parameter registry: panel, order, tier and help text for every socket. |
| `core/ui.py` | Data-driven panels, operators, per-section randomise/reset, copy-paste. |
| `core/lod.py` | Displacement modes, base subdivision, adaptive dicing space, octave level-of-detail. |
| `core/render.py` | Quality presets, performance tiers and device probing. |
| `core/anim.py` | **One clock for the whole system.** Kepler rates, the drivers, and `sync()`. |
| `core/nodeutil.py` | Socket resolution that fails loudly instead of guessing. |
| `plnt_field.py` | Terrain field -- emits geometry **and** shader versions from one source. |
| `plnt_surface.py` | `PLNT_SurfaceShader` -- per-pixel surface, ocean, displacement. |
| `plnt_tech.py` | Technology layer (cities, roads, grid, agriculture, night lights). |
| `plnt_atmos.py` | Cloud and atmosphere shells. |
| `plnt_patch.py` | `PLNT_Patch` ground rig. |
| `PLNT_presets.py` | 13 presets + `apply_preset` / `randomize`. |
| `plnt_shots.py` | Hero shot definitions + camera model. |
| `tools/` | Measurement and build tooling; **not shipped in the extension**. |
| `renders_v1/` | The v1 hero renders, kept for before/after comparison. |
| `logs/PLNT_PlanetGen_prev2.blend` | The pre-v2 scene, kept so the change is reversible. |

### Tools

| Tool | Purpose |
|---|---|
| `tools/groundtruth.py` | Dump every render-relevant fact from the .blend. |
| `tools/ablate.py` + `ablate_paired.sh` | Paired, thermally gated cost attribution. |
| `tools/validate_build.py` | Build every node group on factory startup; report dead nodes. |
| `tools/test_scaffold.py` | Empty scene -> planet; audits orphans, tooltips, inert inputs. |
| `tools/dump_tree.py` | Emit Python that rebuilds a node group (links by socket index). |
| `tools/apply_v2.py` | Apply the v2 modules to the .blend (superseded). |
| `tools/apply_v3.py` | Build the v3 scene from the builders and save it. |
| `tools/deliver_v3.ps1` | Back up, apply v3, run every check, render verification shots. |
| `tools/anim_check.py` | Render a short sequence and fail if the frames are identical. |
| `tools/build_extension.py` | Assemble the shippable package. |
| `tools/verify_v2.py` | Render the shots that expose each change. |

## Visual defects found by rendering, and what they taught

The automated checks pass on graphs that still look wrong. These were only
visible in a frame.

**The atmosphere vanished.** The analytic shader is a surface, and a camera ray
crosses a closed shell twice, so the full-chord alpha has to be split between
the two hits. Gating on `Backfacing` looked correct and is orientation
dependent: when the generated normals do not point the way you assumed, the
near face is zeroed and the atmosphere disappears completely. Splitting as
`a_face = 1 - sqrt(1 - a_total)` composes back exactly -- `(1 - a_face)^2 =
1 - a_total` -- and does not care which face is which. The volume version never
had this failure mode because volumes ignore normals.

**Rock strata read as contour lines.** Two mistakes compounding: the tint went
above 1.0 so the bands blew out to white, and the slope gate started at 0.20,
which put "bedding planes" on flat sand where no rock is exposed. Now tinted to
1.13 and gated from 0.38.

**Satellites read as a debris field.** Scale 0.55-1.85 on modules up to 64 units
long makes orbital hardware the size of small moons. Real satellites are
invisible dots at planet scale, so the job is to suggest infrastructure rather
than fill the frame: scale 0.15-0.45, density 0.34 -> 0.20, and a deeper shell
so they do not all sit on one sphere.

**The planet swallowed its own atmosphere.** Applying v2 rebuilt
`PLNT_TerrainField`, which destroys the datablock `PLNT_GlobeRig`'s group node
points at. Elevation collapsed to a constant 0.5, so the globe inflated from
~1000 to a perfectly smooth 1034 -- above the cloud deck at 1004 and the
atmosphere shell at 1030. Both shells were buried inside the planet.

The symptom read as "the clouds and atmosphere disappeared", which sent the
first two attempts at fixing this into the atmosphere shader, where nothing was
wrong. The surface *shading* still looked correct throughout, because the
shader evaluates its own copy of the field per-pixel and never touches the
geometry rig -- so the frame looked plausible while the terrain was flat.

Two guards now exist. Every Group node referencing a PLNT group is recorded
before a rebuild and re-pointed afterwards, so orphaning a consumer is no
longer possible. And a radius check fails the apply outright, with the measured
values, if the globe ever reaches the shell radii -- this class of bug should
stop the build rather than produce a convincing wrong picture.

**Relative paths, again.** A chained render used relative paths and silently did
nothing -- the Flatpak sandbox resolves them against `/app/blender`, so Blender
loaded the factory default instead of the project file. This trap is already
documented in this README and still caught me. Always absolute paths.

## Cloud shadows: a look change, not a speed change

**This section used to claim cloud shadow rays were the largest remaining
performance opportunity. That claim was wrong and the measurement is now in.**
Paired and thermally gated, `cloudshadow_off` runs at **98.2 %** of baseline:
the shadow rays are 2 % of render time, inside the noise. Clouds as a whole are
30 % of render time, but almost all of that is the shell being shaded, not the
shadow rays it casts.

The refactor below is still worth doing, for the *look*: analytic cloud shadows
are better defined than transparent-shadow-ray ones. It is a look change with a
neutral cost, and it should be described and budgeted as one.

Sampling the cloud field analytically at the point the sun ray pierces the
1004-unit shell, then setting `PLNT_Clouds.visible_shadow = False`, gives
better-defined shadows and removes those rays.

The work is a refactor, not an addition. `build_clouds` computes coverage from
three warped 4D noises blended by `Band Strength` and thresholded by
`Cloud Coverage`. That block needs extracting into a shared `PLNT_CloudField`
group which both the cloud shader and the surface shader consume -- replicating
the maths separately would let the two drift apart, which is the same class of
bug that produced the `.001` node group duplicates.

Sketch:

1. Extract coverage into `PLNT_CloudField(Position, Coverage, Density, Seed,
   Band Strength, Detail Scale) -> density`.
2. In the surface shader, intersect the sun ray with the cloud sphere:
   `t = -(P.L) + sqrt((P.L)^2 - (|P|^2 - Rc^2))`, sample the field at
   `normalize(P + tL)`.
3. Attenuate the surface albedo by the sampled density, gated on a new
   `Cloud Shadow` input so it folds away at zero.
4. Set `PLNT_Clouds.visible_shadow = False`.

It has still not been attempted, because it is now known to be a look change
rather than a saving, and a shader refactor that cannot be verified in a render
is how the last two regressions in this project happened.

## The out-of-memory cause, finally identified

v1 blamed the dicing rate and raised it on shots 04/05/06. Paired measurement
showed dicing does not affect render time at all, which left the real cause
open -- until the v2 batch reproduced it.

Shots 07-10 carry no `dice` value in their shot definitions. v1's
`render_all.sh` passed `--dice ${DICE:-2.0}` unconditionally, so they rendered
at 2.0. The v2 rewrite made that conditional, so with `DICE` unset they dropped
to **1.0**, quadrupling micropolygon memory. Shot 07 was killed at 261s with
**rc=143** -- SIGTERM, which is what `systemd-oomd` sends under host memory
pressure, not the SIGKILL a kernel OOM would use.

So the out-of-memory condition is real, it is driven by dicing, and dicing
drives **memory rather than speed**. Both halves of that were previously
half-understood: v1 had the memory link but wrongly attached a speed model to
it; the v2 measurements killed the speed model and nearly lost the memory link
with it.

Two guards now:

- `render_all.sh` defaults `DICE=2.0`, matching what v1 actually used.
- Success is no longer "the output file exists". A stale frame from a previous
  session satisfies that, which is exactly how a SIGTERM-killed shot reported
  OK and then produced a detail ratio of exactly 1.000 against v1 -- because it
  *was* v1. The check now compares the output's modification time against the
  shot's start time and names the failure mode.

## Known defect: cold lava crust has no texture

On the volcanic preset, sub-sea-level regions render as flat, hard-edged
near-black with no surface detail -- visible in shot 05 as dark blobs with
coastline-shaped edges between the glowing fissure networks.

The v1 fix for the "flat salmon ocean" problem worked by making most of the
molten sea emit almost nothing, so the hot cores would survive AgX tonemapping.
That was right, but nothing was ever added back to give the *cold* crust
character: it has no micro-relief, no tonal variation and no albedo break-up,
so it reads as a hole rather than as basalt.

Fix: drive `micro_bu` and a dark tonal variation from the existing lava crust
noise below sea level, the same way `rock_strata` modulates exposed rock. The
nodes are already there (`lava warp`, `lava cracks`, `heatregion`); the cold
branch simply never uses them for anything but emission.

## Known look changes in v2

Two deliberate-but-debatable shifts, both one-parameter reversible:

**The atmosphere scatters more than the volume did**, and the hero set shows
the pattern clearly. Detail ratio against how much atmosphere fills the frame:

| shot | atmosphere in frame | detail v2/v1 |
|---|---|---|
| 06 desert | a sliver at one edge | **1.41** |
| 05 volcanic | small | **1.32** |
| 01 pristine_alien | limb-dominant | 1.31 |
| 07 colonial_outpost | night side | 1.15 |
| 02 earthlike | full disc | 0.99 |
| 03 ringed_ice | full disc | 0.76 |
| 08 industrial_world | full disc plus haze | **0.72** |

Where the surface fills the frame, v2 adds detail. Where the atmosphere fills
it, the extra scattering trades surface contrast for glow.

**The metric is confounded on shots 09 and 10, and probably 08.** Those frames
now contain far more large, smooth metal -- orbital bands, hubs, satellites,
megastructures -- and smooth geometry lowers mean Laplacian energy per pixel
even when the scene is unambiguously richer. Shot 09 scores 0.555 while
visibly carrying more structure than v1. Do not read those as quality
regressions; the two causes have not been separated. On shot 01 the lit
side roughly doubled (0.177 -> 0.340) and the night side lifted from near-black
(0.0065 -> 0.0315).

**This is free to fix.** `Intensity` does not affect render time -- it is the
same node graph either way -- so lowering it toward ~0.6, with `Night Glow`
at 0, recovers v1's contrast at no speed cost. Left at 1.0 here because it is
an aesthetic call on the hero set, not a defect.

**The rings are structurally richer but darker.** Split by region on shot 03:

| region | detail ratio v2/v1 | mean brightness |
|---|---|---|
| planet | 0.889 | 0.178 -> 0.210 |
| rings | 0.664 | 0.084 -> **0.054** |

The planet's softening is the atmosphere doing legitimate aerial perspective.
The ring number is partly a metric artefact -- v1's rings were dense,
near-aliasing grooves, which score high on Laplacian energy, while v2's are
broader ringlets with real divisions. But the 35% darkening is real, and comes
from the new per-band composition mixing ice toward dust and rock plus
`Band Contrast` at 2.3 (a power above 1 darkens values below 1). Real ring
systems are not uniformly bright, so this may be correct; `Ring Density`,
`Ice Colour` and `Composition Scale` are the knobs if not.

## Extension install, verified

```
installed from zip: True
addons enabled:     ['bl_ext.user_default.plnt_planet']
panels: 14   operators: 11   scene property: True
```

`tools/test_install.sh` installs the built zip into a throwaway profile through
Blender's own installer and confirms it enables. This is a stronger check than
importing the package: inside an installed extension the package name is
`bl_ext.<repo>.<id>`, so the path-based module loaders the working tree uses
cannot work at all and have to be rewritten to relative imports.

## Automated checks

```bash
./tools/check_all.sh
```

Runs everything that can be verified without rendering, and exits non-zero if
any of it regresses.


`tools/test_scaffold.py` builds a complete planet from an empty scene and then
asserts the things that have actually gone wrong on this project before:

- **No orphaned parameters.** Every node-group input resolves to a panel.
  Previously every ring parameter, all eight patch parameters and the whole
  sun/starfield setup had no UI at all.
- **No undocumented sockets.** All 174 started with an empty description.
- **No inert inputs.** Every exposed input must have a path to the group
  output. `Ring Seed` was computed into a node that was never connected, so
  every seed produced identical rings; this check is the generalisation of that
  bug and currently reports zero across all fifteen groups.
- **No dead nodes** in newly generated groups.
- **Preset bleed.** `check_defaults()` fails if a socket a preset writes is not
  reset by `LOOK_DEFAULTS` / `RING_DEFAULTS` / `ATMO_DEFAULTS`.

## Running it

```powershell
.\render_all.ps1 -Mode final -Out renders_v3
.\render_all.ps1 -Mode test -Shots 2,3 -Out logs\check
.\tools\check_all.ps1
.\tools\deliver_v3.ps1 -WhatIf
```

Or a single shot directly:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b `
  "$PLNT\PLNT_PlanetGen.blend" `
  --enable-autoexec -P "$PLNT\plnt_headless.py" `
  -- --mode final --shots 1,2,3 --out renders_v3
```

Paths **must be absolute**. This started as a Flatpak trap -- the sandbox
resolved relative paths against `/app/blender` and silently loaded the factory
default -- and the habit is worth keeping on Windows, where a relative path
resolves against whatever directory the shell happens to be in.

`--time-scale` sets the clock from the command line, with no add-on registered:

```powershell
& "C:\Program Files\Blender Foundation\Blender 5.2\blender.exe" -b `
  "...\PLNT_PlanetGen.blend" -P "...\tools\anim_check.py" `
  -- --shot 9 --frames 48 --time-scale 1.0 --out logs\anim
```

## In the UI

N-panel -> **PLNT Planet** tab. The panels enumerate node-group interfaces
directly, so a socket added to any generator appears automatically and cannot
be orphaned.

- **Quick** row: the eight controls that change a planet's identity.
- **Basic / Advanced / All** tier switch, plus a search box that filters every
  panel by parameter name.
- Sub-panels: Terrain, Surface Look, Ocean & Ice, Civilisation, Clouds,
  Atmosphere, Rings, Orbital, Megastructures, Sun & Sky, Ground Patch, Camera.
- Per-section **Randomise** and **Reset**, so experimenting in one area is
  reversible without disturbing the rest.
- **Copy / Paste settings** as JSON to share a planet.
- **Quick Render** (480x270, 32 samples) into the Image Editor -- everything
  else is render-only, so this is how a slider gives feedback.
- Render quality, displacement mode, resolution and output path live in
  **Properties > Render**, where Blender keeps render settings.

Every operator is `REGISTER|UNDO`.

```python
apply_preset("earthlike", seed=2291)
randomize(seed=42, tech_level=6.0)
sun(azimuth_deg=120, elevation_deg=20)
```

### Installing as an extension

```bash
blender --command extension build --source-dir ext/plnt_planet --output-dir ext
```

Then install `ext/plnt_planet-2.0.0.zip` from Preferences > Add-ons. The N-panel
offers **Create Planet System** in an empty scene.

## Architecture notes

**The field is evaluated per-pixel, not per-vertex.** `plnt_field.py` builds the
same graph into a `GeometryNodeTree` (for displacement) and a `ShaderNodeTree`
(for shading), because `ShaderNodeMath`/`TexNoise`/`TexVoronoi`/`MapRange`/
`VectorMath` exist in both. Reading masks from interpolated vertex attributes
quantises every coastline to the base mesh; evaluating in the shader does not.

**Residual displacement.** The globe stores `elevation` as an attribute. The
shader displaces by `(field_elevation − attribute_elevation) × Relief Strength`,
i.e. exactly the detail the base mesh could not carry, recovered at dice
resolution. This is what makes close-ups hold up.

**Sun direction.** `matrix_world` is *not* a dependency-tracked driver path -- it
silently freezes. Instead `PLNT_SunDir` is an empty parented to the sun at local
`(0,0,1)`; since the sun sits at the pivot origin its world location *is* the
sun's Z axis, and `TRANSFORMS`/`WORLD_SPACE` location drivers do track.

**Preset resets.** `apply_preset` writes a full `LOOK_DEFAULTS`/`CLOUD_DEFAULTS`/
`ATMO_DEFAULTS` baseline before each preset. Without it any value a preset sets
leaks into every preset applied afterwards.

**Lava is crust-and-fissure, not a bright fill.** AgX desaturates highlights, so
a uniformly bright emissive ocean collapses to flat pale salmon. The molten sea
is dark basalt broken by warped-Voronoi fissures, with a four-stop ramp
(near-black crust -> deep red -> orange -> white-hot) and squared intensity, so
most of the area emits almost nothing and the hot cores survive tonemapping.

**City lights are area-limited, not brightness-limited.** Settlements first read
as invisible because each core was 1-2 px across; raising emission barely helped.
The Voronoi cell scale (58 -> 27) and core width are what make them resolve.

**Writing modifier values does not refresh anything.** Setting
`mod.properties.inputs[...]["value"]` leaves the depsgraph clean, so Blender
keeps handing back the previous evaluation. Dragging a slider in a panel tags
the object for you; an operator writing the same value does not. Every operator
that writes modifier inputs has to call `update_tag()` or the change silently
does nothing on screen. This was reached through a level sweep of the orbital
rig that reported zero geometry at every level while the rig was perfectly fine.

**Random Value sockets are Min=0, Max=1, ID=2, Seed=3**, and they retype
themselves with `data_type` -- there is not a separate pair of sockets per
type. Indexing 2/3 as Min/Max builds silently and then fails at the first
integer assignment.

**Socket names do not appear in the API reference.** They are defined at
runtime, so they must be introspected, never guessed. `core/nodeutil.sockin`
raises with the real socket list rather than letting a wrong guess through.

**Blender 5.2 API changes worth knowing**
- `feature_set` no longer exists; adaptive subdivision is native
  (`SubsurfModifier.use_adaptive_subdivision` + `adaptive_pixel_size`).
- Geometry-node modifier inputs are no longer plain IDProperties:
  `mod.properties.inputs["Socket_N"]["value"]`, keyed by identifier not name.
- Editing a node group's interface **resets every modifier value** to defaults.
- `Map Range` and `ShaderNodeMix` have duplicate socket names -- index by integer
  (Mix RGBA: in 0/6/7, **out 2**).
- GN-generated geometry carries no material; it needs a `Set Material` node.

## Performance -- measured, not assumed

Every number below comes from `tools/ablate_paired.sh`: each mutation is run
against its own baseline taken immediately before it, at 1280x720 / 128 fixed
samples with adaptive sampling **off**, and both cells are gated on the GPU
having cooled to 64C first.

### Two measurement traps this project hit

**Thermal throttling.** An RTX 2060 under sustained load falls from 2100 MHz to
1500 MHz and reports `SW Thermal Slowdown: Active` at 84C. In the first
(unpaired) matrix this made cells run later ~6% slower for reasons unrelated to
the mutation -- three mutations that should have been neutral-or-faster all
measured +5 to +6%. Any ablation run as a straight sequence on this hardware is
measuring the cooler, not the code.

**Mutations that break the image.** The `field_stub` cell appeared to save 93%.
It had rendered a degenerate frame: mean luminance 30.1 against 50.5 for every
other cell. Every cell now records the rendered image's mean, max and lit
fraction so an invalid mutation is caught instead of being reported as a win.

### Where the time actually goes (shot 02)

| component | share | how measured | confidence |
|---|---|---|---|
| **Atmosphere volume** | **54%** | hiding it: 93.6s -> 42.9s | paired |
| Clouds | 30% | hiding them: 120.7s -> 84.4s | paired |
| Whole 193-node surface shader | 9% | grey Principled: 99.4s -> 90.4s | paired |
| Displacement (bump + true) | ~16% | unlinking the Displacement output | unpaired |
| Adaptive subdivision | ~2% | disabling the Subsurf modifier | unpaired, in noise |

The last two come from the first matrix, which thermal throttling invalidated
for effects under about 6%. They are directionally right -- neither is the
bottleneck -- but do not quote the exact percentages.

The volumetric atmosphere is more expensive than the surface shader,
displacement and subdivision combined. Cycles ray-marches a uniform spherical
shell with up to 1024 steps for every camera ray and every shadow ray.

**`dicing_rate` does not buy render time.** Raising it to 4.0 measured no
faster. The earlier claim that "cost scales as pixels / dice^2" was wrong: the
dice increases on shots 04/05/06 bought *memory*, not speed, and the
out-of-memory cause remains open. A newly identified suspect is `PLNT_Patch`,
which evaluates to **20.7M triangles** and was left visible in the viewport.

**True displacement beats bump here.** `displacement_method='DISPLACEMENT'`
measured 10% faster than the shipped `'BOTH'`: real geometry costs less than
the three extra shader evaluations Cycles needs to build a bump normal.

**Cycles constant-folds.** Making a shader's inputs constant collapses the
graph, so a feature gated at `Amount = 0` is eliminated at compile time rather
than costing a lookup. That is what makes the optional detail features in
`core/surface_detail.py` free when switched off.

### Like-for-like render times

Same shots, same resolution, same samples, rendered from the pre-v2 backup and
from the applied scene. `detail` is the high-frequency (Laplacian) energy ratio
v2/v1 -- the metric that catches detail deleted in the name of speed.

| shot | preset | v1 | v2 | speedup | detail |
|---|---|---|---|---|---|
| 02 | earthlike | 157.3s | 46.4s | **3.39x** | 0.99 |
| 03 | ringed_ice | 122.7s | 36.7s | **3.34x** | 0.90 |
| 06 | desert | 230.5s | 165.7s | 1.39x | **1.82** |
| 10 | megastructure | 69.1s | 41.1s | 1.68x | 0.99 |
| | **total** | **579.6s** | **289.9s** | **2.00x** | |

**Twice as fast overall, with detail intact.** Three shots hold their detail
within 1%; shot 06 carries 81% *more*, which is the dune fields and rock strata
adding real surface texture.

**The gain is shot-dependent, and honestly so.** It tracks how much atmosphere
is in frame. Shots 02 and 03 show the whole disc against space, so the limb is
a large fraction of the pixels and the analytic atmosphere pays off fully. Shot
06 is a 200 mm lens filling the frame with desert: the atmosphere is a sliver at
one edge and displacement dominates. Quote the range, not a single figure.

**One number worth not burying:** shot 03 sits at 0.90, about 10% less
high-frequency energy than v1. The rings gained a great deal of structure, so
the loss is elsewhere -- most likely the analytic atmosphere softening the disc
slightly relative to the volume. Small and plausible, but real, and not
isolated.

### Measured result of the fix

| mutation | baseline | mutation | ratio | image mean change |
|---|---|---|---|---|
| `atmo_surface` (analytic atmosphere) | 134.4s | **38.3s** | **28.5%** | +9.4% |
| `atmo_off` (no atmosphere at all) | 93.6s | 42.9s | 45.9% | -4.0% |
| `clouds_off` | 120.7s | 84.4s | 69.9% | -54.2% (clouds are the subject) |
| `flat_shader` (grey Principled) | 99.4s | 90.4s | 90.9% | - |

Read these with the caveats above in mind: baselines ranged 93.6-134.4s across
pairs, so effects under about 10% are inside the noise. The atmosphere result is
far outside it. The +9.4% image mean says the analytic version is brighter than
the volume, so it is a look change as well as a speed change and has to be
judged by eye, not only by the clock.

### What the dicing rates should probably become

Shots 04, 05 and 06 still render at `dice` 3.0, 2.5 and 3.0, inherited from the
v1 attempt to stop out-of-memory kills. Two measurements now say those values
buy nothing: raising the dicing rate to 4.0 measured no faster, and disabling
adaptive subdivision entirely changed render time by under 2%. They were only
ever a memory workaround.

Memory pressure is lower in v2 -- the volumetric atmosphere is gone, the
ground patch no longer evaluates 20.7M triangles in the viewport, and the
orbital rig no longer realises its instances. So those three shots could very
likely return to `dice = 1.0` and gain surface detail for free. That has not
been done here because it is a memory gamble on a multi-hour batch, and the
out-of-memory root cause is still unidentified. Worth trying on a single shot
first: `DICE=1.0 ./render_all.sh final 6`.

Closing the browser and Steam before a batch is worth doing regardless: they
hold ~790 MB of the 6 GB card.

### The fix

`core/atmosphere.py` replaces the ray-marched volume with an analytic surface
shader. The optical path through a spherical shell is a chord, so it has a
closed form: with `b = |P x d|` the ray's impact parameter and
`t = sqrt(R^2 - b^2)` the half-chord, a ray that misses the planet crosses
`2*(t_outer - t_inner)` of air and one that hits it gets only the near part.
That is exactly why the limb is bright -- grazing rays travel much further
through air. 62 nodes, evaluated once per hit, no stepping, no volume.

---

## Delivered

### v2 changes

**Performance.** The bottleneck was found by measurement, not by the plan's
hypotheses: the ray-marched atmosphere volume was 54% of render time, more than
the surface shader, displacement and subdivision combined. `core/atmosphere.py`
replaces it with a closed-form chord through the shell.

**Detail.**
- Rings: a real 196k-vertex polar annulus in place of a two-vertex quad, with
  named divisions that stay put across seeds, spiral density waves, azimuthal
  clumping, shepherd-moon wakes, per-band composition and Henyey-Greenstein
  forward scattering. 153-node shader, 23 parameters.
- Orbital: a twelve-module instanced library, truss bands whose bay count is
  derived from the circumference, station hubs and a tapered space elevator.
  2,621 instances from 6,240 unique triangles at level 10, with the Realize
  Instances node removed entirely. The greebles now take the curve's rotation,
  which is what turned the dashed ribbons into structures.
- Megastructures: mirror belts, partial ringworld arcs with lit inner faces,
  and a Dyson swarm, on their own object.
- Surface: ocean glint variation, coastal foam, dune fields, rock strata, ice
  cracks, vegetation clumping and impact craters -- each gated by an input that
  Cycles folds away when it is zero.

**Usability.** Panels enumerate node-group interfaces instead of hand-written
lists, so nothing can be orphaned. 159 reachable parameters, all documented,
where previously every one of the 174 sockets had an empty description and
rings, patch, orbital and sun had no UI at all. Basic/Advanced/All tiers,
search, per-section randomise and reset, copy/paste as JSON, quick render.

**Reproducibility.** `core/scene.py` builds the whole system in an empty scene,
and `PLNT_GlobeRig` -- which existed only inside the .blend -- is now in source.
The extension builds and validates with Blender's own tooling.

### Hero renders: v1 vs v2

Ten shots, 2560x1440, Cycles GPU (OptiX), 1024 samples, AgX. Identical settings
either side.

| # | preset | v1 | v2 | speedup | detail |
|---|---|---|---|---|---|
| 01 | pristine_alien | 8.6 m | 2.5 m | **3.49x** | 1.31 |
| 02 | earthlike | 10.3 m | 2.3 m | **4.54x** | 0.99 |
| 03 | ringed_ice | 9.9 m | 2.1 m | **4.64x** | 0.76 |
| 04 | ocean_world | 28.7 m | 6.8 m | **4.21x** | 0.96 |
| 05 | volcanic | 16.7 m | 5.0 m | **3.35x** | 1.32 |
| 06 | desert | 30.8 m | 18.8 m | 1.64x | **1.41** |
| 07 | colonial_outpost | 12.9 m | 3.0 m | **4.23x** | 1.15 |
| 08 | industrial_world | 33.5 m | 7.3 m | **4.58x** | 0.72 |
| 09 | hyperdeveloped | 20.3 m | 6.0 m | **3.38x** | 0.56 |
| 10 | megastructure | 13.4 m | 3.8 m | **3.51x** | 0.56 |
| | **total** | **185.1 m** | **57.6 m** | **3.21x** | |

Three hours of render time down to under one. `detail` is the high-frequency
energy ratio v2/v1 -- see the caveats above: it is confounded on 09 and 10,
where far more large smooth geometry now fills the frame.

### Why some shots used dice > 1.0 (v1 reasoning, now superseded)

The v1 notes claimed "cost scales as pixels / dice^2" and raised dicing on
shots 04, 05 and 06 to stop out-of-memory kills. The first half of that is
wrong: paired measurement shows the dicing rate does not buy render time at
all, and disabling adaptive subdivision changes it by under 2%. The dice
increases bought *memory*, not speed, and the out-of-memory root cause was
never identified. See "What the dicing rates should probably become" above.

### Composition verification

`plnt_check.py` measures subject coverage, frame edges touched, centroid offset
and emptiest quadrant against the brief's mandatory rules. 9/10 pass outright.
Shot 07 flags only because a night-side planet falls below the luminance
threshold, so the detector sees the lit crescent rather than the disc -- the
frame itself has the limb crossing three edges with a diagonal terminator.
