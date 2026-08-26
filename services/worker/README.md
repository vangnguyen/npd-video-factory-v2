# NPD Video Factory V2 worker

The V2-02 worker claims IDs from the transient V2 Redis queue, reads canonical jobs from
PostgreSQL and runs the resumable vertical-slice pipeline:

`niche profile -> content -> storyboard -> Vietnamese TTS -> subtitles -> local assets -> manifest -> Remotion -> QC -> awaiting_review`

## Reliability

- claimed jobs move to `npd:video-jobs:processing`;
- inflight jobs are recovered to the queue when the single Sprint 1 worker restarts;
- validated artifacts under `storage/jobs/{job_id}` are reused after restart;
- progress never moves backward because state changes go through the PostgreSQL job repository;
- renderer network/502/503/504 failures receive one bounded retry;
- stage failures are persisted with stable error codes.

## Sprint 1 TTS

`TTS_PROVIDER=espeak` uses the offline `espeak-ng` Vietnamese voice inside the worker container. This removes external credentials from the smoke test while preserving the provider interface for later production adapters. Narration is synthesized per scene, assembled into an exact-duration PCM master, and persisted with measured cue timing so subtitles follow speech rather than placeholder scene duration.

## QC

The worker runs FFprobe and FFmpeg content analysis after render and requires:

- MP4 larger than 100 KB;
- H.264 video;
- 1080x1920 dimensions;
- 30 fps;
- audio stream;
- duration within 3 seconds of the requested duration.
- central-frame luminance samples that are not predominantly black;
- decodable audio with a non-silent peak.
