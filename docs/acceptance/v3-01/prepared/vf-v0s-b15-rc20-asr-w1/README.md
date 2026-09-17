# VF-V0S-B15 — RC-20 ASR W1 Operation 1 preparation

Status: **PREPARED_NOT_AUTHORIZED**. This directory is an unsigned, non-loadable
preparation package. It contains no G-01/G-02/G-03 approval, authority receipt,
confirmation token, active window, mounted bundle, reservation or provider result.
Do not present `gate-template.json` as a final runtime bundle: the real loader
rejects it because approval slots are intentionally absent.

## Exact binding

- Governance main: `4ac4880d5627c2800eb918d24c59da5f8e047091`.
- RC: `vf-v3-01-rc20` → `93b5441d44347c9c40b745bdfed0969880853f68`.
- Executable tree: `611450db8b70b67c39090dc245a86465cc9a5bdb542f732b9bde0c7e289e1630`.
- Dual-CI provenance: `PASS`, SHA-256 `5caca534d1cfa6a4e3d9b4f9f9b6b1c33b024ec65afdfc36cf875c673bc1eb86`.
- Ledger: `vf_vf_v3_01_rc20_5ff19bf478b41d3580e486bb6e37279d`, PostgreSQL 16.15, system ID `7686186223531422166`, migration head `0015_v3_01_dispatch`.
- Fresh Operation 1 ID and ledger key: `v3-01-rc20-openai-transcription-asr-al-0001-9722891b4ae68168375adea9fc53cc6ad89c20fa8f3c5d8535f056173f428624-call-01`.
- Canonical runner: `app.provider_single_dispatch.run_single_dispatch`, Git blob `a61a035d7b8e60be61581ce5d9d59028e2715688` in RC-20.

The operation ID follows the repository's RC/lineage/provider/capability/slot
derivation. Main/tree, ledger, media and W1 bindings are additionally fixed by
the prepared scope, operation manifest and package. No RC-19 operation-specific
identity, authority, bundle or expired window is reused.

## Reproducibility and safety

`prepare_materials.py --check` recomputes inputs and every material twice,
checks exact bytes and canonical hashes in `prepared-material-hashes.json`, and
performs no write. Canonical object hashes use sorted-key compact UTF-8 JSON;
the template SHA hashes its exact pretty UTF-8/LF file bytes. The template is
deliberately `runtime_loadable=false` and has `NOT_CREATED` approval slots.

The read-only ledger audit found all execution-state tables empty, no provider
receipt, no reservation, no idempotency collision, and separate RC-19 custody.
No prepared metadata registration is required by the current repository
contract, so **no durable write** was made for B15.

The [official Whisper-1 price](https://developers.openai.com/api/docs/models/whisper-1)
was rechecked at USD 0.006/minute. The internal fixed accounting conversion
of 27,000 VND/USD gives 162 VND/minute and 326.3004 VND for 120.852 seconds.
The 500 VND operation and 1,250 VND window ceilings are **proposals only**.
The proposed future window is 2026-09-21 21:00 → 2026-09-22 01:00 ICT
(2026-09-21 14:00 → 18:00 UTC), `PROPOSED_NOT_AUTHORIZED`.

The prepared operation-bound bootstrap is `DEFERRED_BY_CONTRACT`: B15
preparation → B16 separately approved final gate/authority/bundle → B17
zero-call operation-bound bootstrap qualification. B15 does not invoke B16 or
B17. Kill switch remains engaged, Operation 2 remains locked, and credential
reads, budget reservation, real provider calls, production business writes and
actual cost are zero.

PR #78 remains an unchanged draft for historical B14G handoff/evidence.
