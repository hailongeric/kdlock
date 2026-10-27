# Historical QEMU host I/O diagnostics

This retained subset contains host I/O observations only. Retired benchmark
records and their associated archive members were removed at the user’s request.
Original complete-archive claims no longer apply to this subset.

## Host I/O diagnostics

`host-inventory-1` binds the running PID 257489 to installed
`qemu-system-x86` package `1:8.2.2+ds-0ubuntu1.18` and executable SHA-256
`8a35ccba41582fc6c38b9df85fc9e35fa1d42f414d2d7d8090ee9b2f5e7c0854`.
Its raw command-line hash is
`08a7ad4ddad7da7d6437c5ebcc2987894c2e69b1cd8abd31db0bd491f30ce917`.
Both existing qcow2 drives use writeback cache; no named IOThreads or explicit
aio/pool override were reported. The first snapshot has 68 threads, including
one `worker` pinned to CPU 63, with recent system-disk I/O while KD is idle.

Two serial diagnostic arms, `ram-1` and `disk-1`, each created and verified
33,554,432 bytes with eight CPU-pinned workers, fsync, and a 12-second setup
settle interval. All files remain in their new VM directories. No KD module or
lock workload ran concurrently. These are I/O stimuli, not throughput samples.
The [summary](io-summary.json) retains per-worker host I/O and block counters.
RAM endpoints had 67/68/68 QEMU threads; ext4 endpoints had 71/72/72.
Extra workers had positive write-byte counters. System-disk writes increased
even during the RAM control and both subsequent 12-second observation intervals.
The ext4 arm added 34,648,064 block-layer bytes between its before/after receipts.
Thus ordinary root-disk activity is a demonstrated source of worker I/O, but
these observations do not identify the exact producers or activity in historical
timing intervals. The background writes confound a simple RAM-versus-disk
attribution. These observations do not qualify any historical timing interval.
The [raw index](raw-index.json) binds every full host capture and stderr file
to its retained local path and the 268,489-byte archive, SHA-256
`0ad70baada318e865e8d84d0457c65db318f76d030f92ca893530cedda460e23`.


The [guest I/O observation](guest-io-1.json) sampled 12.066 seconds of idle
process metadata. `jbd2/sda1-8` accounted for 32,768 disk-write bytes;
`multipathd` issued 208 bytes of writes with no accounted block writes.
There were no new/exited processes or access errors. Deferred journal/writeback
activity does not identify the original file writer or the historical timing
effect, so this evidence does not clear any failed host endpoint.
