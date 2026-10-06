# Milestone 02 — canonical shots, previews and production planning

MILESTONE: Phase 10C–10G / 10K–10S backend implementation

STATUS: Technical implementation PASS; human campaign UAT remains pending.

HEAD SHA: Parent 84b39f5. This receipt accompanies the next progressive backend commit; use its containing Git commit as the exact implementation marker.

UI CHANGES: Four-stage Studio and planning screens implemented in working tree; separate UI milestone follows browser verification.

BACKEND CHANGES: Native TimelineSnapshot 1.1 persisted in the existing project document with atomic legacy projections; stable shot IDs, scoped mutations/history/revert; version-bound cached silent visual proxies with progress/cancel; existing-provider AI suggestions with explicit apply; sample-preserving narration placement; landscape templates; additive planning store, unified queue, source dates/freshness, lexical similarity with human override, configured heuristic priority, explicit script/storyboard batches with durable receipts, historical approved video library.

TESTS: Complete Native suite 214/214 PASS in 92.584s (`native-regression.log`); dedicated shot adapter 22/22 and shot-production 12/12 are included. The latter executes FFmpeg portrait/landscape rendering and preview/caching/cancel/concurrency checks with synthetic PCM. Provider-dependent check separately made one actual OpenAI suggestion using the existing credential, no retries, no apply or production dispatch (`provider-check.json`). Synthetic fixtures are not provider acceptance or human UAT.

SCREENSHOTS: Studio 1366×768, 1920×1080 and production queue captures under `screenshots`; final viewport review follows UI refinement.

EVIDENCE: `baseline.json`, `uat-preparation.json`, `provider-check.json`, `preservation-verification.json`, `native-regression.log`.

REGRESSIONS: Read-only live workflow/intelligence table digests match the frozen baseline; all 1,596 Phase 8/9 evidence files and 15 certified final video hashes match. Runtime dependencies unchanged. A fresh Python process validates persisted canonical timeline v4 in the isolated technical clone.

BLOCKERS: Phase 10Y requires the human to complete the actual campaign and five shot actions. Those have not been performed by the Owner. Main accepted service has not been interrupted; new implementation runs separately on 8030 for UAT.

NEXT ACTION: Finish Studio/browser/security verification, commit UI, deliver concrete campaign guide for human use and approval.
