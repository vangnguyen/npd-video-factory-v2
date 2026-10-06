# Phase 9K — Real handoff matrix

PHASE: 9K — Content Intelligence practical acceptance, storyboard/media review checkpoint

STATUS: PHASE9K_STORYBOARD_MEDIA_REVIEW_REQUIRED; 5/5 real brief handoffs and Owner-approved v2 scripts, 25 proposed scenes, final acceptance PENDING

HEAD SHA: `cee0eabb2c301674c537145788b2c9a2f3fc864b` at checkpoint capture. Tested running application: `2980fdf16e6580fb4a9fbefb82f689cba22ea7da`. The report-only commit is recorded separately in Git history.

FILES CHANGED: native store's separate saved-script review, Studio label, three Native tests and one Studio test, script-review/storyboard/verification helpers, Owner receipts, per-case proposed plans, 25 graphics/static previews, logs and restart evidence under `9k/`. No Phase 8 evidence changed.

TESTS: 132/132 Native and 32/32 Studio PASS after the final application change. Live Studio and fresh-process reopen 5/5 PASS with durable script receipts and render disabled. Actual server restart and 25/25 graphic hash/dimension/narration/source bindings PASS.

EVIDENCE: earlier authorization/provider/script snapshots remain unchanged; current `owner-script-decision-v2.txt`, `owner-script-authorization-v2.json`, `script-approval-manifest.json`, `storyboard-media-review-bundle.md`, `storyboard-media-review/review-manifest.json`, `visual-review.json`, `storyboard-media-before-restart.json`, `storyboard-media-after-restart.json`, `script-approved-media-pending-studio.png` and each case directory.

NEW CAPABILITIES: five actual human script-only decisions bound to unchanged v2 narration/lineage, persisted in existing events and visible in Studio; production approval remains separate. Twenty-five sourced original graphics and reviewed layout proposals are ready for Owner media review. Earlier brief-duration instructions and retained-research fork are reused.

REGRESSIONS: none observed in the accepted Windows Native scope. All existing production rows preserved, including the earlier Owner-created IHG project. Nineteen records of its original research run remain unchanged. Ten accepted MP4s and all Phase 8 evidence match the release baseline. Dependencies unchanged.

BLOCKERS: Owner storyboard/media/rights approval, five actual video productions and technical/artifact/watch-listen acceptance. Five exact v2 script approvals are complete. No new credentials or paid provider required.

NEXT ACTION: return the concrete 25-scene storyboard/media bundle to Owner and stop before production. Do not enqueue TTS/render from script-only approval.

## Production candidates

All rows are actual projects in `C:\NPD-Video-Factory\phase2\workflow.sqlite3`, with actual intelligence records in `intelligence.sqlite3`. One real OpenAI `gpt-6-luna` script response per case is retained. All v2 revisions were made with the existing native draft-save operation; no additional provider requests were made.

| Case | Brief decision | Score after approved idea edits | Handoff | Script | Owner script approval | TTS/render | New MP4 |
|---|---|---:|---|---|---|---|---|
| 01 — IHG × Green Paradise | APPROVE_WITH_EDIT | 53.330 | REAL_NATIVE_PROJECT | v2, native revision 3 | OWNER_APPROVED | NOT_REQUESTED | None |
| 02 — Smart-city certification | APPROVE_WITH_EDIT | 54.389 | REAL_NATIVE_PROJECT | v2, native revision 3 | OWNER_APPROVED | NOT_REQUESTED | None |
| 04 — Saigon Park buyer education | APPROVE_WITH_EDIT | 53.256 | REAL_NATIVE_PROJECT | v2, native revision 3 | OWNER_APPROVED | NOT_REQUESTED | None |
| 06 — Vang Nguyễn/date context | APPROVE | 64.971 | REAL_NATIVE_PROJECT | v2, native revision 3 | OWNER_APPROVED | NOT_REQUESTED | None |
| 08 — Vietnam Q2/2026 | APPROVE | 83.996 | REAL_NATIVE_PROJECT | v2, native revision 3 | OWNER_APPROVED | NOT_REQUESTED | None |

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

Full source/finding references, score, versions and provenance are in `research.json`, `idea.json`, `brief.json`, `handoff.json`, and `script-v1.json`/`script-v2.json`. The original provider proposal remains in v1 and the actual job result; v2 explicitly labels Codex editorial changes and retains its v1 reference. Storyboard and media remain unapproved.

## Case 01 preservation and rank resolution

The old review manifest pointed to generation 1 idea `dc3f7bc714e2413189c83580bb092c30`. Before this task, Owner regenerated in Studio and selected another generation 2 idea, approved brief `509678f5d09c46cdab6a3f51f06f168d`, and imported it into production. That earlier project was locked against brief replacement.

The latest Rank #1 directive was resolved to current generation 2 rank #1 `26402b74c99b4d6d9c9d331db58da792`. A new retained-research run/candidate set with explicit original IDs and provenance preserves the earlier imported project, its approval and all history. The fork performs zero source-retrieval or idea-provider requests and retains the original source timestamps and hashes. The new case 01 script candidate is distinct from the preserved earlier project.

## Frozen review artifacts

Review bundle SHA256: `ba8f2a4572497fe59ece072f767d0d0a54f668304ebb090cfb9338d1bb287d1c`.

Review manifest SHA256: `061cc4579a89419217f5d1b9bbfd241039cb99c2f9a2470fe4250704a8dc65c7`.

The original Phase 9 idea/brief and script review bundles/manifests remain byte-identical. Owner's reply `Duyệt v2: 01, 02, 04, 06, 08` identifies these exact five v2 scripts. Current decisions are stored separately in native event receipts and `script-approval-manifest.json`; frozen old snapshots retain their earlier pending state. Media/production/publishing are not authorized by that script-only reply.

Each case now has five proposed graphics and scene options in `storyboard.json`, `asset-lineage.json` and `proposed-production-proposal.json`. No media has been imported into live projects yet. Full checkpoint fields, actual review IDs and visual scope are in [storyboard-media-checkpoint.md](C:/NPD-Video-Factory/source/evidence/post-mvp-roadmap/phase-9/9k/storyboard-media-checkpoint.md).

INTERNAL_PRODUCTION_READY = YES

CONTENT_INTELLIGENCE_READY = NO
