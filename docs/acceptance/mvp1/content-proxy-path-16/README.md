# Content shared proxy path (source only)

Task VF-MVP1-CONTENT-PROXY-PATH-DIAGNOSTIC-16, stacked on Draft PR #110 at
`308e3b0a35fe44a039c7c10ec65f9d7cee155af4`.

Primary classification: **UNKNOWN_BLOCKER**. The successful task-10 auth
artifact preserves HTTP 200/model identity/counters, but omits its interpreter,
HTTP implementation, environment identity and proxy/CA/transport observations.
It cannot establish the exact historical probe path or explain the later 401.
No cause is inferred from the difference between GET and POST, or from a runtime
spec revision alone.

The task-15 runner and source establish a Python/httpx POST in the Codex Cloud
host sandbox, launched as an exec-command subprocess. It did not launch a Docker
child for HTTP. The adapter used `transport=None`, `trust_env=True`, the official
origin and disabled redirects. Runtime readiness was current/ready for the fixed
Network Secret at api.openai.com. Proxy/NO_PROXY/CA booleans were not captured at
that historical send. Current offline observations show proxy and CA available,
no NO_PROXY bypass, and matching safe flags in a fresh interpreter subprocess.
The stored public diagnostic distinguishes missing historical observations from
current observations.

`app.codex_cloud_content_http.CodexCloudContentHTTPClient`
(`codex-cloud-content-http-v1`) now owns the one Cloud HTTP path for both
Responses POST and a separately approved auth GET. Both share
`ProtectedResolverReference`, the exact `CodexCloudContentSecretTransport`
backend and its unchanged opaque handoff. The HTTP constructor fixes
`https://api.openai.com`, `trust_env=True`, `verify=True`, redirects off, and
the profile timeout. There are no selectable host, alias, secret variable or
proxy parameters. An arbitrary custom transport is rejected before handoff;
missing proxy routing or NO_PROXY bypass fails closed.

Default command (no network, no ledger access):

```sh
python scripts/content-cloud-auth-probe.py diagnose
```

For a scope-bound in-memory identity check, supply a public disabled scope and
its raw SHA using `--scope` and `--scope-sha256`. Only the equality boolean is
returned; the opaque value is never encoded, hashed, printed or persisted.
Disabled/expired scope metadata does not become execution authority.

The future `probe` command is disabled without a separate, hash-pinned
`ContentAuthProbeApproval` file and output directory. The approval must identify
the exact current source HEAD, the disabled scope's raw/canonical SHA, Owner,
fixed GET /v1/models/gpt-6-luna, and an active UTC window of at most 60 minutes.
It cannot activate Content generation. An exclusive durable claim keyed by
the public approval is stored under
`/workspace/shared/npd-vf-content-auth-probes/consumed/`; changing output
directories cannot authorize a second call. Neither this task nor CI runs a
real probe. Future execution requires new explicit Owner authority.

The original prompt/profile/rights/request and operation-identity derivation
remain pinned. Candidate verification compares immutable request/admission AST
nodes so reviewed HTTP routing changes do not require rewriting old artifacts.
Actual Content calls remain behind the existing durable safety controller.
The non-Cloud synthetic adapter tests retain their offline transport path.

Validation: 104 focused tests; 1,962 full Python tests passed, three
PostgreSQL-only cases delegated to CI. Tests cover shared constructor/backend,
proxy/CA flags, custom transport rejection, missing proxy and NO_PROXY bypass,
fixed host/alias/variable, no ambient API-key fallback, value-free diagnostics,
disabled/expired probe authority and durable no-retry claims. All HTTP results
in tests are synthetic.

Historical evidence and the dev accounting epoch are unchanged: committed
10,000 VND, reserved 0, daily ceiling 20,000. The two 5,000 VND balances remain
conservative accounting, not confirmed OpenAI spend. No third Content operation
is created. Auth probes, provider calls, raw credential reads, reservations,
new charges, spend and production writes in this task are all zero.
