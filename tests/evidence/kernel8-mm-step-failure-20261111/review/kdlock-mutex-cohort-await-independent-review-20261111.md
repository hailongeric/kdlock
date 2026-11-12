# Independent source review of the cohort await correction

Result: **no source-level finding** in the reviewed two-hunk change. This is
static review only, not a compiled or runtime pass. The source-proved race and
the failed run's exact writer-acquire refusal are related evidence; the raw
queue interleaving in that run is still unavailable.

The reviewed checkout is `/home/eric/vm/vm-shared/kdlock-main`, HEAD
`35840b0ff18c506a6395d64f6ef9d5a0079b4788`. The only unstaged source change at
inspection was `kernel/mutex.c`. No file in the repository was edited, no VM
command or test/build/project import was issued, and no Git mutation was made
by this review.

## Ordering and caller coverage

The correction distinguishes the private pre-publication batch from the same
storage after publication. In the combined acquire path, `mutex.c:1033-1039`
now requires exact `node->possible_batch == batch` for both atomic and
writer-cohort requests, then retains the original `batch->initialized`
rejection. `kd_mutex_enqueue` still independently requires the declared possible
batch to be present and fresh (`mutex.c:506-511`) before it publishes the node
(`514-518`, and `link_request:479-492`). No external cohort actor can legitimately
construct this new request's batch before its queue publication.

After publication, a predecessor can claim OFFERED to SELECTED_PROXY
(`serve_writer_cohort:795-797`), take **the successor's** possible batch (`813`)
and initialize it (`start_batch:620-654`). Thus await must permit that exact
storage to be initialized by the remote actor. The new cohort branch at
`mutex.c:971-977` checks the immutable storage identity without sampling the
remotely mutable initialized flag. This removes the contradictory refusal and
does not authorize a second initializer.

The queue/link publication already orders the previously initialized node and
possible-batch pointer. The pointer is set while private in `jit.c:631-654` and
is not changed by remote cohort selection. Await does not need a new acquire
read of `batch->initialized` to establish progress: its existing turn/result
release/acquire operations remain the synchronization route. Its original
requester, enqueued and wait-started checks remain. The existing selection CAS,
result-ready check and `start_batch` invariant still determine whether this
requester may initialize a local batch or return a completed proxy result.

All maintained callers and policy branches were checked:

| Caller / lane | Review result |
| --- | --- |
| JIT rwsem/rwlock writers | `jit.c:819,852` prepares WRITER_COHORT and passes `&call->possible_batch`; the pointer already matches the node field set by `jit.c:654`. `rw.c:241-248` forwards that same batch. |
| Default sleepable mutex | Does not select the new cohort branch; the await initialized rejection remains. Its combine path uses the owner's own physical batch, rather than initializing the offered successor's possible batch in advance. |
| Atomic spin / atomic writer | Existing atomic context and exact possible-batch validation in await remain. The acquire identity condition is unchanged for atomic requests; adding cohort to that condition does not loosen it. |
| Local/non-delegating and killable cohort writer | Exact batch identity remains valid even if the request wins locally, cancellation wins, or no proxy is selected. Existing cancellation, readiness and result ordering are unchanged. |
| Native rwsem compatibility records | Native nodes intentionally have `possible_batch=NULL` (`mutex.c:1404-1445`) and use the separate native enqueue/start path. Ordinary acquire/await already reject `native_local`; this fix does not route those records through the source cohort path. |
| Split enqueue/await API | No maintained call site outside the combined wrapper was found. Its declared reserve-before-enqueue contract (`mutex.h:243-256`) and enqueue's fresh possible-batch check remain; cohort await now enforces that exact same reserved identity. |

The source call-site search found the combined acquire in `kernel/jit.c`, its
rw wrapper in `kernel/rw.c`, the wrapper-to-await call in `kernel/mutex.c`, and
the public declarations. No different maintained direct caller depended on a
cohort batch pointer distinct from `node->possible_batch`.

## Lifetimes and invariants retained

No batch/node field is reset by the new branch. No result, callback, unlock,
cancellation or retirement probe is removed. Existing physical-finish and reap
rules still prohibit reuse while serving/cohort-active and before physical
release, exact obligation retirement and owner retirement. In particular,
`kd_mutex_reap_batch:1331-1381` clears initialized only after those duties end;
`request_pool.c:78-84` still refuses request reuse while its possible batch is
initialized, its grant is linked or its node is not retirable. The correction
therefore permits waiting on a remotely owned batch, not reusing its storage.

The prior erroneous post-publication read could also race a remotely managed
batch lifecycle. The new pointer comparison avoids using that mutable bit as
an admission condition after the offer is visible. Pre-publication freshness,
result/selection arbitration and terminal lifetime validation remain separate.

## First-fault evidence and limits

The independently read first diagnostic records the first oops, not only the
late replayed tail: at uptime 1195.577328, PID 2942, it reports
`kernel/kdlock/kernel/jit.c:855`, `kd_jit_acquire+0x45d/0x4b0`, EAX/EDX
`0xfffffff0` (`-EBUSY`). The subsequent `exit.c:916` BUG is oops number 2.
The existing saved `jit.o` mapping places this offset at the BUG after
`kd_rw_write_acquire`; this does not identify which initialized-batch guard
returned the error or directly show the queue scheduling order.

The 28,096-byte diagnostic slice was found byte-exact at offset 66,764 of the
36,616,785-byte current-boot serial stream. The first BUG text is at offset
70,860, matching the saved index. Decompressed current-boot bytes independently
match that index's raw SHA-256. The source interleaving above is a concrete
allowed path to the refusal; it is not asserted as a captured queue trace.

Remaining validation: build the corrected kernel and run directly affected
checks only in the VM under its ordinary authorization/gates. Preserve the
failed run, panic and original serial/receipts separately. The fix has not
been executed or shown to pass the deeper syscall run. This review does not
attribute the failure to source lowering/context, change the auxiliary-context
premise, or establish MM completion/performance.

## Exact reviewed inputs

| Input | SHA-256 |
| --- | --- |
| Corrected `kernel/mutex.c`, 49,000 bytes | `014b4a9cfb4609eb8a1e49cc14e715302b13060dc641519a7e68b22a7e515564` |
| HEAD `kernel/mutex.c` before correction | `949ed7175a6f68fc6e91ac3ef84742e4f631fc159809dab0bc23f342d81ecbc0` |
| `/tmp/kdlock-mutex-cohort-await-fix-20261111.patch`, 900 bytes | `89efc3046e901959d2d851af81e0f04dce39b0b6df1e612bbe1f8df614237154` |
| `kernel/mutex.h` | `85df670f30b3e8598d5fdab44b86f4e4095b4a3287d064c6a28d1d4119264ade` |
| `kernel/jit.c` | `8afc20568eea8d7f4022033ec6b14c70752a0e225fd2cb0d58f0957e5746a6b2` |
| `kernel/rw.c` | `1f17e4d0d7d4ded6d6b7d2bf123f7f36bda309f0643ccf1897320be6e49f6393` |
| `kernel/request_pool.c` | `df30718bf96fcdb637ed6ff8b1459de5963e255069556001685dc1d5cf59ee4e` |
| `serial-full-01/first-diagnostic.txt` | `834c5d5aa72e205bdc56c8d0acdd36e931eec20edbabccaf53bcd6a68a341666` |
| `serial-full-01/index.json` | `c767439d1aea1c163330266c6e740f18dbe28f158626971aa05dc6f06f269888` |
| `serial-full-01/current-boot-serial.bin.gz` | `5bfee7994d3e4a79c05b40d8ceedee63c775c6700baad72ac57050de640f1e7e` |
| Decompressed current-boot serial | `f3f3f88cdcdef2f8401f3e2aa0a50339e7785574ad3ceb0e6a4ce4395d1c5662` |
| Preserved `serial-full-01/serial.log.gz` | `4213bdb114367112a7eefab551e0e80f4a7758b01300dad46ad40b6f6955c776` |
| Saved `20-instructions.stdout` for `jit.o` | `d980ae2c70d5c19461fc9fd44653c70d25e54795df7a0afdf206e68c37f87625` |

Serial paths above are beneath
`/tmp/kdlock-kernel8-mm-step-20261111-01/`; the saved object output is beneath
`/tmp/kdlock-kernel8-aux-object-capture-collection-20261111-02/payload/capture/`.
