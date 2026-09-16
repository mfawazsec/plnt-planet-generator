# PLNT v3: where everything is

> **From the original working tree.** Kept as the command map between the
> Linux/Flatpak shell tooling and the PowerShell ports. The render harness,
> ablation scripts, `logs/`, `renders*/` and the demo `.blend` it refers to
> are not part of this repository. See the
> [repository README](../README.md) for what is.

## Use it

| What | Where |
|---|---|
| Installable add-on | `ext/plnt_planet-3.0.0.zip` |
| The scene | `PLNT_PlanetGen.blend` |
| Build the add-on | `& "$blender\5.2\python\bin\python.exe" tools\build_extension.py` then `blender --command extension build --source-dir ext\plnt_planet --output-dir ext` |
| Verify everything | `.\tools\check_all.ps1` |
| Install test | `.\tools\test_install.ps1` |
| Render the heroes | `.\render_all.ps1 -Mode final -Out renders_v3` |
| Apply v3 to the scene | `.\tools\deliver_v3.ps1` (supports `-WhatIf`) |
| Prove it animates | `blender -b <blend> -P tools\anim_check.py -- --shot 9 --frames 48 --time-scale 1.0 --out logs\anim` |

In an empty scene the N-panel offers **Create Planet System**. The quick row
carries **Quality**, **Performance** and **Time Scale**; the thirteen parameter
panels are grouped under Planet, Sky, Civilisation and Scene.

## The two dials

**Quality** is what the picture is worth: Draft 1280×720/64, Fast 1920×1080/96,
Preview 1920×1080/192, Final 2560×1440/512, Archive 2048 with full dicing.

**Performance** is what the machine can afford: Low for laptops and 4 GB cards,
Balanced for the 6 GB card this was built on, High for 8 GB and up. They are
independent: a laptop can render Final quality at Low performance.

## The clock

`Time Scale` is **world hours per second of footage**. The file ships Frozen
(0), because every hero still must match frame to frame. Timelapse (1) turns a
24-hour planet once in 24 seconds of playback and takes a low satellite round
its orbit in about 90. Everything else keeps its own Kepler period, so the
relative speeds stay honest at any setting.

Headless, with no add-on registered, the clock is three custom properties on the
Scene: `plnt_time_scale`, `plnt_day_length_h`, `plnt_beacon_rate`. Set them
directly, or pass `--time-scale` to `tools\anim_check.py`.

## Windows notes

The `.sh` tooling is Linux/Flatpak only, with absolute `/home/...` paths and
`flatpak run`. The PowerShell ports take the same arguments as parameters.

| What | Where |
|---|---|
| First-time setup | `tools\bootstrap.ps1` (builds the venv Pillow needs) |
| Cost attribution | `.\tools\ablate_paired.ps1`, `.\tools\ablate_vol.ps1` |
| Wide unpaired sweep | `.\tools\ablate.ps1 -Matrix 1` or `-Matrix 2` |
| v1 like-for-like | `.\tools\baseline_v1.ps1` |
| Shared harness | `tools\PlntBuild.psm1` |

Differences that matter:

- System Python 3.12 is now installed (`%LOCALAPPDATA%\Programs\Python\Python312`)
  with Pillow and NumPy, so `montage.py` and `compare.py` run without the venv.
  Tools that run *inside* Blender still use its bundled interpreter.
- Windows has no SIGTERM, so the `rc=143` that identified an out-of-memory kill
  on Linux never appears. The runners map `0xC0000005` / `0xC0000374` instead.
- The runners **exit non-zero** when a shot or check fails. The bash versions
  always exited 0, so a failed batch looked fine to anything calling them.
- `render_all.ps1` defaults to `PLNT_PlanetGen_optix.blend`; pass `-Blend` for
  the canonical scene, and `-Out` for a directory other than `renders\`.

## Roll back

| What | Where |
|---|---|
| Pre-v3 scene | `logs\PLNT_PlanetGen_prev3.blend` |
| Pre-v2 scene | `logs\PLNT_PlanetGen_prev2.blend` |
| v1 hero renders | `renders_v1\` |
| v2 hero renders | `renders\` |

Copy the blend back over `PLNT_PlanetGen.blend` to undo. Re-running
`deliver_v3.ps1` never overwrites the pre-v3 backup; it takes a timestamped copy
instead.

## Read it

| What | Where |
|---|---|
| v3 report | `V3_REPORT.md` |
| The audit v3 answers | `AUDIT_2026-09-12.md` |
| v2 report | `V2_REPORT.md` |
| Architecture, API traps, defect log | `README.md` |
| Raw paired benchmark cells | `logs\ablate\paired.jsonl` |
| Hero timings | `logs\hero_times.json` |
| Per-tier measured seconds | `logs\quality_times.json` (written by the renderer when `-Quality` is passed) |

## Look at it

| What | Where |
|---|---|
| v3 heroes | `renders_v3\PLNT_shot_01..10.png` |
| v2 heroes | `renders\PLNT_shot_01..10.png` |
| Animation proof frames | `logs\anim\` |
| Contact sheets | `logs\sheet_v3.png`, `logs\sheet_heroes_v2.png` |
| Build a sheet | `python tools\montage.py --dir renders_v3 --out logs\sheet_v3.png` |

## Known gaps

1. **Cloud shadows.** A look change, not a saving. `cloudshadow_off` measures
   98.2 % of baseline, so the shadow rays are 2 % of render time. The analytic
   refactor is still worth doing for better-defined shadows; the design is in
   `README.md`. Not attempted.
2. **Cold lava crust.** The fix is written and queued; confirm in a frame.
3. **Atmosphere is brighter** than the volume it replaced. `Intensity` toward
   0.6 recovers v1 contrast at no speed cost.
4. **Rings are darker** but structurally richer (`Ring Density`,
   `Composition Scale`).
5. **Craters** render but have not been isolated in any frame.
6. **Motion blur** is off and untested at these angular rates.
