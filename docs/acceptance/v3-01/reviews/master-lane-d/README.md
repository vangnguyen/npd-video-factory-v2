# Master directive Lane D — offline DR / observability / G-11 candidate

## Binding and decision

- Exact Draft PR base after the approved PR #87 positive-duration timing merge and exact-main closure: `56fc2c4ddcc0b220510051a5148d9ba913965357`.
- Historical current executable RC: `vf-v3-01-rc21` at `6dcf144a4e3830e27fd617e52bc8eeab0952126e`.
- Starting executable-tree SHA: `f19a721d00e802fa5e6156a26d4bfb76ecf71036e701ee416af7997a064bf502`.
- This branch changes executable tooling. It is a **candidate**, not an RC-21 execution package. Merge is O1-gated; if merged, revalidate the tree and create fresh lineage before any authority.
- Production remains `NO-GO`; no provider credential, real provider call, budget reservation, external alert, deploy, publish, production backup or restore is authorized here.

PR #87 preserves raw provider timing evidence and adds only a separately
provenanced, opt-in positive-duration representation whose checked-in defaults
remain disabled. This candidate does not classify derived timing as raw/provider
truth. G-11 locks the exact timeline, subtitle and automated-QC bytes used for
review; their derivation/provenance remains part of those bound artifacts, and
neither an artifact hash match nor structural validation attests human
acceptance.

## D1–D10 evidence boundary

| Task | Candidate result | What remains unproven |
|---|---|---|
| D1 Backup/restore tooling | Existing `v2-11-backup.sh`, `v2-11-restore.sh`, and guarded disposable V3 drill retained. New `audit-backup` verifies all eight backup-file hashes, migration/commit/Redis recovery policy without restoring. | A new RC-21 backup/restore drill and production-like restore need their own isolated target and gates. |
| D2 Rollback rehearsal | `rollback-plan` requires distinct commits and immutable image digests, records ordered isolated steps with a deterministic hash. | Actual image rollback has **not** been rehearsed in this task; production rollback requires G-04/G-09/G-10. |
| D3 RPO/RTO | The new disposable drill records outage start and recovery completion separately from total drill time. `measure-drill` verifies outage-to-recovery RTO ≤900s and the nine-target/no-post-backup-write local RPO basis ≤60s. | The historical V3-01-07 report claimed RPO 0s/RTO 33s, but 33s was total drill elapsed; independent outage-to-recovery RTO was **not** recorded. Fresh Docker CI must produce the new markers. Neither local result is production RPO/RTO. |
| D4 Monitoring backend | Explicitly disposable SQLite store persists whitelisted operations-snapshot metrics with RC binding, strict timestamp ordering, SHA-256 row chain, and tamper verification. Raw provider/customer fields are never stored. | No deployed collector, scheduler, paging backend or production retention claim. |
| D5 Alert delivery | Only internal preview codes from the existing eight-code allowlist are accepted. External delivery is rejected on ingest and remains disabled. | Owner-approved external destination/delivery testing is absent. |
| D6 48-hour soak | `soak-plan` reports sample span, continuity gaps, critical previews and health; it **always** returns `PREPARATION_ONLY_NOT_PRODUCTION_SOAK` and never sets a start timestamp. | Real non-backdated, deployed locked-RC 48h soak and human acceptance require G-09. |
| D7 Artifact locking | `lock-review` hashes seven distinct non-symlink files, binds RC commit, and produces a deterministic lock manifest; any content change invalidates the hash. | No real final video is locked yet. |
| D8 G-11 | `prepare-review` uses the existing schema/template; `validate-review` requires the canonical 27 distinct check IDs and exact lock bindings. A structural PASS never attests human acceptance. | Human G-11 decision remains O5. |
| D9 Desktop/mobile | Standalone responsive offline player verifies lock and selected file hashes with WebCrypto and exposes the full video for separate desktop/phone review. No upload/network route. | Actual full watches remain human actions. |
| D10 Headphones/phone speaker | Same offline package exposes voice/music for diagnosis and instructs two complete final-mix listens. | Actual headphone and phone-speaker listens remain human actions. |

## Safe usage (candidate tooling only)

Run from the repository root with `PYTHONPATH=apps/api` (or an editable API install):

```text
python -m app.dr_g11_offline measure-drill evidence/v3-01/vf-v3-01-20260828T073400Z-527fd1f/operations/dr-observability/drill-summary.json
python scripts/v3_01_dr_observability_acceptance.py evidence/v3-01/vf-v3-01-20260828T073400Z-527fd1f/operations/dr-observability/two-axis-contract.json --expect-verdict BLOCKED
python -m app.dr_g11_offline audit-backup <disposable-backup-dir> --rc-commit <exact-40-char-commit>
python -m app.dr_g11_offline monitor-ingest --directory <vf-dr-local-disposable-dir> --rc-commit <exact-40-char-commit> <redacted-operations-snapshot.json>
python -m app.dr_g11_offline monitor-verify --directory <same-disposable-dir> --rc-commit <same-commit>
python -m app.dr_g11_offline soak-plan --directory <same-disposable-dir> --rc-commit <same-commit>
```

The monitor directory basename must begin `vf-dr-local-`. `monitor-verify` and `soak-plan` refuse a missing store instead of inventing evidence. Never point these commands at a production database or expose the authenticated snapshot token. The ingestion input is an already-redacted local JSON export; the module has no HTTP client or external alert transport.

For a future real video, `lock-review` requires `--rc-commit` plus `--final-video`, `--timeline`, `--subtitle`, `--voice`, `--music`, `--rights-manifest` and `--automated-qc`. Save its JSON response as the lock file. Re-run `verify-lock <lock.json>` with the same seven path flags immediately before review; any changed byte fails. `prepare-review <lock.json>` creates a still-`NOT_EXECUTED` review record; `validate-review <review.json> --lock <lock.json>` checks structure. Open `docs/acceptance/v3-01/tools/g11_offline_review.html` locally on desktop and mobile; select the lock and seven exact files. Complete the 27-check review separately. No tool action promotes an artifact to `ACCEPT` or Production GO.

## Candidate acceptance and owner gates

Focused tests cover checksum tampering, RC mismatch, timestamp replay, monitor-chain tampering, external alert rejection, kill-switch rejection, soak-gap detection, 27-check duplication, fake `ACCEPT`, lock mutation and immutable rollback-digest requirements. The full candidate CI must run on the exact Draft PR head. This source change must not merge without O1. Production-like DR, alert delivery, deployed soak and final watch/listen remain separately owner-gated.
