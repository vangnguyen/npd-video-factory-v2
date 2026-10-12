# Native clip effects and transitions

This increment implements editable clip styling against the existing canonical timeline in both Native Source (Mode B) and narrated video (Mode A). It addresses Master Spec sections 39–40 and original Waves 3I, 6 and 16. The shot view remains the default. It does not certify either complete mode or final acceptance bundles A/B/C.

## Implemented behavior

The shared inspector edits brightness, contrast, saturation, hue rotation, grayscale and blur through a closed numeric catalog. Blur is proportional to visual viewport width. Effects preserve their saved order. Unsupported legacy effects remain readable; a render containing them fails explicitly. Reset can replace them with the approved empty catalog.

Uploaded visual clips support incoming and outgoing cut, fade, crossfade and slide decisions. Uploaded audio supports cut and fade envelopes, including the existing audio crossfade envelope. Generated narration does not expose these controls. Visual outgoing crossfade requires one contiguous enabled next clip on the same track, a sufficient next-clip duration and a compatible incoming transition. Its previous source frame is held within the validated source window. It does not extend source media or shift the canonical timeline. Audio crossfade envelopes require the editor to arrange any intended overlap.

All saves use existing typed operations, workspace/role permissions, locks, revision/hash checks, approval invalidation and immutable timeline history. Unrelated crop, reframe, source windows, audio, captions and generated narration are preserved. Drafts cannot be submitted through a different inspector. Context changes and uncertain acknowledgements require reconciliation before another save; the client does not automatically replay a write. Undo/redo creates new immutable versions.

New style decisions are tagged `clip-style-v1`. Invalid effect values, duplicates, audio visual effects, generated-voice property bypasses and transition durations beyond a clip reject before persistence. A trim/split that would leave an invalid styled transition rejects; adjust the transition first.

Render contract 2.4 carries approved effects and outgoing transitions. Python, JSON Schema and renderer checks reject invalid catalogs and incompatible crossfade pairs. Versions 2.0–2.3 keep their prior field restrictions. Both Native render adapters preserve the emitted 2.4 version. The renderer applies saved filter order and frame-based visual transitions. Existing brand, captions and audio pipelines remain in use.

## Verification and limits

The evidence index is [clip-style-evidence.json](north-star/clip-style-evidence.json). Studio has 728 passing tests, related Native modules 49 (including three static HTTP tests), renderer 46 and related API 17. Static HTTP verifies 64 served module hashes. These are scoped suites, not a new certification of every North Star requirement.

Two owned local bundles use synthetic moving video/audio, a saved Mode B ASR fixture and prepared measured Mode A narration. Shipped controllers run with fixture DOM and signed local HTTP: Mode A has 23 controller requests and Mode B 12. Both produce actual preview/final media, pass local full QC and preserve original media. Both restore exact history and physical media in separate keyless processes, then undo/redo while keeping approval invalidated.

The original FFmpeg/PIL pixel oracle decodes final videos and compares three sampled regions per mode against canonical and deliberately omitted-effect/transition controls. That evidence verifies brightness, saturation, incoming slide and outgoing fade. Additional [decoded-media parity evidence](NATIVE_CLIP_STYLE_PARITY.md) now qualifies all six effects, a contiguous visual crossfade and outgoing slide at declared fixture samples in both modes, plus a reversed-array renderer regression. Its blur edge masks and sample purposes are explicit. Other combinations, full renderer parity and perceptual/semantic quality remain open.

Vietnamese captions remain visible in inspected output frames. The Mode A frame after the short imported clip ends retains the existing brand/caption layout; this synthetic fixture is not a complete editorially accepted video.

Rejected first attempts are retained: Mode B n1 exposed the Source adapter forcing 2.3 and was repaired; Mode A n1 used an incorrect test-driver mutation route and correctly received an authorization rejection. Only n2 bundles qualify as this component's passing local evidence.

No new ASR/TTS/provider inference, paid call, real publication or deployment occurred. Real browser/non-developer acceptance, genuine media/voice quality, Owner UAT, all supported effect/transition parity, renderer limits and original complete Modes A/B/A/B/C remain open. Historical accepted artifacts are retained; only newly owned temporary fixtures are torn down after verified export.
