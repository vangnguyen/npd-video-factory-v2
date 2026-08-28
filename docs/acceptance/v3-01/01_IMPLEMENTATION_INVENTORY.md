# V3-01 implementation inventory

This inventory is a static and deterministic-test audit on base commit
`cae40eda871d0f9c7fc315229361a40032d48967`. It does not establish real-provider,
production-path or human-quality acceptance.

V3-01-01 through V3-01-08 are merged at exact `main`
`f42a1709cba6f087369c1636bab9bd06053f7613`, tagged `vf-v3-01-rc1` for controlled acceptance
planning only. V3-01-09 is an unmerged OpenAI Vision adapter remediation based on RC-1. None of
these local/CI entries establish production-path, real-provider or quality acceptance.

## Foundation

| Capability | Primary code | Existing tests/evidence | Audit result |
|---|---|---|---|
| API/job intake | `apps/api/app/main.py`, `platform_routes.py`, `models.py` | `test_create_job.py`, Docker E2E | Implemented/mock-tested |
| Durable state/audit | `db.py`, `state.py`, `repositories.py`, migrations `0001`-`0011` | durable platform/provider tests, Alembic CI | Implemented/mock-tested |
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
| Transcript/scene/silence/highlight | `auto_edit_providers.py`, `auto_edit_logic.py`, `auto_edit_service.py`, `flow_a_acceptance.py` | Auto Edit suite and measured two-run fixture evidence | Contract/mock PASS with pre-call safety; real accuracy absent |
| Vision/reframe | `vision_*`, `openai_vision_provider.py`, `flow_a_acceptance.py` | fixture/E2E plus V3-01-09 strict Responses-schema, retry/circuit/rights/budget/secret tests | OpenAI `gpt-5-mini` adapter implemented/mock-tested and disabled; real provider absent |
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
| Human/content QC | no signed full-watch artifact on current RC | none | Missing |

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
| Provider safety plane | `provider_safety*.py`, authenticated snapshot route, settings and Compose contracts | multi-controller/restart/retention plus V3-01-09 pre-secret/pre-network denial tests | PostgreSQL-backed local contract passes; external execution hard-blocked; local key excluded from Compose containers |
| Cost | durable VND-only budget days, atomic reservation, operation/attempt ledger, 50/80/100 alerts and global kill switch | concurrent controller, restart and configuration tests | Implemented/mock-tested; production-like multi-instance and real acceptance absent |
| Upload malware boundary | quarantine state, archive-deny policy, deterministic EICAR contract and internal clamd client | `test_auto_edit_analysis.py`, migration replay | Local/mock PASS; clamd and edge/WAF not deployed |
| Rights/provenance | asset/media models, full provider rights hook, artifact/storage receipt verification | provider safety, media and publishing fixture tests | Schema/hook implemented; real rights unaccepted |
| Backup/restore | `v2-11-backup.sh`, `v2-11-restore.sh`, `v3-01-dr-observability-drill.sh` | guarded disposable Docker backup/failure/restore/hash verification target | Local/CI only; production-like DR untested |
| Rollback/deploy | guarded V2-11 helpers and DR runbook | migration replay and disposable data restore; no locked image rollback | Production-like rollback remains blocked |
| Observability | authenticated `operations` snapshot, correlation headers, structured secret-redacted logs and alert previews | focused tests plus disposable E2E target | Local/CI only; no monitoring backend or external alert delivery |
| Soak | `v2-11-soak.sh` | no completed window | 24-hour helper does not meet V3 48-hour gate |

## Runtime ownership

The Compose project contains only V2-owned PostgreSQL, Redis, MinIO, API, Studio, renderer and
worker. The optional ComfyUI bridge is off by default. No Agent Hub, n8n, Caddy, CRM or shared
Redis/database service is defined. This boundary must be preserved by every remediation PR.
