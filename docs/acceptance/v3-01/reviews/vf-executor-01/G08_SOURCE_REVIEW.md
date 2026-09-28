# G-08 technical review — VF-EXECUTOR-01

Verdict: **BLOCKED FOR FULL EXECUTOR ACCEPTANCE; DRAFT FOUNDATION ONLY**.
This is a technical review, not an Owner approval or execution authority.

Reviewed against base `7c023307d6a1e56a732a6ca96235a7ab3b32a253`.
Exact candidate SHA and CI URLs are recorded in the Draft PR/final handoff.

Verified source boundaries:

- Provider entrypoint is unconditionally blocked, including valid-shaped input.
- Arbitrary shell/script/command/path inputs are rejected and never echoed.
- Only the canonical check-only API is invoked by qualification; no new engine.
- Qualification DB access is forced read-only; secret probe never opens plaintext.
- Provider reachability is TLS only; no provider HTTP request exists in probes.
- Shared workflow concurrency disables cancellation; qualification uses flock.
- Public PR events and unapproved workflow commits fail admission unit tests.
- Provisioning leaves the actual repository-scoped runner offline with an empty
  workflow allowlist and no runtime/custody/secret grants.
- RC-22 content, tag, operation and authority are unchanged.

Blocking findings:

1. Actual E1–E10 run, durable manifest and security qualification are absent.
2. Canonical custody/evidence/secret references and permissions for the new
   runner account remain unspecified. Historical custody is not adopted silently.
3. Public personal-repository runner needs an enforced security boundary;
   hook/labels alone are insufficient. No service may start on this basis.
4. Full canonical dispatch integration and requested transition/cleanup order
   remain unimplemented; the hard latch is intentionally retained.
5. E9 is a rejected fixture staging probe and E10 is a negative check-only probe;
   neither establishes valid package loading or operation readiness.
6. Candidate workflow files are protected by exact workflow commit pinning.
   Historical canonical executable-tree hashing includes CI.yml only under
   `.github/workflows`; future provenance must explicitly include these workflow
   files without rewriting historical RC evidence.

Offline coverage maps the new host/request/admission tests to existing
`test_provider_runtime_bootstrap.py`, `test_provider_single_dispatch.py` and
`test_provider_single_dispatch_check_only.py` for socket/namespace mismatch,
stale/consumed operation, active reservation, provider receipt/idempotency and
authority/bundle/scope rejection. CI must also run the existing full regression.

No merge recommendation until these blockers are resolved. O1 is mandatory
before merge even after technical review passes. No O2 request is made.
