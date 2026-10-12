# Meta media analytics: scoped API count readers

Master Spec sections 48/49 now have explicit Instagram Reels and Facebook count readers connected to the existing API analytics provider, durable sync queue, observation history and operation cost ledger. This is an API/backend component for Wave 10. Native account configuration/collector/refresh/Studio controls, genuine scoped OAuth and audience data, further platform metrics, production and full original Mode A/B/A-B-C acceptance remain open. No broad readiness state is promoted.

`apps/api/app/analytics_meta.py` uses the existing official HTTP wire and publishing target binding. Its client accepts only the configured Graph API version, `graph.facebook.com`, GET, and closed query shapes. It cannot publish, upload, delete, follow pagination, read comment text or return arbitrary fields. This increment adds no automatic startup client, token read or network activation. The existing execution flags and explicit live cost policy remain required; credentials are supplied through the established runtime resolver.

The separate read credential requires an explicit API version, numeric Page ID, target/workspace/profile binding, expiry and closed read scopes. A Page token is verified through `/me`. Instagram also requires its linked professional account to match the target, then verifies the exact media owner and REELS product type. Facebook verifies the Page and exact video `from` owner. The publication receipt, workspace, active sync attempt, account target, credential lifetime and runtime flags are rechecked before each operation; changes of Page/API-version profile between operations block further reads.

| Platform | Normalized fields | Observation basis |
| --- | --- | --- |
| Instagram Reels | views, reach, likes, comments, shares, saves | Exact-media lifetime insights; `saved` maps to saves |
| Facebook | views, likes, comments | Exact-video node views and empty-data edge summary counts |

Unsupported or missing values stay null. Counts are not rounded/coerced from strings, booleans, negatives, nonfinite values or integers beyond exact numeric representation. Media lifetime counters cannot accept a date-range query. They are not impressions, a measured exposure window, account totals or daily interval growth. Meta publication-time evidence remains null, with no fallback to receipt or collection time.

Watch time, average watch duration, completion, followers, CTR, revenue and RPM are not inferred. The official SDK names watch-time metrics but does not establish their units in the source snapshot used here. Facebook's detailed `video_insights` definitions/version support and additional metrics still require verification. The current Facebook adapter provides node counters; it does not claim the full video-insights metric set or calibrated view semantics.

Meta rate-limit HTTP responses and closed Graph rate-limit codes use the existing bounded retry/history path. Authorization and unsupported-metric errors fail with sanitized codes, without guessing a fallback or converting errors to zero. Every read uses the existing operation ledger. Mock responses stay marked mock and never become real audience evidence or authorize publishing, deletion, media spending or deployment.

## Verification

48 new API tests pass: request/credential/normalization contracts plus both platforms through owned SQLite sync processing, immutable refresh history, exact key replay, repository reopening, cost records, foreign account/media refusal, changed read profile, disabled execution, date-range refusal and rate-limit scheduling. Another 107 existing analytics/HTTP/publication-time tests pass. No Native/Studio/Docker or real-provider test is claimed by these batches. Repository reopening is within the test process; it is not a new production cold-restore certification.

Earlier failed attempts are retained in the evidence index: incorrect URL-parser return handling was fixed; the test fixture omitted its provider primary key and added a forbidden validation field; a test reused immutable request headers as a mutable constructor input. The shared strict contracts were preserved. Only the final passing source/test log is claimed.

## Primary source basis

The Meta developer documentation endpoints returned fetch errors/429 during this increment. A pinned snapshot of Meta's published [IGMedia SDK object](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/master/facebook_business/adobjects/igmedia.py), [InstagramInsightsResult](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/master/facebook_business/adobjects/instagraminsightsresult.py) and [AdVideo SDK object](https://raw.githubusercontent.com/facebook/facebook-python-business-sdk/master/facebook_business/adobjects/advideo.py) verifies endpoint and field names. Meta's [Facebook-Login Instagram collection](https://www.postman.com/meta/instagram/documentation/6yqw8pt/instagram-api) describes the linked professional-account boundary. SDK availability is not proof that a configured version/account/app can return every field; real permissions, eligibility, definitions and provider acceptance remain separate.

See [evidence index](north-star/meta-analytics-read-counts-evidence.json). Exact final source HEAD, preserved historical artifact checks and Git recovery pair are recorded externally in `recovery/20261007/meta-analytics-read-counts-program-state.json`.
