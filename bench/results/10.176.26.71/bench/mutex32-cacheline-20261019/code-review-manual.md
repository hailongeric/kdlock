# Candidate machine-code review

Static review of candidate `76af84414bd4548e11f60c67ae7174ec63644496`
passes the five manual obligations listed in [code-review.json](code-review.json).
This review covers the candidate arm before the separate prefetch trial. It
inspects frozen ELF data on `380G10`; it does not build, load or execute it.

The inspected inputs are bound by SHA-256:

| Input | SHA-256 |
| --- | --- |
| Packed32 provider | `849b9435466850014f597b5ce85a84a3030195203c3ec9b277d8efae83f9d8b6` |
| Candidate provider | `c1cd9fc6c6acbc7e4c7c43fc79e9b35cdbeeb36699d54c0a288296c151dd0b0d` |
| Packed32 workload | `a4c65953f49304129928886bc8538e6fa0b1da4eaa3cc3ca4c5949c1c0384b21` |
| Candidate workload | `e4d00099d944daae5cb1e2bd13c84a046f27adbaa035327c062c427e9d11a837` |
| Automated review JSON | `fe5ec1fd0ccd2c516db8ef65d0a36e10527bda28d2eb6eaf0ed7c18412e033f1` |
| Review script | `86e6f5f882fece2bdedd6815db0e3ff6990ed60c3d7b1ea771165291e9c9bcbb` |

The JSON records the `nm` and full `objdump -dr --no-show-raw-insn` commands
and their output hashes. Source/archive binding and live validation are
separate checks. Addresses below are unrelocated `.text` addresses in these
specific ELF files; they are not guest virtual addresses.

## Queue-head decisions

Candidate `__kd_mutex_lock_slowpath` starts at `0x12730`. At `0x1284f`, the
head loads its own node's `next` pointer. A nonzero pointer falls through
`0x1285b` to COMBINER publication and `kd_mutex_run_combiner`, skipping the
tail load and retirement CAS completely. The initial queue publication at
`0x12764` remains an `xchg` on lock offset `+28`; this optimization concerns
the later head decision, not initial publication.

For an empty link, `0x128e0` loads the delegation tail and `0x128e4` compares
it with this node's encoded tail at node offset `+72`. A different tail
branches directly to `0x128fa`, the delayed-link load, without executing a
locked operation on the lock. If they match, `0x128eb` executes the retained
`lock cmpxchg` of that tail to zero. The returned old value is compared again
at `0x128f1`: success jumps to the ordinary head-exit path at `0x12878`,
while failure enters the delayed-link loop. The loop at `0x128f8` through
`0x12906` retains PAUSE and repeated link loads until a real successor appears.

The source's two link reads are `smp_load_acquire`, which compile to ordinary
loads on this x86 build. The producer's full tail exchange precedes its link
publication and orders the initialized node fields before that link. Skipping
the failed CAS therefore does not discard the publication ordering. The
origin retains its exact CPU/slot reservation throughout this decision, so
an observed different tail cannot become this same encoded slot again before
the origin retires it. The optimization neither releases a node early nor
allows a delayed publisher to write a reused node.

## Ownership checks

Candidate `kd_mutex_execute_cs` starts at `0x10ee0`. At entry, `0x10f31`
loads the authoritative owner, masks the low three flags and compares it with
the current task. `0x10f44` rejects PICKUP. `0x10f52` reads the gate phase;
masking with `0xfffffffd` and comparing with one accepts exactly HELD (1) or
COMBINER (3). The separate physical-owner reload and comparison remain at
`0x10f66` through `0x10f70`. Rejection still reaches the existing BUG paths.

Retirement retains fresh checks after the frame and routing validations.
`0x11fe6` reads current, `0x11fef` reloads owner, and `0x11ff5` through
`0x12001` check physical identity and PICKUP. The phase load at `0x12003`
accepts only HELD/COMBINER. `0x1200e` reloads the physical owner again and
checks it at `0x12015`. Any failure reaches the BUG at `0x1206b`; frame
retirement stores begin only after all these checks, at `0x1201e`.

The earlier packed32 retirement called `kd_mutex_delegation_owned` at
`0x13e49`. The candidate inlines the same predicate at that site. Its global
external definition still exists at `0x148d0`, and separate unlock routing
still calls it. That external body retains null-lock and foreign-task
rejection, owner identity, PICKUP and phase checks. There is no cached
ownership result spanning the translated body and no removed physical probe.

## Outer producer hint

The candidate workload's `rb_body` occupies `0xf0` through `0x1fd`; its global
continuation label `rb_entry` is inside that function at `0x15a`. Reviewing
the full function, including the instructions after this label, shows that
the owner load at `0x11d` must observe zero before reaching the acquisition
CAS at `0x1d1`. The CAS itself decides ownership. Its failure returns to the
gate hint at `0x12d`; only an exact comparison with COMBINER (3) terminates
the retry window early. Other phases retain PAUSE and the eight-probe bound.
The embedded phase load replaces the old out-of-line hint call without
changing the acquisition or fallback conditions.

These findings establish the intended generated control flow for the inspected
artifacts. They do not quantify cache transfers, prove all concurrent kernel
interleavings, or establish a performance improvement. The deterministic
fixtures, VM probes and separately recorded timings remain necessary evidence.
