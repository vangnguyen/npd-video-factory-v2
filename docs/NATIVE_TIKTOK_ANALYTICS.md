# Native TikTok analytics and finite Studio refresh

This Wave 10 increment connects the existing provider-neutral TikTok Display API reader to the accepted Native runtime, signed HTTP, Studio, immutable refresh history, qualified winner/learning and Bridge proofs. It reuses the same publication receipt, account registry, cost ledger, Runner, backup and canonical project. It adds no database migration, ORM dependency, credential acquisition or publishing authority.

Implementation parent: `558d9b707f1e96880c588a772a81b6cd869d42c2`. The final committed/pushed HEAD and fresh accepted-artifact verification are recorded in `C:/Users/PC/Documents/ChatGPT/Video Factory/recovery/20261007/tiktok-analytics-preservation.json`; offline source recovery uses the full-base plus incremental pair in `tiktok-analytics-recovery-pair.json`.

## Read contract

YouTube retains its existing v1 dated report request, consent, result, refresh policy and history. TikTok uses the closed v2 counter contract: `query=null`, `metric_scope=cumulative_video_counters`, and one explicit numeric `remote_post_id` that appears in the completed original receipt's `public_post_ids`. Multiple IDs are presented for explicit selection. The provider's publishing job ID, private-only publication and an unrelated post cannot substitute for an actual public post ID.

The reader confirms the configured `open_id` with `GET /v2/user/info/`, then sends one exact authorized ID to `POST /v2/video/query/`. Both operations have durable response hashes and nullable cost records. It requires separately configured read credentials and the official `user.info.basic` and `video.list` scopes. Publisher credentials, dry-run results and account checks do not grant analytics consent. No private token, credential path or upload URL enters a public DTO.

`views`, `likes`, `comments` and `shares` preserve nonnegative counters, zero and missing values. Unsupported impressions, reach, watch time, average view duration, completion, saves, follower gain, clicks, CTR, revenue, RPM and observation-window duration remain null. Empty responses do not claim an owned video was returned. No dated report coverage, publication age, velocity or revenue is invented from cumulative counters.

The protocol follows official [Video Query](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-query), [Get User Info](https://developers.tiktok.com/docs/en/tiktok-api-v2-get-user-info) and [Video Object](https://developers.tiktok.com/docs/en/tiktok-api-v2-video-object) documentation. Real app eligibility, permission grants and response compatibility still require separate acceptance.

## Runtime and Studio

The existing analytics and refresh gates remain disabled by default. Protected runtime configuration supplies the read factory; startup does not decrypt credentials. Signed routes enforce workspace identity, RBAC, CSRF, exact publication/receipt/configuration hashes and current finite consent. Local dispatch fences now load the complete verified receipt before comparing the selected post. Retries, rate-limit backoff, expiry, cancellation, ambiguous outcomes and restart recovery keep their existing limits and never renew consent automatically.

Studio explicitly reads the source and operator configuration before accepting consent. TikTok exposes actual receipt ID choices and hides date/revenue controls. A finite plan requires a separate background-read acknowledgement, fixed post/account/source, aware start/deadline, maximum runs, interval and bounded retries. Every child read preserves the chosen post, creates a new immutable observation and retains two provider response references. Reading stored history is available with factories, collector, scheduler and publishing disabled.

Qualified winner proofs carry a null query and `matching_native_official_cumulative_counter_scope`. The existing scoped recommendation policy still applies. Learning cannot promote missing retention/completion or protocol mocks into real audience evidence. The retained technology-profile fixture produces `insufficient_data`, zero eligible learning observations and no automatic action. Its configured niche is a real catalog selection; media, provider responses, human approval and audience data remain explicit fixtures.

## Verification and limits

`docs/north-star/tiktok-analytics-evidence.json` indexes final logs, source-bound public DTOs, backup hashes and retained failures. The signed Studio rehearsal uses actual HTTP and the real controllers with a fake DOM; it is not a rendered browser or non-developer UAT test. Two public receipt IDs, one manual read, one finite scheduled read, two immutable observations, scoped winner/learning and a separate-process keyless restore are exercised. It leaves the canonical project unchanged and makes no provider, paid, real publishing or production call.

The full Studio suite has 631 passing cases, including 12 new counter/source/role/late-response/finite-refresh checks. Native collector/HTTP/observability checks and 120 related YouTube/refresh/winner/learning/Bridge regression cases are recorded separately; overlapping runs are not added into a unique-test total. Full Native/media/renderer/Docker regression is not claimed.

The initial import/receipt-fence, fixture timestamp/logger, legacy test expectation and rehearsal control/qualification/POST-response comparison failures are retained. Final checks use the pure Native import boundary, full verified receipt, catalog-configured fixture scope, correct actual control IDs and persisted GET history. No failed evidence or accepted media was overwritten.

Remaining requirements include genuine TikTok read acceptance, Meta analytics, browser/non-developer review, channel/time-series comparison, broader winner calibration and learning feedback, every outstanding Mode A/B requirement and full A/B/C media bundles. Docker, isolated production, soak and deferred Owner UAT remain separate. The matrix stays 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED; 59 broad groups remain unclosed. Full implementation, real-provider acceptance, deployment and North Star readiness remain NO.
