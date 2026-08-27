# V2-11 Soak Testing

## Purpose

Soak verifies runtime continuity; it is not a substitute for functional, contract or security
tests. The default observation is 24 hours with one readiness sample per minute.

```bash
VIDEO_FACTORY_SOAK_SECONDS=86400 \
VIDEO_FACTORY_SOAK_INTERVAL_SECONDS=60 \
VIDEO_FACTORY_SOAK_REPORT=/var/lib/npd-video-factory-v2/acceptance/v2-11-soak.jsonl \
./scripts/v2-11-soak.sh
```

The script is read-only and records timestamps plus readiness state without credentials or project
data. Do not shorten the window and still call it a 24-hour PASS.

## Evidence to correlate

- API/worker/renderer/Studio restart counts and fatal logs;
- PostgreSQL, Redis and MinIO health;
- queue and processing-list continuity;
- webhook queued/running/retry/succeeded counts and oldest age;
- signed receipt verification across worker/API restart;
- disk, memory and container health;
- no unexpected network call or secret-bearing log;
- publishing/external execution/human-approval settings;
- Agent Hub outage period, if injected, separately from V2 health.

PASS requires zero unexplained V2 outage, no lost canonical request/event/delivery state, no stuck
delivery beyond retry SLO, no safety-boundary change and successful post-window smoke. A planned
restart must be identified by timestamp and change record. Any semantic fix affecting runtime
restarts the observation window.

V2-11 does not run a real production soak in CI. CI uses deterministic restart/recovery tests and a
short local smoke only; production soak remains an owner-gated deployment acceptance step.
