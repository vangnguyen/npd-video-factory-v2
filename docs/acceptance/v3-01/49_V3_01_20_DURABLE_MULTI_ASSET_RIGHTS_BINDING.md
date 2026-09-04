# V3-01-20 durable multi-asset rights binding remediation

## Outcome

V3-01-20 is a source-only, zero-call remediation for the RC-11 ASR Operation 1 preflight blocker.
The operation stopped before the credential, budget and provider boundaries. It remains not
consumed, and its dated authority is retired.

```text
RC-11 ASR Operation 1: BLOCKED_PRE_CALL / NOT CONSUMED / AUTHORITY RETIRED
Provider calls / credential reads: 0 / 0
Reservation / actual cost: 0 VND / 0 VND
Durable ledger: 0 operations / 0 attempts / 0 budget days / 0 circuits
RC-11 ASR Operation 2: NOT APPROVED / LOCKED
ASR real-provider-tested: NOT_TESTED
Production: NO-GO
```

The immutable blocked receipt is
[`operation-1-blocked-0-call.json`](../../../evidence/v3-01/vf-v3-01-20260904T145744Z-5e1e16a/operations/rc11-asr-operation-1/operation-1-blocked-0-call.json).
It records receipt SHA-256
`ea08b92edcb51e087ab8e8b38adef88573e0c842edf36b93bb7e3caac05492bc`.
The receipt is evidence of correct fail-closed behavior, not ASR provider or quality evidence.

## Root cause

The RC-11 ASR gate intentionally binds two distinct assets through `rights_records[]`. The
non-durable controller already selected the record for the current `asset_id`; the durable
controller still projected only legacy `scope.rights_record`. For RC-11 that legacy field is null,
so durable preflight attempted to evaluate a null record before any reservation or dispatch.

This is an executable authority-contract mismatch. It is not an OpenAI, `whisper-1`, credential,
budget or input-quality failure. Reducing the gate to one RightsRecord would weaken the approved
multi-asset contract and is not an acceptable workaround.

## Canonical remediation

Both controllers now use the same canonical selection path:

```text
ProviderExecutionGateScope.rights_for_asset(asset_id, asset_hash)
  -> ProviderSafetyController._verified_rights_records(...)
  -> exact one RightsRecord for the current asset
  -> expiry and permission evaluation
  -> reservation / durable ledger only after rights PASS
```

Selection binds both the asset identifier and asset SHA-256 when the call context supplies the
hash. Record-array ordering cannot affect the result. A wrong asset, missing record, tampered hash,
expired record or unauthorized use remains fail closed and creates no durable operation
reservation. The legacy singular record remains supported for existing single-asset gates through
the same helper; it is not used to weaken the RC-11 multi-asset gate.

## Deterministic coverage

The RC-11 gate itself is loaded offline and exercised through both in-memory and disposable-SQLite
durable controllers. Tests cover:

- exact asset slots 1 and 2;
- non-durable/durable decision and RightsRecord parity;
- reversed multi-record ordering;
- wrong asset identity/hash and missing record;
- duplicate record SHA and tampered record content;
- expired rights and unauthorized commercial use;
- unauthorized operation scope;
- retained legacy single-record compatibility;
- zero durable operation rows for every denied case.

Local zero-call validation on source commit
`5e1e16ab8736d2800e1c93a6490eca37d691475e` produced:

| Check | Result |
|---|---|
| RC-11 focused multi-asset suite | 16 PASS |
| provider/gate/safety related suite | 94 PASS |
| full Python/API/worker/bridge regression | 405 PASS |
| Studio | 14 PASS |
| Renderer | 14 PASS; typecheck and bundle check PASS |
| Alembic upgrade/downgrade/re-upgrade through `0013` | PASS |
| acceptance register and ASR compatibility validation | PASS |
| local Docker deterministic E2E | NOT RUN; Docker Desktop daemon unavailable |

The draft PR's exact-head GitHub CI must supply the isolated Docker E2E result before G-08 review.
No test read a provider credential, made a provider call or incurred VND spend.

## Acceptance effect

V3-01-20 promotes only the remediation's `implemented` and `mock-tested` evidence to PASS. It does
not change `ASR-01`: implemented and mock-tested remain PASS, while real-provider-tested,
production-path-tested and quality-accepted remain `NOT_TESTED`. `V3-01-GAP-003` and
`V3-01-GAP-013` remain `IN_PROGRESS`.

The following RC-11 items are not reusable for live execution:

- the retired Operation 1 authority and its dated window;
- either RC-11 operation ID;
- the RC-11 gate bundle as live authority.

The exact WAVs, transcripts and RightsRecords may later be rebound if their hashes, permissions and
expiry still validate. They are not recreated by this remediation.

## Next owner boundary

This branch stops at a separate G-08 review. If G-08 permits merge, the safe sequence is:

```text
merge V3-01-20
-> exact-main full regression
-> lock vf-v3-01-rc12
-> derive fresh ASR operation IDs
-> create a fresh scope, bundle and dated window
-> rebind G-01/G-02/G-03-ASR
-> governance PR and separate G-08
-> separate RC-12 ASR Operation 1 authority
```

No merge, RC-12, credential read, provider call, budget reservation, deployment, publishing,
public ingress or production analytics action is authorized by this document.
