# AssemblyAI direct ASR source integration

This source-only change introduces a fail-closed direct ASR route for
`assemblyai-transcription / universal-3-5-pro / vi`. It is based on the two
sealed provider-selection benchmark manifests in `benchmark-provenance.json`.
Those benchmark runs are evidence for provider selection, not production
acceptance or runtime authority.

The immutable request profile preserves the exact five ordered keyterms and
scenario-only context used for both assets. AssemblyAI word `start`/`end`
milliseconds are mapped without repair to positive provider-native intervals.
The Flow-A segment is only an envelope derived from the first and last native
word bounds; provenance never labels it as provider-native segment timing.

The provider adapter permits one accepted upload and one transcript creation.
After a transcript ID is acknowledged, all further interactions poll that ID.
Ambiguous upload or job acknowledgement fails/reviews closed and never creates
another upload/job automatically. Credentials are selected through a sealed
provider/alias/systemd-credential mapping and never enter evidence.

The v3 ASR gate supports this provider without changing historical v1/v2
OpenAI bundle bytes or meanings. Future live use still requires a new RC,
lineage, G-01/G-02/G-03, gate bundle, dispatch authority, O2, activation,
resolver policy, catalog and Owner dispatch decision. The source default is
`ASSEMBLYAI_ASR_LIVE_EXECUTION_ENABLED=false`.

Planning cost is provider-specific: USD 0.21/hour model + USD 0.05/hour
keyterms + USD 0.05/hour context, total USD 0.31/hour. Provider credit debit,
modeled cost and out-of-pocket spend remain separate evidence fields. No prior
Whisper budget ceiling is transferred.

PR #103 remains an unmodified draft fallback at
`827c53cb2c022f48b056c48d8c6951e26d0fcf1e`.
