# Source-prepared kernel16 spin pair

This isolated lane extends exact source 7338197a for an explicit Native/KD plain
spin comparison. It has offline routing/validator checks only. No module was
built, signed, loaded or run; no throughput or full kernel compatibility result
exists. Kernel16 private headers and core implementation are unchanged. Do not
apply the patch blindly to 8e88f001 or 9a8801cb: the newer spin layout differs.

The workload remains one increment of the same padded counter, followed by 256
register-only post-work rounds outside the lock, one bulk ioctl per pinned
worker and 100% writes. Spin snapshot version 2 distinguishes it from the existing
mutex/rwsem version 1 without changing the snapshot size. The built module's
nano_family/nano_backend metadata and build receipt must agree. KD uses its
plain spin clobber entries, exact spin family/unlock kind and existing lifetime
records; Native uses native spin_lock/spin_unlock. Unsupported TCLock/spin and
mixed spin-family builds refuse explicitly.

Future build selection is `--families spin --backends native kdlock`, with exact
kernel16 source/output and `--expected-release 7.0.0-38-kdrebuild16`. The builder
compares private include/kernel headers against those of the selected kernel
source before and after build; differing layouts refuse. The builder does not
prove that kernel-source/output/runtime identity is correct by itself. Full ELF,
config, Module.symvers, source provenance, signing and running identity still
need the normal independent checks. Only two modules are selected; no kernel or
TCLock build is part of this lane.

Future runner selection is `--family spin --scope spin-pair`, an explicit
`--worker-cpus` list of eight distinct available guest CPUs and a distinct
`--collector-cpu`. Functional phases use 1/2/4/8 workers; timing requires paired
Native/KD spin functional receipts from the same build, boot, runner and CPU
placement. It adds one 1-second interval per count, with training/compilation
outside timing and fixed-image claim checks between phases. Spin reports raw
whole-run throughput without peak qualification; no normalization is supplied.
KD recording remains on and Native has no KD recorder, so overhead differs and
must be disclosed. A pristine spin guest may start at taint 0; after the expected
signed out-of-tree module the existing final 4096 check remains mandatory.

A matching recovery point, pinned provider/compiler dependencies and fresh
GS/return-symbol proof are required before execution. At source preparation,
the new guest had no verified recovery point. A later recovery task verified
a restore in the same QEMU process; fresh-process restore remains untested.
These source changes do not authorize a boot or module load. The surrounding
validated controller must perform recovery and host placement checks; this selected-family runner is not a standalone VM launcher.

The existing process-wide eight-host-CPU allowance does not prove per-vCPU
pinning. Keep the 40-vCPU/64 GiB profile and allowed host CPUs 16–19, 36–39. The
controller must record equivalent worker/collector/service placement; at eight
workers, collector/service sharing is unavoidable within that allowance.

KD functional phases retain the existing requirement for returned foreign
protected completions at contended counts. NO_JIT is not promoted to that pass.
Snapshot/operation/lifetime checks and synthetic offline records do not prove
real exclusion/progress. Multiple foreign spin bodies under one continuous
physical acquisition remain a separate, unestablished batch witness. No existing
dirty spin-evidence files are included in this lane.
