# Explicit SQL narration reuse: API, worker and terminal safety

Integrated activation: `147870298d35b8f2bcb4f304633172d7c619ce4b`. Additional terminal/ledger corrections: `5aff8e615f5fb1fda8ea1a12ba4e1bd0e92a6de7`. The full North Star remains the objective; this component does not close Mode A/B or any broad capability group.

## Result

An opt-in factory now constructs the same typed narration loader, admission and completion fence for the API and worker. Its flag defaults to false. Unsupported storage, half-configuration or mismatched service instances reject execution. Constructor and availability reads do not stage audio or dispatch providers.

The scoped API checks access to both master and child before reading a mutation body. Explicit reuse binds the current approved source, family/member, child content/timeline, exact voice/profile/normalization and raw/prepared artifact proofs. A child receives independent bytes and retains its own script/review/approval and unknown rights. Original master approval, publishing authority and human acceptance are never transferred.

Review queue admission persists the exact selector and verified actor before queue handoff. Final selection comes from the child's own approved review on unchanged versions. Unknown handoff, running jobs and failed/cancelled/stale intents are observed without automatic copy or expensive replay. The ordinary same-project TTS cache scope remains unchanged.

Independent review found a concrete race: another worker could commit a terminal status while `start_render` was pending; the selected processor then continued audio work and overwrote the original failure. The activation fix observes the authoritative non-running status before any IO. A separate current-source fix extends this guard to ordinary render jobs. Actual isolated SQLite tests cover failed, awaiting_review and ready transitions, unchanged error/events/cost and zero dispatch.

The same follow-up fixes accounting for disabled voice. Empty disabled narration now records the render operation without inventing an eSpeak usage/cost record. Original historical rows remain intact; explicit local fixture voice and actual reuse accounting are retained. Post-terminal cost persistence remains a separate transaction; this change does not claim distributed ledger/render atomicity or recovery of legacy running jobs.

## Evidence and limits

The original activation source passed 50 tests over synthetic narration/approval, a fake queue and explicit mock DSP/renderer/QC. Independent selected20 overlaps that batch. After the terminal fix, eight distinct narrow cases passed across two runs: the first had seven passes and a fixture timestamp comparison failure; the failed case passed after comparing hydrated SQLite DTOs. Independent recheck passed six scoped cases, including the original race and corrupt-WAV guard. These numbers are not added into a whole-program test total.

Three trailing blank lines were removed before committing the 11 activation files. Original archives remain unchanged; independent AST/EOF comparison verifies that this final trim has no semantic change. The integrated current terminal/ledger correction passed 18 regressions, including six new SQLite cases, selected terminal cases, final actor binding and Phase 8 audio/QC/silence tests. Earlier real assertion failures and helper collection errors are retained.

A new isolated runtime installed 74 exact cached wheel pins without network installation or changes to either existing environment. Real SQL/FastAPI/VieNeu imports and four CPU ONNX session constructors passed; all eleven model/card files and installed SDK source were rehashed. No inference, ONNX run or listener occurred in that qualification. Three unused SDK metadata dependencies remain missing, so general SDK `pip check` and production runtime acceptance are not claimed.

At this snapshot, the server-prepared reuse proposal and Studio controller are still in a separate implementation branch. Six-target spoken SQL production is being prepared against the corrected source. Synthetic test speech, fixture approvals, runtime initialization and historical native narration do not establish new spoken SQL renders, human listening or Owner UAT. PostgreSQL/Redis/S3/Docker, genuine external providers, complete original A/B/C and production deployment remain unaccepted.

Evidence: [sql-narration-activation-evidence.json](north-star/sql-narration-activation-evidence.json). Matrix remains 5 IMPLEMENTED_REAL / 58 PARTIAL / 1 NOT_VERIFIED, with 59 broad groups unclosed. Phase10 technically ready=YES; Owner UAT required=YES; Phase10 ready=NO. Implementation complete, real-provider acceptance, deployment and North Star readiness remain NO.
