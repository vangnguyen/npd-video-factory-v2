# Observability and soak audit

## Current result

`LOCAL OBSERVABILITY PASS / DELIVERY AND SOAK BLOCKED`

V3-01-07 adds an authenticated read-only operations snapshot, request/correlation propagation,
structured secret-redacted logs and visibility for dependencies, queues, failed jobs, disk,
provider safety state, VND cost and retention. Seven alert scenarios are detected as internal
previews with runbook and correlation IDs; external delivery is hard-disabled. The disposable DR
run verifies these signals after restore under `EV-V3-DR-OBS-001`.

This remains local/CI evidence. There is no deployed monitoring backend, accepted alert destination
or continuous 48-hour locked-RC observation. `V3-01-GAP-009` therefore remains `IN_PROGRESS`.

## Required signals

- API, Studio, worker, renderer, PostgreSQL, Redis and object-store health;
- request/job/project/correlation ID propagation without PII or secrets;
- queue depth, oldest age, stage duration, retries, cancellations and dead work;
- provider latency/error/rate-limit/circuit state and cost usage;
- render duration, CPU/GPU/memory/disk/object-store capacity;
- publication outbox/reconciliation state when G-06 is later approved;
- backup freshness, scheduler/collector freshness and evidence retention;
- security denials, auth failures and anomalous ingress.

## Alert tests

The local `ALT-001` contract covers queue backlog, provider degradation, storage unavailability,
disk pressure, failed jobs, VND cost threshold and unhealthy service. Each preview includes severity,
correlation ID and runbook and contains no secret or customer PII. Production alert delivery remains
separately owner-gated and disabled.

## 48-hour soak contract

`SOAK-001` starts only after a locked RC, production-like staging, DR readiness and owner G-09. The
start time must be explicit and cannot be backdated. PASS requires continuous evidence for 48 hours:

- no unexplained outage or restart;
- readiness and scheduler/queue freshness inside the accepted SLO;
- no data, artifact or audit loss;
- bounded retries and no poison-loop/cost anomaly;
- zero unapproved external write or provider execution;
- every incident classified, resolved and linked to evidence.

No current timestamp is a soak start. Green CI and an idle process do not substitute for the window.

Open gaps: `V3-01-GAP-007`, `V3-01-GAP-009`, `V3-01-GAP-010`.
