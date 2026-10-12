# Native clip-style decoded-media parity

This component closes the missing local decoded-media evidence for the six supported effects and a contiguous visual crossfade. It also fixes draw order within a renderer track. Original full Waves 3I/6/16, Modes A/B, browser/non-developer/Owner acceptance and final A/B/C remain open.

The renderer now sorts visuals by track order and then timeline start. Equal-start layer order remains stable. It excludes a clip from its own transition-peer lookup. This prevents an older clip from covering an incoming crossfade when the canonical snapshot's array order differs from temporal order. Track layering, source windows and timeline duration remain unchanged.

The parity driver uses the shipped shared inspector and signed owned local HTTP. It reviews the next clip's incoming fade before setting the previous clip's outgoing crossfade; the conflicting-pair rejection remains intact. Source Mode B splits its three-second clip at 1.5 seconds, inside a saved transcript gap. Narrated Mode A uses two existing adjacent clips. Style decisions preserve source windows and unrelated audio/caption/voice tracks; undo/redo and approval invalidation use existing immutable canonical history.

## Evidence

See [clip-style-parity-evidence.json](north-star/clip-style-parity-evidence.json) for exact paths, hashes and receipts. Passing bundles are Mode A n4 and Mode B n1. Mode A has 24 signed controller requests, Mode B 14, including seven/eight style-controller requests respectively. Both use synthetic moving video/audio, prepared measured narration or saved ASR fixtures. Actual preview/final rendering and local full QC pass. Exact history, physical media and render bindings recover in separate processes. Prepared narration remains unchanged; no new inference occurs.

The independent oracle imports no renderer implementation. It derives sRGB color matrices, contrast/brightness transfer and Gaussian blur from [W3C Filter Effects 1](https://www.w3.org/TR/filter-effects-1/#filter-primitives). PIL blur and resampling approximate browser output; the result is sampled fixture evidence, not pixel identity or universal/perceptual correctness.

Four fixed temporal samples per mode have declared purposes: first-clip color catalog, crossfade/draw order, second-clip chain appearance and outgoing slide. Five color-effect omissions must differ observably and lose to the saved first-clip output. Blur uses an edge mask derived only from canonical/no-blur oracle images, never the actual output. The blend sample must defeat hard-cut and reversed-draw-order controls; the slide sample must defeat an omitted-slide control. Other comparisons remain diagnostic, including near-ties during mostly offscreen transitions. Complete-frame/semantic quality is not accepted by this oracle.

A separate direct renderer probe reverses the two clips' manifest array without changing the project. Three whole decoded frames before/during/after crossfade exactly match the canonical Mode B video (MAE 0). It uses retained verified source video and the exact mixed PCM from the scoped backup. This probe is not a new project render acceptance or full QC certification.

Renderer typecheck and all 48 renderer tests pass, including two new draw-order/self-peer regressions. Earlier Studio728/Native49/API17/static64 evidence remains linked at the preceding clip-style commit; these suites were not rerun for this renderer/test-driver-only increment. Actual signed controller/renderer/QC/recovery runs are fresh.

## Retained nonqualifying attempts

Mode A n1 correctly rejected an outgoing crossfade conflicting with the next clip's incoming fade. The driver now reviews the next clip first. Mode A n2/n3 render/QC passed but the chosen color chains could not separately reveal brightness/contrast in the oracle region; these are not the six-effect parity acceptance bundle. Mode A n4 uses an intermediate brightness level so both operations remain observable.

Earlier oracle attempts are retained. The first broad comparison included nearly indistinguishable color omissions during an outgoing slide and diluted blur by flat areas. The final oracle declares each sample's purpose and independently selected blur edges, retains diagnostic comparisons and requires observable controls for every qualified effect. No failed receipt was overwritten or relabeled as passing.

No provider/paid call, real publication, production deployment, main merge or Owner UAT occurred. Only newly owned temporary fixtures are torn down after export. Historical accepted media stays intact. Other effect values/combinations, canvases, complex layer/transition limits, full browser/non-developer/Owner flows, real providers and all original North Star gaps remain separate acceptance work.
