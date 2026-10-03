# Canonical handoff receipt — MVP-1 multi-input dev candidate

TASK: `VF-MVP1-MULTI-INPUT-IMPLEMENT-01`
VERDICT: `MVP1_MULTI_INPUT_DEV_CANDIDATE / ACCEPTANCE_OPEN`
REPO: `vangnguyen/npd-video-factory-v2`
BASE MAIN: `fa81c59fbe6b745cba8fed979e30e52a13199afa`
BRANCH: `codex/vf-mvp1-multi-input-01`
COMMIT/PR/CI: recorded in the final local task receipt after commit/PR creation.

Users can create real A/V review and final MP4 through the existing Studio from
images, architectural illustrations plus script, text-only source narration,
and mixed image/video/text. The mixed fixture has **no audio stream**, confirmed
by real ffprobe; no transcript was fabricated. Speech video remains blocked at
real ASR. Instructions-only prompts do not automatically become narration;
the successful prompt proof supplies an explicit narration section. None of
these paths is human-quality or production accepted.

## Implementation and tests

| Work item | Implemented / tested | Open boundary |
| --- | --- | --- |
| MI-01 input/project | Shared upload quarantine/storage, original hashes, JPEG/PNG/MP4, render metadata, text kinds, append-only content versions/CAS; UI persistence/refresh and dev-server resume | Real production storage/malware/deployment qualification not performed |
| MI-02 content/storyboard | Deterministic source-preserving scene draft, prompt/narration separation, editable scenes and script diff, content approval; no LLM claims or factual invention | Unstructured idea/prompt creative generation and professional content acceptance need configured approved adapters/human review |
| MI-03 multi-source timeline | Discriminated analysis/storyboard/mixed source, project/rights/version guards, image display time/fit/crop/cut/fade, explicit internal template vs AI strategy; migration and hostile tests | AI image/video selection correctly blocks; not silently replaced with a montage |
| MI-04 A/V/review/final | Existing production package/processor/renderer/QC, original audio mapping, real offline dev narration, safe scene subtitle cues, authenticated playback/download, stale approval invalidation and rerender | Professional Vietnamese voice/human listening, trustworthy measured narration word alignment and deployed production-path acceptance remain open |

| Case | Implemented | Deterministic / isolated real-file UI test | Real external provider | Deployed production path | Human quality |
| --- | --- | --- | --- | --- | --- |
| T01 speech video | Existing guarded ASR path preserved | PASS rejection: HTTP503, no succeeded analysis/transcript | NOT_RUN / BLOCKED | NOT_RUN | NOT_ACCEPTED |
| T02 ordinary image | Yes | PASS image-only caption → review/final | TTS NOT_RUN; external media not needed for selected montage | NOT_RUN | NOT_ACCEPTED |
| T03 architecture + text | Yes | PASS synthetic architectural illustration + supplied script | TTS NOT_RUN; no official-design claim | NOT_RUN | NOT_ACCEPTED |
| T04 idea without video | Yes, source-preserving deterministic draft | PASS explicit `idea` input + internal motion graphic | Creative LLM/TTS NOT_RUN | NOT_RUN | NOT_ACCEPTED |
| T05 prompt only | Explicit narration section supported; instructions-only needs script | PASS prompt-with-narration; pure instructions fail closed | Content/TTS NOT_RUN | NOT_RUN | NOT_ACCEPTED |
| T06 script only | Yes | PASS immutable source script → scenes/template/review/final | TTS NOT_RUN | NOT_RUN | NOT_ACCEPTED |
| T07 mixed | Yes | PASS real silent video + two PNGs + script → same timeline; two dev E2E passes | ASR genuinely not needed for this verified no-audio fixture; TTS NOT_RUN | NOT_RUN | NOT_ACCEPTED |
| T08 edit after approval | Yes | PASS old final stale/blocked → new content/timeline → new review/approval/final; two dev E2E passes | TTS NOT_RUN | NOT_RUN | NOT_ACCEPTED |

All test approvals are **synthetic dev actions**, not Owner production acceptance.
Media rights fixtures are self-authored specifically for dev; no benchmark asset
or old RightsRecord is reused. eSpeak audible MP4 is not voice acceptance. Scene
cues contain empty `words[]`, not fabricated measured word timestamps.

## Actual artifacts

Local root:
`C:/Users/PC/Documents/Codex/2026-09-28/ti-p-t-c-vf-executor/work/vf-mvp1-proof-20261003-01`

| Proof folder beneath that root | Important artifact / SHA-256 |
| --- | --- |
| `ui-image-script-1790998328107` | `review.mp4`: `d07f749465342af9076005da67cffa5a5d39e8be94055d494b7fcff8c3955799` |
| same | `final.mp4`: `34aee7e88655dc0a3c4c0ef7b4dfe403e5d304f6646d48ae04beb3eb67ea68b6` |
| same, T08 | `final-after-edit.mp4`: `669bcaa58c114dc0cdbb5984262b7dbeab1a517a2148b3f59dc7ce698ae82c19` |
| `ui-mixed-1790998339705` | `final.mp4`: `e0d345d60f11d48fde52ac295546b12d8e6a7720761667cec2f9b19463830e44` |
| `ui-image-only-1790998016314` | `final.mp4`: `25236a4d579498ffc33d8d25406d49e946fff7fe1120780029db1af5b807869a` |
| `ui-idea-1790998059104` | `final.mp4`: `a7a5dc856e43f34d4d3f3f0218ca8b69daab51b84a9092038132d3a10c8e5a65` |
| `ui-prompt-1790998349993` | same exact final content/hash as the supplied narration text-only fixture |
| `ui-script-1790998070924` | same exact final content/hash as the supplied narration text-only fixture |
| `ui-spoken-blocked-1790997676612` | `speech-analysis-blocked.json`, HTTP503, failed ASR stage with no fabricated transcript |

Each successful render folder also contains storyboard, media plan, timeline,
source assets, production package (subtitle/audio metadata), review/final render
records with real QC, UI screenshot and proof report. The repeated T08 proof has
the corresponding `*-after-edit.json` and screenshot. `fixtures/` and
`fixtures-spoken/` hold the first-party source/rights manifests.
`DEV_REVIEW_INVENTORY.json` hashes 152 retained artifacts including failed early
proofs, successful proofs and JUnit reports. Private local dev sessions/DB are
excluded; JSON artifact credential-pattern scan: PASS / 0 findings.

Early local failures (missing browser libraries, protected-video playback,
project/upload loading races and startup interruptions) are retained, not
reclassified as successes. Fixes and successful new dev runs are separate.

## Actual regression

- API: `1651 passed / 1 skipped`, full regression JUnit
  `full-regression-final.xml`; subsequent final B-roll source-duration change
  independently tested with `30 passed` in `targeted-final.xml`.
- Worker/ComfyUI bridge: `44 passed`, `service-tests.xml`.
- Studio: `15 passed`; renderer: `16 passed`, TypeScript PASS.
- SQLite migration: full upgrade → downgrade to base → upgrade PASS; downgrade
  with retained storyboard data fails closed in its dedicated unit test.
- Historical repository/evidence verifier PASS; OpenAI compatibility replay PASS;
  Flow A historical fixture remains correctly `BLOCKED`, not real acceptance.
- One existing executor test was isolated from the installed host catalog using
  an absent temporary catalog. It retains the same fail-closed assertions and
  does not grant or read live authority.

## Boundary receipt

PROVIDER_EXTERNAL_CALLS (task): `0`
PROVIDER_CREDENTIAL_RESOLUTIONS (task): `0`
EXTERNAL_PROVIDER_UPLOADS/JOBS (task): `0 / 0`
RESERVATIONS (task): `0 VND`
PROVIDER_COST (task): `0 VND`
PRODUCTION_WRITES (task): `0`
DEV_WRITES: `YES — isolated project/content/media/render/QC/test artifacts`
SOURCE/SOFTWARE NETWORK: `YES — GitHub/tool/package transport; not zero network`
HOST LIFETIME COUNTERS/DB/RUNTIME: `NOT_VERIFIED — not accessed for this task`
AUTHORITY/O2/RUNTIME/SYSTEMD/SPENT-MARKER WRITES: `NONE`
PUBLIC INGRESS/DEPLOY/MERGE/PUBLISH/NEW RC: `NONE`
CI/HUMAN ACCEPTANCE: `CI recorded after PR; human NOT_ACCEPTED`
RC28 ACCEPTANCE TRANSFER: `NONE`
OLD RUN/CONTEXT: `36998080744 untouched; spent context not reused`
OP2: `LOCKED / NOT_AUTHORIZED; no dispatch`
PR103: `OPEN / DRAFT`, head `827c53cb2c022f48b056c48d8c6951e26d0fcf1e`, read-only reverified, no mutation.

BLOCKERS: professional approved voice/alignment; authorized real speech ASR;
generic creative AI content/media when requested; real-input owner review;
deployed storage/queue/PostgreSQL path, consecutive production E2E, DR/soak and
remaining production acceptance/security gates.
NEXT_SAFE_ACTION: Owner review of source/Draft PR and the isolated MP4 proofs;
choose a separate bounded acceptance plan. **Not executed by this task.**
