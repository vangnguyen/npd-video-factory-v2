# V2-04 Auto Edit Analysis acceptance

Completed: 2026-08-27. Branch: `feat/v2-04-auto-edit-analysis`, based on approved `main` after
PR #3.

## Delivered

- [x] resumable numbered-part upload contract with durable status;
- [x] safe filename, bounded size, SHA-256, duplicate detection and magic-byte/MIME validation;
- [x] FFprobe media metadata and S3-compatible immutable source asset;
- [x] provider-independent Vietnamese transcript with segments and word timestamps;
- [x] version-1 original transcript evidence that has no overwrite endpoint;
- [x] scene evidence from shot/audio/transcript inputs, with Vision explicitly deferred;
- [x] reversible silence decisions that do not cut through spoken words;
- [x] explainable Top 3/Top 5 highlights;
- [x] PostgreSQL migration and restart recovery;
- [x] provider usage/cost in VND and deterministic zero-cost CI;
- [x] fail-closed `not_configured` live transcription behavior;
- [x] no source mutation, approval, render, publish or paid external call.

## Verification

- Python compile: PASS.
- Python API/worker tests: **70 passed** (including 7 focused Auto Edit tests with
  SQLite foreign keys enabled).
- Alembic upgrade -> downgrade base -> upgrade: PASS locally.
- Renderer: **9 passed**; TypeScript typecheck and Remotion bundle smoke PASS.
- Studio: **4 passed**; JavaScript syntax checks PASS.
- Docker images install from committed npm locks with `npm ci`: PASS.
- Compose, fail-closed safety, secret-pattern and diff checks: PASS locally.
- Docker deterministic E2E: PASS on fresh PostgreSQL, Redis and MinIO volumes.
  The run rendered and analyzed a 30.059-second, 1080 x 1920 H.264/AAC video,
  validated FFprobe metadata, resumable upload, transcript, scenes, silence
  decisions and highlights, then verified PostgreSQL/MinIO recovery after API
  restart.

The first PostgreSQL E2E exposed a same-transaction scene/highlight foreign-key
ordering defect. The repository now flushes scenes before dependent highlights;
the regression is covered with foreign keys enabled and the full Docker E2E
subsequently passed.

## Boundary

This increment is not approved for production deployment. The Auto Edit timeline and
non-developer review UI belong to V2-07. V2-05 is the exact next implementation increment:
VisionProvider, OCR, semantic frame/scene analysis, quality signals, subject tracking and smart
reframe, still without autonomous publish.
