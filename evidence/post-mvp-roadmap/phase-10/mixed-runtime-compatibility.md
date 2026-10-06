# Phase 10 — compatibility during a running release

The accepted Native process on 8026 continues running its original loaded Python modules. Shared static files changed during Phase 10 development. A read-only release check discovered that an unconditional import of the new shot module received HTTP404 from that old process and prevented Native bootstrap on reload. This temporary regression was corrected before the implementation handoff.

The new server advertises strict boolean `capabilities.native_shot_studio` and `capabilities.production_intelligence` in the existing `/api/session` response. Native loads the new CSS/module only after the advertised capability. Without it, the original workspace and all original controls remain in place. Content Intelligence keeps the original Phase9 approval route and avoids all `/api/production` preflight requests. Capability advertising neither grants authority nor replaces cookie/CSRF boundaries.

Actual browser verification on 8026 after correction: original workspace grid visible; New Project and Render controls enabled for the current approved Phase8 project; accepted final MP4 loaded at1080x1920/readyState4; new module/style/navigation absent; no browser console errors. Original Content Intelligence research and saved findings/ideas/brief loaded, new preflight hidden, New Content enabled, no console errors. No live edits, approval, provider call, or process interruption occurred.

Actual browser verification on8030 after an idle restart of the agent-owned UAT process: four stages and five stable shots loaded; saved project revision6/canonical timelinev5 persisted; cached visual proxy loaded at540x960/readyState4; no browser console errors. The two session capabilities were true. No new TTS or final render was dispatched.

Evidence: `screenshots/main-8026-legacy-compatible.jpg`, `screenshots/main-8026-intelligence-compatible.jpg`, `technical-browser-receipt.json`, `final-preservation-verification.json`. Runtime bootstrap tests cover absent/false/nonboolean capabilities and zero legacy production preflight requests. The real HTTP session test covers strict flags, cookies, CSRF, cross-site/host rejection and unchanged project tables.

Deployment: Phase10 is served separately on8030 against `C:/NPD-Video-Factory/phase10-uat`. A future normal planned restart of8026 can load Phase10 backend code; this task does not claim that the accepted live process has already been upgraded. Existing Phase8/9 functionality stays available during the current run.
