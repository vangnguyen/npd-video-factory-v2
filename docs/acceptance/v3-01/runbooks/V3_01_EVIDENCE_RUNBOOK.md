# V3-01 evidence runbook

This runbook manages redacted acceptance evidence. It does not call providers, read `.env`, deploy,
publish or rotate credentials.

## Validate the checked-in register

From repository root with Python 3.12 and dependencies installed:

```powershell
python scripts/v3_01_acceptance.py validate-repo
```

The command requires all acceptance documents, the exact 60 matrix IDs, valid gap records,
G-00 through G-12, valid JSON schemas and a clean secret scan.

## Run directory contract

Use `evidence/v3-01/<run_id>/` where `run_id` starts with `vf-v3-01-`. Store a redacted
`run-manifest.json`, small `evidence-*.json` records and human-readable summaries. Keep raw provider
payloads, HAR files and sensitive operator material only in ignored `raw/` or `private/` locations.
Never copy tokens, cookies, private keys, customer PII or `.env` content into evidence.

Validate and hash a run:

```powershell
python scripts/v3_01_acceptance.py validate-run evidence/v3-01/<run_id>
python scripts/v3_01_acceptance.py write-hashes evidence/v3-01/<run_id>
python scripts/v3_01_acceptance.py validate-run evidence/v3-01/<run_id>
```

The final validation must occur after `SHA256SUMS.txt` is generated. Hashes bind evidence files, not
external secrets.

## Provider or external action stop gate

Before any provider, staging, publish, analytics, backup/restore or canary action, verify the exact
owner gate in `15_OWNER_GATES.md`. If its approval record is absent, expired, for another commit,
target, provider, budget or artifact, stop and record `BLOCKED`. Never retry an ambiguous external
write; reconcile read-only first.

## Evidence review

An evidence record is acceptable only when it names a test case, matrix rows, axis, commit,
environment, provider metadata, hashes, UTC interval, result, assertion, VND cost, gaps, reviewer and
reproduction command. HTTP 200, screenshots, logs or CI green alone do not prove a different axis.
