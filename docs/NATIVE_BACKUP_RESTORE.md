# Native offline backup and recovery

This utility snapshots the existing Native data root and restores into a new directory. It never stops or starts services, rewrites the source root, enables publishing, supplies human approval or restores over an existing directory. PostgreSQL, Redis, S3 and ComfyUI service recovery require their separate runbooks and acceptance.

Use the preserved source revision and its pinned Native runtime. Keep the package in an access-controlled recovery directory: it contains private projects, uploads, transcripts, research and artifact metadata. ZIP is unencrypted; Windows permissions inherit from the parent directory. Secret-file contents are excluded, but configured runtime/secret paths remain references. Recover encrypted credentials separately through their existing protected mechanism. Do not commit recovery packages or runtime credentials.

## Snapshot

Arrange an offline window using the normal Native service controls. The utility refuses a held server lease or active queued/running operations; it does not terminate them. Supply the explicit runtime configuration and a new output path outside its data root:

```powershell
$env:PYTHONPATH='C:\vfns01;C:\vfns01\apps\api'
& 'C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe' scripts/native_backup_restore.py backup --config '<runtime-config.json>' --output '<new-recovery-package.zip>'
```

Retain the returned SHA256 independently of the package. SQLite's backup API includes committed WAL transactions without copying live journals. Database quick checks, current immutable version bindings, all-table logical hashes, source membership and file hashes must agree before the fresh package is committed. Source catalog/lock JSON is copied as configuration evidence; it never replaces checked-in configuration during restore.

Limits are 50,000 entries, 10 GiB total and 2 GiB per file. Unknown databases, linked paths, hardlinks/junctions, special files and secret files inside the state root reject. Copy-time changes reject the snapshot. Failed partial packages remain available for diagnosis; the original is retained.

## Fresh restore

Verify the independently retained package checksum and choose a nonexistent destination under an existing access-controlled parent:

```powershell
& 'C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe' scripts/native_backup_restore.py restore --backup '<recovery-package.zip>' --destination '<new-data-root>' --expected-sha256 '<trusted-64-character-sha256>'
```

Restore rejects existing destinations, original-source destinations, traversal, duplicate names, compressed/encrypted or linked archive entries, unindexed files, altered bytes and incompatible database state. It extracts to an owned staging directory, validates each byte hash and the database/history state, then renames that directory into place. Failure leaves the staging directory for inspection and never commits the destination.

The receipt supplies hash-scoped `receipt_path` and `runtime_config_path`. The new configuration changes only the data root; source/runtime/secret path references must be reviewed for the recovery host. Configuration evidence is under `_recovery/<manifest-sha256>/configuration/`. Previous recovery receipts survive subsequent backups. No service starts automatically. Review the result before using normal startup controls; production startup/deployment remains separately Owner-gated.

## Executed recovery rehearsal

`scripts/north_star_native_restore_contract.py` builds a fresh technology project with explicitly fixture research/ideas and an unpriced fixture operation. It creates an actual two-second FFmpeg test video/audio, snapshots and restores the databases/assets/configuration, then moves only its fresh synthetic original directory to a retained sibling so reads cannot accidentally use the original.

The n3 rehearsal passed exact project/version/research/cost/hash comparisons, complete restored video/audio decoding, a visible editor update with a new canonical revision and an unchanged unrelated project. Unapproved render still rejects. Evidence is indexed by `docs/north-star/native-restore-evidence.json`; neither fixture approvals nor this rehearsal constitute Owner UAT, genuine provider acceptance, full Mode A/B acceptance or production deployment.

## New Source production after recovery

`scripts/north_star_native_source_recovery.py` adds operational Source-mode acceptance using a separately preserved six-format technology backup. It verifies the trusted archive SHA256, restores into a fresh owned seed, independently snapshots that seed and restores again into another fresh root. Exact master/family/child state and every original asset, preview and job file hash match. Only the newly created seed is moved to a retained `-offline` sibling; its old operational path is unavailable and its bytes remain intact. The original six-format source roots and archives are untouched.

In final n2, six authenticated requests read the restored project, save a new canonical subtitle-track lock, verify that rendering is blocked without new approval, create a fresh effects preview, record an explicitly automated review fixture and enqueue a new final job. Actual local rendering and FullQC pass at 1080×1920. Source paths, private staging, audio inputs and the new mix belong to the restored root. The fresh preview builds PCM under the new root scope and the final render reuses it. The master, other variants, frozen family records, previous project versions and all old asset/preview/final files remain unchanged. A separate process recovers exact post-render state.

Historical absolute result paths are retained as original receipt evidence; they are not rewritten to imply past jobs ran in the new directory. Current operational APIs resolve media from the configured restored root. The rehearsal verifies a new edit, preview, approval-gated render and QC after recovery. It does not certify PostgreSQL/Redis/S3/credential restore, genuine ASR, browser/Owner UAT, publication or production deployment. Exact logs and 22 exports/media/archive hashes are in `docs/north-star/native-recovery-render-evidence.json`. The first fixture/log remains retained: its script initially expected HTTP 400 rather than the established 409 approval-gate response; no product guard was relaxed.
