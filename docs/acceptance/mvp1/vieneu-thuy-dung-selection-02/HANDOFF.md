# VF-MVP1-VIENEU-THUY-DUNG-SELECTION-02

Owner selected **Thùy Dung**, VieNeu-TTS v3 Turbo, from audition source
`f642e487e89bc8ecf86045c67682a8ec087cd6d2`. This is selection of a production
candidate, not acceptance of new project outputs, deployment or publishing.

## Locked identity

- Provider/model: `vieneu-tts` / `vieneu-v3-turbo`.
- Selected synthesis profile SHA-256:
  `f2d848766784e7bd892680f933a799ec812c1c8acff62b019ac777aa1292c4d3`.
- Model revision: `61b85e3d937fbbacb387714180e8182823512523`.
- SDK 3.8.3, source `85344322b7258b4e25479b692e8e3396baf9db34`.
- Runtime: ONNX Runtime 1.30.0 / CPU / NumPy 2.5.3 / sea-g2p 0.9.1.
- Codec revision: `ceff0d0749bfb3fa2d61149794ec6feef0d1e1ae`.
- Apache-2.0 model/codec/SDK/preset evidence stays pinned in the original
  audition provenance. No cloning or arbitrary voices/endpoints.
- Synthesis: temperature 0.8, top-k 25, top-p 0.95, repetition penalty 1.2,
  max frames 300, max chars 256, zero babble retries. No hidden pronunciation edits.

The exact historical profile is not rewritten. Its historical license-purpose
label still describes the audition; `VieNeuVoiceSelection` is a separate Owner
selection sidecar. Mai Anh and Ngọc Huyền remain loadable for historical audition
replay, but are no longer the configured worker default. The selected worker
factory rejects other voices and altered synthesis profiles. Local execution is
still disabled by default and forbidden in production configuration.

## Real-input lifecycle

`scripts/vieneu-selected-review.py` reuses the existing content/storyboard,
timeline, production package, decoded-audio reflow, Remotion renderer, audio
mix, approval and full-QC implementations. It uses an isolated SQLite/local
object-store harness, **not** a second production platform or a production E2E
claim. Private project media and input manifests must remain outside Git.

An input manifest contains exactly three ordered cases: `image_script`,
`script_only`, `mixed_no_audio`. Each case has `script`, `image`, `video` fields
and a nonempty `script_approval_reference` to the actual editorial decision.
Every supplied file reference contains `path`, raw-file `sha256`, and an explicit
`permission_reference` to the Owner's bounded internal-use decision. Script-only
uses the existing first-party motion graphic; it is not AI-generated video.
Image/script needs an image, and mixed needs an image and actual no-audio MP4.
Magic-byte checks and real ffprobe decoding run before synthesis; source audio
blocks the mixed path instead of being muted or removed. No ASR/resolver/budget
transport is allowed in these paths.

The first invocation requires clean committed source and a fresh output directory.
It saves original inputs/hash references, script, raw TTS units, decoded audio,
estimated caption schedule, storyboard, timeline, A/V review MP4 and QC. It
does **not** auto-approve the movie or render a final. A later invocation with
`--owner-review` consumes the exact MP4 SHA and explicit
`APPROVED_FOR_FINAL_RENDER`/`Owner` decision for each case. The normal persisted
version-bound approval/final path then runs, on the same clean source commit.
An expired/stale package cannot borrow the prior approval. Final-output human
quality review remains separately pending. Two WAVs are not consecutive MVP E2Es.

Example invocation (all inputs/output outside the repository):

```text
python scripts/vieneu-selected-review.py --inputs <private-inputs.json> --output <fresh-review-root> --ffmpeg <ffmpeg> --ffprobe <ffprobe>
python scripts/vieneu-selected-review.py --inputs <private-inputs.json> --output <same-review-root> --owner-review <exact-owner-review.json> --ffmpeg <ffmpeg> --ffprobe <ffprobe>
```

No Owner-review file may be invented by the operator. Google Drive visibility is
not sufficient to infer media rights, project choice or a script approval. Real
project selection/use confirmation and exact output review are still required.

## Acceptance boundary

`ESTIMATED_SEGMENT` / `WORD_ALIGNMENT_OPEN` are unchanged. Decoded audio duration
is measured, not word alignment. Lossless script-to-narration coverage is checked;
machine decode/QC cannot prove correct spoken names or naturalness. Human review
must bind exact new A/V outputs and check pronunciation, project names, warmth,
cadence, pauses, swallowed syllables and long sentences. No auto-selected winner.

All RC28/spent ASR contexts and old audition evidence are untouched. Spoken video
and mixed-with-audio remain blocked without valid ASR acceptance. No external
provider call, secret read, production write, deployment, merge or publishing is
authorized. Actual commands, test/CI results, output hashes and unresolved input
dependencies are recorded in the external task receipt, not inherited from f642.
