# V3-01 implementation inventory

## Current V3-01-27 acceptance-lineage checkpoint

PR #56 merged evidence-only as exact governance `main`
`c0f051c866d329544486e5e757349f0543ace980`; exact-main CI `34500843723` passed 5/5 and
the executable tree remained RC-16
`55b22f773dc108f6c51a1b52db825b1caa8e8a51`. The original RC-16 W1 lineage is retired:
Operation 1 remains consumed/failed/`REVIEW_REQUIRED` and Operation 2 remains locked.

[V3-01-27](64_V3_01_27_ACCEPTANCE_LINEAGE_IDENTITY_CONTRACT.md) is a source-only remediation
that versions the gate contract. Historical v1 bundles, operation IDs, scope hashes, receipts and
nullable ledger rows remain unchanged. New v2 gates require a canonical, hash-derived
`acceptance_lineage_id` bound to the exact RC/provider/model/capability/sequence, both operation
slots, execution-scope hash, trusted call context and durable evidence. Missing, tampered, stale or
cross-lineage identities fail before reservation.

This draft changes executable contract code and therefore requires a new RC only after separate
Owner G-08, merge and exact-main regression. It creates no RC, bundle instance, acceptance window
or runtime authority and performs 0 provider calls, 0 credential reads, 0 live reservations and
0 VND spend. ASR remains 0/2 PASS, Vision remains 2/2 PASS and Production remains `NO-GO`.

## Current RC-16 W1 quota checkpoint

The executable inventory is unchanged at RC-16
`55b22f773dc108f6c51a1b52db825b1caa8e8a51` and tree SHA-256
`5025279241fb0b55e6fa26cc850c82a1fd5e4dc9fc4e15c43f716f50441e6ecd`. Separately authorized
Operation 1 passed preflight, reached OpenAI once and received HTTP 429
`credit_balance_exhausted`. The operation is consumed/failed and `REVIEW_REQUIRED`; no transcript
or W1 quality result exists. Operation 2 remains not approved/locked. The owner's subsequent credit
replenishment report does not create runtime authority. See
[V3-01-26](63_V3_01_26_RC16_ASR_W1_QUOTA_EVIDENCE.md).

## Prior RC-16 W1 governance checkpoint

PR #54 merged the executable W1 profile path as RC-16
`55b22f773dc108f6c51a1b52db825b1caa8e8a51`; exact-main CI `34302351310` passed 5/5.
Annotated `vf-v3-01-rc16` peels to that commit and the canonical executable tree hashes to
`5025279241fb0b55e6fa26cc850c82a1fd5e4dc9fc4e15c43f716f50441e6ecd`.

At that checkpoint, the governance proposal bound the exact W1 profile SHA
`9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1`, fresh RC-16 IDs,
unchanged approved inputs and the unchanged 500/1,250 VND, 90/120-second envelope. It changes no
executable file. Bundle and runtime were disabled; both operations were unauthorized. Historical
RC-15 remained immutable. See
[62_V3_01_RC16_OPENAI_ASR_W1_GATE.md](62_V3_01_RC16_OPENAI_ASR_W1_GATE.md).

## Earlier RC-15 governance checkpoint (historical)

PR #50 merged the source-only timestamp-semantics remediation as `7d1290aacac61df98a51544731243e5e322a8644`.
Exact-head CI `34140738281` and exact-main CI `34142662132` completed successfully, 5/5 jobs.
Annotated `vf-v3-01-rc15` locks that exact executable commit; executable-tree SHA-256 is
`9fab766b285eb2db580032b914eb2ccdf474d18b3958fd218a73a22fb75701e8`.

Evidence `EV-V3-RC15-ASR-GATE-001` covers only offline revalidation of the fresh RC-15
operation IDs, unchanged two-input rights/transcript hashes and proposed 08 September 2026
14:00-18:00 UTC window. Bundle and runtime remain unmounted/disabled. The proposed governance
merge and its governance-main CI do not yet exist; dual-CI provenance remains
`PENDING_POST_MERGE`. The executable-RC CI cannot substitute for that second CI role.

RC-14 Operation 1 remains consumed/`REVIEW_REQUIRED`, actual cost unknown, with only a
500 VND conservative safety charge. Both RC-14 operation IDs and the old authority/window
are retired for live execution. RC-15 Operation 1 is `NOT APPROVED / NOT EXECUTED`;
Operation 2 is `NOT APPROVED / LOCKED`. No credential read, reservation, provider call or
spend is authorized by this proposal. Vision remains 2/2 PASS; ASR remains 0/2 and
real-provider `NOT_TESTED`; production remains `NO-GO`.

The source contract preserves only adjacent-anchored provider boundary points. It does not
fabricate duration or pass those points to interval consumers: `PositiveDurationTranscript`
continues to fail with `POSITIVE_DURATION_TRANSCRIPT_REQUIRED` when a point is present.
Provider evidence validity therefore does not establish downstream Flow A readiness.

See [56_V3_01_RC15_OPENAI_ASR_GATE.md](56_V3_01_RC15_OPENAI_ASR_GATE.md).

This inventory is a static and deterministic-test audit on base commit
`cae40eda871d0f9c7fc315229361a40032d48967`. It does not establish real-provider,
production-path or human-quality acceptance.

V3-01-01 through V3-01-17 are merged in executable RC-10
`c2b1aec2d54dd90bcb486f8a68c97746b39963aa`, tagged `vf-v3-01-rc10`. RC-3 operation 1 was
authorized, consumed once and ended `REVIEW_REQUIRED`; all RC-3 IDs are locked. RC-4 is retained
as evidence that the stale hard-coded operation allowlist failed closed. RC-5 operation 1 later
completed provider execution once, but its post-call evidence serialization failed; it is consumed
and permanently `REVIEW_REQUIRED`, while operation 2 is permanently locked. V3-01-13 is merged and
mock-tested in exact RC-6. PR #30 preserved executable RC-6 while merging its governance rebind.
The separately authorized operation 1 then stopped fail-closed before credential read, reservation,
ledger mutation or provider dispatch because the runner omitted the bundle's window-limit field.
It remains not consumed with 0 calls/0 VND; its authority is retired and operation 2 is locked.
V3-01-14 unifies the runner/bundle limits model in locked RC-7. RC-7 operation 1 later timed out
once and is consumed/`REVIEW_REQUIRED`; operation 2 is locked. V3-01-15 adds timeout-phase evidence
offline. V3-01-16 splits provider HTTP timeout at 90 seconds from the controller hard envelope at
120 seconds in locked RC-9. Fresh RC-9 IDs, scope, budget window and G-01-A/G-02-A/G-03-A records
validated offline in an unmounted bundle. PR #35 later merged that governance-only scope and its
exact-main CI passed. Separately authorized operation 1 then stopped before credential read,
reservation, ledger mutation or provider dispatch because the bootstrap conflated executable-RC CI
with governance-main CI. It remains not consumed with 0 calls/0 VND, but its authority is retired;
operation 2 is locked. V3-01-17 now supplies the canonical dual-CI provenance model and zero-call
collector in locked RC-10. Exact executable RC CI run `33527973264` passed 5/5. Governance-only PR
#37 merged at `fd78a1690a5a2fd7b07e9e7822deda834f02ea6d`; governance CI `33532594395` passed 5/5 and
dual-CI provenance proved identical executable trees. Separately authorized RC-10 Operations 1 and
2 then completed with complete structured output, usage/cost, durable-safety and secret-containment
evidence. Both are consumed/succeeded and establish 2/2 consecutive real-provider PASS for Vision,
officially closed after PR #39 merged and exact-main CI `33703619599` passed 5/5. Production-path
and quality acceptance remain absent. Governance-only PR #40 then merged as
`4c74fa18a86b29ae8324885dacc6fdbca74ad066`; exact-main CI `33706971864` passed 5/5 and the
executable tree remained unchanged, so that docs merge did not create RC-11. PR #41 subsequently
merged the V3-01-18 fail-closed ASR path as exact RC-11
`207ff9fee5557eb0976f575c9263b61d995b20a0`; exact-head CI `33711738092` and exact-main CI
`33712762815` passed. The owner selected `whisper-1` and approved the bounded G-01/G-02/G-03-ASR
parameters and exact two-input rights scope. PR #42 merged that governance bundle as
`8ad490c02c36aafe9447a3eb0766a1d1f1f122d7` without changing executable RC-11. Operation 1 has a
separate future-window owner authority; this preparation package does not execute it and Operation
2 remains locked. The offline post-run evaluator, real-media evidence shape, TTS gate design and
G-11 instruments do not promote any acceptance axis; real-provider, production-path and quality
acceptance remain absent. See
[44_V3_01_18_OPENAI_ASR_COMPATIBILITY_ADAPTER.md](44_V3_01_18_OPENAI_ASR_COMPATIBILITY_ADAPTER.md)
and [45_V3_01_RC11_OPENAI_ASR_GATE.md](45_V3_01_RC11_OPENAI_ASR_GATE.md).

PR #43 subsequently merged the offline evaluator/TTS/G-11 preparation as governance/tests only at
`090f9085ccccf8ef30b926d7cc04a6c8a402128e`. The separately authorized RC-11 ASR Operation 1 then
stopped before credential, reservation and provider dispatch because the durable controller used
the legacy singular rights field against the two-asset ASR gate. It remains `BLOCKED_PRE_CALL`, not
consumed, with ledger `0|0|0|0`; its authority is retired and Operation 2 is locked. V3-01-20 now
uses one exact asset-ID/hash rights selector in both non-durable and durable controllers. This
source/mock remediation merged in PR #44 as exact RC-12
`ca5483c889742c27af3368b9b487350d7daa217d`; exact-main CI `33889772222` passed 5/5 and annotated
`vf-v3-01-rc12` peels to that commit. A fresh unmounted RC-12 ASR bundle binds new operation IDs and
the unchanged approved inputs, but neither operation has runtime authority. This does not execute
ASR or promote its real-provider axis. See
[49_V3_01_20_DURABLE_MULTI_ASSET_RIGHTS_BINDING.md](49_V3_01_20_DURABLE_MULTI_ASSET_RIGHTS_BINDING.md).

PR #45 then merged the RC-12 governance scope as `f765f216f90b0d05071cc7c873a2edb6d5bdcec4`.
Under a separate one-operation authority, RC-12 Operation 1 reached one provider response but
failed strict response validation. It is consumed/failed/`REVIEW_REQUIRED`; the exact mismatch,
transcript, usage and actual cost were not retained and are not reconstructed. V3-01-21 adds
value-free validation paths and allowlisted response-shape diagnostics plus correct credential-alias
scanner semantics. This is source/mock remediation only; Operation 2 is retired and ASR
real-provider remains `NOT_TESTED`. See
[51_V3_01_21_ASR_RESPONSE_DIAGNOSTICS.md](51_V3_01_21_ASR_RESPONSE_DIAGNOSTICS.md).

PR #46 merged that executable remediation as exact RC-13
`1e0146b44b19a5afcef267132d71d36d24a952e4`; exact-head CI `33974602125` and exact-main CI
`33976046393` passed 5/5. The strict provider response schema is unchanged. The RC-13 governance
proposal revalidates the same two WAVs, transcripts and RightsRecords under fresh operation IDs,
scope hash and window, but remains unmounted and has no operation authority. See
[52_V3_01_RC13_OPENAI_ASR_GATE.md](52_V3_01_RC13_OPENAI_ASR_GATE.md).

PR #47 merged that governance scope as `b41ed673bc343e33092a3d91253045729b663c7c`. Under a separate
bounded authority, RC-13 ASR Operation 1 reached OpenAI once and received HTTP 200 with 17 segments
and 412 words. Twenty-seven word objects failed the strict RC-13 `end <= start` model rule. The
operation is consumed/`REVIEW_REQUIRED`, actual cost is unknown and Operation 2 is locked/retired.
V3-01-22 adds deterministic pre-mapping classification and representation-preserving timestamp
canonicalization for future responses. Historical values were not retained, so their exact split is
left unknown and no accepted transcript is reconstructed. See
[53_V3_01_22_ASR_TIMESTAMP_CANONICALIZATION.md](53_V3_01_22_ASR_TIMESTAMP_CANONICALIZATION.md).

PR #48 merged V3-01-22 as exact RC-14
`0b0965c650f4d06a057acbbb1a7ed9d7b933478b`; exact-head CI `34041347519` and exact-main CI
`34042079905` passed 5/5. Annotated `vf-v3-01-rc14` peels to that merge. The fresh governance
proposal revalidates the same immutable ASR assets and rights under new operation IDs, scope and
window. It remains unmounted, performs no credential read/provider call/reservation, and does not
promote ASR real-provider acceptance. See
[54_V3_01_RC14_OPENAI_ASR_GATE.md](54_V3_01_RC14_OPENAI_ASR_GATE.md).

PR #49 then merged that governance scope as
`46937d9fe4804c7c7190995afb2c48377c70f70e`. Under separate authority, RC-14 Operation 1
received OpenAI HTTP 200 once in 10,479.579 ms with 20 segments/413 words. Exactly 27 words were
`start == end`; the strict adapter rejected the response, so the operation is consumed/
`REVIEW_REQUIRED`, actual cost is unknown, 500 VND is only the safety charge and Operation 2
remains locked. The exhaustive follow-up report proves all 27 points are bounded, monotonic,
inside one selected segment and anchored to the following word start. Provider text/punctuation
were not retained and remain unknown. The revised source contract preserves only such anchored
word boundary points at the provider-evidence layer and requires an explicit positive-duration
proof before scene, silence and persistence consumers. See
[55_V3_01_22_ASR_ZERO_DURATION_WORD_SEMANTICS.md](55_V3_01_22_ASR_ZERO_DURATION_WORD_SEMANTICS.md).

## Foundation

| Capability | Primary code | Existing tests/evidence | Audit result |
|---|---|---|---|
| API/job intake | `apps/api/app/main.py`, `platform_routes.py`, `models.py` | `test_create_job.py`, Docker E2E | Implemented/mock-tested |
| Durable state/audit | `db.py`, `state.py`, `repositories.py`, main migrations `0001`-`0013` | durable platform/provider tests, Alembic replay | Implemented/mock-tested; production path untested |
| Redis queues/recovery | API services and `services/worker/npd_worker/main.py` | worker recovery suites, Docker E2E | Implemented/mock-tested |
| Object storage/assets | `object_storage.py`, `artifacts.py`, `platform_models.py` | artifact and MinIO recovery tests | Implemented/mock-tested |
| Interactive auth/RBAC | `human_auth.py`, normal-router dependency, external hash-only registry | `test_human_identity_ingress.py`, Docker E2E | Implemented/mock-tested on V3-01-01; production untested |
| Studio | `apps/studio-web/auth.mjs`, authenticated API wrapper and login shell | 14 Studio tests plus Docker E2E | Authenticated locally; production untested |

## Trend, ideas and content

| Capability | Primary code | Existing tests/evidence | Audit result |
|---|---|---|---|
| Trend adapters/normalization | `trend_providers.py`, `trend_service.py`, `trend_repository.py` | `test_trend_intelligence.py`, E2E | Fixture + contract only |
| Clustering/scoring/ideas | `trend_scoring.py`, `trend_service.py` | deterministic Trend/Idea suite | Implemented/mock-tested |
| Script/storyboard | `providers.py`, `services/worker/npd_worker/pipeline.py` | `test_providers.py`, `test_pipeline.py` | Deterministic artifact path exists |
| Research/claim ledger | no claim-level source ledger located | none | Missing |
| Originality/similarity | no enforceable guard located | none | Missing |
| Immutable script versions | script JSON is a job artifact, not a claim-linked version model | pipeline tests only | Does not meet V3 acceptance |
| Flow B acceptance plane | `flow_b_acceptance.py`, strict VND policy and offline evaluator | 17 focused tests plus two-run redacted fixture evidence | Contract/mock PASS; runtime research/originality and all real axes remain blocked |

## Upload, Auto Edit, Vision and media

| Capability | Primary code | Existing tests/evidence | Audit result |
|---|---|---|---|
| Resumable upload/validation | `auto_edit_*`, `media_validation.py`, `media_security.py` | upload, quarantine, EICAR/archive and E2E tests | Local/mock PASS; production scanner and ingress untested |
| Transcript/scene/silence/highlight | `auto_edit_providers.py`, `openai_transcription_provider.py`, `auto_edit_logic.py`, `auto_edit_service.py`, `flow_a_acceptance.py`, `provider_safety.py`, `provider_safety_durable.py` | Auto Edit suite, measured two-run fixture evidence, `EV-V3-OPENAI-ASR-ADAPTER-001`, RC-11/RC-12/RC-13/RC-14 gate validation, `EV-V3-DURABLE-MULTI-ASSET-RIGHTS-001`, `EV-V3-ASR-RESPONSE-DIAGNOSTICS-001`, `EV-V3-ASR-TIMESTAMP-CANONICALIZATION-001` and `EV-V3-ASR-ZERO-DURATION-SEMANTICS-001` | OpenAI ASR is implemented/mock-tested behind fail-closed safety. RC-14 Operation 1 proved exact preflight, HTTP 200 provider reach and a 20-segment/413-word response; 27 exact equality points were rejected and the consumed operation remains `REVIEW_REQUIRED`. The forensic follow-up preserves only bounded adjacent word boundary points in provider evidence, while positive-duration edit/subtitle/persistence consumers remain explicitly blocked. No ASR real-provider PASS, production-path or quality evidence exists |
| Vision/reframe | `vision_*`, `openai_vision_provider.py`, `evidence_serialization.py`, `flow_a_acceptance.py` | fixture/E2E plus strict Responses-schema, exact-main CI, canonical evidence, split-timeout, dual-CI and two accepted RC-10 operations | Vision structured analysis is 2/2 consecutive real-provider PASS on immutable RC-10; real subject-tracking/reframe accuracy, production path and human quality remain untested |
| Media/B-roll planning | `media_intelligence_*` | `test_media_intelligence.py`, E2E | Implemented/mock-tested |
| Stock/image/video | provider protocols and deterministic fixtures | provider failure/rights tests | No real provider adapter accepted |
| ComfyUI | `services/comfyui-bridge`, eight allowlisted workflows | bridge unit tests | Mock/disabled backend only; no GPU evidence |
| Flow B cross-stage evidence | source/claim/script/storyboard/provider/asset/audio/render hash contract | `EV-V3-FLOW-B-CONTRACT-001` | Two locked-commit fixtures PASS; no real source/provider or production path |

## Studio, production and QC

| Capability | Primary code | Existing tests/evidence | Audit result |
|---|---|---|---|
| Timeline/editing | `timeline_*`, timeline JSON schemas, Studio | timeline/Studio suites | Implemented/mock-tested |
| Preview | `timeline_service.py`, preview worker queue | E2E renders 540x960 fixture | Implemented/mock-tested |
| Subtitle/audio mix | `production_*`, `production_audio.py` | V2-08 suite, E2E | Implemented/mock-tested |
| Approval/final render | `production_service.py`, `production_repository.py` | version invalidation and render tests | Implemented/mock-tested |
| Technical QC | `production_qc.py`, worker QC | decoded video/audio E2E | Implemented/mock-tested |
| Human/content QC | no signed full-watch artifact on current RC | G-11 schema, 27-check JSON template and Markdown full-watch/listen checklist prepared offline | Instrument ready; real human review and quality acceptance remain missing |

## Publishing, analytics and Agent Hub

| Capability | Primary code | Existing tests/evidence | Audit result |
|---|---|---|---|
| Publishing orchestration | `publishing_*`, platform capability JSON | `test_publishing.py`, E2E | Dry-run only; idempotent mock receipt |
| Official platform adapters | contract-only provider definitions | not-configured tests | Missing |
| Analytics | `analytics_*` | `test_analytics_learning.py`, E2E | Fixture + contract only |
| Winner/learning | `analytics_logic.py`, `analytics_service.py` | explainability/null tests | Recommendation-only mock path |
| Flow C acceptance plane | `flow_c_acceptance.py`, strict VND policy and offline evaluator | 16 focused tests plus two-run redacted fixture evidence | Contract/mock PASS; official providers, remote publish, production path and quality remain blocked |
| Agent Hub bridge | `bridge_*`, `agent-hub-bridge.v1.schema.json` | `test_agent_hub_bridge.py`, E2E | Signed fixture/draft-only path; real HTTP untested |

## Operations

| Capability | Primary code/docs | Existing tests/evidence | Audit result |
|---|---|---|---|
| Fail-closed configuration | `config.py`, production Compose, CI safety job | main CI safety job | Implemented/mock-tested |
| Human identity emergency controls | `HUMAN_API_ENABLED`, `HUMAN_WRITE_ENABLED`, empty default registry, Redis rate limit | security suite and Docker E2E | Implemented/mock-tested; production writes remain disabled |
| Provider safety plane | `provider_safety*.py`, `provider_gate_loader.py`, `provider_ci_provenance.py`, `evidence_serialization.py`, authenticated snapshot route, settings and Compose contracts | multi-controller/restart/retention, gate-loader/RC binding, dual-CI provenance, redacted error ledger, canonical evidence/fallback/limits tests, exact RC-10 bundle guard and phase-specific split-timeout tests | PostgreSQL-backed local contract and two consecutive RC-10 real-provider operations pass with complete evidence; production-like multi-instance acceptance remains pending |
| Cost | durable VND-only budget days, atomic reservation, operation/attempt ledger, 50/80/100 alerts and global kill switch | concurrent controller, restart/configuration tests and two bounded RC-10 operations | RC-10 recorded `284.343280 VND` total actual cost inside the 1,250 VND window and reconciled reserved VND to zero; production-like multi-instance evidence remains absent |
| Upload malware boundary | quarantine state, archive-deny policy, deterministic EICAR contract and internal clamd client | `test_auto_edit_analysis.py`, migration replay | Local/mock PASS; clamd and edge/WAF not deployed |
| Rights/provenance | asset/media models, full provider rights hook, artifact/storage receipt verification | provider safety, media and publishing fixture tests plus both exact RC-10 RightsRecord bindings | Exact owned Vision input binding passed twice under the Vision-only purpose; broader real/final-asset rights, retention and public-output coverage remain unaccepted |
| Backup/restore | `v2-11-backup.sh`, `v2-11-restore.sh`, `v3-01-dr-observability-drill.sh` | guarded disposable Docker backup/failure/restore/hash verification target | Local/CI only; production-like DR untested |
| Rollback/deploy | guarded V2-11 helpers and DR runbook | migration replay and disposable data restore; no locked image rollback | Production-like rollback remains blocked |
| Observability | authenticated `operations` snapshot, correlation headers, structured secret-redacted logs and alert previews | focused tests plus disposable E2E target | Local/CI only; no monitoring backend or external alert delivery |
| Soak | `v2-11-soak.sh` | no completed window | 24-hour helper does not meet V3 48-hour gate |

## Runtime ownership

The Compose project contains only V2-owned PostgreSQL, Redis, MinIO, API, Studio, renderer and
worker. The optional ComfyUI bridge is off by default. No Agent Hub, n8n, Caddy, CRM or shared
Redis/database service is defined. This boundary must be preserved by every remediation PR.

## RC-17 fresh W1 lineage v2 checkpoint

PR #57 merged V3-01-27 as exact executable RC-17
`d08ffc005d7f3ad517d355977b0bc3cc8d686906`; exact-main CI `34550127181` passed 5/5 and
annotated tag `vf-v3-01-rc17` peels to that commit. The executable-tree SHA-256 is
`ee9831c59bba0df9a8fe975d8f539028d218cc0279b5fcf4acc72724b0910b40`.

The governance package in [65_V3_01_RC17_OPENAI_ASR_W1_LINEAGE_GATE.md](65_V3_01_RC17_OPENAI_ASR_W1_LINEAGE_GATE.md)
binds one canonical lineage ID and two fresh operation IDs to the unchanged W1 profile, exact
assets/transcripts/RightsRecords and unchanged safety envelope. It is offline only: bundle
unmounted, both operations unauthorized, provider calls/credential reads/reservations/spend zero.
ASR remains 0/2 real-provider PASS, Vision remains 2/2 and Production remains `NO-GO`.
