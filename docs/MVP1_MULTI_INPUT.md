# MVP-1 multi-input development candidate

Task: `VF-MVP1-MULTI-INPUT-IMPLEMENT-01`. This is source and isolated-dev work,
not a release, deployment, provider authorization or completed MVP acceptance.

## Shared lifecycle

The existing Studio now creates projects and uploads JPEG/PNG/MP4 through the
existing authenticated quarantine/upload service. Architectural renders are
image assets with explicit metadata; an uploaded illustration is not an
official design. Original file hashes and original text remain preserved.

The existing `project_versions` store holds append-only `mvp1-content` snapshots,
original-text/content digests and script diffs with optimistic concurrency.
Refresh and harness restart retain this state. Script/idea scene splitting is
deterministic and source-preserving, not an LLM result or factual verification.
Prompt instructions remain separate from narration. An explicit `Lời đọc:`,
`Narration:` or `Kịch bản:` section supplies narration; instructions alone need
user-authored script or a separately configured/approved content adapter.

The user edits narration, visual brief, media choice, fit/crop, display duration,
scene order, cut/fade transitions and original-audio keep/mute, then approves the
storyboard. AI image and AI image-to-video choices report
`MEDIA_PROVIDER_NOT_CONFIGURED` and retain the editable plan; they are never
replaced with a mock or slideshow. Internal motion-graphic/title-card backgrounds
are first-party templates explicitly labeled **not AI**.

## Timeline identity and compatibility

`TimelineCreateRequest.source_kind` distinguishes `video_analysis`,
`storyboard_media` and `mixed`. Video analysis still requires a succeeded,
project-bound analysis. Audio-bearing video cannot bypass transcript validation.
Validated no-audio video takes a real FFmpeg visual-signal branch and stores no
transcript; this is not ASR marked N/A for speech.

Storyboard/mixed timelines require the current approved content version and
same-project assets with allowed rights. Image clips use schema `1.1`,
`kind=image`, `source_start=0`, `source_end=null`, `speed=1` and independent display
duration. Historical timeline `1.0` / render `2.0` remain loadable; new still-image
extension bytes cannot masquerade as those versions. Render `2.1` expresses the
new image/transition contract. Existing MediaPlanner/B-roll image consumers also
use image display duration rather than invented source duration.

Migration `0016_mvp1_multi_input` adds the content-version FK and an exactly-one
analysis/content check. Existing video rows retain their analysis bindings.
Downgrade refuses to discard storyboard identities while such data exists.
SQLite upgrade/downgrade/replay is tested; production PostgreSQL migration is
not authorized or claimed here.

## Audio, subtitles and approvals

The existing production package, processor, Remotion renderer, FFmpeg audio mix
and FullProductionQC are reused. Original audio has real trim/speed/gain mapping.
Narration is fitted using measured PCM chunk lengths; this is **not measured
word alignment**. Scene cues have empty `words[]` until trustworthy alignment
exists. Existing native ASR words map from preserved source intervals, never
from character counts. Manual subtitle edits clear word alignment.

Review is real A/V at 540x960. Final uses existing 1080x1920 H.264/AAC profile.
QC probes streams, decodes frames, checks dimensions/A/V duration, silence,
clipping, black output, subtitles and coverage. Only unioned planned still-image
holds discount freeze detection; unexplained video freezes remain failures.

Changes to content, timeline, audio or subtitles invalidate approvals/finals.
The Studio fetches protected review/final media through its existing human
session and offers MP4 download. Final rendering cannot reuse a stale approval.

Professional natural Vietnamese voice and measured narration word alignment
remain acceptance requirements. eSpeak is an offline dev proof only, never a
human-quality pass. No external TTS/ASR/media/content provider was executed.

## Isolated proof harness

`scripts/mvp1-dev-server.py` loads the existing API and Studio on loopback, with a
fresh explicit dev root, SQLite/local object storage, in-process queue transport,
the existing production processor and an external-IP socket guard. A synthetic,
short-lived local test-owner session is private and removed on shutdown.
`--resume` reuses only its marked dev root. This harness is not the deployed
PostgreSQL/Redis/MinIO/runner path or production malware scanning.

`scripts/mvp1-dev-fixtures.py` makes self-authored PNGs and real FFmpeg MP4; its
optional local voice creates a speech-stage blocking fixture. No owned-ASR
benchmark recordings are reused. `scripts/mvp1-ui-proof.mjs` exercises the UI
with loopback-only browser requests and writes MP4, storyboard, media plan,
timeline, production/audio/subtitle metadata, QC, rights/source manifest and
screenshots. All approvals in this harness are synthetic dev actions.

Actual commands exercised (paths were absolute at invocation):

```text
python scripts/mvp1-dev-fixtures.py --output <fresh-fixture-directory> --ffmpeg <isolated-ffmpeg>
python scripts/mvp1-dev-server.py --root <fresh-dev-root> --tools <isolated-tools> --renderer-port 3018
python scripts/mvp1-dev-server.py --resume --root <same-dev-root> --tools <isolated-tools> --renderer-port 3018
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> image-script
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> mixed
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> image-only
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> idea
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> prompt
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> script
node scripts/mvp1-ui-proof.mjs <dev-root> <local-playwright-module> spoken-blocked
python -m pytest apps/api/tests -q
python -m pytest services/worker/tests services/comfyui-bridge/tests -q
node --test apps/studio-web/tests/*.test.mjs
npm run typecheck
npm test
alembic -c alembic.ini upgrade head
alembic -c alembic.ini downgrade base
alembic -c alembic.ini upgrade head
```

Renderer commands ran from `renderer/` with isolated Linux Node 22 and extracted
browser libraries. All servers bound loopback. Tool/package downloads and
GitHub source/PR traffic are software/source network, not provider calls.

## Remaining acceptance

No path is production or human-quality accepted by these artifacts. Speech ASR
needs fresh separate authority, never reuse of the spent RC28 context. Generic
creative prompts without narration and AI media requests remain blocked at
their unconfigured stage. Professional voice/alignment, real-owner inputs and
full-watch review, approved production-path repetition, PostgreSQL/Redis/MinIO,
DR/soak, budget/security and deployment gates remain open. Trend/publishing/
analytics/learning/Agent Hub remain on the overall roadmap, not added blockers
to this dev task. No historical RC/evidence is rewritten or transferred.
