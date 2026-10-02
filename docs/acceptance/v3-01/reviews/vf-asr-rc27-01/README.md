# VF-ASR-ASSEMBLYAI-G08-MERGE-RC27-01

Status: `RC27_SOURCE_LOCKED / GOVERNANCE_CLOSURE_CANDIDATE_READY`

This record closes the source-only AssemblyAI direct-ASR G-08 gate and records the immutable RC-27 source candidate. It grants no provider, credential, deployment, runtime, lineage, operation, O2, or production authority.

## Controlled source merge

- Repository: `vangnguyen/npd-video-factory-v2`
- Pull request: `#104`
- Base main: `996ccb7b6aced3e3b41bc673eef124a9a8d9b454`
- Exact reviewed head: `4cf1b49e4eea34fed515ed44c25a5445e147bbda`
- Reviewed diff: `22 files / +2102 / -115`
- Exact-head CI: `36952325138` — `PASS 5/5`; `1553 passed / 1 skipped`
- Merge method: `merge commit`
- Merge commit: `76add7193926780add892128dbe373312fb54c56`
- Merge parents:
  1. `996ccb7b6aced3e3b41bc673eef124a9a8d9b454`
  2. `4cf1b49e4eea34fed515ed44c25a5445e147bbda`
- Exact-main CI: `36953851895` — `PASS 5/5`; `1553 passed / 1 skipped`

## RC-27 source identity

- RC tag: `vf-v3-01-rc27`
- Tag type: `annotated`
- Tag object: `e335e627c5b635b426f9a0e749d7c305b10d0649`
- RC commit: `76add7193926780add892128dbe373312fb54c56`
- RC CI: `36954477895` — `PASS 5/5`; `1553 passed / 1 skipped`
- Executable tree SHA-256: `72b56baeb25fc12b0b4917324b8f3793708442b77fd37a8d72bf918f200ec79c`
- Workflow tree object: `a7acb6b4574314f2a603fff276ddb03ce95e41e4`
- Executor executable tree SHA-256: `59e74e1a76dc4925edbdb8b1c18c24c14ba4e6b01a237bf66d9fc359cc6a9293`

## AssemblyAI source contract

- Provider: `assemblyai-transcription`
- Model: `universal-3-5-pro`
- Language: `vi`
- Profile: `asr-assemblyai-vi-direct-v1`
- Profile SHA-256: `4531122508d7884804824ca7e29646fad41acabd1914dd330237c30793bc3d11`
- Keyterms SHA-256: `5b555dd98d59e6ac31f9f88470bd97d2910f479e68165f7940465c94fb7ceccf`
- Context prompt SHA-256: `aa9844e215fb5589eeca1480bc0b3d279ee7001c8e2eae46234a9ba58c120adc`
- Default live execution: `DISABLED`

## Provider-selection evidence

- Classification: `PROVIDER_SELECTION_BENCHMARK`
- Production acceptance: `NO`
- Asset-01 evidence manifest: `9339e76145c05c81ba6eed47c04d5423e50cfe5bea2f6d87a7446a5473b43b80`
- Asset-02 evidence manifest: `f1e49ebdc360aeae72ffed706c3d8199a1ce1c7044dac04f8bbcf5f4e2139aa2`
- Benchmark provenance SHA-256: `1ca36fc2575b58571562de97a05fe15819702dde062d21fe75024a3a2fc17bb9`

## Governance evidence

- Sealed registry highest before allocation: `V3-01-APP-108`
- G-08 approval: `V3-01-APP-109`
- G-08 record SHA-256: `f42f272ed80a65ab46defedc77cd08886e19e7b5d8a4753fd321ded2b820451a`
- RC-27 source provenance SHA-256: `c4167162e98452301a3ec05e3b40f51473544d9cd0733c7b9364b050b0dbafb4`
- Governance closure status: `CANDIDATE_NOT_MERGED`
- Final dual-CI provenance: `NOT_CREATED`
- Governance candidate executable-tree drift: `NONE`

## Historical and zero-execution boundaries

- RC26 W2 lineage: `FAILED_FIRST_OPERATION / CLOSED_FOR_CONSECUTIVE_ACCEPTANCE`
- RC26 W2 Operation 1: `FAIL / CONSUMED / NON-RETRYABLE`
- RC26 W2 Operation 2: `LOCKED / NOT_AUTHORIZED`
- Credential reads: `0`
- Audio uploads: `0`
- Transcript jobs: `0`
- Provider calls: `0`
- Reservations: `0 VND`
- Spend: `0 VND`
- New lineage or operations: `0`
- O2: `0`
- Runtime activation: `0`
- Host deployment: `0`
- Production: `NO-GO`

## Next gate

Owner review and controlled merge of the governance-only Draft PR are required. After that merge, fresh exact governance-main CI and final dual-CI provenance must pass before any RC27 deployment, qualification, promotion, fresh AssemblyAI lineage, operations, G-01/G-02/G-03, O2, runtime activation, credential resolution, or provider dispatch may be created.
