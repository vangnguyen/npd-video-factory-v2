# V2-10 acceptance — Analytics and Learning

## Accepted scope

V2-10 is accepted only as a local/CI, fixture-backed and recommendation-only increment. A green
acceptance proves durable analytics semantics and safety boundaries; it does not prove a real
platform integration or authorize a production deployment.

## Mandatory deterministic flow

The Docker E2E must prove this complete chain:

1. create a final owner-approved, QC-passed V2-08 render;
2. create a successful mock V2-09 publication receipt with no external action;
3. enqueue a `winner_candidate` analytics fixture sync;
4. persist all 16 normalized metric points and a historical snapshot;
5. produce factor-level winner evidence and Trend/Idea-linked learning insights;
6. assert no rank, content, budget or publishing mutation;
7. restart the worker and collect a second `normal` snapshot;
8. preserve unsupported VND revenue/RPM as `null` and `supported=false`;
9. restart the API and prove the report/history are byte-for-byte stable.

The E2E artifacts are uploaded under `v2-10-analytics-learning-e2e` by GitHub Actions.

## Unit and contract gates

- campaign-independent `AnalyticsProvider` contract and eight truthful provider states;
- nullable normalized metric serialization;
- winner, normal, underperforming and insufficient-data scoring;
- evidence-bearing factor calculations;
- idempotent replay and changed-payload conflict;
- bounded rate-limit retry and terminal failure;
- scheduled-refresh and fixture gates;
- PostgreSQL recovery and historical snapshot retention;
- worker queue recovery/acknowledgement;
- report, sync, snapshot, assessment, insight, history and provider endpoints;
- responsive Studio utilities, mock labels and null-vs-zero display;
- config rejection for raw credentials, production fixtures and all external analytics execution.

## Migration and CI gates

- Alembic upgrade to `0009_v2_10_analytics_learning`;
- downgrade to base and replay to head;
- Python compile and complete Python test suite;
- Studio Node tests and JavaScript syntax;
- renderer tests, typecheck and bundle check;
- Compose configuration and independent-runtime boundary;
- secret scan and `git diff --check`;
- deterministic Docker E2E with media decode/QC retained from V2-01 through V2-09.

## Safety assertions

Acceptance requires all of the following to remain true:

```text
PUBLISH_ENABLED=false
PUBLISH_EXTERNAL_EXECUTION_ENABLED=false
PUBLISH_OWNER_GATE_ENABLED=false
ANALYTICS_EXTERNAL_EXECUTION_ENABLED=false
ANALYTICS_SCHEDULED_REFRESH_ENABLED=false
HUMAN_APPROVAL_REQUIRED=true
```

Database checks and response literals additionally enforce no external analytics call, no
automatic action, no paid-media mutation, no content deletion and no autonomous insight
application. No secret or credential value may appear in source, API output or E2E artifacts.

## Evidence labels

The final handoff must distinguish:

| Claim | Accepted state |
|---|---|
| Deterministic analytics adapter | Implemented and mock-tested |
| Durable snapshots/recovery | Implemented and Docker-tested |
| Winner detection and learning | Implemented and deterministic-tested |
| Official platform contracts | Implemented, `not_configured`/contract-only |
| Real provider data | Not tested |
| Production deployment | Not performed |
| Autonomous execution | Disabled |

## Local acceptance evidence — 2026-08-27

- complete Python suite: `120 passed`;
- Studio unit/contract suite: `12 passed`;
- renderer suite: `14 passed`, plus TypeScript typecheck and bundle verification;
- Alembic upgrade/downgrade/re-upgrade through `0009_v2_10_analytics_learning`: passed;
- Docker Compose E2E: passed through the V2-01–V2-10 chain, including worker/API restart
  recovery and decoded final-media QC;
- browser QA: desktop and 390 px mobile layouts rendered the persisted fixture report with no
  console error; mobile `scrollWidth` equalled the 390 px viewport, so no horizontal overflow was
  detected;
- representative UI fixture: `winner_candidate`, one durable snapshot, `12,000,000 VND` revenue,
  four official providers reported as not configured, and `external_execution_enabled=false`;
- Docker volumes created only for local QA were removed after validation. No production system was
  accessed or changed.

These are local implementation results. GitHub CI results are recorded on the draft pull request
and remain a separate owner review gate.

## Owner gates after V2-10

V2-10 must remain a draft/unmerged change until the owner reviews CI and this acceptance record.
The next planned increment is V2-11 hardening/Agent Hub bridge design. It must not activate live
publishing, official analytics collection or autonomous learning without separate scope, security,
credential, cost and production approvals.
