# Native Trend Radar and frozen channel feedback

Native Studio now has a capability-gated top-level Trend Radar. It reuses the
Video Factory provider contracts, opportunity scoring, descriptive learning
aggregation and personalized ranking rules. The accepted API Radar and its
tests remain separate and unchanged. No Agent Hub package, database, Redis
namespace or process memory is shared.

## Collection and evidence

All default providers, including deterministic fixtures, are NOT_CONFIGURED.
Page reads never collect signals. An Owner explicitly queues a configured
provider; fixture collection additionally requires a fixture acknowledgement.
Editors can refresh estimates and select an opportunity. Viewers can inspect
saved signals and scores. Existing session, origin, CSRF, rate limit and RBAC
guards precede body parsing. Request keys are hashed for durable exact retries;
conflicting requests reject. Lost browser replies never cause automatic POSTs.

Collections, normalized observations, clusters, assessments, handoffs and learning
snapshots live in the existing independent `intelligence.sqlite3`, with the
existing append-only versions, hashes and decisions. Initialization adds an
index, not a destructive migration or document rewrite. Collection claims are
atomic; cancellation blocks late commits. Queued work survives restart. Interrupted
running work is marked failed without automatic provider replay. A matching
successful collection can be reused for 15 minutes, preserving observation dates.

Raw metrics remain null when unavailable. Every signal retains provider/config
identity, source reference, observation time, normalized raw hash, evidence text
and source collection. Provider publication dates are separate. Source references
grant no right to download or reuse creator media. Source confidence concerns
the receipt or quotation, not truth, virality or a performance prediction.

## Approved RSS / Atom

`TrendSourceProvider` includes collect, topic search, metrics and reference methods.
The RSS adapter supports explicitly approved public feeds. It uses the existing
DNS-pinned public HTTPS retrieval, checked redirects, TLS verification, bounded
body/decompression and timeouts. RSS/Atom XML content types are explicitly allowed
for this adapter; the existing research text defaults are unchanged. DTDs and
entities reject. Dates and titles are retained; enclosures are never downloaded.
Social counters, velocity, acceleration and locale stay null if not supplied.

Use an outside-state JSON registry with `schema_version` equal to
`native-trend-feed-registry-v1`, the exact Native `workspace_id`, and `feeds`.
Each feed requires `provider_key` starting with `rss-`, `display_name`, a public
`feed_url`, optional country/language, and `owner_access_approved: true`.
Launch with the existing human auth/workspace options plus
`--trend-feed-registry <path> --enable-trend-feeds`. This explicit configuration
is necessary; no feed is enabled or fetched by this implementation. Registry and
workspace mismatch fail closed. Authorized social/search API adapters and actual
RSS/provider acceptance remain required; they do not fall back to fixtures.

## Clusters, lifecycle and scores

The versioned clustering policy combines keyword and hashtag similarity, entity
overlap, compatible provider-supplied embeddings, temporal distance and
cross-platform co-occurrence. Embeddings are optional, bounded, model-labelled and
not synthesized by this layer. Every selected similarity edge preserves its
components and available evidence. Temporal coincidence alone cannot merge topics.
Family identities reuse retained references or canonical topic keys; each refresh
preserves prior cluster versions and immutable assessment snapshots.

The seven lifecycle states use the shared available-metric/age heuristic. They
are estimates. Opportunity weights are configurable per frozen channel, niche,
target platform and objective. Neutral or fixed scoring defaults are explicitly
labelled, including unavailable saturation/engagement and placeholder rights/
policy risks; they never become raw metrics or publishing approval. Native detail
shows source observations, historical lifecycle versions and score explanations.
Bounded scans and truncation are recorded. Current views deduplicate each context
before applying lifecycle filters, so an old breakout does not reappear after a
new declining assessment.

Studio includes Trending Now, Rising Fast, Breakout, Early Signals,
Cross-platform, Low Competition, High Monetization Potential and Near Saturation.
Filters cover source platform, country, language, niche, channel, time range,
format and objective. Low-competition/saturation filters require the relevant
provider counts. Monetization is a configured planning estimate. Responsive CSS
covers 1366/1920/2560 layouts; actual browser/non-developer/Owner UAT is unverified.

## Trend → research → idea → production

Selection freezes the exact assessment, raw signal hashes, channel selection and
reference-only policy. It atomically creates the existing research draft and
content opportunity with an idempotent handoff receipt. It performs no research,
paid idea generation, voice inference, rendering or publication automatically.
The existing explicit research/idea/brief approval workflow remains in use.

Approved production freezes this context in the existing validated lineage and
applies the configured channel/niche/brand defaults. New guided narration review
uses the same canonical timeline. Analytics features read that frozen render
context, preserving trend family and channel hashes; current project edits cannot
retroactively change the published features. The independent bridge outbox captures
estimated trend opportunities and remains usable without a Hub receiver.

## Channel-history learning

The Native adapter reads actual retained Native analytics snapshots and their
frozen publication/render/channel bindings. It chooses latest distinct
publications in a bounded consistent read, requires matching platform/channel/
niche and factor coverage, and excludes insufficient or incompatible assessments.
It reuses the shared minimum-group/control and median-association rules. Missing
feature values and publishing times remain null. It cannot accept arbitrary
client-provided scores or channel-history assertions.

Native official analytics remains NOT_CONFIGURED. Explicit fixture snapshots
remain mock throughout learning and personalized ranking. Fixture history cannot
rank real trend signals. Insufficient observations make no ranking adjustment.
Recommendations never edit projects, publish, delete media or change budgets.
Actual official channel/account/winner history, real feedback acceptance and full
Artifact C remain program requirements.

## Publishing gap and measured QC

The local rehearsal exposed a storyboard publishing projection gap: measured
dimensions/codecs were nested inside full QC. The publishing adapter now projects
those exact measurements only after checking the full QC status, document hash,
final hash and checksum. The certified legacy/Source envelope stays unchanged.

Generated voice/model provenance still blocks storyboard publication, including
dry-run admission. Source-image exceptions cannot clear this independent gate.
The rehearsal retains that blocker, rejected publishing approval, unavailable
official analytics, zero learned observations and unchanged recommendation ranking.
It does not fabricate a completed publication, analytics snapshot or winner result.
The next publishing increment must add reviewed generated-voice provenance without
weakening unknown-rights, exact-artifact or human publish approval requirements.

## Evidence boundaries

`scripts/north_star_native_storyboard_qc.py --narration-preparation --local-tts
--trend-radar` exercises actual signed-human HTTP, Native queue/persistence,
installed locked local TTS, measured canonical timing, audible preview, final
original-PCM reuse, full FFmpeg/libass QC, frozen-preview rejection, both databases
in backup/restore and separate-process checkpoint replay. Trend, research, ideas,
authored images/script and human legal/production approvals are explicit fixtures.
No market trend, independent research, semantic Vision, speech/Owner acceptance,
real publication, provider analytics, paid operation or deployment is inferred.

The index `north-star/native-trend-radar-evidence.json` and wave report retain
failed rehearsals/tests and the final verified source hashes. The separate
six-publication unit fixture proves compatible channel-learning recommendation
behavior; it is not observed audience history or a playable-media certification.
Full Mode A/B and original North Star acceptance remain incomplete.
