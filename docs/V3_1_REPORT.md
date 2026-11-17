# PLNT v3.1.0: Blender 5.3 and DLSS

*16 November 2026 · Blender 5.3.0 vs 5.2.1 LTS · RTX 2060 6 GB, driver 621.24 / Ryzen 5 3600 · Windows 11*

## What changed in the package

| Change | Why |
|---|---|
| `core/render.py`: new `apply_viewport_denoiser()`, called from `apply_performance()`. Low/Balanced/High select DLSS with Performance/Balanced/Quality upscaling. | Feature-detected from the enum, so 5.0 to 5.2 keep `AUTO` exactly as before. Viewport only: Cycles in 5.3 offers no DLSS for final renders. |
| `tools/PlntBuild.psm1` finds Blender 5.3 first and no longer hard-codes the `5.2\python` folder. | Tooling followed the old release. |
| Version 3.1.0. `blender_version_min` stays 5.0.0. | |

Built on top of `main` as of PR #9, so the packaged-import fixes from #1 (`51a7c93`) are included and not repeated here.

Verified on both 5.3.0 and 5.2.1 (5.2 run against an empty user config): `extension build` and `validate` pass, and `tools/test_install.ps1` reports 18 panels and 17 operators. Create Planet System builds the earthlike system in 12 to 14 s. All three performance tiers report DLSS on 5.3 and leave the viewport on `AUTO` on 5.2.

The benchmarks below were run before merging `main`. The render timings use the September reference `.blend`. The viewport results concern Cycles and the driver, not PLNT's shaders, so they carry over.

## Does 5.3 render PLNT faster?

No measurable difference. Same `PLNT_PlanetGen.blend`, orbital camera, 1920x1080, OptiX, OIDN, Balanced performance. One process per render, three rounds with the version order alternated, never two renders at once:

| Quality | 5.2.1 (s) | 5.3.0 (s) | Median delta |
|---|---|---|---|
| FAST, 96 spp | 33.1, 30.8, 36.5 | 32.7, 35.4, 35.1 | +5.8 %, inside the spread |
| PREVIEW, 192 spp | 34.2, 33.5, 43.4 | 36.6, 33.6, 34.3 | +0.3 % |

The two versions' images differ by 80 dB PSNR, against 96 dB for a rerun on the same version, so there is no visual regression.

**The more useful finding is that samples are not where the time goes.** Doubling samples, from FAST to PREVIEW, costs about 1 s. Nearly all of the ~33 s is fixed cost: Geometry Nodes terrain evaluation, adaptive subdivision dicing and BVH build. No denoiser can reach that. The speed levers for PLNT are evaluation and dicing (subdiv level, `adaptive_edge`, persistent data for animation), not sampling.

## Does DLSS improve the viewport?

**Not on this machine.** Cycles offers DLSS, the RTX 2060 passes its checks (compute capability 7.5, driver 620 or newer), and NGX loads the driver's built-in `nvngx_dlssd.dll` 310.9.0. But:

- Per-sample viewport time is the same for every denoiser: OptiX 0.0979 s, DLSS Performance 0.0988 s, DLSS Quality 0.0987 s, OIDN 0.0991 s, DLSS Balanced 0.0992 s. That is about 85 samples per 30 s window each, read from `--debug-cycles`. DLSS Performance renders a quarter of the pixels and should be several times faster per sample.
- Viewport output with DLSS Balanced or Performance is **bit-identical** to OptiX at the same moment (PSNR 120 dB).
- NGX logs end at `NVSDK_NGX_CreateFeature_Validate`. The Ray Reconstruction feature is configured but never evaluated, and nothing logs an error.

So DLSS silently falls back to the OptiX denoiser at full resolution. Whether that is a Turing limitation or a 5.3 bug is not established; the evidence above is enough for a Blender bug report. PLNT still selects DLSS, because the fallback is harmless and cards where it works get the benefit.

What the viewport test did show: on this scene it takes about 7 s before the first viewport pixel, for every denoiser. That is the same fixed evaluation cost as above.

## Other 5.3 changes reviewed

From the [5.3 release notes](https://developer.blender.org/docs/release_notes/5.3/), nothing else affects PLNT:

- **Cycles** lists "minor GPU render optimizations", with no changes to adaptive subdivision, displacement, OIDN, light tree or BVH. That matches the flat timings above.
- **Geometry Nodes** has no performance changes. `Realize Instances > Preserve Normals` matters only for mirrored instances.
- **Python API** has no changes to `scene.cycles.*` or Geometry Nodes modifier inputs. `PropertyGroup.name` is now read-only by default; PLNT does not write it.
- **Vulkan is now the default backend on Windows.** The Cycles viewport goes through CUDA-Vulkan interop, which works. The MCP add-on's viewport screenshot returns a stale image under Vulkan; `bpy.ops.screen.screenshot` does not.
- **Viewport renders now pause during final renders**, which helps on a 6 GB card.

## Method notes

- The GPU idles near 75 °C with about 40 % load from the Windows compositor (`dwm`). That load is constant across both versions, but it widens the spread.
- An earlier run was discarded: a benchmark runner that had been stopped kept rendering alongside its replacement. Every number above comes from strictly serial runs.
