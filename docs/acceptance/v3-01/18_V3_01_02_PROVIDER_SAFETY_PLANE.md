# V3-01-02 provider safety plane

## Checkpoint result

`PASS FOR LOCAL/CI CONTRACT AND MOCK CONTROLS; NO-GO FOR REAL PROVIDER OR PRODUCTION USE`

The implementation code was locked at `062959287497a5999999adccb65602b88c04947e`, PR #14 exact
head was `83c31934e9505a2ec076a9a3ccb309a78aacf9ba`, and the bounded G-08 merge produced exact `main`
`dee8ac279b9ae5f4f94fbb654efb41bfdaf38ae3`. It introduces a central fail-closed
provider control plane without activating a credential, external network call, paid provider,
public ingress, deployment, publication or analytics write.

Evidence run: `vf-v3-01-20260827T153608Z-0629592`.

## Controls implemented

- one `ProviderSafetyController` for preflight, execution, retries, polling, budgets, circuits and
  secret-free status;
- VND as the only accepted budget currency;
- zero approved external budget by default, with exact 50/80/100 percent alert thresholds;
- per-operation and daily ceilings, including failed, timed-out, retried and pending-cost attempts;
- bounded exponential retry, per-request timeout, total elapsed-time cap and polling hard limit;
- global concurrency cap and closed/open/half-open circuit behavior with one half-open probe;
- duplicate external-operation rejection;
- global kill switch engaged by default and configuration validation that refuses to disengage it
  during V3-01-02;
- credential references restricted to `secret://`, `vault://` or `external://` aliases; credential
  values are not stored in the controller, API snapshot, evidence, audit or job data;
- RightsRecord-compatible input, an explicit rights decision hook and fail-closed handling for
  missing, unknown, revoked, expired or incompatible rights;
- normalized provider capability metadata for deterministic status reporting;
- artifact verification for non-empty payload, hard size limit, declared content type, SHA-256 and
  object-storage receipt consistency;
- request/source references are represented by hashes in artifact evidence;
- an authenticated read-only `GET /api/v1/provider-safety` snapshot with no credential alias/value;
- media resolution and OpenAI TTS entry points are guarded by the global provider safety state.

## Fail-closed configuration

The checked-in development and production contracts retain:

```text
PROVIDER_EXTERNAL_EXECUTION_ENABLED=false
PROVIDER_PAID_EXECUTION_ENABLED=false
PROVIDER_GLOBAL_KILL_SWITCH_ENGAGED=true
PROVIDER_BUDGET_CURRENCY=VND
PROVIDER_PER_OPERATION_LIMIT_VND=0
PROVIDER_DAILY_LIMIT_VND=0
```

V3-01-02 settings validation rejects USD, non-zero provider budgets, external-provider activation,
paid-provider activation and a disengaged global kill switch. G-01/G-02/G-03 are not inferred from
environment values and remain pending owner gates.

## Verification

| Check | Result |
|---|---|
| Provider safety focused tests | PASS; 10 tests |
| Full API/worker/bridge Python regression | PASS; 157 tests |
| Renderer tests | PASS; 14 tests |
| Renderer TypeScript and bundle check | PASS |
| Studio tests and JavaScript syntax | PASS; 14 tests |
| Docker deterministic E2E | PASS, including auth, pipeline, media, QC, restart and persistence |
| Development and production Compose validation | PASS |
| Python compile, shell syntax, acceptance harness and `git diff --check` | PASS |
| Real-provider requests | 0 |
| Actual provider cost | 0 VND |

The local Node checks used the bundled workspace Node binary because Node/npm is not globally
installed on this Windows host. No dependency was changed or approved during verification.

## Evidence interpretation

`OPS-01` and `OPS-03` now pass the implemented and deterministic mock-tested axes. `OPS-04`
continues to pass only for schema/hook and deterministic provenance behavior. No real-provider,
production-path or quality axis changes to PASS.

`V3-01-GAP-010` advances from `OPEN` to `IN_PROGRESS`, not `REMEDIATED`, because the control-plane
attempt/circuit/budget runtime is currently process-local. Production-grade durable attempt
reconciliation, multi-instance coordination, monitoring/retention and owner-gated provider
acceptance remain outstanding. Real rights coverage under `V3-01-GAP-013` also remains open.

## Intentional limits

- no credential approval loader;
- no non-zero budget activation;
- no external or paid provider execution;
- no production deployment or public route;
- no official publish or analytics collection;
- no claim that a contract/mock artifact is real-provider evidence;
- no release candidate and no change to the repository verdict `NO-GO`.

G-08 record `V3-01-APP-003` authorized only PR #14 after exact-head CI and is now consumed. The
post-merge exact-main [CI run 33090995730](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/33090995730)
passed all five jobs. No deployment, provider, credential, budget, public-ingress, publishing or
production-analytics gate was granted.
