# Native shared-mm mmap writer correctness

This original Native probe supports the scoped MM work in the
[project roadmap](../../../docs/ROADMAP.md). The separately prepared
[actual-backend comparison](../../../bench/mmap_lock/README.md) reuses the writer
payload with its own Native/KD bindings. These 4 KiB device-mapping checks are
not validation of the planned 128 MiB anonymous mmap1 workload.

The current runner is ported to `7.0.0-38-kdlock1`; execution remains pending.
Run `run.py` only in the verified Linux 7 VM with a current confirmed snapshot,
source manifest, explicit boot UUID, SHA-bound host reference and fresh host
receipt. It builds the standalone
Native observation module and client, runs both basic C checks, and then runs
six focused cases serially:

1. Reject a foreign mm using the same file, reject unsupported mapping modes,
   split a two-page VMA without access, and unmap both pieces.
2. One worker completes 1,000 map/unmap pairs.
3. Sixteen pthreads complete 5,000 pairs each and observe queued Native writers.
4. Close every descriptor while one VMA remains, then unmap it.
5. Repeat the VMA-only lifetime with sixteen threads sharing one mm.
6. Close the descriptor and exit with the untouched VMA; native `exit_mmap`
   must destroy the VMA and release the final file/mm reference.

Every worker reports an exact TID and the same mm, mmap lock and object identity
as the controller. All mmap cycles must have zero faults, zero cloned VMAs,
matching successful creation/close counts and no remaining VMA. The scope case
requires exactly one clone and two closes. Final module health must have zero
files, zero mm references and zero release errors after every completed process.
Failures preserve the module and logs; timeouts do not kill callers or prove drain.
No KD/TCLock provider or guest kernel modification is used.

`capture_kernel.py` is the historical Linux 6.1 source capture, not a current
entry point. Linux 7 uses its authenticated Ubuntu source archive and separate
source/build identity.

The sixteen-worker case additionally retains a real blocked-writer kernel stack,
with an immediate Native mmap-lock caller. It does not infer writer contention
from a queue containing unknown reader/writer types. Kernel-stack access failures
or absence of the required positive observation are failures, not passes.

First run [sites.py](../../../bench/mmap_writer/sites.py) in the idle VM to
derive the exact direct-call bytes and following return PCs from the verified
Linux 7 ELF. Review its retained function disassembly, then pass its receipt
using required `--writer-sites` and `--writer-sites-sha256` arguments. The runner
re-derives those sites before loading the module. A positive site additionally
requires bracketing `D` states, matching wait channels and unchanged scheduler
execution counters. Unexpected compiler call-chain shapes fail closed.
The old [writer_sites.json](writer_sites.json) retains its historical 6.1 identity.
See the [retained diagnosis](../../../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/README.md).

## Three scheduling return sites

The diagnostic revision based on `7814c61a0be20f5db3b9fb41b6079ef6d2938b5f`
extends only the userspace representation of exact scheduling return PCs.
The scope3 ELF has three `schedule` returns in
`kd_mmap_local_lock_slow_signal`: `0x2c8`, `0x3dd` and `0x5d3`.
All three remain in the decoded instruction and return lists. The two spin
rescheduling branches remain reachable in the killable writer path, so dropping
them would produce an incomplete description. A return PC alone does not prove
sleep: the existing task/mm/lock identity, complete caller chain, `D` state,
wait-channel and unchanged scheduler-bracket checks remain authoritative.

The original two-number client form and argument count are preserved. Only a
three-return receipt uses `--wait-returns 712:989:1491` in the two existing
return-argument positions. This explicit form requires exactly three distinct,
positive decimal offsets; malformed values, overflow and a fourth return are
refused. The six-intermediate-frame limit and two returns per intermediate frame
remain unchanged. The mapping runner and separately versioned strict-held
diagnostic use the same argument helper and classifier.

Focused VM checks cover each of the three exact PCs, missing or malformed third
returns, the four-site bound, old-form compatibility and the unchanged rejection
of wrong frames or sleep brackets. Replay of the original baseline ELF capture
and positive raw chains is compatibility evidence only: it does not repeat or
relabel the completed baseline 42-point measurement. Preserve that baseline's
original source, diagnostic, receipts and timing bytes, and retain the failed
candidate capture as a failed attempt. Candidate live correctness uses the new
diagnostic identity before its first timing point. Kernel/runtime sources,
payload ioctl layouts, upstream applications and timed workload code are outside
this change. Source review is not a VM execution pass; all new checks are pending.
