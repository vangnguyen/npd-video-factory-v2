# Phase 10 shot edit acceptance — draft

As of 2026-10-06T13:08:28.908445+00:00. Implementation HEAD `b8d8e646f38bbdf81553e32a68f2cf923ed2e2e2`. This is actual technical evidence from the new campaign projects on the isolated Native Studio at port 8030. It is not personal Owner watch/listen acceptance. The accepted Phase 8/9 projects on port 8026 were not edited by this audit.

All five required edit types are proven; narration was edited in case 01 and also repaired in case 04. Three real `gpt-6-luna` proposals were explicitly applied under the delegated task authority. One AI edit was reverted through a new saved revision. All thirteen before/after comparisons pass canonical projection, stable-ID, lineage, approval invalidation and immutable history checks.

| Case | Required action and actual result | Project revision / canonical version | Technical state |
|---|---|---|---|
| 01 | Replace first-shot image, `e46d8d10cd0748f6a55576d4ee1ab394.jpg` → `35f6439f4f384ae0a306efcf07b804fb.jpg` | r14 → r15 / v0 → v1 | PASS |
| 02 | First-shot requested duration set from an estimated 7.5 s to explicit 9.5 s; four following timestamps move | r13 → r14 / v0 → v1 | PASS |
| 04 | Swap third and fourth shots, preserving each stable ID and its content | r13 → r14 / v0 → v1 | PASS |
| 01 | Manually edit first-shot narration; default subtitle follows it; asset is unchanged | r17 → r18 / v3 → v4 | PASS |
| 08 | Regenerate selects an alternate existing asset, `1e04096ed48e49d2b455bbb06e3f329f.jpg` → `11a1db038ac245c6b75659d603bb2ff5.jpg` | r13 → r14 / v0 → v1 | PASS; deterministic existing-media selection |

“Regenerate” here selects a stored candidate. It does not generate a new image or video with an AI provider. Explicit duration is a requested visual schedule. [Case 02 actual-runtime proof](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/videos/20261006T125947862870Z-execution-f98ab8db/case02-requested-duration-actual-runtime.json) confirms shot 1 exports exactly 9.0 seconds and shot 2 starts at 9.0. The full draft estimate is 46.5 seconds; the measured final is 45.0 seconds. Actual speech samples remain at speed 1 with no pitch change; the final scene holds to the configured target after speech.

## Real AI commands, apply and undo

| Case | Provider response ID | Applied field | Actual saved state |
|---|---|---|---|
| 01 | `resp_0bb36f7b0f4e8201016ac4e875b40c87d0b4b974d15f82f2b2` | Heading `Lời kỳ vọng hay dữ kiện?` → `Kỳ vọng hay dữ kiện?` | r15 → r16 / v1 → v2 |
| 02 | `resp_06153544f245e2e1016ac4e903edc487d0b20476873c2aac5f` | Requested duration 9.5 s → 9.0 s | r14 → r15 / v1 → v2 |
| 08 | `resp_0d7466eb602082aa016ac4e9d0d4c887d0b0feb4a4bc765420` | Existing asset `11a1db038ac245c6b75659d603bb2ff5.jpg` → `14d69c8121ad48558f33125e3ebc47f0.jpg` | r14 → r15 / v1 → v2 |

The aggregate binds each exact request key, context digest, input project revision, input timeline digest, original provider response bytes/usage, proposed values, explicit applied values and the persisted scope event. Each new command made one actual provider call with zero retries. The audit made zero provider calls. Prior proposals from the technical clone are excluded. These commands generated suggestions; they did not generate media, verify facts or dispatch a render.

For case 01, reverting the heading creates r17 / v3. Its canonical content SHA `59bfdbea8085984923b8394dbcec2239db469ad1a5b7e669b0f5d303e7a3a7fc` equals the after-replacement r15 state. The replacement image stays selected. Earlier versions and events remain intact, and an old production approval is not restored by undo.

## Scope, cache and approvals

Narration repair in case 01 changes “Hãy đọc đúng phạm vi của một phát biểu.” to “Hãy kiểm tra nguồn.” The case 04 second shot replaces the English onset “Bài Kick-Off Vinhomes Sài Gòn Park” with “Bài viết về sự kiện khởi động dự án”. Both actual UI saves change only narration and its matching default subtitle, preserve all assets and research lineage, stale the prior script review and clear production approval. Voice dependencies include the changed shot plus the next enabled shot because its warm-context input changed. Further actual UI narration repairs set case 06 shot 4 to “Thông tin trong bài nói về quý một năm hai nghìn không trăm hai mươi sáu, chưa xác nhận thị trường hiện tại.” (r13 → r14 / v0 → v1), and case 08 shot 5 to “Bạn có thể đọc bài gốc và gửi câu hỏi cần đối chiếu.” (r15 → r16 / v2 → v3). Both matching subtitles follow the narration; all assets and research lineage stay exact. Case 06 voice scope is shots 4–5, with shots 1–3 eligible for reuse; case 08 voice scope is shot 5, with shots 1–4 eligible for reuse. Final actual voice metadata confirms these exact recompute/reuse results: case 06 fresh 2/reused 3 and case 08 fresh 1/reused 4. All four narration saves stale the prior script review and invalidate production approval. The final case 08 CTA is “Gửi câu hỏi để cùng đối chiếu bài gốc.” (r16 → r17 / v3 → v4). This thirteenth save changes only the last-shot narration and matching subtitle, keeps all media and lineage, and invalidates only shot 5 voice dependency. These are saved text corrections, not an auditory PASS.

All saves invalidate the exact current production approval and mark the preview stale. Image/heading changes affect only the selected visual shot, with zero voice dependencies. The duration edit retimes the four subsequent shots and changes one visual proxy. Reordering preserves all visual shot content, so five visual proxies can be reused; voice dependencies include the moved third/fourth shots and the next shot because the certified voice recipe depends on ordinal and preceding narration. Saving or applying these edits dispatches no TTS or full render.

| Actual READY preview | Revision / timeline version | Reused proxies | New proxies |
|---|---|---:|---:|
| 01 AI heading applied | r16 / v2 | 4 | 1 |
| 02 AI duration applied | r15 / v2 | 4 | 1 |
| 04 reordered | r14 / v1 | 5 | 0 |
| 08 AI asset applied | r15 / v2 | 4 | 1 |

The original baseline previews each built five new proxies. The listed previews are exact historical READY revisions, not a claim that every latest revision is previewed. Every listed READY receipt has a byte-exact preview MP4 hash, five completed shots, zero provider/TTS calls, `silent_visual_proxy` audio mode and `final_approval_eligible = false`. Case 01 r17, later r18, and case 04 r15 were STALE at their edit snapshots; inherited counters from earlier revisions are not evidence of a READY current preview.

The immutable job records, prior asset metadata and research lineage are exact before/after every recorded edit. Canonical proposal/media/edit-plan projections remain consistent with the served shot view and read-only SQLite snapshots. This report verifies those records; accepted source artifact byte preservation is documented separately in the regression preservation evidence.

## Evidence and open acceptance

- [Current append-only action matrix](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/action-matrix-v4.json): 13 operations, 13/13 independently recomputed comparisons PASS; 5/5 required edit types complete. The [10-operation receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/action-matrix-v2.json) is also retained unchanged. The [initial 4/5 receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/action-matrix.json) is retained unchanged.
- [Actual isolated Studio restart](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/restart-persistence-v1.json): five before/after document, canonical shot, revision, lineage and version-history checks PASS.
- [AI apply proof aggregate](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/ai-edit-proof/20261006T124023763202Z-8205a6bc/aggregate.json): 3/3 actual provider proposals and saved applies PASS, original JSON receipts copied byte-exact, case 01 undo proof and 8 READY preview receipts.
- [Campaign draft](C:/NPD-Video-Factory/source/PHASE10_REAL_CAMPAIGN_UAT.md): actual candidate, selection and new-script provenance.
- Current regression: [231/231 Native PASS](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/tests/20261006T124519873582Z-native-boundary-suite-6d026ab4/summary.json) and [56/56 Studio PASS](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/regression/studio-frontend-tests.log); temporary tests are not campaign production acceptance. Earlier 228/228 Native results are retained as history.

Five projects were read through the actual authenticated API and read-only database before and after the isolated 8030 restart: revisions 18/15/15/13/15 and timeline versions 4/2/2/0/2 are unchanged, with exact document/canonical/lineage and version-history digests. Root delegated reapproval and job enqueue occurred after startup during the capture; those additional stored events are recorded explicitly, so approvals/jobs are not falsely described as unchanged. Main 8026 was not touched by this audit. This actual restart proof precedes the later case 06/08 narration edits; it does not claim those later edits survived a second server restart.

The five selected queue plans were aligned through the existing planning API with the actual production template format and configured duration: 01/02/06 portrait 45 seconds, 04 landscape 45 seconds, 08 landscape 60 seconds. The [metadata correction receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/queue/20261006T125118334107Z-execution-2e1a496a/planning-format-alignment.json) records all five project revisions preserved. Planning metadata updates do not alter their approved documents or active render snapshots.

All five latest renders now pass actual video-verifier checks against their current approved project and canonical shot snapshot. Raw source WAVs, provider timing evidence, trim PCM, separate sample-preserving render voice, manifest, final MP4, canvas, duration and research lineage are bound to the current revision. Current-attempt fresh/reused voice counts are 01: 2/3, 02: 0/5, 04: 2/3, 06: 2/3, 08: 1/4; these distinguish current attempt work from the five total source scenes in each film.

The [final actual restart receipt](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/shot-edits/restart-persistence-v2.json) proves all five latest documents, canonical versions, complete version/event history, approvals and job records unchanged after the final isolated8030 restart. No new jobs or human final decisions were created; each current MP4 remained accessible through actual HTTP200 byte-exact and range206 first-1024-byte checks. Current queue states are five VIDEO_REVIEW and zero PRODUCED.

[Owner review bundle](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/videos/owner-review-bundle.md) and [machine current manifest](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-10/final-uat/videos/owner-review-current-manifest.json) identify the exact five current files, full scripts, sources, warnings and pending personal Owner decisions. Codex delegated preparation is recorded separately from personal Owner review. No new campaign video is certified by this report, and no Owner watch/listen decision is inferred.

PHASE10_SHOT_EDIT_TECHNICAL_ACCEPTANCE = PASS
PHASE10_SHOT_EDIT_ACCEPTANCE = OWNER_REVIEW_PENDING
HUMAN_WATCH_LISTEN_ACCEPTANCE = PENDING
