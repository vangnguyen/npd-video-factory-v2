# Phase 7 — configurable brand profiles and video templates

STATUS: PASS for the supported Windows Native technical scope; no human production acceptance is claimed.

Three configuration profiles (generic, Ngọc Phương Đông, Vang Nguyễn) and twelve 9:16 templates cover property, news/update, personal brand and event purposes at 30/45/60 seconds. Official brand assets are absent: both seed brands explicitly use reference palettes/fonts and no logo or default music. The exact accepted Thùy Dung voice remains locked.

Project choices store a validated full profile/template snapshot and hashes. Subsequent catalog edits cannot change a selected approved snapshot. Changes advance the revision and invalidate approval, preserving manual scene bindings, motion/trim/transition settings and rights-confirmed music. Existing documents remain readable without rewriting their stored bytes. Brand font/logo availability and integrity are checked before TTS. Rendering uses configuration for font, palette, captions, CTA, intro, music gain and reference margins.

## Verification

- 103/103 native tests PASS (`native-tests-fixed.log`); 27/27 Studio tests PASS (`studio-tests.log`). Seven brand tests cover frozen snapshots, all twelve templates, duration refusal, assets/rights/fonts/voice/hash validation, legacy preservation and optimistic concurrency.
- Four actual FFmpeg renders PASS decode, H.264/AAC, 1080×1920, 30 fps, no-black, duration/audio/clipping checks. All four purposes and all three durations are represented. Exact reused source WAV SHA is `2b5f57c31c2514683a6465e408b2cbe20e949cc9e3921a84f68c28ab983a73e5`, speed 1, zero new provider or TTS calls. `brand-real-render.json` identifies each project/job/output/hash.
- Actual browser applied NPD/property30 then Vang/personal45, reloaded, showed the stored choice and disabled rendering pending review. Revision 14→16, approval cleared; sources, music and manual options preserved. `ui-verification.json` and `studio-brand.png` record this explicit isolated fixture.
- Extracted real frames in `ngoc-phuong-dong-reference.png` and `vang-nguyen-reference.png` show distinct fonts/palettes, visible headings, CTA and phrase captions.

## Failure found and fixed

The first full run reported two Windows `WinError 10053` transport errors on early invalid-header refusals; an earlier music-only run also exposed the same issue. Merely shrinking rejected test bodies did not solve the underlying behavior and was reverted. The server now flushes the JSON error, sends `Connection: close`, half-closes its write side and discards at most 1 MiB for at most 250 ms before closing. Rejected data is never parsed, persisted or dispatched. A real 288 KiB unread-body regression verifies 403/JSON and zero projects. Original full-WAV rights/CSRF/stale/busy tests remain in place. Large/slow hostile uploads remain bounded and may terminate the transport at that limit.

## Limits

The target-duration policy preserves speech speed, refuses voice that exceeds the selected duration and holds the final CTA/music until the target. This short accepted reference narration leaves 8.04/23.04/38.04 seconds after voice for 30/45/60-second tests; long holds are technical coverage and require human pacing review. These are reference fixtures, not four production editorial videos. Purpose labels do not invent news/events. Reference margins require actual platform/device preview; no official platform certification, official logo, semantic image understanding or new-voice word alignment is claimed. Phase 8 still needs ten real final candidates with actual human watch/listen acceptance.
