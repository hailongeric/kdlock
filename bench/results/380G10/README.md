# Historical results from 380G10

These compact comparisons were measured on the original Xeon Gold 6133 host and
its 40-vCPU VM, with 20 guest CPUs per NUMA node. Their captured source, kernel,
boot policy, worker placement and frequency policy remain authoritative.
They are historical evidence; they do not validate the current source or the
new physical host.

- [RCUHT rwlock comparison](bench/rwlock_compare/20261010-rcuht/README.md)
- [Rwlock cacheline scaling](bench/rwlock_compare/20261009-scaling/README.md)
- [Initial rwlock comparison](bench/rwlock_compare/20261009/README.md)
- [Spin/mutex evidence index](bench/tclock_compare/HISTORY.md)

Retained raw evidence and source-host scratch files are in `raw/legacy/`.
The October 21 cleanup removed entries dated before October 1, 2026; see the
[retention note](../README.md#record-retention) and
[removal inventory](tests/repository-cleanup-20261021.json).
Some entries are documentation or maintenance artifacts with no measured machine
identity; this directory records their storage origin, without relabeling their
contents. See [the common layout](../README.md) for relocation and compatibility.
