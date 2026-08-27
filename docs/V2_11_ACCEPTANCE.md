# V2-11 Acceptance

## Scope result

V2-11 implements the Agent Hub bridge and production hardening bundle at version `0.12.0`.

| Requirement | Evidence state |
|---|---|
| dedicated service auth | implemented and locally tested |
| versioned REST/event contract | implemented and contract-tested |
| signed webhooks | implemented; deterministic fixture tested |
| anti-replay/idempotency | implemented and locally tested |
| delivery persistence/retry/recovery | implemented and locally tested |
| active + historical HMAC keyring | implemented and rotation-tested |
| security headers/config validation | implemented and locally tested |
| backup/restore/deploy scripts | implemented; syntax/contract tested only |
| Docker deterministic E2E | required before PR acceptance |
| real Agent Hub integration | not tested in this PR |
| production deployment/soak | not performed; separate owner gate |

## Deterministic acceptance flow

1. Sign `POST /api/v1/bridge/project-requests` as the dedicated Agent Hub service.
2. Create `Vịnh Tiên Agent Hub Draft` with source campaign
   `CMP-VGP-VINHTIEN-202609-01`.
3. Verify a canonical project and immutable version are persisted with `draft_only` evidence.
4. Verify no pipeline job, render, publication or external action is created.
5. Replay the same idempotency key and receive the same project.
6. Reuse it with a changed payload and receive conflict.
7. Process the `video.project.created` delivery through the no-network fixture adapter.
8. Verify receipt key ID/body hash/signature and persistence after restart.
9. Verify changed body, unknown key, expired timestamp and replayed nonce fail.
10. Verify a rotated active key signs new receipts while the historical key verifies old receipts.

## Safety impact

No publishing, paid provider, customer messaging, CRM write, Ads mutation, CMS publish or Agent Hub
shared-state capability is introduced. HTTP webhook delivery is false by default and prohibited in
CI/test. Production fixture providers remain prohibited.

## Honest limits

- Browser-user SSO/session enforcement is not production-deployed; only the service identity is
  enforced on bridge routes.
- The HTTP webhook adapter has no real Agent Hub acceptance evidence yet.
- Production Caddy routing, deployment, restore rehearsal and 24-hour soak were not run.
- Real Vision/media/publishing/analytics providers and the human-accepted Vietnamese production
  voice remain outside V2-11.

The PR must remain draft and unmerged until CI is green and the owner reviews these limits.
