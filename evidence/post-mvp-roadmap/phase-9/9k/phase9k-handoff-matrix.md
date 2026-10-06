# Phase 9K — Real handoff matrix

PHASE: 9K — Content Intelligence practical acceptance, five real videos checkpoint

STATUS: PHASE9K_FINAL_HUMAN_WATCH_LISTEN_REVIEW_REQUIRED; brief/script/media approvals and actual new videos 5/5, final human acceptance 0/5

HEAD SHA: `a44bb0dd234e4c620dd394d18e7a9112be62f988` for production/evidence checkpoint. Tested running application: `9ce137afa8ac62fdb8ce5b35fbba997013adfef3`. The following report-only commit is recorded separately in Git history.

FILES CHANGED: optional Native approval review_reference with two additional tests, approved-production/acceptance helpers, actual Owner media receipts, 25 Native asset imports/snapshots, five new MP4/ffprobe/QC/voice/subtitle/timeline manifests, 25 sampled actual frames, persistence/HTTP/visual evidence and current reports. No Phase 8 evidence changed.

TESTS: 134/134 Native and 32/32 Studio PASS; Studio unchanged after its run. Five actual jobs have 11/11 QC, artifact/source/lineage integrity and fresh-process persistence PASS. Five live MP4/range-seek/final-approval guards PASS. Main-service restart after render was policy-blocked before execution; prior actual restart remains separately recorded.

EVIDENCE: frozen brief/script/storyboard review bundles remain unchanged. New `owner-media-decision.txt`, `owner-media-authorization.json`, `production-approval-manifest.json`, `real-production-jobs.json`, `actual-production-verification.json`, `real-video-fresh-process-reopen.json`, `actual-video-preview-http-verification.json`, `actual-video-visual-review.json`, `final-video-review-bundle.md`, `final-video-review-manifest.json`, `actual-videos-native-studio.png` and five actual output directories.

NEW CAPABILITIES: exact human chat approvals now retain honest source/reference metadata in existing Native approval; reviewed original assets enter the existing editor, with unchanged narration/voice preset. Five intelligence-origin previews trace research → idea → brief → script → assets → render. Actual TTS: 43 fresh local calls, network blocked, speed 1, 0 retries; no paid provider calls this production step.

REGRESSIONS: none observed in the accepted Windows Native scope. All existing production rows preserved, including the earlier Owner-created IHG project. Nineteen records of its original research run remain unchanged. Ten accepted MP4s and all Phase 8 evidence match the release baseline. Dependencies unchanged.

BLOCKERS: five explicit human watch/listen decisions for exact MP4s. Cases 02/04/06 are below requested duration targets; Owner must accept measured duration or request revision. No credentials/provider blocker. Post-render main-service restart was not performed because the tool rejected stopping/restarting the service; fresh-process persistence PASS is recorded separately.

NEXT ACTION: return the five completed MP4s for Owner watch/listen; record actual decisions before final-download/queue PRODUCED/readiness. No publishing.

## Production candidates

All rows are actual projects in `C:\NPD-Video-Factory\phase2\workflow.sqlite3`, with actual intelligence records in `intelligence.sqlite3`. One real OpenAI `gpt-6-luna` script response per case is retained. All v2 revisions were made with the existing native draft-save operation; no additional provider requests were made.

| Case | Brief decision | Score after approved idea edits | Handoff | Script | Owner script approval | TTS/render | New MP4 |
|---|---|---:|---|---|---|---|---|
| 01 — IHG × Green Paradise | APPROVE_WITH_EDIT | 53.330 | REAL_NATIVE_PROJECT | v2, native revision 9 | OWNER_APPROVED | REAL_SUCCEEDED | 34.17s |
| 02 — Smart-city certification | APPROVE_WITH_EDIT | 54.389 | REAL_NATIVE_PROJECT | v2, native revision 9 | OWNER_APPROVED | REAL_SUCCEEDED | 40.47s; below 45–60s target |
| 04 — Saigon Park buyer education | APPROVE_WITH_EDIT | 53.256 | REAL_NATIVE_PROJECT | v2, native revision 9 | OWNER_APPROVED | REAL_SUCCEEDED | 36.04s; below 45s target |
| 06 — Vang Nguyễn/date context | APPROVE | 64.971 | REAL_NATIVE_PROJECT | v2, native revision 9 | OWNER_APPROVED | REAL_SUCCEEDED | 36.74s; below 45s target |
| 08 — Vietnam Q2/2026 | APPROVE | 83.996 | REAL_NATIVE_PROJECT | v2, native revision 9 | OWNER_APPROVED | REAL_SUCCEEDED | 47.23s |

Scores are **HEURISTIC_SCORING**, with all components, configured weights and rationales in `idea.json`. Rank #1 selection happened before the requested editorial changes/rescoring; these scores are not performance predictions.

## Stable identity chain

| Case | ResearchRun ID | ContentIdea ID | Approved ContentBrief ID/version |
|---|---|---|---|
| 01 | `90f6da5bade74fbeb437fb982bd9f973` | `3ebbe98f7e994621afc9430d4ebcd6ac` | `7656c589693943fc8e1cf756d753a6cd` v3 |
| 02 | `3ea3ddd8a0fc4ae997a9fbb147d077cc` | `0e3b2a2b48414e70b0eaff0078891ad4` | `60f72f0db7034e7cbb83e56756cd8ae6` v3 |
| 04 | `7223aa771b5045248126b7db4c6ee785` | `b0ca213241d34a21aa7b503e509d939f` | `4d1bbbc0d16d4a9d9426954d38f686d7` v3 |
| 06 | `3a15587370a246bb91d58de4359a1423` | `05c431bf5c7e4f37a8660056484e539e` | `44a5dded97c147b6807b67373ddfa3d2` v3 |
| 08 | `66c54e6139834042a15d61f59e60f13d` | `205ec970353c43639e0aa6b3e600e9f3` | `42cf14d3e0c14d97ac1ffcf99c164b8a` v3 |

| Case | Native project ID | Actual native script job ID | v2 narration SHA256 |
|---|---|---|---|
| 01 | `afcd9b5d5ee45e3dac2c209bba6cfd8f` | `98237d9c8431410baec55f2976883810` | `eac7f17bbe9dfe4f06d7f4524fae97fa90e20b90fda708586197233cee028a16` |
| 02 | `09d719f2a8b9598992082278b9da8321` | `7ba126bea10746059b030146def393ea` | `522d799fe35223c01ffc1671236512e880da9f455d2c4c8d7dbd6132257ac270` |
| 04 | `817c42e9459b51cbaf5c83999b221df0` | `608fcf0e79d54bbc8e06513e622a7797` | `29e2ac570d3caaa78a395554e19ea331401d93611cc85402660d1a0340477dbb` |
| 06 | `c5a3b3a6e6045af88d57f08aa425905c` | `83dc590fd7d04fa9b73f5ff5b0f5663b` | `3b69f1c2037d5ac800806990176ae858505df3dc5c8ccd3d6b83ae6896559f33` |
| 08 | `df21ef39df655f88865bee6563cf23cb` | `c5b1ae812d134fc99ffbdac8665bbd82` | `e271916f45124e4302ef47badce7d0902526022d59d8fe2b98a179f8524f727a` |

Full source/finding references, score, versions and provenance are in `research.json`, `idea.json`, `brief.json`, `handoff.json`, and `script-v1.json`/`script-v2.json`. The original provider proposal remains in v1 and the actual job result; v2 labels Codex editorial changes and retains its v1 reference. Owner storyboard/media approval is stored separately with exact assets and snapshots. Original reviewed plans are archived byte-exact; current plans additionally record actual timing/job hashes.

| Case | Actual render job ID | Actual final MP4 SHA256 |
|---|---|---|
| 01 | `a847230bfb32426084666e581b8386c9` | `7008dbdd74bea6240d71cff591a3504d7c91e8625ef74abba2c084571931bff0` |
| 02 | `80e06f058bdb4b4a88fac71ace8240e9` | `326bb7d4fc899de33f9d43b16c77754251628a6b6403ab3a602703dadd9cc624` |
| 04 | `e500f4700c6b476c8b1db1dd5c774b58` | `c37a207cdc070210f52119676c4d577076c0d52b758dc3983637f7f16dd2bfc7` |
| 06 | `4ef0f02df38d4fa882805f38d6b56992` | `92d95e9d9c065e07a8438ae0f3c28303c2b754e061625b73213a45b36fc1bf5f` |
| 08 | `8972ad4cf0df4b3bb766d5aac3608854` | `3c9d38ca44fab1c7721da59609d05c76c1f238a273e15f959d1acc89ad809fee` |

All five final human review records remain empty; Opportunity Queue remains IN_PRODUCTION. The old Phase 8 MP4s and fixture render contribute zero products to this table.

## Case 01 preservation and rank resolution

The old review manifest pointed to generation 1 idea `dc3f7bc714e2413189c83580bb092c30`. Before this task, Owner regenerated in Studio and selected another generation 2 idea, approved brief `509678f5d09c46cdab6a3f51f06f168d`, and imported it into production. That earlier project was locked against brief replacement.

The latest Rank #1 directive was resolved to current generation 2 rank #1 `26402b74c99b4d6d9c9d331db58da792`. A new retained-research run/candidate set with explicit original IDs and provenance preserves the earlier imported project, its approval and all history. The fork performs zero source-retrieval or idea-provider requests and retains the original source timestamps and hashes. The new case 01 script candidate is distinct from the preserved earlier project.

## Frozen review artifacts

Review bundle SHA256: `ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c`.

Review manifest SHA256: `061cc4579a89419217f5d1b9bbfd241039cb99c2f9a2470fe4250704a8dc65c7`.

The original Phase 9 idea/brief and script review bundles/manifests remain byte-identical. Owner's reply `Duyệt v2: 01, 02, 04, 06, 08` identifies these exact five v2 scripts. Current decisions are stored separately in native event receipts and `script-approval-manifest.json`; frozen old snapshots retain their earlier pending state. Media/production/publishing are not authorized by that script-only reply.

The later actual Owner reply `Duyệt storyboard/media: 01, 02, 04, 06, 08` authorizes the exact 25 reviewed graphics, scene options, rights and internal production. Its source/reply/hash are retained in `owner-media-authorization.json`; Native approvals retain that reference. Twenty-five assets have been imported and five real jobs succeeded. This reply does not approve final watch/listen or publishing. The old [storyboard checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-checkpoint.md) remains a historical record; [real production checkpoint](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/real-production-checkpoint.md) records current state.

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
