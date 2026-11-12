# Pending grant collection candidate

This source-only candidate replaces the capacity-wide frame walk in
`kd_episode_collect` with a list of frames whose grant actor has started and has
not finished. The proposed benefit is less frame inspection when most reserved
capacity is unused. No build, executed check or performance improvement is
claimed here. The separate bench session owns all VM work.

The baseline is `b74e65106a9f2315ded12264d570848ed48f0e13`. Its recorder A/B
receipts remain under `/tmp/kdlock-main-recorder-ab-20261112-zk79bf/report`.
The receipt archive SHA256 is
`c57e1a4d18a8e1829387dfd67da9fb45ab527ead219e03d8b0c43b6ca9a5c45b`.
The report SHA256 is
`6d4d76b8679e5b0f869ebc0639eee833d27440d4b2fed283dd7efe5db69a4674`.
Those measurements isolate the combined observation path, not collection cost.
Preserve that revision, its frozen source, kernel9 outputs and recovery entry.

## Ownership and ordering

The current source actor owns the new list under the existing offer/result
ordering. `kd_jit_mutex_drive` rejects a second drive before invoking `run`;
`run` adds its exact frame once, with the existing grant user already held.
Prepared requests and acquisitions cancelled before a grant never enter this
list. No owner pump reads or mutates it. The list is separate from the pool's
guarded live-slot list and conveys no source, grant or physical-release rights.

Insertion compares frames in the same provisioned array and keeps ascending
slot order. Collection preserves the old walk's relative release order. It
still validates current S_W authority through `kd_jit_collect_grants` before
reading any list entry, retains the grant-held/started/linked checks, releases
source image use before the image actor, then finishes the grant actor and
finally calls the unchanged pool collector. Every collection call site remains.
Image, request, source, physical ACK and retirement checks remain unchanged.

The grant user retains each list entry and the saved next entry. The list link
is removed before the grant user's final finish can free or reuse its slot.
The successful path never accesses that frame afterward. A failed finish
consumes no user and restores its held flag and exact list position. Private
cleanup and cancelled acquisition use the same finish helper with an empty
link. Frame initialization resets the link only during cold setup or after
the existing exact slot reservation succeeds.

The change adds one list head per resource set and one link per preallocated
frame. Collection and sorted insertion visit pending frames, so a full set can
still require capacity-proportional work. Cold array initialization and the
pool's live-slot collection remain. Batching, auxiliary stacks, source/image
admission, lock APIs and workload bodies are outside this change.

## Focused checks

`test_episode_collection.py` compiles eight unchanged production function
excerpts and the actual resource/frame declarations with controlled external
source, image and request endpoints. It records input hashes, extracted bytes,
compiler command/output and every case result in a fresh retained directory.
The eight cases cover empty/nonempty authority refusal, prepared versus started
requests, delayed grant unlink, slot-order release, immediate frame reuse,
image return lifetime, each of the three release failure positions, and final
frame access. One case overwrites each released frame before the iterator
advances; another makes the entire frame mapping inaccessible at final finish.

These are bounded userspace C checks in the VM. The source-authority predicate,
image/request endpoints and list primitives are stand-ins; the cases do not
exercise real kernel locking, cancellation races or source transfer. The
unstarted finish case covers the helper used by private/cancelled cleanup, not
the complete cancellation API. Kernel compilation and live fixtures remain
separate requirements.

Set `KDLOCK_COLLECTION_TEST_CONFIG` to a VM JSON file containing the exact
`expected_release`, an existing absolute `scratch_parent` and the absolute
`compiler` path. From the frozen candidate checkout in the VM:

```sh
python3 -B -m unittest discover -s tests -p test_episode_collection.py -v
```

Do not run these checks or any compiler on the source host. Missing inputs,
compiler failure, timeouts and absent live results are not passes.

## Kernel and live validation handoff

`kernel/episode.c` is part of the built-in `kdlock_rebuild` object. Testing new
module headers against the old running kernel9 does not test this candidate.
The frame/resource layout also changes. The test session must build an isolated
candidate kernel from the frozen core, preserve kernel9, and install/boot a
distinct release before building candidate modules against the exact output.
Record the core input manifest, configuration, compiler, ELF hash/Build ID,
boot ID, actual running identity and fresh GS proof. Recheck recovery, idle
state and disk reserve before staging or live work. Frozen inputs stay immutable.

Before timing, run the existing mutex recursive fixture, rwsem reader/mode
fixture and managed killable fixture, with fresh build/boot-bound receipts.
These cover nested return/deferred release, reader/downgrade and cancelled
request retirement affected by the shared collector. Require exact source,
image, physical ACK, frame and final-user retirement plus ordinary shutdown.
Keep fixture failures and recovery separate; never infer drain from timeout.
No full suite, mmap campaign or new contention matrix is requested.

The smallest timing follow-up reuses the recorder-pair plan: both functional
lanes, then three two-second on/off pairs per family, CPU 0/collector 63,
post256, unchanged mix, capacities, proxy limit and training. The nano runner
needs an explicit candidate release and current built-in return-thunk address;
its baseline hardcoded identities must not be reused for a changed kernel.
That runner adaptation is a separate harness change, not a second optimization.
Compare candidate-on with baseline-on and candidate-off with baseline-off;
report each revision/build/boot separately. Keep NO_JIT and unavailable
observation classes, every pair and host-placement limits. Twelve candidate
timed phases provide an exploratory comparison, not strict qualification or
proof that frame scanning explains the full Native/KD difference.
