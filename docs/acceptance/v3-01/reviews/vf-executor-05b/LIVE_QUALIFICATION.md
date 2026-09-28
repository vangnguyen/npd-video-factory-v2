# VF-EXECUTOR-05B live qualification evidence

Verdict: `BLOCKED_APPROVED_PROVIDER_SECRET_SOURCE_ABSENT`

This is a zero-call, qualification-only run. It is not O2 and does not grant
provider execution authority.

## Immutable identities

- Base main: `50cb6d452ea64fbded31a8bfce86fc431835acc6`.
- Executable source commit:
  `cf55b47e5b33de183ef9c3f76993fbb65d63a6e9`.
- Executor executable-tree SHA-256:
  `b35b71396c295339f47803426bf608f7e6af60df5bd303baa03d635d12f41248`.
- Execution workflow commit:
  `f2eff56d989bd6a3ad2e0647b762329bdbba5f21`.
- Operator topology provenance SHA-256:
  `514a2a3cbd21bee5b49a1841261379ad7206390f6c10bbc98331705122780a7d`.
- Custody binding SHA-256:
  `c8d2761e3a5f6f835d6562665aac3eb175b5387bacc9e9e2daa5433c36b00e27`.

## CI and live runner

- Exact-head CI: `36436731347` — PASS.
- Expected head:
  `cf55b47e5b33de183ef9c3f76993fbb65d63a6e9`.
- Checked-out head:
  `cf55b47e5b33de183ef9c3f76993fbb65d63a6e9`.
- Docker deterministic E2E: PASS.
- Runner: ID 6, `npd-vf-executor-ubuntu-02`.
- Live qualification workflow run: `36437615585`.
- During run: Online/Busy only for the selected qualification workflow.
- After run: Offline; listener stopped; service not installed.

## Gate results

- E1 durable evidence: PASS.
- E2 WSL/runtime/executable tree: PASS.
- E3 PostgreSQL custody: PASS; PostgreSQL 16.15, database
  `vf_provider_custody_v3_01`, migration `0015_v3_01_dispatch`.
- E4 ledger read: PASS; zero operations, attempts, alerts, budget days,
  circuits and reservations; one baseline control row.
- E5 GitHub/provenance: PASS from root-owned operator evidence; no GitHub read
  credential was granted to the runner.
- E6 provider network: PASS by TLS handshake only; HTTP requests 0.
- E7 secret source presence: BLOCKED; no approved source exists on the host.
- E8 reservation capability: PASS via SELECT-only read-only qualification;
  reservation created 0.
- E9 bundle/loader: PASS using only the expired synthetic fixture; active bundle
  mounted false.
- E10 check-only/evidence/kill switch: PASS; ledger unchanged; kill switch
  engaged.

## Sealed evidence

- Live evidence directory:
  `vf-executor-05b-bfe356c7095c49f1b7531d6b32874183`.
- Qualification receipt SHA-256:
  `0548b04beeef9041d497cbe925f8e9a942cf54b2007098adcf9b6aa2b8c09de4`.
- Probe manifest SHA-256:
  `355aa5a4238c770eba211e2d1e0ed1f6dee2f116603e2fcf1aa21f086d3db588`.
- Hostile security evidence directory:
  `vf-executor-05b-security-e80df30ee944476ab145c2992e71b7d1`.
- Hostile security receipt SHA-256:
  `ac528669fa139f9598e30f0f4bea60107b5957bd1bb02892f268089fc9f4bd03`.
- Qualification promotion: NOT CREATED.

## Zero invariants

- Real provider calls: 0.
- Provider credential reads: 0.
- Budget reserved: 0 VND.
- Operation consumption: 0.
- Actual cost: 0 VND.
- Production business writes: 0.
- RC-22 mutation: none.
- O2: no.

The safe next step is an Owner decision identifying an already-approved secret
source or separately authorizing its exact non-plaintext binding. After that,
rerun only the live qualification, reseal the successful artifacts, and perform
independent promotion.
