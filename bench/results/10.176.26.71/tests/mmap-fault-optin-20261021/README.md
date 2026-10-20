# Opt-in mmap/fault implementation stage

Status: focused correctness and preservation review complete. Native/KD passed
`live-4`; TCLock passed `live-5`, both at `21451da`. Three failed preparation
attempts remain preserved. Timing, full-mm integration and performance acceptance
remain open; see the [explicit final status](final-status.json).

This follows the retained 46-file mmap/fault review and `d7f7358`, on source
host `380G10` with the same recovery VM. The main agent remains the only writer
and serial test executor. No guest kernel changes or access-setting changes
are planned. The owner-interval diagnostic stays inconclusive; its unvalidated
estimator will not be extended to five workers. All seven mutex regressions and
performance acceptance remain open.

The implementation is a module-owned mapping with a private backing-state lock,
not substitution of selected native mmap-lock calls. Its supported cases,
pre-publication Native fallback, exact originating-task scope and retained
full-mm blockers are defined in the [design](../../../../../docs/design/mmap_fault.md).
Actual CPU faults use ordinary callbacks; controlled ioctls exercise RETRY,
NOWAIT and COMPLETED without attributing those branches to a hardware-fault run.

The fixed correctness order is Native and KD first, then a separate TCLock
validation if both pass. Each invocation runs basic plus directly affected
checks, preserves frozen inputs and retains every failed attempt. No parallel
test or comparison runs are authorized by this plan.

## Retained attempts

`live-1`, source `581ff9c`, stopped in the basic build because the snapshot
omitted `daemon/`, required by `basic/test_daemon_policy`. The control-call
program compiled, but neither basic suite completion nor module correctness is
claimed. No project module was loaded. The failure, source snapshot and logs
remain untouched; actual VM idle was checked before correcting the runner's
snapshot dependency list.

`live-2`, source `7077fcf`, passed both basic programs and built the provider,
TCLock rwlock, payload and client. TCLock module loading failed with
`Cannot allocate memory`; the kernel recorded a 520-byte, 64-byte-aligned
reserved-per-CPU allocation failure. No mmap client ran. This is retained as a
failed attempt, not a correctness pass. The unused KD provider reported zero
modules, writers and frames, retired to state 2 and unloaded normally; actual
idle was then confirmed in `live-2/cleanup.json`.

The same log exposed ignored observation parameters: this runner had compiled
the production provider without the required benchmark overlay. The follow-up
uses the existing private observation preparation, retains its prepared hashes,
and verifies actual parameter values. It also uses the existing allocator hint
refresh module before provider loads, unloaded before any client runs. No
allocator metadata, kernel code or lock admission is changed.

Static review separately found that the controlled fault-in path rechecked
shared/write/execute mode but omitted current read permission. The follow-up
requires `VM_READ` and adds a negative `PROT_NONE` case with zero callback
attempts and exactly one native mmap acquisition/release. No unsafe probe was
run against the earlier implementation. Native/KD validation must pass on the
new revision before the separate TCLock case is eligible.

`live-3`, source `6afa68f`, passed both basic programs and built the observed
provider, allocator helper, TCLock, payload and client. After KD loaded, a
second allocator helper failed to reserve 4,096 per-CPU bytes. No mmap client
ran. The ELF per-CPU sections were 7,592 bytes for observed KD and 520 bytes for
TCLock; the evidence does not distinguish remaining capacity from allocator
hint/fragmentation effects. Exact zero-user retirement, normal unload and actual
idle are retained in `live-3/cleanup.json`.

The next revision builds the common payload against one provider per run,
following the existing comparison runners. Native remains available in both
builds. Compiled mode and actual ELF imports must agree; the unavailable backend
is refused before object creation. All fault, permission, ownership, fallback
and lifetime oracles remain. KD retains observed zero-JIT and exact source
retirement checks; TCLock retains its context-quiescence check. An absent KD
provider's counters are recorded as unavailable, never as measured zeros.

`live-4`, source `21451da38347dd8b1375ca7570ebb56df1e29f98`, passed both basic
programs and the Native and KD clients, 96 checks each. Each main backing object
recorded 408 fault callbacks, 409 balanced reader pairs, 1,013 balanced writer
pairs, six closed scopes and one downgrade, with zero errors and zero remaining
VMAs. Controlled ordinary, RETRY, NOWAIT, COMPLETED and replaced-VMA cases had
the required exact mmap ownership counts; the inaccessible-VMA negative made
zero callback attempts. Explicit Native fallback, private COW/fork isolation
and VMA-only lifetime checks passed. Six objects were destroyed, with zero file
or release-error residue. Observed KD JIT entries/completions were both zero.
Source retirement returned state 2 and zero modules/writers/frames, normal unload
completed and final actual idle passed. The 394 source inputs and four binaries
remained unchanged. TCLock used this successful result as a mandatory
same-revision prerequisite, in a separate serial run.

`live-5`, the same `21451da` inputs, passed both basic programs and the TCLock
client's 100 checks. Its main object recorded 408 callbacks, 408 balanced reader
pairs, 1,012 balanced writer pairs, six closed scopes and zero errors/VMAs.
The difference from Native/KD is the separately checked downgrade: TCLock rejects
it and validates explicit pre-publication Native fallback instead. Four objects
were destroyed with no file or release-error residue. TCLock contexts were
quiescent before normal unload; final actual idle and unchanged inputs passed.
No KD provider was loaded, so its JIT counters are unavailable rather than zero.

| Run | Frozen revision | Result | Compact receipt |
| --- | --- | --- | --- |
| `live-1` | `581ff9c` | Failed basic build: missing snapshot dependency | Failed archive |
| `live-2` | `7077fcf` | Failed TCLock load; no client execution | Failed archive; exact cleanup retained |
| `live-3` | `6afa68f` | Failed second allocator preparation; no client execution | Failed archive; exact cleanup retained |
| `live-4` | `21451da` | Native and KD passed; drained | [Result](live-4-result.json) |
| `live-5` | `21451da` | TCLock passed; drained | [Result](live-5-result.json) |

## Environment and preservation

All builds and tests ran serially in the original 64-vCPU, 24-GiB, two-node VM,
kernel `6.1.159-kdclobber2`, Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, boot
`b65f0205-c8f9-4385-8b13-039cbce243a6`. The actual snapshot
`before-mutex-kdonly-20261017T140354Z` was rechecked. Workers used CPUs 0–4,
with the client coordinator on 63. Host QEMU PID 257489, command, NUMA mapping,
frequency policy and pinning stayed unchanged. Captured thread counts were
67/68/76/69/76 before the five attempts and 67 afterward. These are functional
runs; those changing thread counts are not waived for future timing acceptance.
All three helpers were completed read-only reviewers and touched no files.

The [VM health receipt](final-health.json) verified 2,161 source/prepared/binary
hashes and actual idle. It preserves the two allocator failures separately from
the successful-run kernel logs. The complete unchanged-inventory archives reside
under guest sibling `mmap-fault-optin-20261021-archives-1` and source-host
[`raw/tests/mmap-fault-optin-20261021/archives`](../../raw/tests/mmap-fault-optin-20261021/archives).
The [archive manifest](archives.json) SHA-256 is
`056e73da6c17574c808e42d7a27e8a8cfa6db2ae0e5e5479f31ecb3bb7076454`.

| Archive | Contents | SHA-256 |
| --- | --- | --- |
| `failed.tar.gz` | `live-1` through `live-3`, including cleanup | `3835ebf6ad72116733db8196e4dde46533c8da23980d1aaaac1ebced2b5914a2` |
| `native-kd.tar.gz` | Complete `live-4` | `b470b7da4157186d9fac9ec8fa1b9fc5aa4a20aa0904b437e7cfa15c4ce4aef7` |
| `tclock.tar.gz` | Complete `live-5` | `8f025271094c480732948af5899be50fe1b2671964b5ab8adb44a557425963c8` |
| `metadata.tar.gz` | Host/sync/console/supervision/health receipts | `74840139b32f8fad56681ef0cddfa7f22e0fc72443222b959b6dbbe3b2d222b9` |

The source-host [inert review](offline-review.py) passed
[36,772 checks](offline-review.json) with zero issues: 2,965 archive members,
2,677 files, no symlinks and 17 ELF manifest entries. It checked committed Git
bytes, reconstructed observation patches, actual ELF modes/imports, all six
scope outcomes per backend, exact acquisition/release and retirement receipts,
and host identities without executing archived code. The canonical file hash-map
SHA-256 is `1fab5c9409c6f5d546ef1be052d7025081fee1a2a7427d08f5556867f24af8e6`.

## Supported comparison preparation and open gaps

The [comparison input and scope plan](comparison-plan.json) binds both successful
builds and defines the common shared, read-only, preallocated mapping work.
Native/KD ordinary backing locks and TCLock's short backing lock can be compared
only within that supported scope. Private writable/fork fallback and downgrade
remain separately labeled functional controls. The current clients are not
matched timing workloads: the Native/KD client also performs a downgrade, and
all clients include forced coordination, negative cases and lifetime checks.
A timed client, fresh frozen artifacts and controlled repetitions are still
required; no timing or variance estimate is claimed here.

Signal-driven cancellation, multiple simultaneous metadata writers, remote or
generic filesystem/DAX/userfault callbacks, full native-mm object conversion and
delegated MM ownership transitions remain unvalidated. The owner-interval
diagnostic remains inconclusive with no five-worker extension or causal fix.
All seven mutex points remain unresolved: `c08-t03`, `c08-t04`, `c08-t05`,
`pipebytes-t03`, `pipebytes-t05`, `pipecap-t05` and `rcuht-t02`. Their prior
timings, variance and host/class gaps stay in the
[latency](../../bench/mutex-latency-20261021/README.md) and
[ownership](../../bench/pipecap-owner-20261021/README.md) reports; this functional
stage cannot resolve or accept those regressions by implication.
