# V2-01 local acceptance evidence

Run time: `2026-08-26T19:34:40+07:00`.

## Results

| Gate | Result |
|---|---|
| Python API + worker | PASS — 48 tests |
| Python compile | PASS |
| Renderer | PASS — 9 tests |
| TypeScript typecheck | PASS |
| Remotion bundle | PASS |
| Docker Compose contract | PASS |
| Independent Docker E2E | PASS — terminal `awaiting_review` |
| AgentHub runtime directory/import/state | Absent |
| Publishing/approval safety | Fail-closed |
| Secret-pattern scan | PASS |

## Deterministic render evidence

- MP4 SHA-256: `43678B31679168418B6D4D0CA0648DFEC27A3412E932B74E61061F0E70F44FA6`
- QC JSON SHA-256: `B2F2976AAA4514EC3DAFD5DF94403C92F41AF991A8DB17813DD75B18BDA81D55`
- duration: `30.059s`
- resolution/fps: `1080x1920 @ 30fps`
- codecs: `H.264 + AAC`
- decoded samples: `30`
- dark visual ratio: `0.0`
- luma range: `110.444–127.35`
- audio mean/peak: `-22.7dB / -3.0dB`
- size: `3,398,684 bytes`

The binary and operational log bundle are intentionally git-ignored; GitHub's Docker E2E
job regenerates and uploads them for seven days on each PR run.

## Not claimed

- No paid/external TTS call was made.
- No human Vietnamese voice acceptance was performed.
- No production provider, publish path or analytics flow was tested.
- No production service was changed or deployed.
