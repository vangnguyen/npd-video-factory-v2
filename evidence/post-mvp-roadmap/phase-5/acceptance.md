# Native Auto Editor — technical acceptance

STATUS: PASS for Phase 5 technical scope. Fixture approvals are not human editorial/final approval.

Real render evidence: `editor-real-render.json`, two distinct real FFmpeg outputs in `C:\NPD-Video-Factory\post-mvp-validation\phase5-editor-20261005`, five immutable local reference assets (three generated images, two generated silent videos), generated reference music and the exact previously accepted real Thùy Dung WAV. Zero new provider calls or TTS inference.

- Existing strict native script/scene breakdown is reused; richer planned scenes extend that contract, and exported timelines reuse `app.timeline_models` schema 1.1. Short video loops are explicit bounded source clips, with the selected source time used on the first pass.
- Candidate ranking uses hash-verified transcript word overlap, then deterministic library rotation. Candidate source/analysis hashes and explanation are retained. Filename-only or semantic image guesses are not made.
- Human can change selected image/video, contain/cover framing, image zoom/pan, source trim time and cut/fade. Scene/plan/music changes invalidate script approval. Image motion, actual moving video, both pan directions, source trim and subtitles were exercised with actual FFmpeg.
- Both final MP4s pass full decode, portrait dimensions, 30 fps H.264/AAC, 48 kHz audio, A/V/duration checks, audible finite signal, no hard clipping and no black intervals. Scene-image pixel comparisons confirm actual movement. CTA and text layout are present in `render-reference.png`.
- The exact production music filter was independently measured: 440 Hz music amplitude while voiced / quiet = 0.17545. Music is bounded WAV/MP3 with an explicit rights receipt; immutable original and decoded PCM hashes are retained. Changed music is rejected before voice synthesis.
- Captions use measured sentence activity and weighted phrase estimates, without fabricated word alignment. Fixed reference text margins leave room for social UI; actual TikTok/Reels device overlays still require human viewing. These are reference margins, not platform certification.
- SQLite integrity/reopen and immutable job checkpoints pass. UI played a real 25-second 1080×1920 video, then auto-planned sources, changed scene 2 to another video, saved source start 1.25 seconds and reloaded. Those choices persisted; TTS/render remained disabled pending human approval. `studio-editor.png` records the controls.

TESTS: Native 87/87, Studio 26/26 PASS. Ten additional native tests cover candidate lineage/no filename semantics, stale/CAS/busy/mutated plans, manual choice/restart/approval invalidation, finite trim/motion constraints, existing canonical loop bounds and real music HTTP/rights/MIME/CSRF/race/tamper safety.

LIMITS: The videos use clearly labeled technical reference fixtures and reuse the same accepted speech. They do not satisfy the ten independent human-reviewed release videos. Semantic Vision is unavailable; text selection still requires human visual review. Original Owner project and accepted media are not revised by this test.
