# Native shared-mm mmap writer correctness

This original Native probe supports the scoped MM work in the
[project roadmap](../../../docs/ROADMAP.md). The separately prepared
[actual-backend comparison](../../../bench/mmap_lock/README.md) reuses the writer
payload with its own Native/KD bindings. These 4 KiB device-mapping checks are
not validation of the planned 128 MiB anonymous mmap1 workload.

Run `run.py` only in the existing recovery VM with a current confirmed snapshot,
committed source manifest and fresh host receipt. It builds the standalone
Native observation module and client, runs both basic C checks, and then runs
six focused cases serially:

1. Reject a foreign mm using the same file, reject unsupported mapping modes,
   split a two-page VMA without access, and unmap both pieces.
2. One worker completes 1,000 map/unmap pairs.
3. Sixteen pthreads complete 5,000 pairs each and observe queued Native writers.
4. Close every descriptor while one VMA remains, then unmap it.
5. Repeat the VMA-only lifetime with sixteen threads sharing one mm.
6. Close the descriptor and exit with the untouched VMA; native `exit_mmap`
   must destroy the VMA and release the final file/mm reference.

Every worker reports an exact TID and the same mm, mmap lock and object identity
as the controller. All mmap cycles must have zero faults, zero cloned VMAs,
matching successful creation/close counts and no remaining VMA. The scope case
requires exactly one clone and two closes. Final module health must have zero
files, zero mm references and zero release errors after every completed process.
Failures preserve the module and logs; timeouts do not kill callers or prove drain.
No KD/TCLock provider or guest kernel modification is used.

`capture_kernel.py` copies the unchanged C/header/assembly and build/configuration
inputs as an inert archive for source inspection on 380G10. It does not perform
the kernel participant analysis in the VM or execute captured code on the host.

The sixteen-worker case additionally retains a real blocked-writer kernel stack,
with an immediate Native mmap-lock caller. It does not infer writer contention
from a queue containing unknown reader/writer types. Kernel-stack access failures
or absence of the required positive observation are failures, not passes.

The writer proof uses the exact kernel ELF hash and return sites recorded in
[writer_sites.json](writer_sites.json), because this kernel filters `__sched`
frames from proc stacks. A positive site additionally requires bracketing `D`
states, matching wait channels and unchanged scheduler execution counters.
See the [retained diagnosis](../../../bench/results/10.176.26.71/tests/mmap-writer-native-20261021/README.md).
