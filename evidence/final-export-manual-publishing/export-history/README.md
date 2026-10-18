# Export history evidence

Implemented immutable versions, measured media metadata, thumbnail, approval-at-export label, per-file custody verification, open/download/folder actions where supported, compare versions, and recreate into a new export. Historical files are preserved after project edits. Preparing/failed entries can reconcile; abandoned entries cannot resume.

Sources: `services/windows_native/manual_delivery.py`, `manual_delivery_routes.py`, `apps/studio-web/native-manual-delivery.mjs`. Test/evidence links and limits are in `docs/FINAL_EXPORT_PROGRESS.md`, `../recovery/render-process-restart.json` and `../recovery/bounded-local-replay.json`. No Owner/browser acceptance is implied.
