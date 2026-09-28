# G-08 — VF-EXECUTOR-05A source review

**SOURCE PASS / OVERALL BLOCKED_LIVE_QUALIFICATION_NOT_RUN / NO MERGE
RECOMMENDATION.** This review grants neither O1 nor O2 authority.

## Reviewed change

Bounded independent source review confirms that production qualification and
execution code no longer relies on runner ID 21 and does not replace it with a
hard-coded runner ID 6. The trust root is the immutable, root-owned
`/etc/npd-video-factory/executor.json` binding plus the hash-pinned promotion
chain. The canonical identity is an exact seven-field object binding runner ID,
runner name, execution organization, runner group, execution repository, source
commit and executor executable-tree SHA-256.

Qualification promotion, raw probe receipt and independent security review must
each equal that same expected identity. Missing, partial, extended, wrong-typed
or cross-runner evidence fails closed. Caller requests are forbidden from
supplying either the canonical fields or a runner-identity object. The expected
deployment binding—ID 6, `npd-vf-executor-ubuntu-02`, `npd-ai`,
`vf-provider-execution`, `npd-ai/npd-video-factory-executor`—is operational
configuration, not an embedded production identity.

## Negative and regression review

The source matrix covers legacy ID 21, wrong name, missing identity,
caller-supplied identity, different-runner promotion, different-runner probe,
different-runner security review and executable-tree mismatch. Existing checks
for artifact hashes, manifest convergence, E1–E10 PASS, zero invariants, engaged
kill switch, quarantine clearance and hostile-job admission remain mandatory.
No security gate is relaxed.

Final test counts, secret-scan and diff-check results, final PR head,
executable-tree SHA-256, exact-head workflow run ID and the equality
`EXPECTED_HEAD_SHA == CHECKED_OUT_SHA` are recorded in the external
VF-EXECUTOR-05A handoff after the final commit and CI complete. Recording them
here beforehand would create circular or stale provenance; no value is invented.

## Acceptance boundary

This PASS is source-side only. No `/opt` runtime or service was installed, no
live host configuration, allowlist or qualification evidence was populated, no
self-hosted workflow or live E1–E10 qualification was run, and no O1/O2 request
was made. Runner ID 6 remains OFFLINE, listener STOPPED, service NOT_INSTALLED,
kill switch ENGAGED and allowlist EMPTY.

Provider calls, provider credential reads, budget reservation, operation
consumption and actual cost remain zero. PR #91 must not merge under this review.
The allowed stop is `SOURCE_READY_FOR_LIVE_QUALIFICATION`; the next safe action
is a separately authorized live qualification, not executor activation or
provider execution.
