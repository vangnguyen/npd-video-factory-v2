# Mode B browser integration candidate

The actual Studio browser now carries a source project through upload, completed fixture transcription, local scene/silence/highlight analysis, reviewable cuts, canonical timeline, crop fallback, word captions, uploaded B-roll/music, ducking, preview, separate Reviewer content approval, Editor render and full local QC. This is a component acceptance candidate for Waves 3/6/8/16. The original full Mode B, genuine uploaded-footage/provider acceptance and Owner UAT remain open; all 59 broad capability groups remain unclosed.

The isolated project uses generated moving source pixels and an existing hash-pinned local-real TTS WAV. Its three ASR transport requests and word intervals are explicit fixtures. The Reviewer is an explicit CI identity, not the Owner. There are no new TTS inferences, paid operations, external provider calls, real publications or production changes. Uploaded rights are not promoted into publication clearance.

## Browser-observed workflow

The Editor creates a media project using the technology/AI channel profile and uploads the video by whole-file SHA and chunks. The actual worker completes the fixture transcript and local analysis. The UI reviews the available highlight, keeps all 30 words and applies two non-destructive silence decisions. Center-crop keyframes preserve null subject confidence and `needs_attention=true`.

Word captions, source normalization, an uploaded synthetic music bed with fades/crossfades/ducking, and selected uploaded moving B-roll use the same canonical timeline. An advanced-timeline split and undo restore three source clips. The full-effects preview plays through its 7.4-second duration. The Editor cannot approve; a separately authenticated Reviewer plays the saved preview and approves the content for render. The restored Editor then renders the 7.4-second 1080x1920 final through the actual local worker and QC. The Editor cannot approve the final video or publish. No final Owner watch/listen acceptance is recorded.

Analytics remains empty: the fifteen displayed metrics show unavailable values, with no invented publication or audience history. This verifies empty-state behavior only. It does not certify real analytics or publishing.

## Repairs exposed by the browser

- Reviewer playback now has a read-only **Xem preview đã lưu** control, bound to the current valid saved preview. It creates no render or provider job. Stale, foreign or invalid preview bindings remain rejected; creating a preview still requires edit permission.
- Source-project render and pre-preview guidance no longer display the legacy locked voice or estimated narration labels. Complete effects previews do not cover their burned subtitles with the client overlay.
- Open source-edit disclosures survive saves within the same project. Upload errors identify the actual guard, and uploaded B-roll provenance has a readable Vietnamese label.
- Logout consumes the bounded authenticated empty JSON body before the next keep-alive request. Invalid CSRF is still rejected before body parsing and closes the connection. Nonempty logout fields do not revoke a session. Aborted media connections close without a futile error reply.

## Verification and preservation

Studio: 772 PASS. Native access/HTTP/RBAC: 23 PASS. The retained pre-fix logout test fails with HTTP 501; the same-connection test passes after repair. Existing media/render tests from the preceding sealed CI increment are identified separately and are not added to this count.

The browser final player reports 1080x1920, 7.4 seconds and completed playback. Geometry at 1366/1920/2560 fits the available workspace; browser console evidence is empty. Screenshots are component layout evidence, not non-developer usability or Owner acceptance.

The required thirteen Artifact A files are exported as a CI candidate, with additional manifests, audio clocks, source imports and sampled QC frames. A fresh interpreter restores the owned archive and verifies exact project/job hashes, immutable source hashes and the render checkpoint without replaying ASR or render. Final download remains gated by final human approval. Four owned temporary roots are absent after their normal lifecycle; previously policy-blocked historical roots and accepted artifacts are untouched.

`scripts/north_star_mode_b_browser.py` hosts future isolated rehearsals using a preserved direct-CI candidate and a fresh external output directory. The n4 server was already running when candidate export was added; the export function was invoked against its quiescent owned store before shutdown, without another job, content change or approval. The helper then produced the state archive. This export is recorded separately from the UI actions.

Earlier n1 failed because a snapshot parent directory was absent, before upload; its temporary input was therefore unavailable. n3 retained the keep-alive logout failure. Neither failed attempt is represented as a passing full flow. The passing n4 and cold-restore receipts are indexed in [mode-b-browser-evidence.json](north-star/mode-b-browser-evidence.json). Exact final source HEAD and recovery pair are recorded externally in `recovery/20261007/mode-b-browser-program-state.json`.

Continue genuine speech/ASR/Vision/tracking, original Mode A/B UI and three A/B/C acceptance bundles, configured real publication/analytics and the remaining North Star platform requirements. No broad readiness state is promoted by this browser candidate.
