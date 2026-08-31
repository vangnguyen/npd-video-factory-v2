# V3-01-16 split provider/controller timeout envelope contract

Status: `DRAFT / ZERO-CALL REMEDIATION / G-08 REQUIRED`

Production verdict: `NO-GO`

## Purpose

RC-7 reached the real OpenAI Vision path once and timed out at the former shared 60-second
deadline. V3-01-15 added phase-aware timeout evidence, but exact RC-8 still used one timeout value
for both the provider transport and the controller deadline. Equal deadlines can race and leave no
bounded interval for the controller to persist the provider-timeout result.

V3-01-16 removes that ambiguity with one canonical contract:

```text
provider_http_timeout_seconds = 90
controller_hard_timeout_seconds = 120

invariant:
provider_http_timeout_seconds < controller_hard_timeout_seconds
```

The 30-second separation is a safety interval for controller-side durable attempt, charge and
timeout-evidence recording after a provider transport timeout. It is not a retry window and does
not authorize another provider request.

## Canonical path

The same `ProviderTimeoutEnvelope` model is projected through:

```text
Settings
  -> verified gate budget
  -> ProviderOperationAuthorityLimits
  -> ProviderExecutionGateScope
  -> ProviderRetryPolicy / runner
  -> OpenAI Vision HTTP adapter
  -> ProviderSafetyController
  -> ProviderErrorEvidence
```

New authority input contains both explicit fields. The legacy ambiguous `timeout_seconds` field is
not accepted. Missing, extra, incorrectly typed, equal or reversed timeout values fail closed.
Historical RC-6 and RC-7 bundles are retained byte-for-byte as audit evidence; because they carry
the retired single timeout field, they cannot be loaded as a current gate bundle.

## Timeout classification

| Boundary | Evidence code | Meaning |
|---|---|---|
| provider HTTP deadline | `PROVIDER_TIMEOUT` | transport deadline expired inside the adapter |
| controller hard deadline | `CONTROLLER_ENVELOPE_TIMEOUT` | the whole provider operation exceeded the controller envelope |

Both timeout evidence variants record both configured limits. The provider timeout cannot be
silently relabelled as a controller timeout, and the controller timeout cannot overwrite provider
phase evidence that was already emitted.

## Deterministic boundary coverage

The tests use virtual time/fake transport; they do not wait 89-121 wall-clock seconds:

| Boundary | Expected result |
|---|---|
| provider 89 seconds | still running / completes |
| provider 90 seconds | `PROVIDER_TIMEOUT` |
| provider 91 seconds | `PROVIDER_TIMEOUT` |
| controller 119 seconds | within hard envelope |
| controller 120 seconds | `CONTROLLER_ENVELOPE_TIMEOUT` |
| controller 121 seconds | `CONTROLLER_ENVELOPE_TIMEOUT` |

Durable-ledger coverage also proves that a simulated 90-second provider timeout retains unknown
actual cost, applies only its conservative safety charge, writes the timeout evidence, and blocks
duplicate operation reuse while the controller envelope remains 120 seconds.

## Unchanged owner-controlled limits

```text
500 VND per operation
1,250 VND per acceptance window
one attempt
concurrency 1
no automatic retry
no model/provider fallback
```

Increasing a timeout does not increase budget authority. A later live operation requires a fresh
exact-RC G-01/G-02/G-03 rebind and a separate operation authority.

## Safety and execution record

- OpenAI/provider calls: `0`
- credential reads: `0`
- reservation/spend: `0 VND`
- deploy/public ingress/publish/production analytics: none
- checked-in defaults: external execution false, paid execution false, budget zero, kill switch
  engaged
- RC-8: retained as NO-GO architecture evidence and retired from live acceptance
- RC-9: not created by this PR; it may be locked only after G-08 merge and exact-main regression

## Gate sequence

```text
draft PR + full CI
-> explicit G-08
-> merge
-> exact-main regression
-> lock vf-v3-01-rc9
-> fresh 90s/120s G-02 envelope and G-01/G-02/G-03 rebind
-> fresh operation IDs, scope, bundle and dated window
-> separate owner authority for RC-9 operation 1
```

No step in V3-01-16 grants credential access, a provider call, deployment, public ingress,
publishing or production analytics.
