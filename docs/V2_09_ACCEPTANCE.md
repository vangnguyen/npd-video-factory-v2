# V2-09 acceptance — Publishing dry run

## Accepted scope

V2-09 is accepted only as a local/CI publishing validation layer. The successful flow is:

```text
approved current production package
  -> latest final render with passing QC
  -> rights validation
  -> versioned platform validation
  -> deterministic mock provider
  -> durable dry-run receipt and audit history
```

No test or UI path performs a real external publish.

## Automated evidence

The API suite covers:

- approved final-render dry run with passing rights and platform gates;
- exact idempotent replay before and after repository restart;
- payload conflict for a reused idempotency key;
- blocked unknown rights and platform metadata limits;
- blocked `mode=live` with `external_action=false`;
- durable publication/history API reads;
- absence of raw token or secret material in serialized records;
- startup rejection of partial live gates, raw credential values and CI live execution.

Studio tests cover gate presentation, receipt summaries, idempotency-key reuse and syntax. The
Docker acceptance extends the existing render pipeline through dry-run creation, exact replay,
blocked live attempt, platform-state read, API restart and PostgreSQL recovery. CI additionally
checks that all checked-in provider adapters are official-API contracts, all capability profiles
are versioned, and every default live switch remains false.

## Acceptance assertions

- `dry_run_succeeded` is the only successful V2-09 publication state;
- mock receipt has `external_action=false` and no remote post identity;
- an exact retry returns the same publication and receipt;
- a conflicting retry is rejected;
- invalid rights, stale approval, failed QC or invalid platform metadata cannot reach a provider;
- `mode=live` is blocked and recorded without external action;
- publication and audit evidence survive API restart;
- no OAuth token, cookie, password or secret is committed, logged, persisted or returned;
- no production service is deployed or changed.

## Owner gates still open

The following are deliberately not accepted by V2-09: production deployment, public network
exposure, OAuth onboarding, live platform publishing, provider retries/cancellation, production
rate-limit handling and live content-policy acceptance. They require a separate owner decision and
must follow authentication/RBAC and workspace authorization.

## Next milestone

V2-10 is Analytics and Learning: provider-neutral metrics contracts, read-only ingestion,
attribution-ready joins and learning evidence. It must not weaken V2-09 publishing locks or imply
that live publishing is enabled.
