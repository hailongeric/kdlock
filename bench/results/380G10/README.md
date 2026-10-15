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

Source-host maintenance receipts are separate from those historical VM runs:
[documentation cleanup, 2026-10-12](tests/documentation-cleanup-20261012.json) and
[documentation refresh, 2026-10-15](tests/documentation-refresh-20261015.json).
The latter contains only static documentation/source/evidence checks.
The later [documentation and file cleanup](tests/documentation-cleanup-20261015.json)
updates current guides and records removal of generated caches and verified
duplicate extractions, with their retained recovery archives.

Ignored raw evidence and source-host scratch files are retained in `raw/legacy/`.
Some entries are documentation or maintenance artifacts with no measured machine
identity; this directory records their storage origin, without relabeling their
contents. See [the common layout](../README.md) for relocation and compatibility.
