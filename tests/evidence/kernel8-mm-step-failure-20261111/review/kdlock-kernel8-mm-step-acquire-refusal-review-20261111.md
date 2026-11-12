# Source and saved-object review of the failed deeper MM step

This is source-only diagnosis after the single five-region syscall run failed
retained. It issues no VM command, retry, test, build, project import or Git
mutation and changes no ownership probe or policy. The parent retains sole VM
operation and failure/recovery control. The result below distinguishes exact
machine/source mapping from a source-race explanation that still needs the
first-fault or raw-state join.

## Observed retained record

The saved status observation at
`/tmp/kdlock-kernel8-mm-step-20261111-01/status-step-01/result.json` reports the
runner's `failed_retained` status after
`TimeoutError('client phase jit_round_complete; original owner/fds remain retained')`.
It reports client PID 2908, controller PID 2902 and no completed client return.
The timeout itself proves neither drain nor its cause.

The 1,048,576-byte host serial tail is
`/tmp/kdlock-kernel8-mm-step-20261111-01/host-diagnostic-01/serial-tail.bin`,
SHA-256 `348c831debc43cb2a15d62be1182ab39abf25048d6e289f524e10908adf24990`.
It preserves the original RIP as `kd_jit_acquire+0x45d/0x4b0` with EAX/RAX's
32-bit result `0xfffffff0` (`-16`, `-EBUSY`) and EDX also `0xfffffff0`.
The tail then contains `kernel BUG at kernel/exit.c:916`, a repeated task-death
sequence and a panic at the 10,000-oops limit. Replayed original register text
is not evidence of thousands of independent `kd_jit_acquire` failures. The
tail begins late in that sequence; it is not a complete first-fault record.
No cause is assigned to the secondary `exit.c` BUG without its exact source
and initial-fault sequence.

## Exact object and source mapping

The saved kernel8 object disassembly is
`/tmp/kdlock-kernel8-aux-object-capture-collection-20261111-02/payload/capture/20-instructions.stdout`.
It belongs to the previously pinned `kernel/jit.o` on core
`0d42063ead37dc8fc1631fa56c8348890ede9c5f`.

`kd_jit_acquire` begins at object address `0x1f70`. Its `ud2` at `0x23cd` is
exactly offset `0x45d`, matching the serial RIP and its surrounding code bytes.
The relevant predecessor is:

```text
2234  call kd_rw_write_acquire
2239  mov edx,eax
223b  test edx,edx
223d  jne 23cd <kd_jit_acquire+0x45d>
23cd  ud2
```

This is the source `kernel/jit.c:852-855` writer-acquisition call and its
`BUG_ON(result)`. It is not the earlier operation-enter return, state-publish
BUG, query operation, generated-instruction entry or source CALL lowering.
The prior state-publish branch at object `0x220d-0x2214` has a different BUG
destination. The read-granted, execution-binding and state-transfer BUGs have
different offsets (`0x483`, `0x485` and `0x491`).

The writer return path is exact:

1. `kernel/jit.c:852-855`: `kd_rw_write_acquire(...)`, then BUG on nonzero.
2. `kernel/rw.c:241-248`: argument validation can return `-EINVAL`; otherwise
   it returns `kd_mutex_acquire(...)` directly.
3. `kernel/mutex.c:1020-1033`: the direct acquire wrapper checks its batch,
   enqueues the node and returns `kd_mutex_await(...)`.

The possible propagated `-EBUSY` refusals in this writer path are therefore:

| Source guard | Meaning |
| --- | --- |
| `mutex.c:1028-1029` | passed batch already initialized before enqueue |
| `mutex.c:509-511` | cohort node's possible batch initialized during enqueue validation |
| `mutex.c:970-972` | passed batch initialized on entry to await, after queue publication |

Other `-EBUSY` sites in combine, physical-finish, progress or grant-retirement
helpers do not return through this writer-acquire result. Their failures have
their own checks or are handled by their callers. The recorded return is thus
an initialized-batch refusal; this fact alone does not identify which guard
observed it or explain the batch's initialization.

## Concrete post-publication race in the source

The third guard conflicts with an allowed writer-cohort operation:

| Actor W, original requester | Actor C, predecessor serving W |
| --- | --- |
| Fresh possible batch initialized to false by `jit.c:631` | |
| Pre-enqueue checks pass | |
| `mutex.c:514-518` records the lock, marks enqueued and publishes the offered node/link | |
| | `serve_writer_cohort`, `mutex.c:795-797`, claims W with OFFERED to SELECTED_PROXY CAS |
| | `mutex.c:813` selects **W's** `node->possible_batch` |
| | `start_batch`, `mutex.c:620-654`, establishes the physical writer and sets that batch's `initialized=true` at line 652 |
| Enters `kd_mutex_await`; `mutex.c:970-972` sees initialized and returns `-EBUSY` | |
| The writer return reaches `jit.c:855` BUG | |

This is a legitimate remote-selection interleaving after publication, not a
need to replay source execution or authorize a different native context. The
cohort intentionally uses the successor W's stable batch storage. The source
comment at `mutex.c:802-804` records the ended producer link access and the
retained driver actor. Consequently initialized storage after publication is
not, by itself, proof of an invalid new acquisition.

The fresh-batch checks before publication remain meaningful. The normal
selection/result path already waits for exact turn/result publication and
keeps source, physical batch and request lifetimes distinct. The atomic await
branch at `mutex.c:966-968` already does not impose the same unconditional
post-publication fresh-batch requirement. This comparison identifies a narrow
correctness direction: reconcile the sleepable post-publication await check
with permitted remote initialization while retaining pre-publication checks
and exact selection/result/owner/lifetime assertions. This note does not edit
the guard or claim a tested fix.

## Evidence boundary and next diagnosis

The source race exists independently of the newly admitted `do_mmap` query.
The deeper prefix can change interleaving opportunities without corrupting
S_W. It would be incorrect to infer GS lowering, an auxiliary-stack bound,
the ordinary MM body, or a native RCU/PTL context as the cause merely because
the new run reached more source.

Conversely, the late serial tail alone cannot exclude stale storage, an
unexpected earlier batch initialization or memory corruption. The first
fault, complete saved runtime/event prefixes and any exact retained batch/node
state should distinguish those alternatives. In particular, join the failing
node/acquisition to its reserve, queue publication, remote selection and any
grant/physical-batch initialization before calling this source interleaving
the observed run's cause. Preserve the failed result, original actors' status,
all source/code/protocol inputs and the complete serial bytes before approved
recovery. Do not remove the BUG or lifetime probes to obtain a passing run.
