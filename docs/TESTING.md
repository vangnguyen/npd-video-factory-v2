# Testing — V2-01

## Local checks

Python 3.12+:

```bash
python -m pip install -e "apps/api[dev]" -e "services/worker[dev]"
python -m compileall -q apps/api/app services/worker/npd_worker
python -m pytest apps/api/tests services/worker/tests -q
```

Renderer (Node 22):

```bash
cd renderer
npm ci
npm test
npm run typecheck
npm run bundle:check
```

Independent Docker flow:

```bash
bash scripts/e2e-smoke.sh
```

## E2E acceptance

The script creates five visible, copyright-safe PNG fixtures and one deterministic job. It
must reach `awaiting_review` and produce at least:

- `script.json`, `storyboard.json`;
- `narration.wav`, `narration-timing.json`, `subtitles.srt`;
- `video-manifest.json`, `final.mp4`, `qc.json`;
- contact sheet and Compose logs in the CI artifact bundle.

Assertions cover 1080x1920 H.264, audio presence, duration tolerance, minimum size, decoded
luminance/black ratio, decoded audio level and exact scene-aligned subtitle cues.

## CI gates

`Video Factory V2 CI` runs four independent gates:

1. Python unit/contract tests and compile;
2. renderer tests, typecheck and Remotion bundle;
3. Compose/safety/secret contract;
4. Docker deterministic E2E.

Normal CI performs no paid network call. `Manual paid-provider smoke` only runs when the
dispatcher types `APPROVED`, the protected environment is authorized and its secret exists.
That smoke is not human voice acceptance; a Vietnamese listener must approve production
voice quality separately.
