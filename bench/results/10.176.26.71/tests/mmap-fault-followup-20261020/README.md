# Current mmap/fault integration review

Status: source capture prepared; no new capture or KD mmap/fault test has run.
The single active VM benchmark takes precedence. The capture will run only
after that workload completes and the original recovery VM is confirmed idle.

The [capture script](capture.py) rechecks the live kernel and captured baseline,
recopies the 25 previously audited source/configuration files, and adds
filemap/folio, userfaultfd, ext4/iomap, huge-page and lock/helper sources needed
to inspect implicit unlocks, retry and downgrade. Every old source hash must
match; all new file bytes and provenance remain explicit. It performs no kernel
build, module action or benchmark.

The existing [rwsem integration boundaries](../../../../../docs/design/rwsem_implementation.md#mmap-and-validation-boundaries)
remain in force. The KD object is not installed as `mm_struct::mmap_lock`;
all participants must use one protocol. Ordinary/local ownership, outer-writer
delegation, cancellation, downgrade and originating task context require
separate proofs. The review will identify concrete supported transitions and
remaining blockers; a native syscall result cannot validate KD integration.
No real mmap/page-fault execution through KD is claimed.
