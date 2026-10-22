# Actual mmap-lock body correctness

This probe targets the opt-in compiled `MADV_DONTDUMP` / `MADV_DODUMP` body in
the experimental kernel. It does not delegate readers, the hardware fault
handler, general mmap creation, or arbitrary generated code. It requires a new
captured experimental kernel containing `body.c` and `kd_mmap_advice.inc`.
The previously installed `kdmm1` image does not implement this interface.

After the approved kernel transition, actual snapshot verification and the
ordinary actual-mm API probe, run in the same idle VM:

```sh
python3 tests/kernel/mmap_lock/body/run.py \
  --kernel-source /root/kdlock-kernel-work/mm-body-20261022/candidate-1/linux \
  --kernel-baseline /root/kdlock-kernel-baselines/mmap-kdmm2-20261022 \
  --output /root/kdlock-evidence/10.176.26.71/tests/mm-body-NEW
```

The client creates sixteen isolated three-page anonymous VMAs without touching
them. Kernel callers retain and use that exact mm. Two simultaneous local
readers hold the real mmap lock while sixteen writers publish; releasing the
readers allows a real combiner batch. The first phase performs 2,048 whole-VMA
dump-flag changes and reads each result back. Completed in-tree bodies must
name different origin and executor tasks. The second phase requests sixteen
partial ranges, forcing native splitting on the origin and exact owner/ACK
handback. The third phase performs 512 local calls after the sticky refusal;
delegated completions and handbacks must remain unchanged.

Run a second fresh client with `--cancellation` on the runner. A healthy head and
one follower publish behind a real local reader. SIGUSR1 must not complete the
killable request; SIGKILL cancels the follower, which retains its link until the
reader releases and the head consumes it. Require EINTR, no victim VMA mutation,
one successful head, one cancellation, and exact queue/slot cleanup. This proves
safe retirement, not bounded cancellation latency behind a blocked predecessor.

All workers must join, the exact pool/queue/owner state must be idle, and all
VMAs must unmap before ordinary module unload. A timeout leaves the run and
module in place for diagnosis. Run untouched mmap/munmap and page-fault tests
separately; their success is not a claim of delegated mmap creation or faults.
The [retained stage](../../../../bench/results/10.176.26.71/tests/mm-body-20261022/README.md)
passed on `6.1.159-kdmm2`: 55 body checks, 1,690 different-task completions,
15 exact handbacks/ACKs, 512 sticky local calls, and 11 separate cancellation
checks. Both Native and KD ordinary MM workloads also passed. The VM returned
to recovery. No timing or p95 work belongs to this stage.
