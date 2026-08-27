# Agent Hub Bridge v1

## Boundary

Agent Hub is an optional control-plane client. Video Factory V2 remains the media execution and
content-intelligence owner. The integration imports no Agent Hub package, reads no Agent Hub
database, uses no Agent Hub Redis key, and does not require Agent Hub to stay available.

The only integration surfaces are:

- versioned REST under `/api/v1/bridge`;
- the `agent-hub-bridge.v1` JSON event contract;
- HMAC-SHA256 service requests and outbound webhooks.

The first inbound action is intentionally narrow: `project.create_draft`. It creates a V2-owned
project and immutable initial version but never starts analysis, generation, rendering or
publishing. The request schema fixes `execution_mode=draft_only`, `start_pipeline=false`,
`publish_requested=false` and `external_action_requested=false`.

## Service authentication

Every bridge endpoint requires a dedicated identity with the `service` role and these headers:

| Header | Meaning |
|---|---|
| `X-NPD-Service-Id` | Dedicated caller identity, normally `agent-hub` |
| `X-NPD-Key-Id` | Verification key selector |
| `X-NPD-Timestamp` | Unix seconds, within the configured skew window |
| `X-NPD-Nonce` | Unique request nonce |
| `X-NPD-Content-SHA256` | SHA-256 of the exact request body |
| `X-NPD-Signature` | HMAC-SHA256 of the canonical request |
| `X-NPD-Contract-Version` | Must be `agent-hub-bridge.v1` |

Canonical service request:

```text
UPPERCASE_METHOD
/exact/path
exact_query_string
unix_timestamp
nonce
lowercase_body_sha256
```

Verification uses constant-time comparison. A valid nonce is stored only in the V2 Redis
namespace `npd:video-factory:v2:bridge:auth-replay:*` with TTL. A repeated nonce, changed body,
unknown key, bad signature or expired timestamp fails closed. No raw key is persisted or returned.

## Secret-file contract

`AGENT_HUB_SERVICE_KEYS_FILE` and `AGENT_HUB_WEBHOOK_SIGNING_KEYS_FILE` point to an external,
root-readable JSON file. They may point to the same file. The structure is:

```json
{
  "version": 1,
  "service_identities": {
    "agent-hub": {
      "roles": ["service"],
      "keys": {"inbound-v1": "<base64 key material, minimum 32 bytes>"}
    }
  },
  "webhook_signing": {
    "active_key_id": "outbound-v2",
    "keys": {
      "outbound-v1": "<historical verify-only key>",
      "outbound-v2": "<active signing key>"
    }
  }
}
```

This example is a contract, not a usable secret. The real file must stay outside Git/images,
must not be included in backups or logs, and should be mode `0400` or `0440` with a narrowly
scoped group.

## REST contract

| Method | Path | Result |
|---|---|---|
| `GET` | `/api/v1/bridge/contract` | Version, roles, actions, events and isolation truth |
| `POST` | `/api/v1/bridge/project-requests` | Idempotent draft-only project creation |
| `GET` | `/api/v1/bridge/project-requests/{request_id}` | Durable request state |
| `GET` | `/api/v1/bridge/projects/{project_id}/summary` | Read-only project/cost/publication/analytics counts |
| `GET` | `/api/v1/bridge/events` | Secret-free outbound event history |
| `GET` | `/api/v1/bridge/webhook-deliveries` | Delivery state and signed receipt metadata |

POST requires `Idempotency-Key`. Only its service-scoped SHA-256 is stored. Reusing a key with a
different request returns conflict; an exact replay returns the original project.

`production_deployed` reflects the running environment: it is `false` in local/CI and becomes
`true` only when the bridge is enabled with `APP_ENV=production`. It is status evidence, not a
deployment trigger.

## Signed webhooks

Events are canonical PostgreSQL rows before a delivery ID enters V2 Redis. The worker signs a
canonical JSON body with the active outbound key and sends these headers:

```text
X-NPD-Key-Id
X-NPD-Timestamp
X-NPD-Content-SHA256
X-NPD-Signature
X-NPD-Contract-Version
X-NPD-Event-Id
```

Canonical webhook signature text is:

```text
POST
/agent-hub/events/v1
unix_timestamp
event_id
lowercase_body_sha256
```

Delivery state, attempt count, next retry, body hash, key ID and signature receipt are durable.
The signed Unix timestamp is persisted with the receipt, so an old delivery remains independently
verifiable by its historical key ID after a key rotation.
The Redis queues `npd:video-factory:v2:bridge:webhooks:queued` and `...:processing` contain only
delivery IDs and are recoverable. The default mode is `disabled`; `fixture` is deterministic and
no-network for local/CI. `http` requires a separate external-delivery flag, HTTPS and an
allowlisted host.

The versioned contract reserves the complete event vocabulary from the master specification,
including `trend.opportunity.detected`, `idea.shortlist.ready` and the video lifecycle events.
V2-11 currently emits `video.project.created`; later emitters must reuse the same durable outbox
and must not infer that a declared event is already live.

## HMAC rotation

1. Back up V2 state; separately confirm the external secret file can be restored securely.
2. Add a new outbound key and keep the old key in `webhook_signing.keys`.
3. Change only `active_key_id` to the new ID and deploy through the guarded runbook.
4. Generate one non-production delivery and verify the new receipt uses the new key ID.
5. Verify a historical receipt with its old key ID.
6. Retain the old verify key for the receipt-retention period; then remove it in a separate change.
7. Roll back by restoring the prior key file and image. Never rotate by deleting the active key first.

New receipts use only `active_key_id`; historical verification selects by receipt `key_id`.
Unknown IDs return invalid without leaking key material.

## Known limitation

V2-11 implements the dedicated `service` identity and publishes the complete role vocabulary
(`owner`, `editor`, `reviewer`, `viewer`, `service`). Interactive user SSO/session enforcement for
the Studio is not claimed as production-deployed in this PR. Caddy exposure remains a separate
owner-gated task.
