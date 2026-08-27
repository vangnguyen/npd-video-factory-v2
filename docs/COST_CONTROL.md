# Cost control — V2-04

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

V2-04 deterministic transcription and media-signal providers each record an idempotent `0 VND`
operation. The contract-only live transcription provider fails with `PROVIDER_NOT_CONFIGURED`;
it cannot silently incur cost. Any later live provider requires a VND price contract and owner gate.

The real-provider smoke still requires manual dispatch text `APPROVED`, protected-environment
approval and a configured secret. Publishing, GPU generation and scale tests remain disabled
until their own owner-approved budget and execution gates exist.
