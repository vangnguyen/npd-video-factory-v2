# Native drama voice integration notes

P6 of `VF-FINAL-EXPORT-MANUAL-PUBLISHING-FOCUS-01`. Export Core's focused functional gates are green; wide Native/API cohorts and Owner/browser acceptance remain open. Work below is additive; it does not certify Export or Drama as ready.

Implemented component: `voice_library.py` stores workspace voice versions and write receipts, rights declarations, consent and custody hashes. It performs no TTS and is not wired into Studio yet. Nine library tests plus seventeen backup tests pass; evidence is in `evidence/final-export-manual-publishing/drama-voice/library.json`.

Next integration sequence:

1. Persist project characters, explicit cast references to immutable library versions, speaker-tagged lines and an optional narrator (`false` by default). A global voice must not contain a character assignment. Permit draft/unassigned casts, but block execution until references and script/shot bindings are complete. Every save uses project revision/CAS, invalidates approval and downstream preview/export, and writes an idempotent receipt.
2. Keep a fail-closed boundary so an incomplete drama project cannot accidentally render using the legacy single Thùy Dung voice. Existing ordinary projects retain their current path.
3. Add normalized per-line delivery plans and cache fingerprints using workspace, actual provider/configuration revision, acoustic voice identity/reference hash, normalized text, language, speed/style and pronunciation-policy version. Exclude unrelated characters and visual assets. Reusing the same library voice in another project is allowed inside the same workspace. Changing one character must invalidate only affected line synthesis, then subtitle timing, mix, preview and final export.
4. Implement explicit per-line TTS with measured PCM receipts, assembly and speaker-aware captions. Do not label deterministic tone fixtures as real voices. Validate actual provider capability and reference bytes before dispatch; unknown rights or absent reference consent remain blocked. A library record alone does not configure a provider.
5. Integrate the measured dialogue bundle into the canonical shot timeline and existing narration preparation/render/QC. Native currently binds a single `PROFILE_SHA` in `narration.identity`, `narration.prepare`, `pipeline.synthesize`, render and voice-reuse checks. Introduce a separate, validated dialogue binding; never falsely label two voices with the old fixed profile or rewrite the accepted profile. Preserve sample-based duration fitting and immutable accepted audio/video.
6. Add Voice Library/character/casting/line editor UI, targeted regeneration, project/series persistence and rights display. Expose only working actions; no apparent voice selection may silently use a different voice.
7. Produce a two-character, narrator-disabled local delivery with genuinely different configured voices, then prepare the consolidated five-case Owner export UAT package. Human listening and UAT remain separate from technical or fixture approval.

No platform OAuth, platform uploads, scheduling, analytics/winner/learning/trend expansion or production deployment belongs to this work. Missing providers do not block completion of the remaining architecture and tests. No paid operation, reference-voice cloning or legal override is inferred from fixture metadata.
