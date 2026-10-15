# Studio release of a known terminal B-roll request

The persistent form explicitly inspects the original held internal request.
For a known terminal job, the user acknowledges release, writes one settlement,
then verifies its immutable receipt before the exact pending record is removed.
The old internal controller is replaced only after that proof and trusted CAS;
project data, plans, assets, timeline, preview and approvals stay unchanged.

A lost settlement response requires explicit inspection and receipt verification;
it never automatically retries the POST. Queued, running, absent and receipt-null
requests remain held. The server retains the original operation, job and output.
If local CAS completion or rebinding is uncertain, Studio stays blocked and asks
for a page reload. It does not restore over another request or report success.

WAVE: 3 — Mode B, internal B-roll terminal recovery UI.

STATUS: Scoped UI/controller increment implemented and Node-tested; full wave PARTIAL.

HEAD SHA: `9e58b6b494c9cbfa551561858dba9e7b618f0bab` (product commit).

CAPABILITIES COMPLETED: Explicit inspect/acknowledge/settle/immutable-read controls;
renewed same-actor proof over the original intent; guarded exact raw removal;
safe old-controller replacement; lost-response readback and peer edit fences.

CAPABILITIES PARTIAL: Witness-aware preparation Root UI, complete Mode A/B and
original A/B/C; real browser usability, provider and Owner acceptance.

TESTS: Primary full Studio 2,038 PASS, zero failure/skip, 28,035.6224 ms. Author
final N2 full Studio 1,970 PASS/27,700.6221 ms includes 55 new cases. Independent
final N2 adds two Root/CAS probes. Prior N1 has 282 affected PASS and four
independent probes; those are historical N1, not separate final-N2 runs.
Two expected RED post-CAS recovery cases close in N2. Counts overlap; do not add.

REAL PROVIDER TESTS: None. No new model, media decode, render or external request.

MOCK TESTS: Actual shipped controllers and extracted Root functions with fixture
DOM/transport replay two captured owned SQLite/main-ASGI terminal scenarios.
The 547,474-byte wrapper contains fourteen raw records. The succeeded capture
uses renewed credentials/source drift; the additional cancelled capture is a
persisted terminal fixture, not proof of a cancellation API or worker execution.

EVIDENCE: [Hashed support index](north-star/broll-terminal-studio-evidence.json),
N2 source ZIP/patch, original N1, RED/GREEN logs, final full tests, independent
reviews, exact raw fixture, author branch and verified recovery bundles.

REGRESSIONS: Final frontend checks pass; six existing proof callbacks and all
old controller modules remain exact. The newer witness attribute rule is kept.
Raw fixture physical/Git SHA matches. Backend source is unchanged; its preceding
29-case combined main-route check belongs to the previous backend increment and
was not needlessly rerun for this UI-only change. Full data snapshots stay exact
on success, foreign request, authority drift, controller disposal and CAS failure.

EXTERNAL BLOCKERS: Browser observation is denied by URL policy. Viewport/operator
usability, actual PostgreSQL/Redis, genuine providers and complete original human
acceptance remain unverified; Node/DTO tests do not substitute for those checks.

OWNER ACTION REQUIRED: None for safe implementation. Deferred Phase 10 UAT stays
pending. No actual approval, publishing enablement or deployment is inferred.

NEXT WAVE: Integrate the separate witness transport helper and explicit optional
preparation UI; complete versioned per-scene generative suggestions and the rest
of the original North Star. Unknown ownership still fails closed.

SOURCE_PRESERVED=YES; IMPLEMENTATION_COMPLETE=NO;
REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO.
The matrix stays 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED:
59 broad groups remain unclosed. No full Mode A/B or North Star readiness claim.
