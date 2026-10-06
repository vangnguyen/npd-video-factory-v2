# North Star baseline — 2026-10-07

SOURCE_PRESERVED = YES. Original source and accepted artifacts remain unchanged. Implementation continues on an isolated branch; no main merge or production deployment is authorized.

## Exact repository state before implementation

| Field | Observed value |
| --- | --- |
| Attached workspace | `C:\Users\PC\Documents\ChatGPT\Video Factory`; empty initialized Git repository, unborn `master`, no remote, no tracked source |
| Actual Phase 8–10 root | `C:\NPD-Video-Factory\source` |
| Original branch | `codex/vf-post-mvp-roadmap-execution-01` |
| Original local HEAD | `2ced7bc81f9402368fb22c9e7aca242e740531af` |
| Remote fetch/push URL | `https://github.com/vangnguyen/npd-video-factory-v2.git` |
| Fresh remote main, verified with `git ls-remote` | `fa81c59fbe6b745cba8fed979e30e52a13199afa` |
| Ahead / behind remote main | 99 / 0 |
| Original upstream | None |
| Dirty/staged/untracked source | None, before preservation |
| New branch / checkout | `codex/vf-north-star-completion-01` / `C:\vfns01` |
| Branch remote preservation | Successful `git push --set-upstream origin codex/vf-north-star-completion-01` |
| Tags | Existing `internal-production-v1` and `vf-v3-01-rc1` through `rc28`; no new certification tag |
| Shared Git common directory | `C:\Users\PC\Documents\Codex\2026-09-28\ti-p-t-c-vf-executor\work\vf-asr-w2-source-remediation-01\.git` |

The first worktree creation inside the long attached workspace failed at Windows MAX_PATH. Its partial files were left intact. The successful short checkout used `git -c core.longpaths=true worktree add C:\vfns01 codex/vf-north-star-completion-01`. No reset, deletion, source-history rewrite or live-service restart occurred. Scoped path configuration must be retained when operating on long evidence paths.

## Recovery copies

Recovery root: `C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007`.

| Archive | SHA256 | Bytes |
| --- | --- | ---: |
| `video-factory-pre-north-star.bundle` | `96a1c7f1822e6ecbb79ee0a5ad10ba258e6f6751d2dd7c0ec76cfa2d1523de83` | 189728092 |
| `git-metadata-and-unreachable.zip` | `0562b7670e92a01a1d6dc8ee98e622a7bc30cba64bf9c95ecbad704d456e18d2` | 266019584 |
| `accepted-phase8-9-artifacts.tar` | `9b312e45b82130c1a99d2b1f390f8fb84ebaa0895251518c5c4af6100442bc77` | 56258560 |

The bundle passed `git bundle verify` and includes all 161 existing refs and complete history. The raw Git archive passed ZIP CRC validation and preserves dangling commits/blobs beyond reachable bundle history. `preservation-manifest.json` records every accepted artifact path, phase, expected/actual hash, size and archive checksum. `local-only-commits.txt` contains all 99 full commit SHAs and messages; `refs.txt`, `git-fsck.txt`, `source-status.txt` and `bundle-verification.txt` retain repository observations. These recovery copies contain private project media and remain local.

Recovery into a new short path:

```powershell
git clone --branch codex/vf-post-mvp-roadmap-execution-01 'C:\Users\PC\Documents\ChatGPT\Video Factory\recovery\20261007\video-factory-pre-north-star.bundle' C:\vf-recovered
git -C C:\vf-recovered fsck --full
```

Extract the accepted artifact TAR to a **new** recovery directory and verify against `preservation-manifest.json`; never overwrite existing accepted videos. Raw Git metadata is an additional forensic copy, not a command to replace any current Git directory.

## Evidence and accepted artifacts

| Phase | Source evidence | Certification state |
| --- | --- | --- |
| 8 | `evidence/post-mvp-roadmap/phase-8`, `INTERNAL_PRODUCTION_RELEASE.md`, existing tag `internal-production-v1` | INTERNAL_PRODUCTION_READY = YES, historical Owner acceptance |
| 9 | `evidence/post-mvp-roadmap/phase-9`, `POST_INTERNAL_PRODUCTION_PHASE9_REPORT.md` | CONTENT_INTELLIGENCE_READY = YES, historical Owner acceptance |
| 10 | `evidence/post-mvp-roadmap/phase-10`, `PHASE10_FINAL_ACCEPTANCE.md`, `PHASE10_STUDIO_UX_REMEDIATION_REPORT.md` | Technical remediation recorded; Owner rejected prior candidates; repaired candidates remain pending |

All ten Phase 8 and five Phase 9 MP4s were read and SHA256 verified against `evidence/post-mvp-roadmap/phase-10/baseline.json`, then archived without changing original bytes. Exact hashes are reproduced in `north-star/accepted-artifacts.json`. The prior 1,596-file frozen-evidence audit remains historical evidence, not a new full runtime certification. Repaired Phase 10 videos are under `evidence/post-mvp-roadmap/phase-10/studio-ux-02/video-repair`; prior rejected attempts are retained.

## Tests and runtime

Baseline Studio: `node --test apps/studio-web/tests/*.test.mjs` — **79 passed**, 0 failed/skipped, 499.98 ms on the isolated checkout.

Native baseline initially used the API test venv and failed: 156 discovered, 21 import errors including missing NumPy. That environment is not the certified Native runtime. Rerun uses `C:\NPD-Video-Factory\runtime\venv\Scripts\python.exe`; results are recorded in the wave ledger, without changing its locked dependencies.

Full API collection on Windows failed at `grp` imports in `test_provider_secret_resolver.py`, `test_runtime_activation.py`, `test_runtime_role_failsafe.py`. The Windows-compatible rerun explicitly excludes those three modules. They remain required in Linux CI. Tests and logs are preserved under the recovery root. Historical remediation results of 255 Native / 79 Studio are not reused as fresh test claims.

FFmpeg and FFprobe 9.0.2 are installed. Node is installed. API dependencies are available in the separate `post-mvp-venv`. No `docker` executable is on PATH. The live Native Studio at `127.0.0.1:8030` was inspected read-only: shared navigation, Assets stage, saved projects, portrait workflow and provider status are visible. Its source/database/process were not restarted or modified.

## Capability/readiness boundary

Existing PostgreSQL platform includes auto-edit, timeline, Vision, media-plan, publishing, analytics and bridge schemas/services/tests. Existing Native platform contains the certified Phase 8–10 runtime and shot-centric Studio. Source inspection shows these paths are not yet one complete user workflow. Official stock/trend/publishing/analytics adapters contain contract-only branches. Newer Native implementations must be reused and integrated; their presence does not complete Mode A/B.

PHASE10_READY = NO. OWNER_UAT_REQUIRED = YES. IMPLEMENTATION_COMPLETE = NO. REAL_PROVIDER_ACCEPTANCE_COMPLETE = NO. PRODUCTION_DEPLOYED = NO for this program. Other North Star readiness states remain unproven until their required evidence and gates pass.
