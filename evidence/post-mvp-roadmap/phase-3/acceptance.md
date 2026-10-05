# Phase 3 — canonical multi-input router

STATUS: PASS for ingestion and authoring routing of prompt, idea, existing script, single/multiple images, single/multiple videos, TXT/Markdown/DOCX documents and mixed inputs. Speech-video transcription/understanding remains the separate Phase 4 gate; this does not certify ASR.

The native route reuses the existing pure `app.content_models.ContentDocument` contract for prompt/idea/script validation and the existing native image/video ingestion. It does not start the legacy API/SQLAlchemy stack. An explicit API package path resolves the installed voice SDK's unrelated `apps` package; accepted model/SDK dependencies are unchanged.

`ProjectInput` is exposed as an additive `input` projection: schema_version, version, text_inputs[], image_assets[], video_assets[], document_assets[], metadata, source and canonical hash. Prompt/idea/script source text has its own SHA256. Older saved documents/approval hashes are not rewritten to add this projection. New projects retain input_kind; file additions/edits create new revisions and invalidate approval as before.

Existing scripts enter a clearly labeled deterministic preparation step with **zero provider calls** and preserve the exact narration words. One-sentence scripts are supported: the native proposal contract's minimum scene count extends from three to one, a backward-compatible relaxation; the actual OpenAI generation schema and instructions still require three–five scenes. Prepared scripts remain unapproved until explicit human review.

Documents support UTF-8 TXT/Markdown and text extraction from DOCX, 5 MB/file, 20,000 characters, twenty documents/project. MIME/content, ZIP bounds and XML entity checks precede persistence. PDF, legacy DOC and unsupported/binary content produce explicit errors; they are not silently converted or treated as text. No downloaded document content executes instructions. Provider context above 20,000 characters is refused explicitly rather than truncated.

New media uploads retain an exact original byte copy with source hash/size/MIME/version alongside the existing normalized render asset and thumbnail. The supplied source file is left intact. PNG/JPEG mismatches are rejected; video validation still uses ffprobe/full decode and now records fps/audio presence. Historical uploads without an original byte copy stay usable; no missing original provenance is fabricated or backfilled.

Video-only input with audio explicitly routes to `ASR_REQUIRED`; an attempted content job raises `ASR_PROVIDER_UNAVAILABLE_NO_TRANSCRIPT` while no native ASR is configured. It creates no transcript or inferred speech. Mixed inputs with a supplied script use that script as narration; current rendering continues its disclosed original-audio mute policy. Media-only input requires a brief/script when no transcript/document text is available. Image/video metadata is labeled technical and unanalysed; provider context never assumes semantic content from a filename.

Tests: **57/57 native**, **24/24 Studio JavaScript** PASS. Nine new native cases cover every input family, originals/MIME/provenance, document extraction/security, mixed script preparation, state/version persistence, oversized context and an actual HTTP upload. Video fixtures are real FFmpeg-generated short files; their test tone is not speech/ASR acceptance evidence.

Actual browser check on a separate data root at port 8030: create project → select existing script → upload TXT → prepare script → reload. The exact script and uploaded file survived at revision 3; provider_calls=0, tts_calls=0, one job `awaiting_review`, no approval created, render/approval blocked without source choices. Evidence: `ui-verification.json`, `ui-script-document.jpg`. Unit suite and browser test use fixtures; the Owner's live project and accepted MVP were not edited.

FILES CHANGED: ingestion module, native contracts/store/media/pipeline/server, input/document UI, regression tests and this evidence directory.

CAPABILITIES ADDED: canonical all-input inventory, explicit routing, user-script preparation, document extraction/upload, exact original-media preservation and provenance.

REGRESSIONS: supported native/Studio tests remain passing; legacy API/renderer implementation unchanged. Initial test attempts exposed an import namespace collision and an invalid fixture-only FFmpeg duration string; both were repaired before the passing run, with local logs retained under `runtime/test-runs`.

BLOCKERS: real configured ASR, speech transcript/timestamps, word alignment, Scene Intelligence/complete Approval Dashboard/Brand Templates and ten final human production reviews. Legacy Windows compatibility findings remain open.

NEXT ACTION: Phase 4 provider/credential readiness check and reuse of the existing ASR adapter/profile; stop for a missing credential or a new paid provider as instructed.
