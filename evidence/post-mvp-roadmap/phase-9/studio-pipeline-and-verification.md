# Phase 9F–9K implementation and acceptance checkpoint

This checkpoint separates implemented capabilities, actual provider evidence, technical fixtures and outstanding human acceptance. Phase 8 acceptance applies only to its original ten videos.

PHASE: 9F — HUMAN IDEA REVIEW

STATUS: PASS for the implemented Studio workflow. Practical human choices and brief approvals are PENDING.

HEAD SHA: `fc986b00ddab0dd4ab7003da4b4f48c2d57b4db8` (validated application code; subsequent evidence commits do not change it).

FILES CHANGED: `apps/studio-web/intelligence.html`, `intelligence.mjs`, `native.html`, `native.mjs`, `tests/intelligence.test.mjs`; `services/windows_native/intelligence_routes.py`, `intelligence_service.py`, `server.py`; native intelligence workflow/HTTP tests and evidence helpers.

TESTS: 126/126 native tests and 31/31 Studio tests PASS. Browser verification shows the actual five ranked candidates and retained findings. An isolated, explicitly labeled fixture exercised selection, switching, editing, rejection, brief approval, approval invalidation after editing, reapproval and the existing Studio handoff. These fixture decisions are not Owner acceptance. HTTP tests enforce local session, same origin and CSRF boundaries.

EVIDENCE: `native-tests-final.log`, `studio-tests.log`, `http-tests-fixed.log`, `content-intelligence-ranked-ideas.png`, `content-intelligence-final-runtime.png`, `ui-fixture-approved-brief.png`, `ui-fixture-native-handoff.png`.

NEW CAPABILITIES: Source/query input → findings → five candidates → transparent ranking → named human selection/edit/reject/regeneration → editable brief → explicit brief approval → explicit production handoff. Unstored edits and stale versions block approval. Regeneration and candidate switching invalidate previous brief approval. Research history and prior candidates remain retained.

REGRESSIONS: All 103 original native and 27 original Studio checks remain within the passing suites. Existing data, Phase 8 evidence and its ten accepted MP4 bytes remain unchanged before and after the final runtime restart.

BLOCKERS: Actual editorial selection and brief approval await the Owner. No real Phase 9 brief has been approved or dispatched by Codex.

NEXT ACTION: Owner reviews the immutable ten-case bundle or makes choices in Studio. Apply only those actual decisions, then prepare new scripts for separate review.

---

PHASE: 9G — EXISTING PRODUCTION PIPELINE CONNECTION

STATUS: Implemented; isolated research-to-MP4 contract PASS. Practical production acceptance is PENDING.

HEAD SHA: `fc986b00ddab0dd4ab7003da4b4f48c2d57b4db8`.

FILES CHANGED: `services/windows_native/intelligence_lineage.py`, `intelligence_service.py`, `store.py`, `pipeline.py`, `editor.py`; `scripts/native-intelligence-render-contract.py`; integration/provenance tests.

TESTS: Approved fixture brief creates one idempotent native project with an unapproved script state and no TTS/render dispatch. Existing content jobs, script review, storyboard/editor, render, QC and final review are reused. A real FFmpeg MP4 passed all eleven existing QC checks, preserved source/idea/brief lineage in project/job/canonical timeline and reopened with exact hashes in a fresh process. Final download and queue status were also tested with explicit fixture final-review decisions. The isolated scenario reused accepted voice audio and used fixture providers/decisions; it made zero new provider or TTS inference calls and counts as zero practical productions.

EVIDENCE: `render-contract-fixed.log`, `render-contract.json`, `render-contract-final-review.json`; actual fixture MP4 at `C:\NPD-Video-Factory\post-mvp-validation\phase9-render-contract-20261006-repair1\jobs\b48195bc3e41483780a5973593648297\final.mp4`, SHA256 `e2315022fe6951f988cda17ae4d1f5b7cde7b6a731f62723ad43b19260b9e909`. The initial harness failure is preserved in `render-contract.log`; it was a fixture setup error, not a production-provider PASS.

NEW CAPABILITIES: Frozen research → selected idea → exact approved brief → native script/storyboard/timeline/render lineage, with reference IDs and source-content hashes. No second production pipeline. Corrupted or stale provenance is refused.

REGRESSIONS: Existing job contracts, human script review, locked voice preset, render/QC and final approval remain in effect. Accepted production data and artifact hashes match the freeze.

BLOCKERS: At least five real, human-selected Phase 9 ideas must enter production. New scripts, media and final videos require their own actual human decisions.

NEXT ACTION: After brief approval, use native script generation, prepare inspectable scripts/media and request their required review before voice/render.

---

PHASE: 9I — CONTENT OPPORTUNITY QUEUE

STATUS: PASS for implemented queue and tested transitions; practical items await selection.

HEAD SHA: `fc986b00ddab0dd4ab7003da4b4f48c2d57b4db8`.

FILES CHANGED: `services/windows_native/intelligence_models.py`, `intelligence_service.py`, `intelligence_routes.py`; Studio intelligence page/module and workflow tests.

TESTS: NEW, REVIEWING, APPROVED, REJECTED, IN_PRODUCTION and PRODUCED transitions exercised. PRODUCED requires the existing accepted-final-video/hash guard; a succeeded render alone remains IN_PRODUCTION. Repeated handoff returns the same native project. Invalid/stale/rejected/unsaved actions are refused.

EVIDENCE: `native-tests-final.log`, `render-contract-final-review.json`, actual Studio screenshots, `practical-cases.json`.

NEW CAPABILITIES: Filterable queue with topic, configured project, reason now, source freshness, heuristic opportunity score, suggested hook, candidate format and status. Source updates are editorial signals, not measured market popularity or social velocity.

REGRESSIONS: Existing production dashboard/projects are preserved; intelligence persistence is separate and additive.

BLOCKERS: No actual Phase 9 queue item has an approved production handoff yet.

NEXT ACTION: Record real human selection/approval and track the same item through native production.

---

PHASE: 9J — TESTS AND REGRESSION VERIFICATION

STATUS: PASS for the implemented technical scope. Provider evidence and practical acceptance remain separately classified.

HEAD SHA: `fc986b00ddab0dd4ab7003da4b4f48c2d57b4db8`.

FILES CHANGED: Four `services/windows_native/tests/test_intelligence_*.py` modules; `apps/studio-web/tests/intelligence.test.mjs`; render/UI/release verification helpers; test, restart, source-integrity and actual-provider evidence.

TESTS: Native 126/126 = 103 existing + 23 intelligence tests; Studio 31/31 = 27 existing + 4 intelligence tests. Coverage includes models, quote grounding, reference validation, configurable ranking/risk, persistence/history integrity, separate-process reopening, restart with no unknown-outcome replay, idempotency, stale versions, source tampering, failed retrieval/provider results, brief approval invalidation, provenance and HTTP boundaries. Actual public-source retrieval and thirteen acknowledged responses from the already configured OpenAI provider produced ten valid five-candidate results; three actual responses with invalid references were rejected and retained. They were followed only by explicit new generation operations after a known completed response, never silent replay or fabricated results.

EVIDENCE: `native-tests-final.log`, `studio-tests.log`, `source-storage-compatibility-tests.log`, `ten-case-source-integrity.json`, `actual-provider-ledger.json`, `intelligence-persistence.json`, `final-runtime-before-restart.json`, `final-runtime-after-restart.json`, `final-runtime-restart.json`, `final-runtime-restart-verification.json`, isolated MP4 evidence.

NEW CAPABILITIES: Repeatable release/restart read-only verification; legacy Windows newline capture is accepted only when reconstructing the original retained-content hash succeeds. New captures use exact UTF-8 bytes. No original source, finding, receipt or human-review preview was rewritten for compatibility.

REGRESSIONS: None found in the certified Windows Native scope. Native tables/schema/rows, installed runtime versions, all accepted Phase 8 evidence and ten video bytes match the frozen baseline. Intelligence tables also match across the actual final server restart. Legacy Docker/RC28 tests were outside the accepted Native release and were not reopened or claimed PASS.

BLOCKERS: The fixture MP4 is technical evidence only. Fresh-provider script/TTS production for the five practical choices and real human acceptance remain pending.

NEXT ACTION: Complete the practical acceptance gates; repeat only checks affected by any subsequent implementation change.

---

PHASE: 9K — PRACTICAL ACCEPTANCE

STATUS: WAITING_FOR_HUMAN_REVIEW. Ten actual research cases and fifty ranked candidate ideas are ready; this phase has not PASSED.

HEAD SHA: `fc986b00ddab0dd4ab7003da4b4f48c2d57b4db8`.

FILES CHANGED: Configured ten-case inputs; `case-01.json` through `case-10.json`; retained failure/invalid-response evidence; `practical-cases.json`, `actual-provider-ledger.json`, immutable review bundle/manifest and screenshots.

TESTS: All ten actual cases retain sources and exact quotations and have five validated/scored candidates. Source-integrity checks PASS for all ten. Mix: three Green Paradise, two Saigon Park, two Vang Nguyễn, three Vietnam property/news. Each case includes seven requested evaluation dimensions, explicitly labeled Codex editorial assessment rather than human acceptance. Current real human selections = 0; brief approvals = 0; practical production handoffs = 0/5; human practical acceptance = PENDING for 10/10.

EVIDENCE: `idea-brief-review-bundle.md` SHA256 `1ac01b244e396e3d53f76197b1c475e134275fd2c605463981fc3048ba5872e4`; `idea-brief-review-manifest.json` SHA256 `32e0ad2b4052d77ca46e833dd23d8bd462868d8ece8104ad19bca13ffe63a19e`; per-case artifacts; actual retained sources/requests/responses under `C:\NPD-Video-Factory\phase2`. Suggested cases 01, 02, 04, 06 and 08 each have a concrete rank-1 brief preview frozen in that manifest. They are proposals, not automatic selections.

NEW CAPABILITIES: A reviewable practical dataset and evidence-bound brief previews for the Owner, alongside the live Studio workflow at `http://127.0.0.1:8026/intelligence`.

REGRESSIONS: Phase 8 acceptance remains valid and unchanged; it does not approve these new topics, scripts or videos.

BLOCKERS: The Owner must select/edit/reject the new ideas, approve at least five exact briefs, review their generated scripts/media, and accept final results. None of those human decisions may be fabricated or inferred from Phase 8 approval.

NEXT ACTION: Await the pending concrete Owner review request while preserving its bundle, manifest, current versions and source evidence. Continue the existing pipeline once those actual decisions arrive.

CONTENT_INTELLIGENCE_READY = NO
