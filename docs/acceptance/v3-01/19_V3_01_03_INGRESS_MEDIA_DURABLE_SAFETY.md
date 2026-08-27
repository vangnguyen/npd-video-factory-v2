# V3-01-03 ingress/media security and durable safety state

## Checkpoint decision

`PASS TARGET FOR LOCAL/CI REMEDIATION ONLY; NO-GO FOR PUBLIC INGRESS, REAL PROVIDERS OR PRODUCTION`

This checkpoint begins from exact merged `main`
`dee8ac279b9ae5f4f94fbb654efb41bfdaf38ae3`. It addresses the local/CI portions of
`V3-01-GAP-010` and `V3-01-GAP-011` without activating a public route, credential, provider call,
paid execution, deployment, publication or production analytics.

## Media trust boundary

The upload lifecycle becomes:

```text
initialized -> uploading -> quarantined -> trusted -> completed/completed_duplicate
                                      \-> rejected
                                      \-> quarantined + scan error (fail closed)
```

- the assembled file is quarantined before FFprobe, decoder or object-storage promotion;
- ZIP, RAR, 7z, gzip, bzip2, xz and tar signatures are denied before any decompression;
- V3-01-03 performs no archive ingestion, so archive-bomb expansion is structurally absent;
- the deterministic scanner proves only clean/EICAR contract behavior and is rejected by production
  configuration;
- the bounded clamd `INSTREAM` client is internal-only, checks the assembled SHA-256 before sending,
  enforces the upload-size ceiling and timeout, and stores only verdict metadata;
- only a `clean` verdict can mark an upload trusted and create/promote an asset;
- infected/rejected media remains untrusted, while scanner unavailable/error retains quarantine and
  returns a fail-closed error;
- no media bytes, token, credential or provider payload is placed in API safety snapshots or the
  provider ledger.

The checked-in production Compose deliberately uses `MEDIA_MALWARE_SCANNER_MODE=disabled`. This
means a hypothetical deployment would reject completion rather than silently trust a file until an
internal scanner is separately approved and configured. No clamd service is added by this PR.

## Ingress/WAF contract

[`ingress-media-security.v1.json`](../../../packages/contracts/ingress-media-security.v1.json)
specifies the future edge boundary: exact upload routes/methods, TLS, request-body limits,
per-IP/principal throttles, path normalization and secret-free security logs. Its authorization
flags are false. It is design evidence only and changes no Caddy, DNS, firewall, WAF or public
route.

## Durable provider safety state

Migration `0011_v3_01_03_security_durable_safety` adds V2-owned PostgreSQL tables for:

- a singleton transaction control row;
- daily VND committed/reserved totals;
- provider/capability circuit state;
- secret-free operation reservations and outcomes;
- per-attempt usage/cost outcomes;
- one-time 50/80/100 percent budget alerts.

Reservation and completion transactions update the control row first, which serializes decisions
across API instances. Tests exercise two independent controllers against one database to prove
duplicate blocking, global concurrency and atomic daily reservation. Startup recovery releases stale
reservations, reconciles already-recorded attempt charges into committed VND totals, records a
recovered terminal state and opens the affected circuit. Operation history
has an explicit retention deadline; deletion is implemented but configuration-blocked in V3-01-03
so no evidence is silently removed.

The authenticated provider-safety snapshot now reports the PostgreSQL backend, totals for durable,
active, recovered and attempted operations, stale count, oldest active age and retention days. It
contains no credential aliases or request/response bodies.

## Required local/CI acceptance

- migration upgrade, downgrade and replay;
- clean upload promoted only after scan;
- EICAR and archive input rejected before decoder/storage;
- disabled/unavailable scanner retains quarantine and creates no asset;
- production fixture scanner rejected by configuration;
- two-controller duplicate/concurrency and atomic-budget tests;
- circuit state and stale-reservation recovery after controller restart;
- expired terminal retention purge never removes an active operation;
- API capability and provider-safety snapshot remain secret-free;
- full Python, Studio, Renderer, Compose safety and deterministic Docker E2E regression;
- secret scan, acceptance validator and `git diff --check`.

## Intentional limits and remaining gates

- `GAP-010` remains `IN_PROGRESS`: no external call, real cost, production-like multi-instance load,
  alert delivery or approved retention cleanup was tested.
- `GAP-011` remains `IN_PROGRESS`: no internal clamd deployment/signature-update acceptance,
  public ingress, WAF, edge rate-limit or production quarantine operation was tested.
- `G-01`, `G-02`, `G-03` and `G-04` remain pending.
- external execution and paid execution stay false; provider budget stays `0 VND`; global kill switch
  stays engaged.
- a draft V3-01-03 PR requires a new explicit `G-08` before merge.
- production deployment, public ingress, real publishing and production analytics remain prohibited.

Repository verdict remains **NO-GO**.
