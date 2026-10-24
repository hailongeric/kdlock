# Restore lock-only MM integration

The user's corrected scope is lock implementation and minimal API/lifetime
substitution, with native MM bodies and algorithms unchanged. The source cleanup
restores eight integration files to `b8b31a7`, retains the shared KD mutex/rwsem
backend, and removes 309 tracked body-specific implementation/probe/campaign
files. The removed bytes remain reachable in `806e9a8`; history is not rewritten.
The explicit archive branch is `codex/archive-mm-body-20261024` at that commit.
The 28 former probe guides and 31 historical result documents are explicitly
retired, while numerical evidence and raw artifacts remain intact.

The interrupted kdmm30 build was safely stopped after installation, before any
candidate boot or live MM case. Recovery stayed running and was hash-verified,
with 73 runtime modules, no test module and no armed next boot. See the
[exact stop record](../mm-boundary-interior-private-20261024/README.md).

The retained wrappers cover initialization/destruction, concurrent local readers,
local writers, killable/try/nested/downgrade operations and asynchronous read
ownership transfer. No production mutex API, JIT admission, ACK routing or frame
retirement code is changed by this cleanup. The operation-specific advice, fault
and unmap queues, prepared split helpers, page/table eligibility, ownership and
teardown extensions are removed together with their generator/build dependencies.

## Completed validation

Run `lock-only-mm-cleanup-20261024/check-1` passed in the existing recovery VM.
No kernel image was built, installed or booted during these checks, and no module
was loaded. The measured temporary budget was 3,398,748 bytes against
3,678,806,016 available bytes before compilation.

| Check | Result |
| --- | --- |
| Restored wrapper patch applied to nine copied native files | Passed, with fuzz disabled |
| Generated local adapter, pool, mutex-local, mutex-OSQ and rwsem objects | All five compiled; expected lock symbols present and body-service symbols absent |
| Basic userspace programs | 2 passed |
| Existing unified mutex API driver | Passed, including compiled nested/early-unlock control flow, strict ABI2 admission and generated execution |
| Native `mmap`, memory, advice, reverse-map and maple-tree source hashes | Unchanged |
| Source scope review | Exact 309 approved removals, eight byte-identical baseline restores, shared core lock code unchanged, all 31 historical record bodies preserved |
| Final recovery health | Same boot and Build ID, 73 expected runtime modules, no test modules, idle, no armed next boot, no fault matches in retained kernel log |

No compile or test failed. Kbuild's Perl helper emitted locale-fallback warnings;
the logs retain them. Before testing, the first mirror-quarantine preflight
refused 11 older script versions without moving any files. Each matched an exact
historical Git blob; the verified retry preserved all 288 existing mirror files
by same-filesystem rename, with 21 paths already absent and no permanent deletion.
This was a synchronization refusal, not a kernel correctness failure.

Reproduce serially in an idle guest, choosing a fresh output directory:

```sh
cd /root/host_fs/kdlock
/root/kdlock-translation-venv-20261019/bin/python3 \
  tests/kernel/mmap_lock/scope.py \
  --kernel-source /root/linux-6.1.159-kdclobber2 \
  --kernel-baseline /root/kdlock-kernel-baselines/mutex-clobber2-20260919 \
  --output /root/kdlock-evidence/10.176.26.71/tests/lock-only-mm-cleanup-20261024/check-2
```

These are source, compilation and userspace API checks. **Live actual-mm adapter
behavior was not tested** on the unchanged recovery kernel. A future lock-only
candidate needs separate verification and kernel authorization. The cleanup makes
no new claim about MM body delegation, Linux-wide semantic equivalence or
performance. See the [current scope guide](../../../../../kernel_integration/mmap_lock/README.md).

## Evidence and retained artifacts

- [Check result](../../raw/tests/mm-lock-scope-cleanup-20261024/check-1.json),
  [source review](../../raw/tests/mm-lock-scope-cleanup-20261024/source-review.json)
  and [final health](../../raw/tests/mm-lock-scope-cleanup-20261024/final-health.json).
- [One essential log archive](../../raw/tests/mm-lock-scope-cleanup-20261024/essential.tar.gz):
  36,770 bytes; SHA-256 `134f0ea5207940dfd1149675600372e5f7df223d1e8ebc41540272bb45d022b4`.
  It contains patch, object-build, API-test and identity logs plus final health;
  unchanged historical archives and compiled outputs were not copied.
- [Approved source inventory](../../raw/tests/mm-lock-scope-cleanup-20261024/scope-plan.json)
  and [recoverable guest moves](../../raw/tests/mm-lock-scope-cleanup-20261024/retired-source.json).
  The preserved mirror files are under
  `/root/kdlock-evidence/10.176.26.71/tests/lock-only-mm-cleanup-20261024/retired-source/`.
- [Non-Git artifact inventory](../../raw/tests/mm-lock-scope-cleanup-20261024/non-git-artifacts.json):
  278 top-level paths enumerated read-only, without rescanning historical archives.
  Installed experimental kernels, captures, source trees, logs and recovery remain.
  The stopped kdmm30 RAM artifacts are volatile; its interrupted compressed image
  is not a verified backup. Permanent cleanup requires separate exact-path approval.

The unrelated changes in
`bench/results/10.176.26.71/tests/vm-disk-cleanup-20261022/README.md` remain untouched.
The untracked, never-executed kdmm30 preboot helper was moved without data loss to
`bench/results/10.176.26.71/raw/tests/mm-lock-scope-cleanup-20261024/unexecuted-verify_install.py`.
No non-Git build, log, kernel, recovery or snapshot is permanently deleted.
