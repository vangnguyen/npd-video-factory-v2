# V3-01 implementation inventory

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
| Transcript/scene/silence/highlight | `auto_edit_providers.py`, `openai_transcription_provider.py`, `auto_edit_logic.py`, `auto_edit_service.py`, `flow_a_acceptance.py`, `provider_safety.py`, `provider_safety_durable.py` | Auto Edit suite, measured two-run fixture evidence, `EV-V3-OPENAI-ASR-ADAPTER-001`, RC-11/RC-12 gate validation, `EV-V3-DURABLE-MULTI-ASSET-RIGHTS-001` and `EV-V3-ASR-RESPONSE-DIAGNOSTICS-001` | OpenAI ASR is implemented/mock-tested behind fail-closed safety. RC-12 Operation 1 proved preflight and provider-response reachability, then failed strict response validation and remains consumed/`REVIEW_REQUIRED`; V3-01-21 adds future value-free diagnostics but no accepted transcript or real-provider PASS |
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
