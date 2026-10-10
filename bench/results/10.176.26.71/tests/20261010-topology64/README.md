# 64-vCPU environment verification, 2026-10-10

The VM on Ubuntu host `10.176.26.71` now exposes 64 online vCPUs, two sockets
with 32 cores each, and 24 GiB RAM. Guest NUMA node 0 has CPUs 0–31 and 12 GiB;
node 1 has CPUs 32–63 and 12 GiB. Each vCPU is pinned to the same-numbered
physical host core and memory is bound to the matching host NUMA node. QEMU
service threads share host CPU 63; use guest collector CPU 63 outside workers.

Independent host affinity checks passed for all 64 vCPUs and QEMU service
threads. Guest topology, `nopvspin`, `nokaslr`, system health and pinned Python
dependencies passed. The captured source, config, build, kernel bundle and live
Build ID match `6.1.159-kdclobber2` and
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`. No kernel rebuild was performed.

Current tracked source bytes, including existing source edits, were synchronized
from the Git checkout on `380G10` to the destination mirror and idle ext4 guest.
The source helper's dry run and write path completed, and every approved guest
hash matched its transferred snapshot. Source edits and Git remain on `380G10`;
all subsequent builds, tests and benchmarks run in this VM.

Affected checks executed in the VM:

- `python3 bench/spin_cacheline/test_assembly.py`: seven checks passed.
- The existing provenance fixture exercised the saved-run CLI with its new
  default assembly directory. Exported JIT text/disassembly matched fixture
  hashes, stayed under this machine's test evidence directory and preserved
  source fixture bytes. This is synthetic evidence, with no new JIT execution.

The original migration functional archive lacks `payload-disassembly.txt` and
could not supply the optional saved-run assembly export. Its frozen evidence
was preserved. No benchmark or full test suite was rerun for this topology
change; the [73-session migration receipt](../../bench/migration-20261010T070707Z/README.md)
retains its original 60-vCPU topology.

Fresh recovery snapshot: `topology64-source-ready-20261010`. Saved states from
the earlier 40- and 60-vCPU configurations must not be loaded into this VM.

Guest evidence is `/root/kdlock-evidence/10.176.26.71/tests/20261010-topology64`.
The [host evidence archive](../../raw/tests/20261010-topology64/evidence.tar.gz)
and its adjacent SHA256 file are ignored by Git. It retains environment,
kernel identity, test output and the synthetic export fixture. Current workflow
and machine result placement are in [the project guide](../../../../../docs/PROJECT_GUIDE.md).
