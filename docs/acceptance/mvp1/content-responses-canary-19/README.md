# VF-MVP1-CONTENT-RESPONSES-CANARY-SOURCE-19

The dedicated canary performs one fixed POST inference compatibility request
under independent Owner authority. It cannot enable Content generation, create
Content operations, reserve budget, or access the provider-safety ledger.
This source qualification makes zero OpenAI requests.

`ContentResponsesCanaryApproval.schema.json` describes the frozen public approval
with schema name `codex-cloud-content-responses-canary-v1`. Authority defaults to
false. Its UTC window must be positive and at most 60 minutes; runtime validation
checks the exact clean source HEAD, canonical and raw disabled scope hashes,
model/backend/credential binding, and disabled Content execution state.
The scope remains byte-identical. Auth GET approval cannot authorize a canary,
and canary approval cannot authorize the auth GET or Content execution.

All three modes use `CodexCloudContentHTTPClient` / `codex-cloud-content-http-v1`:

| Mode | Endpoint | Protected resolver method |
| --- | --- | --- |
| AUTH_PROBE | GET `/v1/models/gpt-6-luna` | `resolve_for_auth_probe` |
| RESPONSES_CANARY | POST `/v1/responses` | `resolve_for_responses_canary` |
| CONTENT_RESPONSES | POST `/v1/responses` | `resolve_for_context` |

The one HTTPX constructor uses the official origin, `trust_env=True`,
`verify=True`, redirects disabled, and the same bounded timeout. Each handoff
reaches `CodexCloudContentSecretTransport._placeholder_handoff()` with fixed
backend `codex-cloud-network-secret-content-v1`, fixed logical alias, and
`NPD_VF_CONTENT_API_KEY` at `api.openai.com`. A custom transport, selectable host,
proxy configuration or caller auth header is rejected. Credentials are never
logged, inspected, hashed, or persisted. In-memory equality diagnostics return
only a boolean. Content execution gates retain their original behavior.

The trusted canary request uses `gpt-6-luna`, reasoning effort `none`, input
`Return exactly OK.`, output cap 16, and `store=False`. Caller text, tools,
conversation, schema, instructions, business data or additional fields are
rejected by canonical byte comparison before handoff. There is no Content
prompt in this request. `CANARY_REQUEST.sha256` records the SHA of the compact,
sorted UTF-8 canonical JSON, rather than the pretty-printed public fixture:

`2cceb20e2a9a9e6c0fff264f0aed51142060b411edaa843dad8ad12f9b8b8aef`

The preserved shared disabled scope has raw SHA
`d92b16a72008b53377f5c2d39ca85605013fc3fb3e333edee23775fa0d640a47`
and canonical SHA
`9dbcf0be64a3730ae6b159bfa904ee34516db05684d27ae16f3b337188f7fc74`.
Its Content execution window is not canary authority; a separate approved
canary window is required. No real canary approval is materialized in this task.

Run `python scripts/content-cloud-responses-canary.py` for offline diagnostics.
The explicit `canary` command requires all five public/pinned inputs:
`--owner-approval`, `--approval-sha256`, `--scope`, `--scope-sha256`, and
`--output-dir`. Missing inputs never enable network mode. The output directory
is create-only. The durable decision claim is stored outside Git under
`/workspace/shared/npd-vf-content-responses-canary/consumed/`, separately from
Content operations. It binds the Owner decision identity, so changing a window,
approval hash, or output directory cannot reuse that decision. Dispatch consumes
the attempt regardless of HTTP, parsing or transport outcome. No retry/fallback
exists; the resolver is detached after the terminal outcome.

Future response evidence records only allowlisted metadata and usage. A completed
response must have the expected model, exactly one `OK` output, no refusal/tool
call, valid token counts and output within 16 tokens. HTTP 401/403, 400, 429,
5xx and ambiguous transport are terminal, separately classified outcomes.
Error messages, raw response bodies and arbitrary error-field values are never
persisted. Returned token usage is `CANARY_OBSERVED_USAGE`; modeled VND cost uses
the pinned profile's rates and is not a Content ledger charge or a provider
invoice. `provider_billing_observed=false` unless billing itself is observed.

The Content epoch remains committed 10,000 VND, reserved 0, daily limit 20,000.
Its conservative balances are not confirmed OpenAI spend. SHA comparisons of
the shared ledger and historical execution/auth evidence are retained outside
Git for this task. Synthetic HTTP fixtures and socket guards qualify the source
offline; a separately authorized completed live canary is still required before
materializing a real Content operation.
