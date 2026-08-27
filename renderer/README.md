# Remotion renderer

Renderer service for the generic `vertical-short-v1`, backward-compatible
`real-estate-short-v1`, and V2-08 `timeline-render-v1` compositions.

## Contract

`POST /render`

```json
{
  "job_id": "vid_...",
  "manifest_path": "/workspace/storage/jobs/vid_.../video-manifest.json",
  "output_path": "/workspace/storage/jobs/vid_.../final.mp4"
}
```

`output_path` is optional and defaults to `final.mp4` beside the manifest.

Success:

```json
{
  "status": "success",
  "output_path": "/workspace/storage/jobs/vid_.../final.mp4",
  "duration": 45,
  "width": 1080,
  "height": 1920,
  "fps": 30,
  "codec": "h264"
}
```

Failures return `status`, `error_code`, a safe message, retryability, and structured details without a raw stack trace.

The service:

1. validates request paths stay below `STORAGE_ROOT`;
2. reads the validated video manifest;
3. exposes local media to Remotion through the internal `/media` route;
4. bundles the Remotion entrypoint once per process;
5. selects the allowlisted composition from `manifest.metadata.template`;
6. renders H.264 + AAC to the requested output path.

The legacy templates support timeline scenes, local video/image media, narration/music,
mobile-safe subtitles, Vietnamese Noto Sans glyph coverage, brand logo, headline/body/emphasis
overlays and a final CTA card. The V2-08 composition accepts ordered editable-timeline layers,
crop/transform/opacity, the pre-mixed 48 kHz audio artifact, dynamic word-highlight subtitles and
540x960/1080x1920/1920x1080/1080x1080 profiles. Subtitle seconds are converted into explicit global
frame ranges at the composition FPS. Renderer progress events map 0-100% render completion into
overall worker progress.

## Development checks

```bash
npm ci
npm test
npm run typecheck
npm run bundle:check
```

Remotion packages are intentionally pinned to the same exact version.
