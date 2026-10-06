# Phase 9K — Audio repair implementation checkpoint

PHASE: 9K — Owner-reported voice instability/roughness, all five videos

STATUS: IMPLEMENTATION_TESTS_PASS; real repaired MP4s and human listening still outstanding

HEAD SHA: c3dd3650680a5af861522b19d71d0fda6ab73eb7 (pre-repair baseline; the following incremental application commit records these changes)

FILES CHANGED: Native pipeline/store, optional voice quality registry/resolver, five tests, local signal/trial/repair helpers and this evidence directory.

TESTS: Native suite 139/139 PASS, including five new context-policy tests. Existing sentence synthesis, network blocking, frame-cap failure, render, approval/persistence/provenance tests pass. Studio source is unchanged; its last relevant suite is 32/32 PASS. Actual provider/model inference trials are separately classified; mocked unit tests prove no production quality acceptance.

EVIDENCE: original-audio-diagnostics.json, scene-trial-case04-seed604.json, scene-trial-case04-seed604-temperature0.6.json and native-tests.log.

NEW CAPABILITIES: opt-in scene-context-v1 groups unchanged narration by scene; deterministic NumPy seed 604 is confined to fresh TTS children. Snapshot reference binds policy ID/version/hash. Metadata records the actual policy, source bytes and unchanged locked sampling parameters. Changing a policy adds a project revision, clears production approval, preserves history and never dispatches. The original sentence policy remains the default.

REGRESSIONS: no verified Phase 8 regression. Frozen SDK/model/preset/profile/dependencies are unchanged. Five Phase 9K previews have actual Owner negative audio feedback and must be revised; their original bytes/evidence will remain intact.

BLOCKERS: human listening is still required for the new audio. Signal measurements cannot establish that perceived roughness is resolved. No new provider/credential/dependency is needed for this repair.

NEXT ACTION: preserve databases/old evidence, store actual Owner negative decisions, reuse the approved words/media under the authorized repair scope, enqueue five new jobs in the existing Native worker, verify and present exact new videos for listening.

## Observations and bounded choice

Original WAVs are mono PCM 48 kHz with zero measured saturation samples. Current rendering applies level gain and AAC encoding without pitch/time stretching. This rules out hard clipping in the original raw signal; it does not rule out audible synthesis artifacts. No claim of full auditory inspection is made.

The existing sentence policy starts separate model contexts for individual sentences. This is a plausible contributor to cross-sentence prosody changes, not a proven exclusive cause of every Owner-described defect.

Actual case 04 trial A uses scene context, the same locked temperature 0.8 and seed 604. The range of measured unit median F0 is 0.955 semitones versus 3.827 for the original sentence units. Trial B lowers temperature to 0.6 experimentally and measures 1.319 semitones. Group boundaries differ, estimates can have octave errors, and neither result is human acceptance. The minimal repair uses A's grouping with the locked parameters; B's sampling override is not promoted.

There is no arbitrary pitch correction, tonal flattening, playback slowdown, denoiser or EQ. Vietnamese lexical tones and the approved words remain intact. Unknown or changed policy references fail explicitly before local synthesis.

The main Studio service stays on application 9ce137afa8ac62fdb8ce5b35fbba997013adfef3. Its existing dispatch already starts a fresh TTS child for every job; that child imports the repaired code. The parent render function remains unchanged and accepts measured scene units. Application/source hashes and this mixed process state will be recorded explicitly. No stop/restart rejected by policy is retried.

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
