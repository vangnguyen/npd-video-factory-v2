# Video Factory V3-01 — Canonical handoff

WORKSTREAM: Video Factory V3-01
TASK: VF-V0S-B6
VERDICT: REVIEW_REQUIRED
REPO: vangnguyen/npd-video-factory-v2

## Authoritative lineage

- Governance main: `d13c57bf480ed3b6b8b56f46370fef58b291810b`.
- Main CI `34916352282`: 5/5 PASS; main provenance: PASS.
- RC `vf-v3-01-rc19` → `dc8ff55322267dfe54674fa6c4003a899bf235ab`.
- RC CI `34875483864`: 5/5 PASS.
- RC executable-tree SHA: `432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
- RC/main dual-CI provenance: PASS; provenance SHA-256
  `12128084c7fff1397b2476e5360b45e13232eef0bbf161f962c3c6de38d43228`.
- Bootstrap entrypoint: `python -m app.provider_runtime_bootstrap`; exact RC source/blob guard: PASS.

## RC-19 durable custody

The lineage-aware algorithm independently re-derived
`vf_vf_v3_01_rc19_5a72b3be5266c9801013f579e75662ed`; it exactly matches the
approved plan. A fresh private PostgreSQL custody environment now exists:

- PostgreSQL `16.15`, system identifier `7685665008963764889`;
- database OID `16384`, schema `public`, peer role `vang_nguyen`;
- private Unix socket
  `/home/vang_nguyen/.local/share/npd-vf-rc19-ledger-d86a01b1a8c5/socket`,
  port `55439`, owner-only mode `0700`, no TCP listener;
- canonical migration head `0014_v3_01_27`;
- canonical control seed `global`, revision 0;
- normalized schema SHA-256
  `0b3e6ef5d39a70d31be53e6e1c15f6d0690c9e6e7e0a882ef4c014a54a36892b`
  reproduced 2/2.

The only durable writes were the fresh cluster/database, migrations and existing
control seed. A disposable migration-replay database completed `0014 → base →
0014` and was removed. These are `LEDGER_BOOTSTRAP_WRITES`, not provider or
production-business execution.

## Virgin state and isolation

State is `VIRGIN_READY_FOR_OPERATION_REBIND`: operations, attempts, budget days,
circuits, budget alerts, provider usage, cost records and idempotency keys are
all 0; reserved VND is numeric 0. There is no provider-request receipt, active
reservation, duplicate or consumed operation.

RC-18 and RC-19 use different cluster roots, system identifiers and databases.
The historical RC-18 database is absent from the RC-19 cluster. No RC-18
operation, reservation, authority, bundle or window was inherited.

## Fail-closed bootstrap finding

Custody, source, lineage derivation, namespace selection and read-only repository
primitives are VERIFIED. The overall task remains `REVIEW_REQUIRED`: the current
`BootstrapLedgerBinding` also requires a fresh operation key, authority receipt,
runtime bundle hash, execution-scope hash and scope hash. VF-V0S-B6 explicitly
forbids creating Operation 1 rebind material. Therefore the real operation-bound
bootstrap entrypoint cannot be invoked honestly yet.

No placeholder, synthetic Operation 1 identity or RC-18 value was used to force
`RC19_EXECUTION_BOOTSTRAP = VERIFIED`. Owner must approve an ordering change:
first prepare the fresh RC-19 Operation 1 rebind without authority, then rerun a
separate zero-call operation-bound bootstrap qualification against this existing
virgin custody.

## Safety and validation

- Focused bootstrap/provenance/lineage/W1/loader: 284 PASS.
- ProviderSafetyRepository, idempotency, reservation and kill-switch: 139 PASS.
- Actual custody read audit: 2/2 identical.
- Migration replay, PostgreSQL connectivity, JSON, links, checksums, secret scan
  and diff hygiene: PASS.
- Kill switch: ENGAGED. Bundle: UNMOUNTED.
- Operation 1 ID/rebind: NOT_CREATED / REQUIRED.
- Fresh authority/window: NOT_CREATED / REQUIRED.
- Operation 2: NOT_APPROVED / LOCKED / NOT_TRANSFERRED.
- Credential reads: 0; budget reserved: 0 VND; real provider calls: 0;
  production business writes: 0; actual cost: 0 VND.
- ASR: 0/2 PASS. Vision: 2/2 PASS. Production: NO-GO.

## Evidence

- [B6 custody evidence](../../../evidence/v3-01/vf-v0s-b6-20260915-rc19-ledger-custody/README.md)
- [Machine-readable handoff](handoff.json)
- Review branch: `governance/vf-v0s-b6-rc19-ledger-custody`.
- Draft PR: pending publication; never merge automatically.
- Historical handoff/evidence remains in Git history; nothing was silently removed.

## Next safe action — recommendation only

Owner review of the bootstrap/rebind ordering. If approved, assign VF-V0S-B7 as
`PREPARED_NOT_AUTHORIZED`, then assign a separate zero-call bootstrap
qualification using the newly bound Operation 1 identity. Stop before fresh
authority/window, runtime bundle mount, provider credential access, budget
reservation, kill-switch transition or provider dispatch.
