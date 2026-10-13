# Meta counter feedback in the SQL/API runtime

The production API code now uses the same separately versioned counter policy as Native Meta. This component is implemented and mock-tested over owned SQLite and authenticated ASGI. It does not certify PostgreSQL/Docker deployment, genuine audience metrics, full runtime parity, original Mode A/B or Owner acceptance.

New Instagram/Facebook collection assessments always use winner-meta-counter-assessment-v1. Invalid or incomplete definition/context evidence stays insufficient instead of falling through to the old retention-based algorithm. Unverified genuine semantics also stay insufficient; the test for this guard injects a genuine flag into an explicitly synthetic response and is not real-provider acceptance.

Comparable cohorts freeze Meta API version, metric scope, mapping, units, returned/unavailable metrics and semantics verification. Malformed definition shapes fail closed without logging private values or serialization exceptions. The current and peer render contexts must verify workspace/project/timeline/hash/niche and matching render profile/duration bucket. Account/target/provider/transport scope, distinct remote posts, latest compatible records and bounded scans remain enforced. Cumulative counters never produce inferred publication age, velocity, retention, completion, watch time or revenue.

The existing processor is exercised with six seeded posts whose explicit synthetic count responses are parsed by the real Meta normalization kernel. Definition availability comes from these same responses, rather than being copied from an incompatible observation. Cohort tests first match six peers, then exclude changed API version, availability and semantics to retain three peers. Mock provider processing yields an explainable Instagram candidate and insufficient Facebook result because sharing/saving evidence is absent.

Learning snapshots freeze the counter algorithm/definition and isolate old retention-based assessments. Instagram fixtures produce six eligible observations; Facebook keeps zero. Different API/units/algorithm rows are excluded. The initial partial Instagram response is also correctly excluded from the complete-definition study. Idempotent replay returns the original snapshot, and later source changes do not overwrite its frozen content. Authentic ASGI Owner creation/read and Viewer write rejection follow the existing SQL API RBAC contract; Native's separate role contract is unchanged. Existing qualified consumers use these stored recommendations without automatic creative or budget changes.

Missing posting-window evidence stays null. Counter limitations explicitly distinguish engagement associations from retention/causality. No new provider calls, deployment, webhook, timeline edit or publication occurs outside the test fixtures. The previous Native/Studio/browser acceptance evidence remains valid and is not counted as a new current browser run.

See [indexed evidence](north-star/meta-counter-sql-feedback-evidence.json). Earlier retained failures included an unavailable model property and a synthetic collection clock ordering mistake. A new genuine-flag guard test also caught an attempt to mutate a frozen assessment draft, causing retry instead of a terminal insufficient result. The processor now replaces the immutable draft, and the guard tests verify succeeded collection with insufficient assessment. No failed run is accepted. The final source, checkpoint and bundle pair are recorded in workspace recovery/20261007/meta-counter-sql-feedback-program-state.json after reviewable commits and branch push.

WAVE:11/12 SQL/API counter-feedback component;15 regression/source preservation
STATUS: implemented/mock-tested component; complete waves remain PARTIAL
HEAD SHA: source parent1ab9201c23d75b094ac94e37bf64f181c7153c0d; final external seal as above
CAPABILITIES COMPLETED: distinct counter processor policy; exact Meta definition/cohort scope; frozen current render validation; immutable scoped learning; authenticated route and fail-closed guards
CAPABILITIES PARTIAL: real provider/cohort/feature calibration; production PostgreSQL/Docker/runtime parity; new Meta webhook/Hub; self-contained replay CI input; original full Mode A/B/A-B-C/Owner acceptance;59 groups unclosed
TESTS: API_new 17 PASS; API_regression 98 PASS; Native_regression 35 PASS
REAL PROVIDER TESTS: none
MOCK TESTS: explicit HTTP/identity/publication/count/frozen-label inputs; ORM/processor/ASGI run locally
EVIDENCE: linked index; final test logs; retained earlier failures; source checkpoint/bundle pair
REGRESSIONS: existing API and Native winner/learning paths pass;15 accepted artifacts/live source checked during seal
EXTERNAL BLOCKERS: genuine OAuth/account/metric/Owner/provider/production gates remain separate
OWNER ACTION REQUIRED: none for safe continuation; previously deferred UAT remains deferred
NEXT WAVE: Meta webhook delivery/isolated Bridge proof and remaining original production/full-flow gaps
