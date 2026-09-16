# PLNT v3

Blender 5.2.1 LTS · Cycles · OptiX · RTX 2060 6 GB / Ryzen 5 3600 / 16 GB · AgX

v3 answers the 2026-09-12 audit (`AUDIT_2026-09-12.md`). Four things changed in
kind rather than in degree:

1. **Every slider works again.** On Blender 5.x a Geometry Nodes modifier input
   is an ID property *group*, so the panel was drawing the group: every
   rig-backed control in the add-on read "ID Property Group" and could not be
   dragged at all.
2. **The picture is faster by measurement, not by belief.** Real displaced
   geometry renders shot 02 in 62% of the time geometry-plus-bump takes, and
   turning off light sampling for city windows takes 30% off shot 08.
3. **The two visible defects are gone.** The night-side "roads" were the edge
   set of an unrelated Voronoi diagram; the "line on the horizon" was two
   separate bugs that happened to land in the same place.
4. **The system moves.** Nothing in this project was animated. Now one Time
   Scale slider drives the planet, the weather, every satellite, the orbital
   bands, the tether climbers, the beacons, the rings, the mirror belt, the
   ringworld arcs and the Dyson swarm, each at its own physical rate.

---

## 1. What was broken, and is not

| Defect | What it actually was | Now |
|---|---|---|
| Every rig slider dead | `layout.prop(inputs, '["Socket_4"]')` draws the ID property *group*, not its `value` | `path_resolve` hands back the group as a struct; 80 slots checked on every build |
| Sliders with no range or tooltip | ID properties start at the full float range with no description; the socket's own range never travelled with the value | `apply_socket_ui()` copies range, default and tooltip onto all 80 modifier slots |
| Randomise could set Radius to ~50 000 | Interface min/max are the *legal* range; Randomise rolled the midpoint of it | Structural sockets are excluded by name, and the roll is centred on each socket's own default |
| The old v1 UI lived in the .blend | `PLNT_presets.py` as a text datablock registered panels under the same `bl_idname` as the add-on | Everything from `class PLNT_Props` down is deleted; `apply_v3.py` re-injects the file and clears the Register flag |
| `apply_preset` never wrote the megastructure rig | No `mega` key existed in the preset table | `MEGA_DEFAULTS` plus per-preset overrides; the "megastructure" preset now builds at Mega Scale 9.5 |
| Create Planet System built no megastructures | `PLNT_Mega` was only ever created by `tools/apply_v2.py` | `build_scene_scaffold` builds it like every other subsystem |
| `Light Material` pointed at the hull | The emissive material the name promised was never built | `PLNT_OrbitalLight` exists, is assigned, and drives the navigation beacons |
| Headless `--dice` defaulted to 1.0 | The value that out-of-memory-killed shots 07-10 | 2.0 in both modes |
| GEOMETRY displacement unreachable | `core/lod.py` supported it; the UI enum did not list it | Listed, and the default |
| Remove Planet System left half the scene | A second, staler copy of the teardown loop | Calls `core.scene.remove_system()`, which also clears lights, cameras and the world |
| The preset dropdown was a choice, not a report | It kept saying "earthlike" after forty edits | The panel says what is actually in the scene, and marks it "(modified)" |
| A batch could overwrite `renders/` | `OUT` was hard-coded | `--out` on the headless renderer, `-Out` on `render_all.ps1` |

---

## 2. Render time: measured, paired, thermally gated

Every number is a within-pair ratio against a baseline run taken immediately
before it, on a GPU gated to within 3 °C of its measured idle floor. The first
ablation matrix this project produced was invalidated by thermal throttling, so
unpaired numbers are not quoted.

| Mutation | Shot | Ratio | Adopted |
|---|---|---|---|
| `disp_geom` -- real displaced geometry, no bump | 02 | **62.4 %** | **yes, the default** |
| `emis_none` -- city lights stop being sampled as lights | 08 | **70.3 %** | **yes** |
| `disp_true` -- displacement instead of displacement-plus-bump | 02 | 73.6 % | superseded by `disp_geom` |
| `detail_60` -- noise octaves × 0.6 | 02 | 92.6 % | Low performance tier only |
| `emis_front` -- front-face emission sampling | 08 | 96.9 % | no, `emis_none` is better |
| `adapt_obj_lo` -- object-space dicing, 6-unit edge | 02 | 101.8 % | yes, for memory |
| `detail_85` -- noise octaves × 0.85 | 02 | 104.6 % | **no** |
| `adapt_obj` -- object-space dicing, 3-unit edge | 02 | 106.7 % | yes, for memory |

Two of these deserve their own sentence.

**Displacement.** Cycles evaluates the displacement subtree three extra times
per shading hit to build a bump normal, and that subtree reads the terrain
field. Dropping the bump chain removes a 4× multiplier on the single most
expensive thing in the scene. The image is not meaningfully different at any
hero framing, which is why this is the default rather than an option.

**Emission sampling.** Cycles was building light-sampling structures for every
lit window on an entire hemisphere of cities. At planet scale those windows
illuminate nothing -- the only surface within reach is the six-thousand-kilometre
sphere they are standing on -- so they are emission to look at, not lights to
sample from.

**What did not pay.** Octave level-of-detail is close to free at 0.85 and worth
about 7 % at 0.6, nothing like the saving its earlier hand-edited measurement
suggested; it is therefore a Low-tier setting rather than a default. Object-space
dicing costs a few per cent of time. It is adopted anyway, for the reason in the
next section.

---

## 3. Low-resource machines

Dicing drives **memory, not speed** -- 2560×1440 costs 2.56 GB of VRAM at
dicing 1.0 against 1.29 GB at 2.0 -- and camera-relative dicing makes that
memory a function of the framing, so a close-up costs four times what a wide
shot does. Blender 5.0's object-space adaptive subdivision measures the edge in
object units instead, which makes micropolygon memory a property of the model.

That is now the Performance dropdown, which is deliberately separate from
Quality: quality is what the picture is worth, performance is what the machine
can afford. A laptop can render Final quality at Low performance.

| | Low | Balanced | High |
|---|---|---|---|
| Base subdivision | 7 | 8 | 8 |
| Adaptive dicing | object, 6-unit edge | object, 3-unit edge | camera-relative |
| Noise octaves | ×0.6 | ×1.0 | ×1.0 |
| Denoising | CPU | CPU | GPU above 8 GB |
| Persistent data | off | on | on |
| Intended for | laptops, 4 GB cards | the 6 GB card this was built on | 8 GB and up |

Base subdivision is interactivity, not render time: level 8 is 983,040 quads
and 2.2 seconds of geometry-nodes evaluation per parameter change; level 7 is
245,760 quads and 0.56 seconds. Low is four times more responsive to drag.

There is also a **7-unit trap worth naming**: `adaptive_object_edge_length` is
in Blender units, and the first value tried here was 0.045 -- 270 m of planet per
micropolygon. It ran the card out of memory before the first tile. Sensible
values on a radius-1000 planet are 3 to 6.

---

## 4. The two visual defects

**The blocky night-side "roads" were never roads.** They were the edge set of a
Voronoi diagram -- feature `DISTANCE_TO_EDGE` -- on a *different, finer* Voronoi
than the one that places cities. An edge set draws the boundaries *between*
territories: closed polygons meeting at three-way knots, running through empty
land and arriving nowhere. On the night side that reads as a wireframe cast over
the dark hemisphere, which is exactly what it was.

A road joins two settlements. Taking F1 and F2 of the *city* Voronoi gives the
two nearest city sites to a point, and the distance from that point to the
segment between them is small only along the corridor that joins them. That is
the Delaunay dual of the same diagram -- the graph of which city neighbours which
-- and it produces a network that starts and ends at cities. Both endpoints must
be settled cells, traffic thins toward the middle of a long haul, and the
corridor wanders slightly using the sprawl noise that was already being
evaluated for the cities, so the wander costs nothing.

**The "line on the horizon" was two bugs that landed in the same place.**

On the *lit* limb, the analytic atmosphere asked "is this air in sunlight?" at
the point where the ray hits the shell. Near the limb the shell is hit almost
tangentially, so that point sits far around the curve from the air the ray
actually travels through, and two adjacent pixels sample sun angles tens of
degrees apart. The terminator smoothstep turned that into a one-pixel step in
brightness. Illumination is now evaluated at the ray's closest-approach point
`C = P − (P·d)d`, which is the deepest and densest point of the chord and varies
smoothly across the limb.

On the *dark* limb, the cloud deck is a zero-thickness shell at full opacity
right up to its own silhouette. Seen edge-on its Translucent lobe fires along
the whole rim. Density now fades out as the surface turns edge-on, which is also
the physically honest thing to do: a real ray near the limb passes through tens
of times more cloud, and the layer should read as a soft band rather than a hard
edge.

A third, quieter contributor: the per-face alpha split was being applied to
*every* ray. A ray that hits the planet is stopped by it and crosses the shell
once, so splitting its alpha halved the atmosphere exactly over the disc and
left a brighter rim outside it. The split now applies only where the ray really
does cross two faces.

---

## 5. Everything else that was worth fixing

- **Coastlines are no longer drawn with a hard pen.** The sea mask was a
  `LESS_THAN`, so the land and ocean BSDFs switched at a single micropolygon
  boundary. On the volcanic preset, where the "ocean" is lava, that punched
  black holes out of the crust. A smoothstep four thousandths wide gives every
  shore a surf zone and costs one node.
- **Cities are no longer a field of identical discs.** Each cell gets its own
  radius from its own random colour and a smooth edge; the strongest few cells
  become capitals with brighter cores, derived from the same Voronoi so a
  capital is by construction a big city.
- **City lights are not one global tint.** Light Colour Temp sets where the
  planet sits on the sodium-to-LED transition; each cell scatters either side of
  it through a three-stop ramp (sodium, mercury vapour, LED).
- **The ocean glint is a sheet of light, not a white dot.** Roughness floored at
  0.08; below about 0.06 a curved water surface under a distant sun returns the
  highlight as a handful of pixels that denoising cannot resolve.
- **The continental shelf stopped glowing.** Shelf Boost multiplied the shallow
  colour and Foam added white on top, with nothing bounding the sum; the boost
  is now capped at 1.2.
- **The planetary grid reads as engineering.** The arcs were 0.0011 of a unit
  sphere -- about 7 km, thinner than a pixel at every hero framing -- so they
  aliased into dashes. Now 0.004 with a smoothstep edge, twice the glow, and
  gated to Tech 8 and up instead of fading in from Tech 5.5 as a faint scratch.
- **Orbital hardware stopped reading as a chain of white beads.** The hull was
  one near-black metal at roughness 0.30, which returns almost nothing except
  the sun. It is now four material classes chosen per instance -- insulation
  blanket, gold thermal foil, bare panel, radiator -- with streaking in the
  instance's own texture space, plus a greeble pass and solar wings in the
  module library. The greebles are scattered over the twelve *library* modules,
  so they cost a few thousand unique triangles once and are free on every
  instance in the scene.
- **The night sky stopped being grey.** Night Glow at 0.02 lifted the whole
  unlit hemisphere into a visible veil that flattened the city lights against
  it; real airglow is a few thousandths of daylight, so 0.004.
- **Dead settings removed.** `volume_step_rate` and `volume_max_steps` have been
  inert since Blender 5.0 moved Cycles to unbiased null-scattering volumes;
  carrying them in the quality presets implied a trade-off that no longer
  exists.

---

## 6. The system moves

One number drives everything: **Time Scale, in world hours per second of
footage**. Frozen (0) is the default, because a hero still is a frozen frame of
a moving system and every shot must match frame to frame. Timelapse (1) turns a
24-hour planet once every 24 seconds and takes a low satellite round in about 90.

Scale: 1 Blender unit is 6 km, so radius 1000 is a 6000 km planet -- the value
the ground patch rig already assumed. A circular orbit just above such a planet
has a period of 84.5 minutes, and Kepler's third law gives every other altitude
`T(r) = T₀ (r/R)^1.5`.

| Element | Radius (R) | Degrees per world hour | Period (world hours) |
|---|---|---|---|
| Planet surface | 1.00 | 15.0 | 24.0 |
| Cloud deck | 1.00 | 16.5 | 21.8 |
| Satellites, low | 1.02 | 246 | 1.46 |
| Satellites, high | 1.16 | 202 | 1.78 |
| Orbital band 1 | 1.24 | 184 | 1.96 |
| Orbital band 2 | 1.34 | 165 | 2.18 |
| Orbital band 3 | 1.46 | 145 | 2.48 |
| Ring inner edge | 1.35 | 163 | 2.21 |
| Ring outer edge | 2.30 | 73 | 4.91 |
| Mirror belt | 1.90 | 98 | 3.69 |
| Ringworld arcs | 2.70 | 58 | 6.25 |
| Dyson swarm | 4.40 | 28 | 13.0 |

Those ratios are the point. A satellite crossing the disc visibly faster than
the ground beneath it is what makes low orbit read as low orbit, and an inner
ring shearing past an outer one is what makes a ring read as several hundred
million independent bodies rather than as a disc.

**The prerequisite.** Every shader that asks whether a point is in daylight was
dotting a *world*-space sun vector against *object*-space coordinates. While
nothing rotated that was a latent bug; the moment the globe turns it becomes the
visible one, because the terminator rotates with the surface and the planet has
no day. A Vector Transform in each of the four shaders fixes it once.

**How the clock reaches the nodes.** Shaders have no concept of the current
frame, so each shader group carries a driven `PLNT_TIME` value in world hours.
Geometry nodes do have a Scene Time node, so the rigs read seconds from it and
multiply by a plain value that `sync()` writes. Both end up holding the same
number, so shading and geometry cannot disagree about what time it is.

**The drivers read scene ID properties, not `scene.plnt`.** The batch renderer
loads the .blend with no add-on registered at all. A driver whose data path
cannot resolve does not raise -- it silently stops updating -- so the entire
system would have frozen in every headless render while working perfectly in the
GUI. `plnt_time_scale`, `plnt_day_length_h` and `plnt_beacon_rate` are custom
properties on the Scene and resolve whether anything is registered or not.
`tools/test_scaffold.py` asserts that no driver anywhere depends on `plnt.`.

**Per element.**

- *Planet* -- object Z rotation, `360° t / Day Length`.
- *Clouds* -- the same, plus 1.5°/h of zonal drift (a 50 m/s jet on a 38 000 km
  circumference), plus weather evolution: all three cloud noises are 4D, and
  advancing the fourth coordinate by 0.02 per world hour turns the pattern over
  in about a week, which is what a satellite loop looks like.
- *Satellites* -- each gets a great circle of its own. The random orbit axis is
  projected perpendicular to the position first, because rotating about an
  arbitrary axis keeps the radius but traces a small circle whose plane misses
  the planet centre. Modules fly nose-first with one face toward the planet.
- *Orbital bands* -- `Band Motion` picks between three defensible physical
  readings: Orbiting (free fall at the Kepler rate), Locked to the surface (the
  active-support ring of the fiction), or Inertial (fixed against the stars). The
  spin is applied in the band's canonical frame and the tilt afterwards;
  folding it into the tilt as a Z euler would make the band wobble like a
  dropped coin.
- *Space elevator* -- no choice: it turns with the planet or it tears out of the
  ground. Climbers run at 200 km/h, about two and a half world days from anchor
  to counterweight, and wrap rather than pile up at the top.
- *Beacons* -- `PLNT_OrbitalLight` strobes at 1 Hz of **footage**, not of world
  time. At Timelapse a world hour passes per second, so a world-time strobe
  would run at 3600 Hz and render as a constant dim glow.
- *Rings* -- the sampling angle is rotated by −ω(r)·t, which shears everything
  that is a function of angle (clumps, spiral density waves, shepherd wakes)
  while leaving everything that is a function of radius -- every named division --
  exactly where it is.
- *Mirror belt* -- orbits at 98°/h, and every mirror is a heliostat: its normal
  is the half vector between the direction to the sun and the direction to the
  planet. Facing outward, which is what it used to do, reflects sunlight back
  into space. As the belt orbits the array re-aims and the specular flare sweeps
  along it.
- *Ringworld arcs* -- `Arc Motion`, same three readings as the bands.
- *Dyson swarm* -- each collector on its own orbit like the satellites, eleven
  times further out, facing the sun.
- *Lava* -- the 4D seed of the crust noises walks at 0.05 per world hour, so the
  plate pattern reorganises over a day.
- *City lights* -- already gated on sun elevation, so they come on at dusk for
  free once the planet turns.

Motion blur is off by default: at these speeds it costs real time and the stills
do not need it.

---

## 7. The interface

The quick row is three dropdowns above the eight identity sliders:

- **Quality** -- Draft (1280×720/64), Fast (1920×1080/96), Preview, Final
  (2560×1440/512), Archive. A line underneath says roughly what a frame will
  cost and at what resolution, from the measured table, overwritten with this
  machine's own numbers once it has rendered anything.
- **Performance** -- Low / Balanced / High, as above.
- **Time Scale** -- with named presets in the Sun & Sky panel.

The thirteen sub-panels are grouped under four parents -- Planet, Sky,
Civilisation, Scene -- because thirteen siblings under one header is a wall, and
the order they happen to be declared in is not an order anyone reads.

Also: `use_property_split` throughout, short labels in the quick row, a
"Rendering on CPU -- expect roughly 14× longer" warning when no GPU is found, an
Archive-at-6 GB warning, and Save/Load for user presets on disk, in the
extension's own user directory (the manifest already asked for the `files`
permission for exactly this).

---

## 8. How it is applied, and how to undo it

`tools/apply_v3.py` does **not** patch the existing file. v2 replaced node
groups one at a time and carried a lot of machinery to survive doing so, because
rebuilding a group removes the datablock and orphans every Group node pointing
at it -- which is how the globe once inflated to a smooth 1034 units, above its
own cloud deck at 1004, while the frame still looked plausible. v3 changes
almost every builder, so it builds a complete system from scratch on
`--factory-startup` and saves that. It is the same code path `test_scaffold.py`
exercises on every check, and therefore the better-tested of the two.

The radius guard survives, on the mean rather than the peak: individual summits
reaching past the cloud shell is normal and always has been (the pre-v3 file
peaks at 1021.6 against a deck at 1004). What is never normal is the whole
sphere moving.

```powershell
.\tools\deliver_v3.ps1 -WhatIf     # say what it would do
.\tools\deliver_v3.ps1             # apply, check, install-test, verify renders
```

To undo: copy `logs\PLNT_PlanetGen_prev3.blend` back over
`PLNT_PlanetGen.blend`. Re-running the delivery no longer overwrites that file.

---

## 9. Three things a clean rebuild exposed

Building the scene from the builders instead of patching the shipped file
surfaced three discrepancies between the two. None of them was visible as an
error anywhere in the graph; all three showed up as the hero frames coming back
wrong, and each took a measurement to find.

**Two sun conventions.** `PLNT_presets.sun` set the pivot only, relying on
`PLNT_Sun` already carrying a base rotation of (0, 90, 0).
`core.scene.set_sun` set the pivot differently and wrote the sun object too.
They disagree by 90 degrees of azimuth. Both produce a plausible sun, so
nothing ever looked broken, and which one you got depended on which function had
touched the rig last. The shipped .blend had been left by the presets one, and
the shot table was authored against it; the rebuild ended with `set_sun` and
relit all ten frames. Both functions now write both objects, and the scaffold
test asserts the base rotation.

**The clock wiped the sun drivers.** `_drive_time` called
`animation_data_clear()` on `node.id_data` before adding its driver, and inside
a node group that is the whole group. It took the three drivers tracking
`PLNT_SunDir` out of `PLNT_SurfaceShader` with it, so the sun vector read as a
constant and the day/night mask stopped meaning anything. Now only the one
socket is cleared, and the scaffold test counts the drivers on every group that
carries a SUNVEC node.

**The sky was the brightest light in the scene.** The nebula in
`core.scene.build_world` is a full-sphere emitter at strength 0.25. Measured on
shot 05 with the planet replaced by flat grey: the sun alone gives 0.035, the
starfield adds nothing measurable, and the nebula took it to 0.262 -- seven
times the sun. Every night side in the set was lit by the sky rather than by
anything in the scene, and the volcanic frame, whose whole subject is lava being
the only light, came back as a pale sphere. The shipped .blend did not have this
because its world predates the builder that makes one. Now 0.0625, which puts
the sky contribution at 0.114 against the delivered scene's 0.113.

**And one recalibration.** The two atmosphere corrections in section 4 each
roughly doubled how much air a ray that hits the planet passes through. Both are
right, and together they put four times the veil over the disc, against preset
Density values that were tuned to the old, wrong number. A measured
`DENSITY_CALIBRATION` of 0.11 in the chord model restores the delivered optical
depth while keeping the corrected geometry, so the preset numbers keep the
magnitudes they were authored with.

---

## 10. One thing that went wrong, and what it cost

The first v3 hero batch was launched with `-Out renders_v3` and wrote shot 01
into `renders/` instead, overwriting the v2 frame it was meant to be compared
against. The batch was stopped after that one shot.

The cause was a shadowed name in `plnt_headless.py`: `out` held the output
directory, and the results list was also called `out`. Being assigned first, the
list replaced the directory before the render loop ever read it, so
`plnt_shots.out_dir(out)` was handed a list, fell through to its default, and
every frame went to `renders/`. `render_all.ps1` caught it correctly and
reported "Blender exited 0 but wrote no frame" -- the modification-time check
that v2 added after a stale frame once scored a detail ratio of exactly 1.000.

Cost: the full-resolution v2 PNG of shot 01. The 1200-px review JPEG survives and
is what the comparison page uses for that plate; the v1 original is untouched in
`renders_v1/`. Shot 02's v2 frame had already been replaced by an audit probe on
12 September, so it is a v2-era render but not the one in the v2 timing table.

Both names are now distinct, and `PLNT_ALL_DONE` reports the directory it
actually wrote to.

---

## 11. The hero batch

Ten shots, 2560x1440, 1024 adaptive samples, dicing 2.0, rendered one Blender
process per shot with thermal gating between them. Identical settings to the v2
batch, so the comparison means something.

| Shot | v1 | v2 | v3 | v2 to v3 |
|---|---|---|---|---|
| 01 pristine_alien | 8.6 m | 2.5 m | **1.1 m** | 2.28x |
| 02 earthlike | 10.3 m | 2.3 m | **1.4 m** | 1.66x |
| 03 ringed_ice | 9.9 m | 2.1 m | **1.4 m** | 1.54x |
| 04 ocean_world | 28.7 m | 6.8 m | **3.7 m** | 1.83x |
| 05 volcanic | 16.7 m | 5.0 m | **2.3 m** | 2.18x |
| 06 desert | 30.8 m | 18.8 m | **1.2 m** | **16.1x** |
| 07 colonial_outpost | 12.9 m | 3.1 m | **2.0 m** | 1.56x |
| 08 industrial_world | 33.5 m | 7.3 m | 7.2 m | 1.02x |
| 09 hyperdeveloped | 20.3 m | 6.0 m | **4.9 m** | 1.22x |
| 10 megastructure | 13.4 m | 3.8 m | 4.9 m | 0.77x |
| **total** | **185.1 m** | **57.6 m** | **30.0 m** | **1.92x** |

Three of these want a sentence.

**Shot 06 went from the slowest frame in the set to the fastest.** 18.8 minutes
to 70 seconds. The speckle the September review flagged was the micro
displacement's second octave aliasing below pixel size at 200 mm, and adaptive
sampling was chasing that noise to the sample cap across the whole frame.
Removing the bump chain removed the noise, and the frame converges immediately.
This is the clearest case in the project of a look defect and a performance
problem being the same bug.

**Shot 10 got slower**, and shot 08 barely moved. Both now carry substantially
more geometry than they did: shot 10 builds the full megastructure rig for the
first time, because `apply_preset` never wrote it before, and both carry the
greeble pass and the solar wings. They are rendering more, not rendering worse.

Detail ratios against v2 (`tools/compare.py`) sit between 0.63 and 1.22, with
shot 06 at 0.40 -- which is the speckle being gone, not detail being lost -- and
shot 03 at 0.63, the ring darkening the v2 report already documented. Mean
brightness per frame is within 20% of v2 on eight of the nine comparable shots.

---

## 12. Verification

Everything below is from the delivered file, on the delivered zip.

| Check | Result |
|---|---|
| `check_all.ps1` | ALL CHECKS PASSED -- 163 sockets reachable, 0 orphans, 0 undocumented, 0 inert, 0 dead nodes |
| `test_install.ps1` | INSTALL_OK -- 18 panels, 15 operators, scene property present |
| Drawable sliders | 80 checked, 0 broken |
| Socket ranges and tooltips written | 80 modifier slots |
| Mega rig written by presets | Mega Scale 9.5 on the megastructure preset |
| Roads | segment model present, cell-edge model gone |
| Sun vector in object space | all four shaders |
| Sun-vector drivers intact | 3 or more on every group carrying a SUNVEC node |
| One sun convention | `PLNT_Sun` left at (0, 90, 0) |
| Sky does not out-light the sun | nebula 0.0625 |
| Clock reaches nodes | `PLNT_TIME` ×4, `PLNT_TS` ×2, `PLNT_SPIN` ×2 |
| No driver depends on the add-on | driver paths are `["plnt_time_scale"]`, `["plnt_day_length_h"]`, `["plnt_beacon_rate"]`, `render.fps` |
| Frozen holds still | globe rotation identical at frames 1 and 120 |
| Time Scale 1 turns the globe | 1.309 rad at frame 120 -- exactly 5 world hours of a 24-hour day |
| Motion renders | 48-frame sequences on shots 02, 09, 03 and 10 all move; frame-mean spread 0.0034 to 0.046 |
| Globe inside its shells | mean radius 1000.6 against a cloud deck at 1004 |
| Hero batch | 10 of 10, no failures, 30.0 minutes total |
| Sub-minute tier | Fast quality, wall clock including scene load: shot 02 in 36 s, shot 08 -- the heaviest frame in the set -- in 49 s |
| Measured tier times | Draft 17.2 s, Fast 29.7 s per frame, written to `logs/quality_times.json` by the renderer itself and quoted back in the panel |

The last of these is the one the brief asked for by name: the lowest quality tier
had to come in under a minute. It does, on the worst shot, measured end to end
rather than render-time only.

### What is still open

- **Dune Scale does not follow the lens.** At 200 mm the dunes are below pixel
  size and the strata read as swirls rather than bedding.
- **Rings are darker than v1.** Documented in the v2 report; `Band Contrast` and
  `Ice Colour` are the knobs, and nobody has made the call.
- **Cloud shadows** remain a look change worth doing and not a saving. The design
  is in `README.md`.
- **Motion blur** is off and untested at these angular rates.
- **Craters** render but have still never been isolated in a frame.
- **The full-resolution v2 PNG of shot 01** is gone, for the reason in section 10.
  The 1200-px review JPEG is what the comparison page uses for that plate.
