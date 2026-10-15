# Optional witnessed B-roll preparation

The preparation controller can explicitly read witness availability and, when
configured and acknowledged, obtain and verify proof before storing an optional
v2 pending record. The existing prepare method keeps its v1 default. The witness
proves the original authorization; it never asserts that execution was absent.

The exact original v1 intent remains a literal string inside the v2 record.
The envelope and both hashes bind that original request. Cold recovery and
retries neither re-sign nor downgrade it. An expired, revoked, malformed or
unverifiable proof remains held. All durable writes/removals retain request
ownership and fresh source/session checks across awaits and storage reads.

This is a controller/API increment. The current Root transport admits only v1
raw records and old routes. It deliberately rejects the new flow until a
separately reviewed adapter and explicit UI controls are integrated. No user
setting or real key has been enabled here.

WAVE: 3/8 — Mode B recovery and authorization increment.

STATUS: Component implemented and locally/mock tested; full waves remain PARTIAL.

HEAD SHA: `61ada558f6dce4163d9c21b1da170c495d5752e5` (controller product); API product
`494950626c925ab45629b387ce63496237806d77`.

CAPABILITIES COMPLETED: Explicit status GET, optional issue/verify-before-store,
exact v2 durable wrapper, immutable signed recovery proof and held-record fences.
The shared private guard now rechecks the live API switch after SQL awaits for
status, issuance and verification; it rejects before further key reads.

CAPABILITIES PARTIAL: Root route/raw admission and opt-in UI, complete original
Mode A/B, general unknown job recovery and full provider/human acceptance.

TESTS: Final author API 21 PASS/64.90 seconds; affected Node 340 PASS/11.292 seconds
with 62 new cases. Independent review adds three actual SQLite/ASGI cases
(10.11 seconds) and two Node cases (385.5962 ms). Primary integration passes
29 SQL/API cases in 101.74 seconds and the complete current Studio suite:
1,983 PASS, zero failure/skip, 18,004.5278 ms. These runs overlap; do not sum them.

REAL PROVIDER TESTS: None. Keys remain NOT_CONFIGURED; no paid/external request.

MOCK TESTS: Ephemeral fixture key/identity, owned SQLite and actual-main ASGI;
Node replays captured DTOs through fixture transport. The 27-request two-scenario
capture predates the API-guard-only repair; its happy DTO contract is unchanged,
while the final API tests bind the repaired source. No old capture is relabeled
as a new source execution. No media decode, model or render was performed.

EVIDENCE: [Hashed support index](north-star/broll-witness-pending-evidence.json),
frozen source N3, author branch/bundles, independent reports, captures and logs.
The exact 610,099-byte DTO fixture has equal physical/Git SHA256; one narrow
attribute preserves its raw EOL. Newer Root attributes and routes are retained.

REGRESSIONS: Final scoped and full Studio checks pass. Historical N1 kept a
queued microtask window after helper return; five RED cases close in N2. N2
then exposed the live API switch defect through three independent RED cases;
N3 closes it. Earlier failures, interrupted buffered runs and all source ZIPs
are preserved, never counted as final acceptance. Four frontend source files
remain exact N2 after the API-only N3 repair; no duplicate broad Node rerun was
needed before the primary combined full suite.

EXTERNAL BLOCKERS: Actual browser observation is policy-denied. Dedicated real
key configuration/provider acceptance, production PostgreSQL/Redis, Owner UAT
and original full A/B/C acceptance remain separate.

OWNER ACTION REQUIRED: None for safe implementation. Phase 10 UAT stays deferred.

NEXT WAVE: Integrate the reviewed Root transport adapter and explicit optional
controls after the separate terminal-release UI increment is preserved. Keep
default v1, publishing disabled, immutable evidence and unknown ownership held.

SOURCE_PRESERVED=YES. IMPLEMENTATION_COMPLETE=NO;
REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO.
The primary matrix stays 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED:
59 broad groups remain unclosed. This component does not certify Mode A/B.


## Transport helper component — still not mounted

WAVE: 3/8. STATUS: Additive helper implemented/mock-tested; full wave PARTIAL.
HEAD SHA: `7d4741e5276a8e3eb8614b7be08a5e4428db938e`.

CAPABILITIES COMPLETED: One private transport instance per explicit operation;
strict scoped route/body admission, original pre-durable issuer body/envelope,
v1/v2 exact raw descriptor, immutable options and fresh guards across every await,
native storage read and helper-return boundary. Failed issuance poisons that
operation; no fallback, new key or automatic request is authorized.

CAPABILITIES PARTIAL: Root import/hook, storage admission, complete private
callback receipt proof, opt-in controls and actual browser/operator acceptance.
The helper cannot replace those Root checks and does not adopt or clear data.

TESTS: Author 54 PASS/17,814.6167 ms; primary 54 PASS/17,009.4548 ms; independent
five new Node cases PASS/2,272.4911 ms. They use the actual common controller
and four exact source dependencies with captured SQL/ASGI DTO transport fixtures.
No new SQL or external provider result is inferred. The preceding full Studio
2,038 PASS belongs to the pre-helper source; this unused additive module did not
justify another broad run. Counts overlap and are not added as unique tests.

REAL PROVIDER TESTS: None. MOCK TESTS: Controller/helper transport and fake DOM
where stated. EVIDENCE: [Hashed transport support](north-star/broll-root-admission-evidence.json),
exact source ZIP, author branch/bundle, peer report and primary log.

REGRESSIONS: No scoped failure. Existing source, fixtures, API, attributes and
Root UI are unchanged. The independent runner's cp1252 console print failed
after the Node child had passed and written complete logs/pins; its report
retains that bookkeeping failure and does not rerun or relabel the tests.

EXTERNAL BLOCKERS: Browser policy denial; real key NOT_CONFIGURED; provider,
Owner and production acceptance remain separate. OWNER ACTION REQUIRED: None
for safe implementation. NEXT WAVE: The sole Root UI owner integrates this
helper with full original raw/proof callbacks and explicit optional controls.

SOURCE_PRESERVED=YES; IMPLEMENTATION_COMPLETE=NO;
REAL_PROVIDER_ACCEPTANCE_COMPLETE=NO; PRODUCTION_DEPLOYED=NO.
The matrix stays 5/58/1 and 59 broad unclosed groups; full Mode A/B is unaccepted.
