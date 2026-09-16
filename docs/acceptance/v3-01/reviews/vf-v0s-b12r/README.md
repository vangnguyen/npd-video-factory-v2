# VF-V0S-B12R — single-dispatch source candidate

This is a source-only candidate. It is not part of `vf-v3-01-rc19`, does not
create an execution authority, and cannot run against the historical RC-19
bundle or window. Baseline main is `7ad25cb039c712d450486778d2981d9ef8175385`;
the baseline executable-tree SHA-256 is
`432979205a0ece93c2351e109c1028b639c5c2da958b29ab6c789342c795f502`.
The candidate executable-tree SHA-256, computed from the staged canonical Git
tree paths, is `4cd897f8dbe2b9356885708701a4cf2b6ad5799f8208c59bad13fcd589702949`.

## Execution contract

`app.provider_single_dispatch.run_single_dispatch` is the sole new Python
entrypoint. A future caller must supply a fresh RC-bound bootstrap binding,
exact verified gate bundle, Owner authority receipt, dual-CI provenance,
operation manifest, immutable ASR inputs, an already-approved runtime safety
policy, and a credential resolver. The runner never promotes checked-in
fail-closed defaults. It verifies the actual imported implementation blob
against the RC Git object and requires a clean exact-RC checkout. Therefore
this candidate is intentionally unusable with RC-19.

The opt-in durable protocol adds nullable dispatch-marker fields to the existing
operation table. Historical rows retain their prior semantics. New operations
follow `INIT → PREFLIGHT_VALIDATED → RESERVED → EVIDENCE_ARMED →
READY_TO_DISPATCH → DISPATCH_STARTED → terminal`. A provider request can be
sent at most once. The ASR adapter calls the runner's callback immediately
before its one `httpx` transport send; no retry or fallback is added.

The evidence recorder writes an exclusive, fsynced `armed.json` before the
provider boundary. It records a dispatch intent before the durable marker. If
either pre-send evidence or marker write fails, the adapter never enters
transport send and the reservation is released. Once the marker commits,
transport outcome is conservatively `POSSIBLY_SENT`: even a timeout or unknown
response consumes the operation. This does not claim that HTTP bytes were
observed or that a safety charge is actual provider cost. A separate terminal
evidence record captures request/response hashes where available, transcript,
provenance, ledger/budget state, RightsRecord binding, and secret-scan result.

The operation-scoped kill switch permits a single bounded transition after
reservation and evidence arming, and re-engages in `finally`. The global
checked-in kill switch remains engaged. Duplicate operation/marker use fails
closed. An unstarted stale reservation is released without consumption; a
marked stale operation is terminal with unknown actual cost and a conservative
safety charge. `0015_v3_01_dispatch` is required for this new protocol; the
RC-19 ledger's `0014` schema is not silently reused.

## Scope and review findings

- Runtime: one new runner; opt-in adapter callback; opt-in durable marker and
  repository lifecycle. No ASR quality, W1 prompt, rights, budget ceiling,
  timeout, retry, fallback, or acceptance threshold change.
- Migration: nullable marker columns and consistency constraints; no rewrite of
  historical operations or receipts.
- Tests: mocked adapter and disposable SQLite only; no real provider credential,
  HTTP request, live reservation, or production business write.
- Portability: Windows fixtures use a Windows-absolute disposable socket path;
  the Unix-socket ownership/symlink contract remains Linux-only and is skipped
  with an explicit reason on Windows, not removed from Linux CI.
- Rollback: before a new RC/operation uses v1 dispatch rows, revert the source
  candidate by normal governance and downgrade migration only after confirming
  no v1 row exists. Once an operation has dispatched, preserve its marker and
  evidence; never erase or reinterpret historical state to roll back.

G-08 must verify the exact PR head, full diff, migration and cleanup semantics,
fresh-RC requirement, and candidate CI provenance. A passing candidate check
is not execution authority. RC-19 remains immutable and its Operation 1
authority/window/bundle are invalid for this changed executable tree. Future
sequence: Owner G-08 → merge → exact-main regression → fresh RC → fresh ledger,
operation, bundle and authority; stop before any provider boundary here.

ASR remains `0/2 PASS`, Vision `2/2 PASS`, and Production `NO-GO`.
