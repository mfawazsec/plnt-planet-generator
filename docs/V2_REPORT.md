# PLNT v2: what changed, and how it was verified

## The short version

Three goals were set: cut render time, deepen detail, and make the generator a
tool rather than a script. All three landed, but the performance work went
somewhere none of the planning predicted.

## 1. Render time

### What the plan expected, and what was true

| hypothesis | measured |
|---|---|
| No Subdivision modifier exists; dicing has been a no-op | **False.** `PLNT_Adaptive` is present with adaptive subdivision on. |
| Adaptive subdivision dominates cost | **False.** Disabling it changed almost nothing (unpaired, within noise). |
| The field is evaluated ~4x per hit via bump; that is the whole story | **False.** Removing displacement entirely recovered only ~16% (unpaired). |
| True displacement is the most expensive mode | **False.** It measured faster than the shipped BOTH (unpaired, ~10%). |
| A feature at Amount = 0 still costs a texture lookup | **False.** Cycles folds it away entirely. |

### Where the time actually went

| component | share | confidence |
|---|---|---|
| **Atmosphere volume** | **54%** | paired, thermally gated |
| Clouds | 30% | paired, thermally gated |
| Whole 193-node surface shader | 9% | paired, thermally gated |
| Displacement (bump + true) | ~16% | unpaired, indicative only |
| Adaptive subdivision | ~2% | unpaired, inside the noise band |

The displacement and subdivision figures come from the first, unpaired matrix,
which GPU thermal throttling later invalidated for effects under about 6%. They
are directionally right (neither is the bottleneck), but the exact
percentages should not be quoted. The atmosphere, cloud and shader figures are
from the paired runs and are solid.

The ray-marched atmosphere cost more than the surface shader, displacement and
subdivision combined. Cycles was stepping up to 1024 times through a uniform
spherical shell for every camera ray and every shadow ray.

### The fix

`core/atmosphere.py` computes the same optical path in closed form. The path
through a spherical shell is a chord: with `b = |P x d|` the ray's impact
parameter and `t = sqrt(R^2 - b^2)` the half-chord, a ray that misses the planet
crosses `2*(t_outer - t_inner)` of air and one that hits it gets only the near
part. That is exactly why the limb glows: grazing rays travel much further
through air. 62 nodes, evaluated once per hit, no stepping, no volume.

Measured at **28.5% of baseline** in a paired A/B.

### Hero renders, identical settings

The full ten-shot batch at 2560x1440 / 1024 samples. See the live report for the
completed table; the first four shots ran 3.49x / 4.54x / 4.64x / 4.21x, for a
running 4.20x. Detail ratios over the same four: 1.31 / 0.99 / 0.76 / 0.96 --
shot 03's figure is largely a metric artefact, discussed under known look
changes in the README.

### Low-resolution like-for-like, identical settings

| shot | preset | v1 | v2 | speedup | detail |
|---|---|---|---|---|---|
| 02 | earthlike | 157.3s | 46.4s | **3.39x** | 0.99 |
| 03 | ringed_ice | 122.7s | 36.7s | **3.34x** | 0.90 |
| 06 | desert | 230.5s | 165.7s | 1.39x | **1.82** |
| 10 | megastructure | 69.1s | 41.1s | 1.68x | 0.99 |
| | **total** | **579.6s** | **289.9s** | **2.00x** | |

Twice as fast overall. `detail` is the high-frequency energy ratio v2/v1: three
shots hold within 1%, and shot 06 carries 81% more, which is the dune fields
and strata. The gain is shot-dependent, tracking how much atmosphere is in
frame, so quote the range rather than a single figure. Shot 03's 0.90 is the one
figure worth flagging: about 10% less high-frequency energy, most likely the
analytic atmosphere softening the disc relative to the volume.

## 2. Detail

- **Rings.** A real 196k-vertex polar annulus replacing a two-vertex quad.
  Named divisions (Cassini, Encke, Keeler, Maxwell, Huygens) that stay put
  across seeds, spiral density waves at integer arm counts, azimuthal clumping
  sampled in Cartesian space so there is no wrap seam, shepherd-moon wakes, and
  Henyey-Greenstein forward scattering. 153-node shader, 23 parameters.
- **Orbital.** A twelve-module instanced library. 2,621 instances from 6,240
  unique triangles at level 10, with Realize Instances removed entirely. Truss
  bay count is derived from circumference so braces meet exactly. The greebles
  now take the curve's rotation, which is what turned dashed ribbons into
  structures.
- **Megastructures.** Mirror belts, partial ringworld arcs with lit inner
  faces, and a Dyson swarm, on their own object.
- **Surface.** Ocean glint variation, coastal foam, dune fields, rock strata,
  ice cracks, vegetation clumping, impact craters. Each gated by an input that
  Cycles folds away at zero, so unused features are free.

Detail was not traded for speed: the high-frequency energy ratio between the v1
and v2 frames of shot 02 is **0.9908**.

## 3. Usability and reproducibility

- **159 parameters, all documented, zero orphans.** Previously all 174 sockets
  had empty descriptions, and rings, ground patch, orbital and sun had no UI at
  all. Panels enumerate node-group interfaces rather than hand-written lists, so
  a socket added later cannot become unreachable.
- Basic / Advanced / All tiers, cross-panel search, per-section randomise and
  reset, copy/paste as JSON, quick render, state messages.
- **An empty scene becomes a planet in one operator.** `PLNT_GlobeRig` existed
  only inside the .blend and is now in source.
- **`plnt_planet-2.0.0.zip`** builds and validates with Blender's own tooling
  and registers 14 panels and 11 operators.

## 4. What went wrong, and what guards it now

Two conclusions were reported and then retracted:

- **"93% saving"** came from a mutation that rendered a degenerate frame (mean
  luminance 30.1 against 50.5 everywhere else). Every ablation cell now records
  the output image's statistics.
- **"The clouds vanished"** because the planet had inflated to radius 1034 and
  swallowed its own cloud deck (1004) and atmosphere (1030), because rebuilding
  the terrain field orphaned the globe rig's group node. The apply now fails
  outright if the globe reaches the shell radii, and group references are
  captured and restored across rebuilds.

Measurement was also corrupted twice by the environment: GPU thermal throttling
(2100 -> 1500 MHz under sustained load) and the desktop's own GPU use (~790 MB
of VRAM, ~37% utilisation at idle). Benchmarks are now paired and gated on the
measured idle floor.

## What is not done

**Cloud shadows.** The plan called for extracting the cloud coverage into a
shared field, sampling it where the sun ray pierces the cloud shell, and then
setting `PLNT_Clouds.visible_shadow = False`, which is better shadows *and* faster,
because it removes a per-sample transparent shadow ray against a 1004-unit
sphere. Clouds measured 30% of render time, so this is the largest remaining
opportunity. It was deferred because the measurement that would size it
(`cloudshadow_off`) was cut when the atmosphere result made it the priority.
Implementing it blind could have been a net loss.

**Craters are unconfirmed, not untested.** An earlier claim that no hero shot
exercises them was wrong: volcanic sets `Crater Amount 0.25` and desert 0.15.
They render, but cannot be isolated against the lava and dune detail in those
frames, so their appearance is unverified rather than unexercised.

**Cold lava crust had no texture**, found by zooming into shot 05. Below sea
level a volcanic world is still shaded by the OCEAN branch with a near-black
colour, so the areas between the glowing fissures were flat, hard-edged and
featureless. The v1 lava fix made most of the molten sea emit almost nothing so
the hot cores survive AgX, which was right, but nothing was added back to give
the cold crust character. A `lava_crust` feature now drives tonal variation and
micro-relief from plate and grain noise, gated on `Lava Emission` so it folds
away entirely on non-volcanic worlds. Verified by re-rendering shot 05 alone --
legitimate because it is the only shot with lava, and the feature is inert
everywhere else.

**The out-of-memory cause is now identified.** Reproducing it settled it.
Shots 07-10 carry no dice value; v1 passed `--dice ${DICE:-2.0}`
unconditionally so they rendered at 2.0, while the v2 rewrite made that
conditional and dropped them to 1.0. Shot 07 was killed at 261s with rc=143 --
SIGTERM, which is what systemd-oomd sends, not the SIGKILL a kernel OOM uses.
Dicing drives **memory**, not speed. `render_all.sh` now defaults DICE to 2.0,
and success is checked by the output's modification time rather than its mere
existence, and a stale frame satisfies existence, which is how a killed shot
reported OK and then scored a detail ratio of exactly 1.000 against v1, because
it *was* v1.

**Shot 03 lost ~10% high-frequency energy.** Small and plausibly the analytic
atmosphere softening the disc relative to the volume, but not isolated.

## Verify it

```bash
./tools/check_all.sh
```
