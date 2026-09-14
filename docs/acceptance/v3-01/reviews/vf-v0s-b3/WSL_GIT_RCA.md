# WSL Git RCA — VF-V0S-B3

Primary class: A — WSL/environment/path interpretation. Not a source or validator regression.

A native Windows-created worktree has a .git file pointing to Windows-absolute
Git metadata. Linux Git treats C:/... as a relative path appended to the working
directory. The first rev-parse therefore fails before the two historical T/U
validators can read any Git objects.

Both historical cases were reproduced against clean commit
8aba0b2f2d79ee5688f9d651f5f5bb93f9a0794d:
test_complete_read_only_review and test_full_offline_gate_owner_binding_audit.

- Linux Git 2.43.0, original environment: 2/2 fail with the same Git initialization error.
- Native configured Windows Git, identical historical files: 2/2 PASS, 6.52 seconds.
- Linux Git with GIT_DIR/GIT_WORK_TREE set to those exact translated metadata/worktree
  paths: 2/2 PASS, 13.49 seconds. No .git/config or source/receipt was changed.
- Candidate bootstrap _git_argv performs this translation only for a Windows-
  absolute worktree pointer under POSIX, fails if the exact metadata is unreachable,
  and never chooses another checkout. Tests cover reachable/unreachable pointers.

Historical T/U files and authority artifacts remain in their original local
governance commits, not this minimal source PR. Their fixed RC18 hash assertions
must not be relaxed to bless the new candidate. This is scope separation, not a
test skip: both cases passed with correct Git metadata above.

The candidate's complete baseline API/worker/bridge suite plus new bootstrap tests
ran independently under WSL: 1047 PASS, 0 failed, 286.55 seconds.
