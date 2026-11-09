# Matched mmap1 scaling: Native complete, KD learning stopped

The Native arm completed all 16 points. KD produced no accepted quiet point
and no worker-attributed proof in this campaign. All 32 KD learning applications
passed and drained, but their rates are unscored. There is no measured KD gain
or Native/KD throughput comparison here. The candidate remains unaccepted and
`master` remains `20fde062729703208ac54445f51fc0f21f24e0e8`.

## Identities and method

- Native runner: `14cc632d8e84010448ee84a6411f8bf8f5220a01`.
- KD runner: `f9fdaa2aa6a71ca0b03dd3a859d63bf746c0983a` on
  `codex/mmap-reached-jit`.
- Provider and daemon build source:
  `130b65939053026339014833774e5fb11b234972`. Their production source and the
  original JIT source are unchanged by the later controller commits.
- Kernel: `7.0.0-38-kdscope5`, Build ID
  `5f2fce72a33480f6e79a79b374b21a0db377ecd1`; Native uses `kd_mmap=off`, KD uses
  `kd_mmap=on`. The ordinary development kernel is a different build.
- Native boot: `fac26aa8-65ee-41c5-b1d9-8aa2be6ac155`; KD boot:
  `76f63ec3-5a66-4030-8d99-f20631fcb7e7`.
- Unchanged will-it-scale: `75f66e45697e6f5f49c33dd950c4e6b289198f8f`;
  `mmap1_threads` / `mmap1_processes -t N -s 2 -m`. Six warmup samples precede
  two measured totals. Throughput is their sum divided by two nominal seconds.
- Grid: `1,2,4,8,16,32,36,60`, one scored round per point. This is the initial
  eight-count subset, not the complete standard 21-count grid.
- 64 vCPUs, 24 GiB, CPUs 0–31 on node 0 and 32–63 on node 1; requester CPUs
  `0..N-1`, collector 63, KD executor pool `0-61`. Host policy remains 2 GHz,
  performance governor, turbo disabled; lazy preemption. Timing is exploratory.
- Selected roots: `0xffffffff817b6f68` (`vm_mmap_pgoff+0x118`) and
  `0xffffffff8181c73b` (`__vm_munmap+0xbb`). No caller body was modified.

## Native results

All points passed placement, data and drain checks. Units are mmap/munmap pairs
per nominal second. One round provides no repeat variance.

| Workers | Threads | Processes | KD threads | KD processes |
| ---: | ---: | ---: | --- | --- |
| 1 | 281886.5 | 354007.5 | learning stopped | unrun |
| 2 | 270153.5 | 659820.5 | unrun | unrun |
| 4 | 233240.5 | 1262634.5 | unrun | unrun |
| 8 | 225144.5 | 1692926.0 | unrun | unrun |
| 16 | 212817.0 | 1761663.5 | unrun | unrun |
| 32 | 199676.5 | 1793531.0 | unrun | unrun |
| 36 | 160882.0 | 1550656.0 | unrun | unrun |
| 60 | 106530.5 | 1210612.0 | unrun | unrun |

The 32-to-36 decline also exists in Native. Worker count and NUMA placement
change together here, so this table alone does not isolate a NUMA cause.

## KD outcome and precise stopping cause

| Root | Final generation | Final status | Distinct CALL additions | Distinct IJ edges | Successful publications |
| --- | ---: | --- | ---: | ---: | ---: |
| `0xffffffff817b6f68` | 33 | NORMAL, still advancing | 28 | 4 | 33 |
| `0xffffffff8181c73b` | 19 | Native-only (`-3`) | 17 | 2 | 19 |

All append-history lines are distinct; no repeated CALL or IJ addition was
found in these final tables. That does not count dynamic visits or establish
which task first reported an edge. The final mmap addition is
`0xffffffff818171b0` (`can_vma_merge_right`). Generation 33 was published after
the last application; its next runtime frontier was not tested.

Munmap first became Native-only after learning index 18, the nineteenth
application. Its attempted generation 20 ended at `0xffffffff81817f57`
(`__split_vma+0x2e7`): the decoder refused a reachable undecodable block after
three decode passes. Cached text was 143360 bytes, below the 262144-byte bound;
7059 instruction bytes / 1830 instructions were decoded, with one incomplete
block. The last learned CALL was `0xffffffff81807810` (`anon_vma_clone`).

The matched disk ELF has `e8 44 d1 ee 00` at the refused site, a CALL to
`__SCT__WARN_trap`. The campaign did not retain the live patched bytes. Disk
bytes do not establish the runtime encoding. This is not evidence that the
warning branch executed: the failure is in static decoding of the expanded
reachable graph. No entire critical section should become permanently local
merely because such a branch exists.

The pool used/published 52 of 128 descriptors, with 76 free and zero private.
Capacity exhaustion did not cause the stop. There were 53 compiler jobs: 52
succeeded and one returned Native-only. The 32-run learning allowance was then
exhausted while the mmap root still advanced. The controller never reached
its separate proof phase or any quiet thread/process comparison.

## Controller evidence and limitations

The final revision passed 22 focused checks in the VM; the existing observer
built successfully. The provider/daemon build was reused with checked hashes,
not rebuilt or claimed as a new lock implementation. The initial fixture
failure and both earlier Native setup failures are retained. Neither Native
setup failure started an application.

The same provider, daemon PID/device description and workspace survived all
32 KD application lifetimes. The recorded 130 translation phase events show
translation stopped throughout each application. All 53 compiler intervals
are disjoint from all application intervals. Compiler wall time totals
757.454646492 s; application wall time totals 257.175813493 s. These are whole
lifetimes, not the scored interval or critical-section time.

Four early guest progress reads were issued before scoring and are retained.
Their possible contribution to learning is unattributed. They were stopped
after recognizing that a newly created guest MM could bind while the factory
was active. Later monitoring used only the existing source-host logs and host
serial log. No quiet point was scored, so no rate is presented as unaffected
by those reads.

The serial excerpt retains ten blocked-task messages around guest time 370 s.
It has no stack trace, so idle versus active wait attribution is unproved.
The no-work service loop uses `TASK_UNINTERRUPTIBLE`, making an idle report
plausible. No detector or validator was disabled. There are no scored KD
windows with which to correlate these messages.

Source inspection also finds `kd_service_pin_cpu()` excludes every active
origin CPU. With 60 simultaneous requesters on CPUs 0–59, pool `0-61` can leave
only CPUs 60 and 61 for executor pinning. This is a code constraint, not a
measured explanation of a KD result in this campaign.

## Retirement and next correction

After the controller exited, the fresh finalizer observed one residual binding.
Bounded ordinary CPU activity reduced it to zero. Exact retirement returned
`state=2, modules=0, frames=0, writers=0`; ordinary unload and final idle passed.
The original failed result remains unchanged. Normal kernel
`7.0.0-38-kdlock1`, Build ID `b61c7bef25d2068f2a05ca3c31a5714c20c4aa62`, was
restored and verified on boot `3df3b864-2ce2-4192-8cd0-beaa327ba871`.

The next bounded step is to retain the live bytes at the exact refused site
on the matched Build ID using the maintained leased instruction reader, then
reproduce its decoding. Support the exact form or give that reached branch an
explicit original-site continuation without making the whole entry local.
Preserve IP/SP/flags, actual CALL/RET words, owners, source leases and final
ACKs. Do not copy a warning instruction into a helper address: its original
site identifies its kernel record. Do not raise learning or image caps to
hide this failure, reuse unversioned module IJ targets, or weaken proof gates.

Raw application records, every unscored rate, compiler log, final histories,
identity captures and failed/positive checks are retained beside this report.
`retained-files.json` also binds final generated artifacts kept in the VM and
the source-host collection. `analysis.json` contains the exact counts and phase
checks. No Nano acceptance or performance acceptance follows from these checks.
