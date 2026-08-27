# Cost control — V2-07

VND is the only accepted cost currency in Pydantic contracts, ORM defaults and the database
check constraint. USD is not a supported runtime currency.

Each provider operation has a deterministic operation key. Replaying the same operation
returns the existing provider-usage and cost records instead of double-counting. Estimated
and actual cost are non-negative; an operation whose provider price is unknown remains
explicitly unpriced rather than being recorded as zero.

Normal development and CI use deterministic content, local fixtures, eSpeak and Remotion;
all three records are `0 VND`. OpenAI TTS is disabled by default and produces an unpriced
record unless an owner-approved pricing source is configured in a later increment.

The V2-03 trend fixture and deterministic Idea Engine also cost `0 VND` and make no network call.
All live trend providers are `not_configured`; enabling one later requires an explicit VND pricing
contract, budget/approval policy and idempotent usage record. Unknown provider cost must remain
unpriced, never converted from or displayed as USD.

V2-05 deterministic transcription, media-signal and Vision providers each record an idempotent
`0 VND` operation. Contract-only live transcription and Vision providers fail with
`PROVIDER_NOT_CONFIGURED`; they cannot silently incur cost. Any later live provider requires a VND
price contract and owner gate.

V2-06 stock search and every media resolution create idempotent VND usage/cost evidence. The
deterministic stock/image/video fixtures cost `0 VND` and make no network call. A plan carries
`max_ai_cost_vnd`; an estimate above it stops before generation and enters `needs_approval`.
External and paid execution have independent fail-closed switches. Missing or unknown live pricing
remains unpriced and cannot be silently treated as zero or converted from USD.

The real-provider smoke still requires manual dispatch text `APPROVED`, protected-environment
approval and a configured secret. Publishing, GPU generation and scale tests remain disabled
until their own owner-approved budget and execution gates exist.

V2-07 timeline mutations and local FFmpeg proxy previews make no external provider call and add no
paid usage record. The preview response declares `external_call=false`; compute/storage capacity is
an operational resource rather than a silently converted provider charge. A future hosted preview
provider must add an idempotent VND price contract and owner gate before it can be selected.
