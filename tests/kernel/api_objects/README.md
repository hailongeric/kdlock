# Scoped API object participants

This correctness runner invokes the actual userspace syscall paths on
`kdscope1-native`. It uses the same immutable file-table/pipe binding as the
original-body benchmark. Setup/query ioctls select and identify objects; they
do not stand in for the operations under test. There is no kernel test payload,
copied critical-section body, or timing score.

Each of the Native and KD arms runs these bounded clients:

- `setfd_client`: exact close-on-exec flags and duplicate flags, file-table
  expansion, concurrent `F_SETFD`, `dup`/`close` and `/proc/self/fdinfo`, a fork
  with a distinct Native file table, and an unshare that retains the old table
  on another task until its final join. QUERY verifies that an existing binding
  never changes; the replacement table defaults to Native.
- `pipe_client`: atomic record transfer with concurrent `FIONREAD` and
  `F_GETPIPE_SZ`, resize and occupied-shrink behavior, failed output-copy and
  unknown-ioctl recovery, blocked reader/writer wakeups, EOF/EPIPE after final
  endpoint closure, and selector validation/cancel/one-shot/token lifetime.
  Wake tests bracket a sleeping task-state observation with two matching
  `/proc/self/task/TID/syscall` observations before the peer acts. A delay alone
  is not counted as a blocked-syscall witness.

Concurrent observations allow the values permitted by native races. Exact data,
flags, capacities and counts are checked at joined or otherwise stable
boundaries. All helper threads and children must finish normally. The pipe
Native arm briefly arms a setup-only KD selector in its negative control test,
then cancels it before creating another object; that does not change its Native
target objects.

The runner captures the explicit kernel identity, source/binary hashes and
three prepared images, explicitly enables `api_bind=1` and records its `Y`
readback, stops the translator, then starts each client. These
tests establish syscall effects and participant exclusion. Publication alone
does not prove returned JIT execution, and the runner deliberately disables
entry/completion observations. The separate `bench/kernel_api/run.py functional`
gate supplies the required returned-body evidence before any comparison score.

Run only in the designated VM after the new kernel's build, boot and bridge
gates, with the confirmed recovery snapshot and current host qualification:

```sh
python3 tests/kernel/api_objects/run.py --output /root/kdlock-evidence/10.176.26.71/tests/api-objects \
  --boot-id EXACT_BOOT_UUID --host-state CURRENT_HOST_JSON \
  --host-reference REVIEWED_HOST_REFERENCE --host-reference-sha256 EXACT_SHA256
```

The default identity is the exact `kdscope1-native` source/build/bundle tuple;
another boot mode is refused. Success requires all four client sessions, exact
joined case receipts, normal process exit, zero provider references, source and
frame drain, retirement and ordinary module unload. A timeout or kernel fault
retains the module state for investigation; it is never a drain receipt.

The focused runner checks are
`tests/unit/infrastructure/test_api_objects_runner.py`. They validate evidence
parsing with fixtures and do not execute the syscalls or prove kernel behavior.
Source review is complete only when reported by the parent; VM compilation and
live correctness remain separate validation results.
