# Cost control — V2-01

Normal development and CI use deterministic content, local copyright-safe assets, eSpeak and
local Remotion rendering. No paid API is called automatically.

The one real-provider smoke workflow requires all three conditions: manual dispatch text
`APPROVED`, approval of the protected `manual-paid-provider` environment and a configured
secret. It makes one bounded TTS request and keeps the audio in a temporary directory.

V2-02 will add provider/cost records and budget caps before broader provider use. Publishing,
GPU generation and scale tests remain disabled until their own owner-approved cost gates.
