# V3-01-25 — W1 Prompt Profile Remediation

## Post-merge closure — 2026-09-09

Owner G-08 approved exact PR #54 head `f2760e52f98336f17f67fabcf7f93edc94d88b38`.
PR #54 merged as `55b22f773dc108f6c51a1b52db825b1caa8e8a51`; exact-main CI
[`34302351310`](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34302351310)
passed 5/5, and annotated `vf-v3-01-rc16` (tag object
`f18659863bc818c307b4679eec8bc3ec8bc5439a`) peels to that exact merge. Canonical executable-tree
SHA-256 is `5025279241fb0b55e6fa26cc850c82a1fd5e4dc9fc4e15c43f716f50441e6ecd`.

This closes only the source remediation/RC lock. It does not authorize W1 live use. The fresh
[RC-16 governance rebind](62_V3_01_RC16_OPENAI_ASR_W1_GATE.md) remains unmounted and requires a
separate G-08, post-merge governance CI and later separate Operation 1 decision. No provider call,
credential read, live reservation or spend occurred during merge/lock.

## Decision and boundary

**DRAFT / OWNER G-08 REQUIRED. W1 selected for remediation, not live use. Production NO-GO.**

PR #53 was merged only after the approved exact head
`874482bd65df24c6d05fdb3bbbc0e1950664235f` was verified with green CI and zero unresolved
review threads. Exact post-merge main is `b9dbb8fd8f1abcbcc920f0df9fb5a343586b7b0e`;
[main CI 34246957872](https://github.com/vangnguyen/npd-video-factory-v2/actions/runs/34246957872)
completed success, 5/5 jobs including Docker deterministic E2E. Local exact-main Python
regression passed 659 tests before this separate source branch was created.

This remediation performs **0 provider calls, 0 credential reads, 0 live reservations,
0 VND spend**. Test resolvers, HTTP transports and disposable ledgers are synthetic only.
No bundle mount, provider activation, new operation, automation, RC/tag, deployment,
publishing or public ingress occurs. W2 and GPT/alignment alternatives remain deferred.

## Exact shared W1 input

[Canonical public profile](contracts/V3-01-25-W1-PROMPT-PROFILE.v1.json):

> Ngọc Phương Đông, Vinhomes Green Paradise, Cần Giờ, tham quan sa bàn, chính sách bán hàng.

Same immutable profile on both assets; no asset-specific prompt, PII, reference transcript,
customer data, instructions to rewrite output or post-processing dictionary. The profile
fixes `whisper-1 / vi / verbose_json / [segment, word]`; temperature is **omitted**, as in W0.
These words are input vocabulary context, not a promise that the provider will recognize
all eight critical terms. No quality improvement is claimed without new reviewed evidence.

| Binding | Exact value |
|---|---|
| Profile ID | `asr-whisper-vi-w1-v1` |
| Prompt UTF-8 bytes | 105 |
| Exact prompt SHA-256 | `6985c297816ea6dc9be2d46b538495704f524ab7ed751f95f9575841c5bd6b48` |
| Canonical full profile SHA-256 | `9c4a7609db9f08c191af297a41d7a21b58bfe539ac5e100ea534196d17776ab1` |
| Ordinary raw-text tokens | 34 |
| Upstream `" " + prompt.strip()` context tokens | 33 |
| Context UTF-8 SHA-256 | `7cf8e972dc834af0022b139a1ba123bcefe6fea34f9d8112fc9eee074c5ad035` |
| Pinned counter | `tiktoken==0.12.0`, local Whisper multilingual ranks |
| Ranks SHA-256 | `b34b360dbb493e781e479794586d661700670d65564001f23024971d1f2fa126` |

Both ordinary-text counts are below the documented 224-token Whisper prompt limit. They
are deterministic **offline source-derived counts**, not a hosted-service observation or
complete control-token stream count. Public rank data (816,730 bytes; 50,257 ranks), MIT
license and upstream commit are vendored; hash/size/rank coverage and package version are
checked. No model weights, Torch, inference or network-backed encoding registry is used.
The packaged wheel was checked for module, ranks, license and provenance inclusion.

## Canonical binding and fail-closed execution path

`Settings selector → canonical profile → verified bundle/scope hash → call context →
shared durable/non-durable preflight → adapter frozen snapshot → request manifest/hash →
provider provenance → expected-profile offline evaluator`.

The source supports only empty/W0 or the exact W1 selector. Runtime defaults remain
fixture, model empty, selector empty, external/paid false, budget 0 and kill switch engaged.
There is no checked-in W1 execution bundle or enabled config.

- All profile fields are required, immutable, exact-typed and hashable. Fresh validation
  rejects missing/extra/changed fields, unsupported prompts, explicit temperature and
  mutation through `model_copy`/`model_construct`.
- W1 profile plus derived hash enter the execution-scope hash. G-01/G-02/G-03 must all
  bind that new scope; monetary limit names and 500/1,250 VND limits are not altered.
- Scope/profile mismatch, W1 under an unverified gate and W0/W1 substitution deny before
  any durable operation row or reservation. Both controllers use the same check.
  The entire ASR execution-scope hash is recomputed from canonical fields, not merely
  compared to the profile hash; paired insertion/removal of profile plus hash cannot
  promote an old W0 scope to W1 or strip a W1 scope back to W0.
- Service snapshots provider/profile before cache lookup and dispatch. A W1 profile hash
  changes the analysis fingerprint, preventing reuse of cached W0 output. Adapter validates
  expected profile and model/language/format/timing fields before credential resolution.
  The profile hash is also snapshotted then; evidence serialization after dispatch does
  not reopen tokenizer data. Artifact loss after a mock response preserves that result's
  metadata, while the next preflight still fails closed.
- Multipart adds exactly one `prompt` field for W1; W0 manifest and request remain unchanged.
  Prompt metadata is public; credential values are never added to evidence. Provider text,
  timing, nullable confidence, cost and raw response hash are not rewritten.
- Provider boundary-point semantics and `PositiveDurationTranscript` remain unchanged.
  Scene, silence, persistence and edit consumers still require real positive-duration intervals.

## Read-only quality and negative-insertion guard

WER **≤15%** and all **8/8** critical terms remain mandatory. Matching preserves Vietnamese
diacritics and contiguous full phrases; no fuzzy, semantic, synonym, partial, post-correction
or reference rewrite is introduced.

The W1 guard binds the original owner-confirmed asset/reference manifest hash, exact reference
bytes/hash/path and each exact eight-term list. It counts all five prompt vocabulary phrases
in hypothesis and reference using the existing NFKC/case/whitespace/punctuation normalization.
Any excess occurrence is `W1_PROMPT_TERM_INSERTION`: this also catches repeated insertions
in asset 01. Asset 02's reference contains **none of the five phrases** and is the mandatory
negative-insertion control. Neither WAV nor its reference/RightsRecord is changed.

Expected profile is selected by the trusted caller from the verified gate, **not inferred
from receipt metadata**. Future W1 evaluator invocation must supply
`--expected-asr-prompt-profile-id asr-whisper-vi-w1-v1` (or the equivalent function keyword).
The input binding and retained provider provenance must both match the canonical profile
and hash. Removing all metadata while expected W1 is supplied fails closed. A W1-looking
receipt without an explicit expected profile also fails. A legacy W0 evaluation without
`w1_prompt_quality` cannot satisfy W1 acceptance, even if its generic verdict is PASS.

`insertion_guard_passed` describes this guard only, **not overall quality**. Missing cost or
provider evidence remains REVIEW_REQUIRED; secret failure remains FAIL. Machine occurrence
checks do not prove all hallucinations absent or perform human audio review. Future owner
review must still compare audio/transcript and the complete evaluator, not this boolean alone.
Tests use synthetic envelopes, never recorded/live W1 success evidence.

## Immutable history and RC impact

RC-15 `7d1290aacac61df98a51544731243e5e322a8644` remains the historical locked candidate.
Op1 remains provider SUCCESS, structured/timing/WER PASS, critical terms **5/8 FAIL**,
acceptance **FAIL / CONSUMED**, actual **326.294996 VND**; Op2 NOT APPROVED / LOCKED.
ASR consecutive stays **0/2 PASS**; Vision stays **2/2 PASS**. Original RC-15 receipt hashes,
references and diagnostic comparison files are unchanged. W0 replay output hashes remain
identical. Old V3-01-24 strategy/manifest files remain dated evidence at their recorded base,
not current approval or current-file inventories; this document supersedes their pending W1 decision.

Canonical runtime-tree SHA on post-PR53 main equals RC-15:
`9fab766b285eb2db580032b914eb2ccdf474d18b3958fd218a73a22fb75701e8`.
This PR intentionally changes runtime/source (`apps/api/app`, API dependency/package-data),
and separately changes offline evaluator/schema. **A new RC is required after G-08, merge
and exact-main regression, but no RC-16 is created here.** Runtime-tree equality must not be
claimed for this source remediation.

New source runtime-tree SHA (computed from the staged Git trees at the same 13 canonical
paths): `5025279241fb0b55e6fa26cc850c82a1fd5e4dc9fc4e15c43f716f50441e6ecd`.

## Verification and next gate

Focused profile, gate/controller, adapter/cache/evidence and negative-insertion suites run
entirely offline. Full Python/API/worker/bridge, Studio, Renderer/typecheck/bundle, migration
upgrade/downgrade/replay, Flow A/B/C and DR acceptance boundaries, compatibility/evidence,
JSON/schema/hash/link/secret checks and diff checks are required. Exact-head CI must pass
all five jobs, including Docker E2E, before Owner G-08. The PR reports exact results/run ID.

Local final Python regression: **895 PASS** (659 baseline + 236 added tests: profile 129,
gate/safety 45, provider/cache/evidence 28, quality/insertion 34). Migration 0013 upgrade →
base downgrade → head replay PASS. Acceptance register: 60 rows, 16 gaps, 35 evidence runs
validated. Historical RC-15 original/derived evidence verification PASS; W0 result hashes
unchanged. JSON/schema, rolling 33-file checksums, links, scoped secret scan and diff check PASS.
[Machine-readable review](evidence/v3-01-25-w1-prompt-profile/review.json) binds the profile,
source/base, unchanged history and zero-call validation boundary; it is not an execution bundle.

Studio and Renderer each passed 14 tests locally. Renderer lockfile is unchanged and reports
two existing transitive audit findings (one high, one moderate); remediation does not run
`npm audit fix` or broaden dependency changes. New Python dependency is the exact pinned
offline tokenizer, not an ASR model or provider SDK activation.

Stop at **Owner G-08 for V3-01-25**. Only after a separate approval:
merge → exact-main regression → lock RC-16 → new ASR IDs/scope/bundle/window →
rebind G-01 model/input profile, G-02 cost/timeout/scope, G-03 exact asset/reference/rights
and prompt-purpose scope → governance PR/review → separate Op1 authority. Same media may
be reused only after hash/rights/expiry revalidation. No old authority is reused; no Op2 now.

## Official sources inspected 2026-09-08

- [Speech-to-text guide](https://developers.openai.com/api/docs/guides/speech-to-text):
  vocabulary prompting and Whisper prompt limits; no guarantee of term accuracy.
- [Transcriptions API](https://developers.openai.com/api/reference/python/resources/audio/subresources/transcriptions/methods/create):
  prompt/language/verbose JSON/timestamps and temperature behavior. Temperature omission
  is preserved, not represented as deterministic provider output.
- [Pinned Whisper tokenizer](https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/whisper/tokenizer.py)
  and [decoding implementation](https://github.com/openai/whisper/blob/86098128c0b4f24f0e2aa2994de830614b474227/whisper/decoding.py):
  regex/ranks and context prefix basis. This is open-source inspection, not hosted API telemetry.
- [Pinned tiktoken source](https://github.com/openai/tiktoken/tree/97e49cbadd500b5cc9dbb51a486f0b42e6701bee):
  local Encoding API; see packaged data provenance/license for exact artifact hashes.
