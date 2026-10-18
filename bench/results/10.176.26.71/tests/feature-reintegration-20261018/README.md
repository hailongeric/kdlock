# Feature reintegration validation, 2026-10-18

This round validates the [compatible branch ports](../../../../../docs/history/feature-reintegration-20261018.md)
and new ordinary sleeping KD rwsem. The selected `d2a2304` mutex implementation
is unchanged. Builds, tests and live execution ran only in the verified
64-vCPU recovery VM on `10.176.26.71`; the guest kernel was not rebuilt or rebooted.

## Results

| Check | Result |
| --- | --- |
| Dependencies and kernel identity | Passed; Linux `6.1.159-kdclobber2`, Build ID `5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, CPUs 0–63, collector 63 |
| Provider W=1 build | Passed; existing build diagnostics retained, not claimed warning-free |
| Basic and affected unit checks | Two basic C programs, 104 admission cases, provider lifecycle checks, 52 direct-runner, 4 API-plan, 9 API-report and 20 rwlock-runner tests passed |
| Ordinary rwsem scheduler probe | Passed twice, including the final source-verification/preflight fixes; 8 API checks, 6 cancellation cases, two sleeping readers, waiting writer and late reader sharing CPU 0; zero errors and complete drain |
| Ordinary rwsem workloads | 24 Native/KD sessions: c01/c08, 0%/20%/100% writes, 1/8 workers, 10,000 operations per worker; all correct and drained, zero JIT |
| Existing rwlock regression | Three backend sessions, c08/20% writes/8 workers; correct and drained |
| Proc snapshot correctness | 12 argbounds and 12 explicit-local taskname sessions across Native/TCLock/KD, 0%/20% mutations and 1/8 workers; all correct and drained |
| Rwlock complete-body evidence | c08/100% writes/16 workers: 1,215,191 entry witnesses and matching completions in 1,600,000 operations |
| Argbounds timed admission | Three default-policy, read-only, eight-worker, two-second runs completed 11,617,577 / 12,437,220 / 13,426,516 delegated bodies; entry and completion counts agree |
| Pipebytes API safeguards | Six one-second smoke sessions, Native/TCLock/KD at 1/8 workers, n16 query; all correct and drained; KD eight-worker run recorded 6,837,009 JIT bodies |
| Final health | No project modules/workers left; no new kernel fault records; final provider has no Linux mutex API imports |

The workload runs comprise **61 successful sessions and two retained failed
delegation-acceptance attempts**, all drained. The separate rwsem scheduler
probes also drained. This is focused integration validation, not a full suite,
throughput-parity claim or replacement for the accepted mutex performance matrix.
Diagnostic CPU sampling has targeted unit coverage; no live `perf record` run
was performed here.

## Retained failures and limits

The fixed-iteration argbounds acceptance attempt at 16 workers returned
`NO_JIT`: its data checks passed and image publication succeeded, but neither an
entry nor a completed delegated body was observed. The short functional snapshot
runs also had zero JIT. The later default-policy timed runs at eight workers are
separate evidence; they do not erase the earlier result. Existing native queue
qualification can keep the tiny snapshot body cold. Logs do not identify which
qualification condition vetoed each sample, so this is an explanation consistent
with the evidence rather than a measured branch attribution.

The taskname acceptance attempt at 16 workers exhausted eight fully drained
helper-learning waves without a completed body. It failed preparation before
measurement and does not validate delegation. The archived uncaptured-R13 helper
refusal remains a separate historical limit; this attempt did not reach that
refusal. Its local controls passed without changing the exact `strscpy_pad()`
payload or weakening admission.

The first outer validation wrapper failed its whole-buffer `dmesg` prefix
assertion after all nine commands passed, because older ring-buffer records were
evicted. The final pre-run record remained uniquely present. Inspection of all
899 subsequent retained lines found no new kernel fault. Individual live runners
also captured `/dev/kmsg` from their own start and passed their fault checks. The
original wrapper failure and its [reconciliation](initial-log-assessment.json)
are retained; it is not silently recorded as a successful wrapper invocation.

Ordinary KD rwsem executes locally and has no delegated outer writer API. It is
not installed in `mm_struct::mmap_lock`, has no TCLock arm, and is not a complete
Linux rwsem/lockdep/RT replacement. The proc payloads use controlled module-owned
records, not live task/MM objects or end-to-end `ps` operations.

## Evidence

- [Compact validation](validation.json), [rwsem probe](rwsem-probe-final.json), [final health](final-health.json)
- [Accepted runtime comparison](runtime-equivalence.json), [static audit](static-audit.json)
- [Command records](commands.json), [session outcomes](sessions.json), [source manifests](source-manifests.json)
- [Raw archive receipt](archive.json), [branch/ref inventory](../../../../../docs/history/feature-reintegration-20261018.json)

Raw logs, all attempts, frozen source/build copies, ELF files, publication images,
source/binary hashes, topology and kernel captures are retained in
`bench/results/10.176.26.71/raw/tests/feature-reintegration-20261018/guest-evidence.tar.gz`.
The original guest directory is
`/mnt/kdlock-builds/feature-reintegration-20261018-v1`.
The recovery snapshot was verified as `before-mutex-kdonly-20261017T140354Z`.
Final documentation and compact receipts are outside the tested source snapshots.
