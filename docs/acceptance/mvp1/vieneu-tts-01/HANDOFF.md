# Candidate source handoff — VieNeu local audition

Task: VF-MVP1-VIENEU-TTS-ENABLEMENT-01.
Dependency base: 0eaa865fc1515dffc7e7482befc8e88a9cacd53f, Draft PR109.
Branch: codex/vf-mvp1-vieneu-tts-01. No merge/deployment/publication/RC.

Implemented: separate preset-only TTSProvider adapter, profile/evidence v3,
revision/license/preset pins, fixed loopback transport, no credentials,
actual WAV decoding, hash persistence, bounded outputs, cancellation and stale
guards, exact restart cache, audio-config voice selection, existing pipeline
reflow/review integration and a three-voice local audition harness.

Local synthetic checks during implementation: first full suite 1913 passed /
5 skipped; subsequent VieNeu-only suite 33 passed. These overlap and are not
added into a unique test total. The final clean-head remote run and final local
test results must be recorded separately after committing this source.
Two skips are root DAC checks and three require actual PostgreSQL. Renderer
initial WSL run lacked its Linux optional package (Windows node_modules);
the isolated Linux dependency install is a test-environment repair, not source
or lockfile mutation. Npm reported baseline dependency vulnerabilities; no
unreviewed upgrade or npm audit --force is authorized in this task.

Final audition/CI state is NOT asserted by this pre-run source handoff.
External task closeout records exact source head, each runtime result, CI,
package hashes, all skips and non-root/PG evidence. A prepared harness is not
audio evidence. Human quality and word alignment remain open.

ASR: historical blocked/spent context remains untouched; spoken video stays
fail-closed until separately authorized ASR remediation/acceptance. No fixture
transcript, historical evidence repair, resolver/systemd/authority access.
OpenAI Realtime marin comparator stays uncalled and separately gated.

Next human step once actual local media exists: listen to the same script in
all three presets, score the rubric, and explicitly choose a voice or request
a bounded pronunciation correction. Do not execute this step automatically.
