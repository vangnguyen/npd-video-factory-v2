# Observability and soak audit

## Current result

`BLOCKED / SOAK NOT STARTED`

V2-11 has request IDs, basic structured application logs, readiness checks and a guarded soak
helper. Deterministic restart/recovery behavior is covered in tests. There is no deployed Video
Factory environment, monitoring backend, accepted alert route, retention evidence or continuous
48-hour RC observation.

V3-01-02 adds an authenticated, secret-free provider safety snapshot containing current aggregate
budget, call and circuit metadata. The underlying controller state is process-local and the
snapshot is not a production monitoring backend, durable history, alert-delivery acceptance or soak
record. It therefore does not close any observability/soak gap.

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

`ALT-001` must inject bounded staging failures for stalled queue, provider failure, storage
unavailability, expired credential alias, cost threshold and unhealthy service. Each alert must
identify component, severity, first/last occurrence, correlation ID and runbook, while containing no
secret or customer PII. External notification delivery itself requires its own approved target.

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
