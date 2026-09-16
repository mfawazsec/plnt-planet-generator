# PLNT — Procedural Planet Generator for Blender

A Blender extension that builds a whole sci-fi planet system in an empty scene:
terrain, ocean and ice, weather, atmosphere, rings, cities and night lights,
orbital hardware, megastructures — all procedural, all driven from one N-panel,
and all animated from a single clock.

**Version 3.0.0 · Blender 5.0+ · Cycles · GPL-3.0-or-later**

---

## Install

1. Download `dist/plnt_planet-3.0.0.zip`.
2. In Blender: **Edit → Preferences → Add-ons → ▾ → Install from Disk…**, pick
   the zip.
3. It enables itself. Press <kbd>N</kbd> in the 3D viewport and look for the
   **PLNT Planet** tab.

## First planet

In an empty scene the panel offers a single button: **Create Planet System**.
It builds the globe, its shells, the sun and the camera from source — nothing
is appended from a `.blend`, so the result is reproducible on any machine.

From there:

- **Preset** — 13 starting points: `earthlike`, `pristine_alien`,
  `colonial_outpost`, `industrial_world`, `hyperdeveloped`, `megastructure`,
  `ringed_ice`, `volcanic`, `frozen`, `desert`, `ocean_world`, `dead_moon`,
  `gas_giant`. Each panel also has its own randomise and reset.
- **Quality / Performance / Time Scale** — the quick row at the top.
- Thirteen parameter panels, grouped under **Planet**, **Sky**,
  **Civilisation** and **Scene**.

**Remove Planet System** takes it all back out again.

## The two dials

They are independent. A laptop can render at Final quality on Low performance;
it just takes longer.

**Quality** is what the picture is worth:

| Tier | What it is |
|---|---|
| Draft | 1280×720, 64 samples. Framing and colour. |
| Fast | 1920×1080, 96 samples. A shareable frame in well under a minute. |
| Preview | 1920×1080, 192 samples. For judging detail. |
| Final | 2560×1440, 512 adaptive samples. The delivery setting. |
| Archive | 2048 samples, geometry-plus-bump displacement, dicing 1.0. Wants more than 6 GB of VRAM. |

**Performance** is what the machine can afford:

| Tier | What it is |
|---|---|
| Low | Laptops and 4 GB cards. Coarser terrain, much less VRAM. |
| Balanced | The tested setting on a 6 GB card. |
| High | 8 GB or more. Camera-relative dicing and every octave. |

The panel quotes measured render seconds per tier, and overwrites them with
your own machine's timings as you render.

## The clock

`Time Scale` is **world hours per second of footage**. It ships Frozen (0), so
every still matches frame to frame. Timelapse (1) turns a 24-hour planet once
in 24 seconds of playback and takes a low satellite round its orbit in about
90. Everything else keeps its own Kepler period, so relative speeds stay honest
at any setting.

Headless, with no add-on registered, the clock is three custom properties on
the Scene: `plnt_time_scale`, `plnt_day_length_h`, `plnt_beacon_rate`.

---

## Repository layout

| Path | What it is |
|---|---|
| `dist/plnt_planet-3.0.0.zip` | The installable extension. Built and validated with Blender's own `extension build`. |
| `ext/plnt_planet/` | Extension package source (manifest + modules), generated from the working tree. |
| `core/` | The working tree — the source of truth. |
| `plnt_*.py`, `PLNT_presets.py` | Flat modules the build folds into the package. |
| `tools/` | Build and validation tooling. Not shipped inside the extension. |
| `docs/` | Development log, version reports, the audit v3 answers. |

### What the modules do

| Module | Responsibility |
|---|---|
| `core/scene.py` | Builds a whole planet system in an empty scene. |
| `core/gen_groups.py` | `PLNT_GlobeRig` as source, rather than only inside a `.blend`. |
| `core/atmosphere.py` | Analytic surface atmosphere (replaced a ray-marched volume). |
| `core/rings.py` | Ring shader and real polar annulus geometry. |
| `core/orbital.py` | Instanced module library, truss bands, space elevator. |
| `core/mega.py` | Mirror belts, ringworld arcs, Dyson swarm. |
| `core/surface_detail.py` | Glint, foam, dunes, strata, ice cracks, vegetation, craters. |
| `core/params.py` | Parameter registry: panel, order, tier and help text per socket. |
| `core/ui.py` | Data-driven panels, operators, per-section randomise/reset, copy-paste. |
| `core/lod.py` | Displacement modes, base subdivision, dicing space, octave LOD. |
| `core/render.py` | Quality presets, performance tiers, device probing. |
| `core/anim.py` | One clock for the whole system: Kepler rates, drivers, `sync()`. |
| `core/nodeutil.py` | Socket resolution that fails loudly instead of guessing. |
| `plnt_field.py` | Terrain field — emits geometry **and** shader versions from one source. |
| `plnt_surface.py` | Per-pixel surface, ocean, displacement. |
| `plnt_tech.py` | Cities, roads, grid, agriculture, night lights. |
| `plnt_atmos.py` | Cloud and atmosphere shells. |
| `plnt_patch.py` | The ground-level patch rig. |
| `plnt_shots.py` | Hero shot definitions and camera model. |
| `PLNT_presets.py` | The 13 presets, `apply_preset` and `randomize`. |

## Building from source

The working tree uses flat top-level modules loaded by path, which cannot work
inside an extension — the package name is `bl_ext.<repo>.<id>`, and
`sys.modules["plnt_tech"]` would collide with anything else on the machine
using that name. `build_extension.py` rewrites those loaders into real relative
imports and assembles `ext/plnt_planet/`.

```bash
python tools/build_extension.py
blender --command extension build --source-dir ext/plnt_planet --output-dir dist
```

Any Python 3 runs the first step; it only moves text around. Blender's own
`extension build` does the packaging and validates the manifest.

## Checks

```powershell
.\tools\check_all.ps1     # everything verifiable without rendering
.\tools\test_install.ps1  # install the zip into a throwaway profile
```

```bash
./tools/check_all.sh
./tools/test_install.sh
```

`check_all` covers the failure modes this project actually hit: dead nodes,
sockets with no UI, sockets with no tooltip, inputs that cannot reach an
output, preset bleed, a broken package, and a planet larger than its own
atmosphere. Its last two checks want a `.blend` — pass one with `-Blend`; the
first three run on factory startup and need nothing.

Blender is found via `$env:PLNT_BLENDER` / `$PLNT_BLENDER`, then the usual
install locations, then `PATH`. For a Flatpak install:

```bash
export PLNT_BLENDER="flatpak run --command=blender org.blender.Blender"
```

## Known gaps

1. **Cloud shadows.** Measured at 98.2 % of baseline with them off — the shadow
   rays are 2 % of render time, inside the noise. An analytic refactor is still
   worth doing for better-defined shadows. Design is in `docs/DEVLOG.md`.
2. **Cold lava crust** — the fix is written and queued; confirm in a frame.
3. **Atmosphere is brighter** than the volume it replaced. `Intensity` toward
   0.6 recovers the older contrast at no speed cost.
4. **Rings are darker** but structurally richer.
5. **Craters** render but have not been isolated in any frame.
6. **Motion blur** is off and untested at these angular rates.

## Reading

| Doc | What it is |
|---|---|
| [`docs/DEVLOG.md`](docs/DEVLOG.md) | Architecture, the API traps, the defect log, cost measurements. |
| [`docs/V3_REPORT.md`](docs/V3_REPORT.md) | What v3 changed and why. |
| [`docs/AUDIT_2026-09-12.md`](docs/AUDIT_2026-09-12.md) | The audit v3 answers. |
| [`docs/V2_REPORT.md`](docs/V2_REPORT.md) | The v2 report. |
| [`docs/DELIVERABLES.md`](docs/DELIVERABLES.md) | Command map from the original working tree. |

Developed against Blender 5.2.1 LTS on Cycles with OptiX on an RTX 2060, AgX
view transform. Every measured number in the docs comes from that machine.

## Licence

GPL-3.0-or-later. See [`LICENSE`](LICENSE).
