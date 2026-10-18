# Main consolidation validation, 2026-10-18

The consolidation preserves the accepted KD-only mutex runtime and integrates
compatible benchmark tooling, documentation and historical evidence. Builds and
tests ran only in the VM on `10.176.26.71`, in frozen copies under
`/mnt/kdlock-builds/main-consolidation-20261018/`. No module was loaded and no new
benchmark timing, whole-project suite or kernel rebuild/reboot was performed.

## Results

| Check | Outcome |
| --- | --- |
| Accepted runtime equivalence | All 181 non-documentation provider/header/translator/daemon/TCLock/payload files match `d2a2304` byte-for-byte |
| Historical evidence preservation | All 369 imported non-Markdown payloads match their original Git versions |
| Dependencies and live kernel identity | Passed; `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot `b65f0205-c8f9-4385-8b13-039cbce243a6`, CPUs 0–63 |
| Provider W=1 build | Completed; 43 warning lines (objtool, macro redefinition and locale diagnostics) retained in the log, not claimed warning-free |
| Daemon and benchmark client builds | Passed with `-Wall -Wextra -Werror` |
| Basic C checks | Both passed |
| Clobber ABI checks | Spin/mutex wrappers, direct spin shell and premature-frame-release negative control passed |
| Benchmark tests | 10 peak, 15 client, 49 direct-runner and 13 rwlock-runner tests passed; no skips |
| Full catalog plan | 945 planned synthetic mutex sessions: five sizes × 21 counts × three arms × three repetitions; preview only |
| Provider imports and final VM state | No Linux mutex API imports; idle, no new kernel BUG/Oops/lockup |
| Static documentation/source audit | No broken local links/anchors; Python AST parsing and Git whitespace checks passed |

The first direct-runner attempt had one failed assertion expecting the old
collector default of 30. The default is now 63 for the documented VM. Only that
test expectation changed afterward; all 49 direct tests passed on the final
source. The original failure and complete logs remain in the archive.

The initial health wrapper also stopped because it assumed the kernel ring log
could not rotate. Its retained overlap shows exactly two added lines from the
clobber fixture's deliberately broken premature-frame-release case. A targeted
repeat recorded the child PID, SIGSEGV return code and matching log entry. All
unmutated clobber fixtures passed. This expected userspace negative control is
recorded separately from kernel health; no general fault waiver was introduced.

## Evidence and limits

- [Guest results](guest-validation.json), [negative-control attribution](negative-control.json), [initial log assessment](initial-log-assessment.json)
- [Runtime hashes](runtime-equivalence.json), [imported evidence hashes](imported-evidence.json), [static audit](static-audit.json)
- [Catalog preview](catalog-plan.json), [raw archive receipt](archive.json), [remote cleanup receipt](remote-cleanup.json)
- [Branch/file dispositions](../../../../../docs/history/main-consolidation-20261018.md)

The raw archive retains both attempts, all command logs, source manifests,
kernel imports and kernel-log snapshots. Frozen build sources remain on the
guest data disk. Final documentation-only edits are outside those test snapshots;
the runtime and tested benchmark code retain their checked identities.

The independent collector-sharing update is validated by the compiled client
parser, peak-accounting tests and plan checks. This pass does not measure live
64-worker scheduling or claim its performance. The accepted
[c01/pipebytes performance matrix](../../bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
remains the performance evidence for the unchanged lock implementation.
