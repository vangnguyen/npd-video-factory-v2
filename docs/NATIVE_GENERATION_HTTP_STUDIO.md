# Native generation through Assets

The existing Native Assets stage now includes image/video generation. Editors
can choose text-to-image, image-to-image, variation, inpaint, upscale,
text-to-video, image-to-video or reference-assisted video; select owned project
images/masks; set prompt, negative prompt, aspect, seed, scale or video duration;
acknowledge the configured provider/fixture mode; and submit a durable request.
The panel reads capabilities and history explicitly. It never enables a provider,
silently fabricates an output or automatically attaches generated media.

Saved requests show progress or the need for cost approval/reconciliation.
Review uses a scoped local image/video route. An explicit import acknowledgment
creates a project version and clears approval. Placement uses the existing shot
or canonical timeline controls. Cancellation stays pending until confirmed;
reconciliation reads the original job and never grants another generation POST.
Unknown rights, fixture labels and unknown actual cost remain visible. History
is bounded to 200 requests per project; reads expand in 25-item increments and
polling is bounded and discarded when project/workspace/revision changes.

Human HTTP routes are:

- `GET /api/generation/providers`
- `GET /api/projects/{project_id}/generation?limit=25`
- `GET /api/projects/{project_id}/generation/{generation_id}`
- `GET /api/projects/{project_id}/generation/{generation_id}/file`
- `POST /api/projects/{project_id}/generation`
- `POST /api/projects/{project_id}/generation/{generation_id}/cancel`
- `POST /api/projects/{project_id}/generation/{generation_id}/recover`
- `POST /api/projects/{project_id}/generation/{generation_id}/import`

Existing human sessions, workspace binding, loopback/same-origin, CSRF and RBAC
apply before request body parsing. Owner/editor can mutate; reviewer/viewer can
read. A service bearer header cannot replace a human session. Strict request
DTOs reject client endpoints, graphs, credentials, workflow routes and results.
Responses and media use `no-store`. The Assets panel receives no provider key or
private origin. It renders text literally and builds only scoped local preview
URLs. Import history validates its frozen asset and immutable project version.

Execution remains disabled by default. Enabling the Native generation API
requires human auth and an external protected registry through
`--generation-provider-registry` plus `--enable-generation-api`. Registry
workspace identity must match the human workspace; credential `enabled` must
also be true. The optional `workflow_manifest` selects an absolute protected
manifest outside Native state. Workflow graphs remain static, pinned and
Owner-reviewed. Repository placeholder workflows stay `NOT_CONFIGURED` even
when a credential is enabled. This configuration path does not authorize paid
provider acceptance, publishing or production deployment.

Backups count all additive generation journals and refuse queued/running jobs.
Actual backup/restore and default-inactive reopen preserve generated originals,
normalized assets, thumbnails, references, cost intents, results, import receipts
and project versions. Interrupted jobs require explicit reconciliation rather
than automatic submission after restore.

The connected rehearsal uses real loopback human HTTP, the actual independent
Native worker and authenticated bridge, actual graph compilation and full local
PNG/MP4 decoding with synthetic pixels/mock GPU APIs. It performs 51 human HTTP
requests, three Native generation submissions, one read-only lookup, a local
post-stage crash recovery and three explicit imports. Viewer writes fail. Six
cost operations retain null billing and zero paid operations. The source stays
unchanged before import. A fresh-root backup/restore and separate-process exact
replay of both roots pass with generation inactive.

The first HTTP rehearsal stopped on a script helper naming collision after
generation completed and before import. Its log/root remain; the corrected
fresh-root rehearsal passes. Unit/HTTP/DOM and full Native regression counts are
recorded in `docs/north-star/native-generation-http-studio-evidence.json`.
DOM tests are not browser usability or Owner UAT. No genuine AI model/GPU,
licensed external content, paid generation, real publishing, Agent Hub receiver
or production deployment is claimed. All original Mode A/B and North Star
readiness gates remain separate from this capability increment.
