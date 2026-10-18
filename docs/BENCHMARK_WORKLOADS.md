# Benchmark workloads and critical sections

This catalog defines the synthetic and syscall/API workloads selected for
benchmarks on `master`. Use [benchmark commands](../bench/README.md) for execution and
[performance status](PERFORMANCE.md) for measured outcomes. Selection is not
a claim that the current KD version has passed every configuration.

The standard grid is 1–8 workers by one and 12–60 by four, three repetitions per
configuration, comparing KD, TCLock and Linux Native where supported. Rwlock and
rwsem use 1% and 20% writes; rwsem compares KD with Linux Native.
Synthetic bodies run repeatedly inside one ioctl per phase; API workers issue
syscalls individually. Include both categories when requesting the full catalog.

The current accepted [KD-only matrix](../bench/results/10.176.26.71/bench/comparison/mutex-kdonly-20261017T140354Z/README.md)
covers c01/post64 and `api-pipebytes-query-n16`. Broader historical owned-mutex
coverage remains in [history](history/README.md), with its original implementation
identity. Sleeping rwsem with outer writer delegation and extracted proc snapshots have explicit
runner modes described below. Full [process inspection and mmap candidates](#process-inspection-and-mmap-candidates)
remain proposals, outside the runnable standard catalog.

## Synthetic cacheline updates

Each counter is a 64-bit value padded to a 64-byte slot. All workers access the
same selected counters under one lock. The bodies contain explicit updates:

| Label | Updates per operation | Selected payload footprint |
| --- | --- | ---: |
| `c01` | Increment counter 0 | 64 bytes |
| `c08` | Increment counters 0–7 | 512 bytes |

Future synthetic cacheline benchmarks use only c01 and c08 for spin, mutex,
rwlock and rwsem. Select `--cachelines 1 8` in the
[spin/mutex runner](../bench/tclock_compare/README.md). KD mutex uses the selected
legacy delegation protocol.

For example, c01 performs a protected load/add/store:

```c
lock(L);
WRITE_ONCE(data[0].value, READ_ONCE(data[0].value) + 1);
unlock(L);
```

`READ_ONCE` and `WRITE_ONCE` do not make this an atomic increment by themselves;
the lock provides exclusion. There is no allocation, traversal or intentional
sleep in the plain payload. The `cNN` suffix counts payload cachelines only,
excluding lock storage and other metadata. Padding separates different counters;
every worker still shares the same counter in c01.

The current KD mutex occupies 256 bytes aligned to 128 bytes, with lock storage
separate from counters and controls. Native uses its own object layout. The c01
name counts payload cachelines only. Spin/mutex loops currently include 64 dependent arithmetic rounds
after each unlock, defined in [post_work.h](../workload_modules/spin_cacheline/post_work.h).
The accepted c01 1–8-worker profile, later 22-count comparison and expanded
21-count mutex comparison use this post64 setting. An eight-round variant is
a different workload and needs its own baseline; it must not be pooled with
those results.

At completion, each selected counter must match the total completed increments;
unselected counters must remain unchanged.

## Synthetic hash updates (`rcuht`)

The table contains 1,024 buckets and 4,096 preallocated nodes, with keys drawn
from 8,192 possible values. Buckets and nodes have 64-byte strides. One global
lock protects the entire table.

Each worker generates source and destination keys outside the lock. Inside the
critical section it searches the source bucket and, when necessary, the
destination bucket. A missing source or occupied destination ends the attempt.
Otherwise it changes the key in place within one bucket, or unlinks and relinks
the node across buckets. Outcome counters are local to the caller.

Every spin/mutex operation is an exclusive update attempt, including misses and
conflicts. Thus “100% writes” does not imply that every operation changes the
table. Despite the `rcuht` name, this payload performs no per-operation RCU
reclamation or allocation.
Final checks validate node count, unique keys, bucket placement and list links.

## Synthetic reader/writer mixes

| Payload | Reader critical section | Writer critical section |
| --- | --- | --- |
| Cacheline `c01`, `c08` | Load the first counter and compare every selected counter against it; c01 also reloads its sole counter | Increment all selected counters |
| `rcuht` | Search one bucket for a key | Perform the hash move attempt described above |

Readers hold the shared read lock; writers hold the exclusive write lock. Reader
validation uses caller-local results. Hash readers are not lock-free RCU readers.

The `wNN` suffix is the write percentage: `w01` means 1% writes and 99% reads;
`w20` means 20% writes and 80% reads. Every worker executes this mix, with a
deterministic initial phase and evenly spaced writes. It does not assign 20% of
workers to a dedicated writer role. The runner supports 0–100% writes and
defaults to the 1% and 20% mixes.

The rwlock loop uses four dependent arithmetic rounds after each read or write
unlock, defined in its own [post_work.h](../workload_modules/rwlock_bench/post_work.h).
This differs from the spin/mutex post64 loop; compare backends within the same
lock family, payload and read/write mix.

For example, `rwlock-cacheline-c08-w20` means eight shared counter cachelines,
with readers checking all eight and writers incrementing all eight, at a 20%
write mix.

## Real API labels and parameters

The client issues syscalls on objects prepared before timing. The compact
subject labels used below spell out `n` for `entries` and `v` for `value_size`;
the runner's session names additionally record threads, repetition and backend:

```text
Compact label:  <kind>-<query>-n<entries>-v<value_size>
Session name:   <kind>-<query>-n<entries>-t<threads>-r<repeat>-<backend>
Plot file:      <kind>-<query>-<entries>-<value_size>.svg (or .png)
```

| Label component | Meaning |
| --- | --- |
| `kind` | Object/API case: `ofd`, `setfd`, `pipebytes`, `pipecap`, `seek`, `utsname` or `xattr` |
| `query` | Operation variant or lookup position, explained for each case below |
| `n16` | `--entries 16`; **the unit depends on the API**, as shown in the next table |
| `v64` | Recorded `--value-size 64`: xattr values contain 64 bytes; UTS requires fixed 64-byte names; the other cases retain this field but do not use it to size their payload |
| `t16` | 16 worker threads, independently of the `n` parameter |
| `r0` | First repetition, numbered from zero |
| Backend suffix | Selected implementation, such as `native`, `tclock`, `kdlock` or `stock` |

**`n16` is not a universal object count and does not mean 16 workers.** The runner
reuses the field name `entries` for several different workload parameters:

| Case | Meaning of `nN` / `--entries N` | Example values | What changing it changes |
| --- | --- | --- | --- |
| `ofd` | Number of preinstalled byte-range locks on one file | `n16` / `n128`: 16 / 128 ranges | List length and search work, particularly for tail and miss queries |
| `setfd` | Requested descriptor-number stride between workers | `n16` / `n512`: minima spaced by 16 / 512 descriptor numbers | Spacing of modified bits in the shared close-on-exec bitmap; the protected operation still changes one bit |
| `pipebytes` | Number of occupied 4 KiB pipe buffers | `n16` / `n128`: 64 KiB / 512 KiB buffered | Number of buffer descriptors traversed and summed per query |
| `pipecap` | Requested pipe capacity in 4 KiB pages | `n16`: request 64 KiB capacity | Capacity returned; the protected query remains a field read |
| `seek` | File length in 4 KiB pages | `n16`: 64 KiB file | File length and the reference point for `SEEK_END`; no file-data traversal |
| `utsname` | Percentage of operations that update a name | `n20`: 20% setters, 80% `uname()` | Read/write mix and frequency of exclusive acquisitions |
| `xattr` | Number of attributes attached to one file | `n16` / `n128`: 16 / 128 attributes | Name-search list length; `vN` separately controls value bytes |

The page-based cases use the client's fixed 4,096-byte setup units on the target
x86-64 kernel. Pipe capacity may be rounded by the kernel; the client records
and checks the actual returned capacity.

Examples:

- `ofd-tail-n128-v64`: query the last of 128 installed lock ranges. `v64` does
  not specify a 64-byte range; each installed range is one byte.
- `pipebytes-query-n16-t08-r0-native`: eight workers query a pipe containing 16
  buffers, in the first Native repetition.
- `utsname-host-n20-v64`: 20% hostname updates and 80% `uname()` reads, with
  fixed 64-byte names. Worker count is a separate field.

The archived [spinlock API report](../bench/results/10.176.26.71/bench/real_api/20261011/RESULTS.md)
and [mutex/reader-writer API report](../bench/results/10.176.26.71/bench/real_api/20261011-sync/RESULTS.md)
contain these real API combinations:
`ofd/tail` at n16/n128, `setfd/toggle` at
n16/n512, `pipebytes/query` at n16/n128, `pipecap/query` at n16, `seek/set` and
`seek/end` at n16, and `utsname/host` and `utsname/domain` at n20. Each records
v64. The client supports additional query variants described below.

## Real-world API critical sections

These workloads exercise kernel metadata accessed through ordinary userspace
APIs: file-lock lists, descriptor flags, pipe state, file offsets and namespace
names. Their critical sections range from a single field read to a linked-list
search or a structure copy. The protected object is shared by the workers in
each case.

OFD queries, descriptor flags and xattrs use exclusive spinlocks. Pipe queries
and file positioning use exclusive mutexes. Consequently, even the read-only
OFD and pipe queries serialize on their target locks. UTS uses shared read
acquisitions for `uname()` and exclusive write acquisitions for name updates.
The descriptions below identify the actual reads, writes and traversal performed
between acquisition and release.

The kernel paths below describe selected helpers in the captured Linux 6.1.159
source. Matched Native/TCLock/KD runs substitute the indicated function only for
the bound benchmark object and reproduce its relevant body in an adapter.
Stock runs retain the original body. Pipe and seek mutex cases support Stock,
Native, TCLock and KD controls. Native retains the kernel-owned mutex;
TCLock and KD use private adapter objects while all benchmark accesses obey the
selected protocol. KD never casts the kernel mutex to its own type. The
[runner contract](../bench/real_api/README.md#contract-and-comparison-limits)
defines allowed consumers and source/instrumentation differences. These are
syscall microbenchmarks on controlled objects, not complete application workloads.

| Case | Userspace API during measurement | Selected original kernel path | Substituted function |
| --- | --- | --- | --- |
| `ofd` | `fcntl(fd, F_OFD_GETLK, &flock)` | `__x64_sys_fcntl` → `do_fcntl` → `fcntl_getlk` → `vfs_test_lock` → `posix_test_lock` | `posix_test_lock` |
| `setfd` | `fcntl(fd, F_SETFD, flags)`, followed by `fcntl(fd, F_GETFD)` | `__x64_sys_fcntl` → `do_fcntl` → `set_close_on_exec` or `get_close_on_exec` | `set_close_on_exec`; verification remains original |
| `pipebytes` | `ioctl(fd, FIONREAD, &bytes)` | `__x64_sys_ioctl` → VFS ioctl dispatch → `pipe_ioctl` | `pipe_ioctl` for `FIONREAD` |
| `pipecap` | `fcntl(fd, F_GETPIPE_SZ)` | `__x64_sys_fcntl` → `do_fcntl` → `pipe_fcntl` | `pipe_fcntl` for `F_GETPIPE_SZ` |
| `seek` | `lseek(fd, offset, SEEK_SET)` or `lseek(fd, offset, SEEK_END)` | `__x64_sys_lseek` → `ksys_lseek` → `vfs_llseek` → `shmem_file_llseek` → `generic_file_llseek_size` → `vfs_setpos` | `ksys_lseek` for the selected file and modes |
| `utsname`, read | `uname(&utsname)` | `__x64_sys_newuname` → `newuname` syscall body | `__x64_sys_newuname` |
| `utsname`, write | `syscall(SYS_sethostname, name, 64)` or `syscall(SYS_setdomainname, name, 64)` | `__x64_sys_sethostname` or `__x64_sys_setdomainname` → corresponding syscall body | The selected setter entry |
| `xattr` | `fgetxattr(fd, name, buffer, size)` | `__x64_sys_fgetxattr` → `getxattr` → `do_getxattr` → `vfs_getxattr` → `__vfs_getxattr` → `shmem_xattr_handler_get` → `simple_xattr_get` | `simple_xattr_get` |

`F_OFD_GETLK`, `F_SETFD`, `F_GETFD` and `F_GETPIPE_SZ` are `fcntl()` commands;
`FIONREAD` is an `ioctl()` request. They are not separate syscall entry points.
For matched runs, the substituted body replaces the original at that point;
the full original helper chain is not additionally executed.

### OFD lock query: `ofd`

This API checks whether a proposed byte-range lock conflicts with an existing
lock on a file. OFD means open file description: ownership belongs to the open
description, rather than to an individual descriptor number.

Setup creates an anonymous tmpfs file with `memfd_create()` and installs N
nonadjacent one-byte write locks using `fcntl(owner_fd, F_OFD_SETLK, &flock)`.
Their starting offsets are 0, 2, …, `2*(N-1)`. Workers query through a separate
open file description, so the installed locks belong to a different OFD owner.

**Critical section.** For the populated file, `posix_test_lock()` holds the
exclusive spinlock `file_lock_context.flc_lock` while it:

1. Follows entries in the `flc_posix` linked list.
2. Compares each entry's owner, start/end offsets and read/write lock type with
   the proposed lock, skipping the same owner and nonconflicting ranges.
3. Copies the first conflict's owner, range, type and related fields into the
   caller's request, or sets its type to `F_UNLCK` if no conflict exists.

The shared list is only read; writes go to the query's result structure.
`F_OFD_GETLK` does not acquire or install the proposed lock. The spinlock protects
a consistent view of lock records that general file-lock operations can modify;
this benchmark keeps the installed records unchanged during queries. Tail and
miss cases exercise pointer traversal and repeated comparisons under the lock.

- `front`: query offset 0, matching the first installed range.
- `tail`: query offset `2*(N-1)`, matching the last range.
- `miss`: query offset `2*N+1`, which has no matching range.

Thus n16/tail queries offset 30, whereas n128/tail queries offset 254 and searches
a longer list. Every operation still makes one query. Allocation/conversion of
the temporary `file_lock` in `fcntl_getlk()` and userspace result copying occur
outside the target spinlock but remain part of the measured syscall.

### Descriptor flag update: `setfd`

This API changes whether a descriptor is automatically closed when its process
successfully executes a new program. The flag is stored per descriptor in the
file table's `close_on_exec` bitmap.

All workers share one `files_struct`, but each has its own descriptor and open
file description. Setup uses `fcntl(fd, F_DUPFD_CLOEXEC, 64 + worker_index*N)`.
This requests the lowest available descriptor at or above each minimum; the
actual allocation determines the final layout.

**Critical section.** `toggle` alternates `FD_CLOEXEC` between set and clear.
`set_close_on_exec()` holds the exclusive spinlock `files->file_lock` while it:

1. Gets the current descriptor table with `files_fdtable(files)`.
2. Sets the descriptor's bit with `__set_bit()` on the set path, or tests it with
   `test_bit()` and clears it with `__clear_bit()` when needed on the clear path.

This is a short update to one shared bitmap word, without list traversal or
allocation. After that section, the client issues a separate `F_GETFD` to verify
the bit through `get_close_on_exec()`. Thus **one counted operation contains two
syscalls**. It does not open or close a descriptor.

N changes bitmap placement, not the number of flags updated per operation.
With exact requested spacing, n16 separates bits by 16 positions (2 bytes),
whereas n512 separates them by 512 positions (64 bytes). This varies how many
workers write the same bitmap cacheline. All workers still contend on the same
file-table lock; independent bit locations do not create independent locks.

### Pipe byte count: `pipebytes`

This API reports how many bytes are currently readable from a pipe. The kernel
stores buffered data in a ring of `pipe_buffer` descriptors, each recording a
buffer's length and backing page.

Setup uses `mkfifo()`/`open()` to create a private FIFO, requests capacity with
`F_SETPIPE_SZ`, then writes N whole 4 KiB pages before timing. Workers use separate
open file descriptions referring to the same pipe. No pipe data is consumed or
added during the queries.

**Critical section.** For `ioctl(FIONREAD)`, `pipe_ioctl()` uses the exclusive
`pipe_inode_info.mutex` to protect this sequence:

1. Read `head`, `tail` and `ring_size`, deriving the ring-index mask.
2. Walk from the captured tail to head and load each occupied `bufs[index].len`.
3. Add those lengths into a local byte-count accumulator.

The mutex keeps the ring indices and buffer metadata consistent. This body reads
shared metadata and changes only local variables; it neither advances the pipe's
tail nor reads the contents of the backing pages. `put_user()` writes the total
to the user pointer after unlocking. n16 traverses 16 buffers and reports 65,536
bytes; n128 traverses 128 and reports 524,288 bytes. N therefore directly changes
the number of protected loads and loop iterations.

### Pipe capacity: `pipecap`

This API reports the pipe's capacity in bytes. This case uses the same pipe
setup, including prefilled pages; N specifies the requested capacity in pages.

**Critical section.** For `fcntl(F_GETPIPE_SZ)`, `pipe_fcntl()` takes the exclusive
`pipe_inode_info.mutex`, reads `pipe->max_usage`, multiplies it by `PAGE_SIZE`,
and releases the mutex. The protected payload reads one capacity field and
writes no shared data. The resulting byte count is returned as the `fcntl()`
return value. This isolates a very small mutex-protected metadata read.

Unlike `pipebytes`, increasing N does not add a buffer traversal to this critical
section. It changes the capacity value; the query remains a short protected read.
The client checks it against the actual capacity returned during setup.

### Shared file position: `seek`

This API changes the current offset associated with an open file description.
Threads sharing that description share its `f_pos`, so their position changes
must be serialized.

Setup creates a tmpfs file and calls `ftruncate(fd, N*4096)`. All workers share
one open file description and its `file.f_pos_lock`. Each operation chooses a
varying displacement `d` between 1 and 1,024 bytes:

- `set`: `lseek(fd, d, SEEK_SET)` returns `d`.
- `end`: `lseek(fd, -d, SEEK_END)` returns `N*4096 - d`.

**Matched critical section.** Native takes the original `file.f_pos_lock`;
TCLock and KD take their private adapter mutexes. Each protects the same steps:

1. Read the filesystem's maximum file size (`s_maxbytes`). For `SEEK_END`, also
   read the inode size with `i_size_read()` and add the requested displacement.
2. Reject a resulting offset below zero or above the maximum.
3. Compare the result with `file->f_pos`; if different, store the new position
   and set `file->f_version` to zero.

The body performs a few metadata reads, checks and conditional shared stores.
N changes the file length and end-relative base. Neither variant traverses,
reads or writes file contents.

In the original kernel path, `ksys_lseek()` uses `fdget_pos()`/`fdput_pos()` around
the llseek call, taking the position mutex for the shared description.
`shmem_file_llseek()` supplies `MAX_LFS_FILESIZE` and reads the inode size for
both supported modes; this tmpfs superblock sets `s_maxbytes` to that same limit.
The adapter uses `fdget()`/`fdput()` and performs the checks and stores above
under the selected lock, reading inode size only for `SEEK_END`.

### UTS names: `utsname`

These APIs read system-identification fields or change the hostname/UTS domain
name. A reader must see a complete name while another worker updates it.

Setup creates a private namespace with `unshare(CLONE_NEWUTS)` and initializes its
hostname and domain name. `host` selects hostname updates; `domain` selects UTS
domain-name updates. Both variants use `uname()` for their read operations.

Here N is the **write percentage**. Every worker interleaves setters and reads:
n20 means approximately one setter per five operations, while n100 means all
setters. The client accepts N from 1 to 100. This does not change the number of
namespaces or the string length; `value_size` must remain 64.

**Reader critical section.** `uname()` takes shared read access and copies the
entire `target_uts->name` (`struct new_utsname`) into a caller-local kernel
temporary with `memcpy()`. It then releases read access. `copy_to_user()` and
the client's result validation follow outside the lock. The protected body
reads the namespace fields and writes only the temporary copy.

**Writer critical section.** The selected setter takes exclusive write access,
copies exactly 64 bytes into `nodename` (`host`) or `domainname` (`domain`),
stores a terminating NUL, then releases write access. The other namespace fields
remain unchanged. The source name is already in a kernel temporary: privilege
checks, `copy_from_user()` and entropy mixing precede the protected update.

Stock uses the global `uts_sem`; matched Native uses a private rwsem, and matched
KD/TCLock use private reader/writer locks. Stock performs `uts_proc_notify()`
under the write lock; matched adapters perform it after unlocking. These scope
and notification differences are part of the comparison. N changes how often
the fixed-size exclusive copy interrupts shared readers.

### Extended attributes: `xattr`

This API retrieves a named metadata value attached to a file. For these tmpfs
objects, attribute records are stored in a linked list.

Setup attaches N `trusted.kdlock.*` attributes to an anonymous tmpfs file using
`fsetxattr(..., XATTR_CREATE)`. Each value contains `value_size` bytes.

**Critical section.** `simple_xattr_get()` takes the exclusive spinlock
`simple_xattrs.lock` while it:

1. Traverses the attribute list, comparing each name with `strcmp()`.
2. Reads the matched attribute's size. With no output buffer, this size is the
   result; an undersized buffer produces `-ERANGE`.
3. Copies the value into the supplied kernel buffer with `memcpy()` when the
   buffer is large enough. A missing name produces `-ENODATA`.

The list and stored values remain unchanged; writes go to the query's result
buffer. Holding the spinlock across search and copy keeps the selected record
stable. Buffer allocation and the later copy to userspace are outside this
lock. The body combines pointer traversal, string comparisons and, for a
successful value query, a size-dependent copy.

- `front`: read the most recently inserted attribute, at the list head.
- `tail`: read the earliest inserted attribute, at the list tail.
- `miss`: query a name that was not installed; expect `ENODATA`.
- `size`: search for the tail attribute but pass `NULL, 0` to `fgetxattr()`,
  obtaining its length without copying the value.

N varies search-list length; `vN` varies value size and hence copy work for
successful value queries. These are independent dimensions. Xattr remains an
exploratory case: the runner guide records that translated bodies are refused by
admission and excluded from accepted KD performance comparisons.


## Sleeping rwsem and extracted proc snapshots

The [reader/writer runner](../bench/rwlock_compare/README.md) now also exposes
these explicit modes. They are separate lock/payload identities and are not
automatically added to an ordinary rwlock or full-catalog sweep.

| Mode | Payloads / backends | Execution contract |
| --- | --- | --- |
| `--lock-kind rwsem` | c01/c08 or RCUHT; `--backends native kdlock` | Sleeping local readers and explicit ABI2 outer writers. KD reserves a reader-free phase before entering the unchanged mutex delegation queue. `--delegate off` selects a distinct ordinary-local KD control with zero JIT. No TCLock sleeping-rwsem port. |
| `--lock-kind spin --workloads argbounds` | Four-word argument-boundary snapshot; Native/TCLock/KD | Every snapshot takes an exclusive spinlock; KD may delegate reads. Controlled optional mutations use the same selected lock. |
| `--lock-kind spin --workloads taskname` | Exact `strscpy_pad()` copy from a 16-byte name to a 64-byte padded buffer; Native/TCLock/KD | Preserve helper semantics and admission. Historical exact-helper refusal remains a known limit; explicit `--delegate off` gives a KD local control. |

Snapshots use module-owned records, fixed lifetimes and worker-local kernel
outputs. They do not operate on live task/MM structures, invoke procfs, fetch
remote argument pages or time `ps`. `--write-percent 0` is read-only snapshot
traffic; a 20% mutation case alternates valid versions and checks the complete
tuple or padded name. Read operations remain exclusive spin acquisitions.

Snapshot preparation saves every published image and uses fully drained helper
learning waves. Readiness requires a complete returned body rather than just a
NORMAL image or entry witness. The benchmark-only provider counts entries and
matching completed bodies separately. Refusals and local controls remain
separate from actual delegated results.

The [rwsem design](design/rwsem_implementation.md) supports ordinary sleeping
read/write, trylocks, downgrade and interruptible/killable cancellation. Its
explicit outer writer pair can delegate admitted bodies through the existing
mutex ABI2. Each reservation closes reader admission and drains existing readers
while schedulable, before any pinned queue publication. Ordinary writers hold an
exclusive phase, so their downgrade cannot create a reader after another writer
has passed drain. Outer reservations remain live until origin unlock/ACK returns;
that pair cannot downgrade or cancel after publication. Separate admission/drain
waitqueues and bounded polling before publication are described in the design;
they preserve the selected KD mutex protocol. The
[scheduler probe](../tests/kernel/rwsem/README.md) exercises sleeping holders and
contenders sharing one CPU and checks pre-publication ordering across downgrade.
This object is not a replacement for the real `mmap_lock`. The
[branch review](history/feature-reintegration-20261018.md) explains why the
archived delegated rwsem could not be copied unchanged; the phase design
resolves those ordering hazards while preserving the selected mutex protocol.

The standard rwsem comparison uses c01, c08 and RCUHT, 1%/20% writes, three
two-second repetitions, and workers 1–8 by one then 12–60 by four. With Native
and KD this is 756 sessions. Use the [runner command](../bench/rwlock_compare/README.md)
and retain complete-body counts, NO_JIT controls, correctness, worker progress
and final drain. Admission and Linux rwsem fairness policies differ; the design
does not imply a throughput advantage.

The [rwsem optimization report](../bench/results/10.176.26.71/bench/rwsem-optimization-20261018/README.md)
records the current comparison, candidate screens, separate baseline controls,
diagnostic profiles and actual execution groups. Its separate spinning-rwlock
reference selects Native/TCLock/KD on c01, c08 and RCUHT at 1%/20% writes and
1/8/32/36/60 workers, with three repetitions: 270 completed sessions. This reference
uses non-sleeping bodies and is not a TCLock rwsem implementation or a rwsem
parity result. The [focused validation](../bench/results/10.176.26.71/tests/rwsem-optimization-20261018/README.md)
records strict JIT checks, cancellation/downgrade ordering, ordinary local
controls and read-only cases. Neither report validates real MM or task-structure
integration.

The [initial writer-delegation comparison](../bench/results/10.176.26.71/bench/rwsem/20261018/README.md)
and its [validation receipt](../bench/results/10.176.26.71/tests/rwsem-delegation-20261018/README.md)
remain historical evidence for the shared-queue baseline, including its
high-count regressions, local fallback results and returned-body counts.

The [earlier 2026-10-18 validation](../bench/results/10.176.26.71/tests/feature-reintegration-20261018/README.md)
passed the prior ordinary-only rwsem scheduling and workload checks. Three default-policy timed
argbounds runs at eight workers returned complete delegated bodies; a shorter
16-worker acceptance attempt remained `NO_JIT`. Taskname's 16-worker preparation
exhausted its helper waves without a completed body; local controls passed.
These outcomes do not establish performance parity or full task/MM integration.

## Process inspection and mmap candidates

**Review, 2026-10-18:** process inspection reaches real task and memory locks,
but container count alone does not establish contention on any one lock. The
short `arg_lock` and task-name snapshots are restored extracted spin workloads.
Full procfs and mmap operations need Native scaling measurements first; the
selected KD provider cannot delegate these complete paths today. Explicit rwsem
writer delegation does not change that full-path boundary.

This review checked the current provider and the retained Linux 6.1.159 source
and procps-ng 3.3.17 traces. All 25 captured kernel/configuration files and the
three traces match their recorded hashes. The [source audit and offline recheck](../bench/results/10.176.26.71/tests/proc-mmap-audit-20261015/README.md)
record provenance and limits. No new live tracing or container experiment ran
for that source review; the separate feature validation above tests extracted
payloads and the explicit KD rwsem object. These are kernel-version-specific
findings; a different production kernel or `ps` version needs its own trace.

### Containers, processes and shared locks

There is no single lock protecting every field of every `task_struct`.
`task_lock(task)` acquires that task's `alloc_lock` for selected fields. Threads
normally share `mm_struct`, `signal_struct` and `sighand_struct`, while each has
its own task structure and `alloc_lock`. Independent processes normally have
separate address spaces and mmap locks, including processes in the same container.
Sharing a mapped file does not by itself make their `mm->mmap_lock` the same lock.

A host PID-namespace scan can see descendant-container processes, subject to
procfs visibility and access policy. A container's procfs normally exposes its
own PID namespace and descendants. Docker's
[PID namespace setting](https://docs.docker.com/reference/cli/docker/container/run/#pid)
can change that visibility, including use of the host namespace. Keep container
count, processes per container, threads per process and concurrent observers as
separate parameters. Here `ps` means the Linux process tool; `docker ps` is a
different container-listing operation.

More processes increase directory enumeration and procfs work. More threads in
one process increase whole-process accounting traversal; simultaneous observers
of the same process can share its signal/accounting locks. Mapping writers in
that process can delay mmap readers. Those are possible bottlenecks to measure,
not evidence that a slow host-wide scan is dominated by one lock.

The retained syscall traces establish the following paths for the audited `ps`:

| Command | Observed process files |
| --- | --- |
| `ps -e -o pid=,comm=` | `stat`, `status` |
| `ps -e -o pid=,args=` | `stat`, `status`, `cmdline` |
| `ps -eL -o pid=,tid=,comm=` | Process `stat`/`status`, `task` directory enumeration, per-thread `stat`/`status` |

None opened `maps` or `smaps`. Basic memory-counter helpers used by `stat`,
`statm` and `status` do not take mmap read ownership in this kernel.
`get_task_mm()` pins an MM reference under `task_lock()`; that is not an mmap
lock acquisition. Argument-displaying `ps` reaches the mmap lock through remote
`cmdline` page access. The kernel's [procfs guide](https://docs.kernel.org/6.1/filesystems/proc.html)
describes the interfaces and the more expensive page-table inspection in `smaps`.

### Task and process-inspection critical sections

Locations below refer to the hashed `kernel-inputs/` files in the source audit.
They identify relevant task/MM protection, not every VFS or security lock in a
complete syscall.

| Operation and source | Lock and protected work | Current KD delegation boundary |
| --- | --- | --- |
| `/proc` enumeration: `fs/proc/base.c:3536`, `next_tgid()` | RCU, PID lookup and task references; thread enumeration also uses RCU | No global `tasklist_lock` held across the scan; not a single lock-body benchmark |
| Name copy: `fs/exec.c:1219`, `__get_task_comm()` | Per-task `alloc_lock`; `strscpy_pad()` copies `comm` | Small ordinary-spin payload; exact helper has a historical admission refusal described below |
| Task pointers/status: `kernel/fork.c:1388`, `get_task_mm()`; `fs/proc/array.c:170` | Per-task `alloc_lock`; MM reference or `fs`/`files` snapshot | Task references, surrounding RCU and mutable pointer lifetimes require a separate audit; not covered by a name-copy test |
| Signal snapshot: `fs/proc/array.c:275,505`; `kernel/signal.c:1389` | Shared `sighand->siglock` with IRQ saving and pointer revalidation; signal state, thread count and related fields | Explicit IRQ spin paths stay on the caller; no current delegated adapter |
| Whole-process statistics: `fs/proc/array.c:533`; `kernel/sched/cputime.c:308` | `signal->stats_lock` seqlock with normally lockless initial reads and RCU thread traversal; retry can take an IRQ-saving exclusive lock | Preserve seqlock/RCU semantics; cannot model the normal path as one exclusive delegated thread scan |
| CPU-time adjustment: `kernel/sched/cputime.c:554,644` | Raw IRQ-saving `signal->prev_cputime.lock`, or per-task equivalent; keeps reported CPU times monotonic | Caller-context accounting, separate from the long traversal; no current delegation |
| Command-line boundaries: `fs/proc/base.c:301` | Ordinary exclusive `mm->arg_lock`; load `arg_start`, `arg_end`, `env_start`, `env_end` | Best extracted KD spin candidate; argument bytes and mmap operations are outside this section |
| Command-line bytes: `fs/proc/base.c:336,358` → `mm/memory.c:5700` | Target mmap read lock with killable acquisition; VMA/page lookup, possible faults and remote copy | Sleeping rwsem and MM-context work; unsupported as a complete KD body |

The long statistics traversal in this 6.1.159 source already uses `stats_lock`,
rather than holding `sighand->siglock` throughout as older code did. Its initial
sequence read is lockless; exit and child-reaping writers can invalidate it and
force retries. Read-only observers do not themselves change the sequence. A
benchmark must retain this distinction when assessing many-thread processes.
The captured x86-64 tick-accounting configuration also uses the plain runtime
load in `read_sum_exec_runtime()`, not its 32-bit runqueue-lock fallback.

Global `tasklist_lock` still matters for fork, exit, reparenting and wait/reaping
paths, including IRQ-disabled write acquisitions (`kernel/fork.c:2476`,
`kernel/exit.c:252`). A creation/exit storm deserves its own workload; ordinary
procfs enumeration is not evidence of that global lock being the bottleneck.

### mmap critical-section boundaries

`include/linux/mm_types.h:597` declares `mmap_lock` as `struct rw_semaphore`.
It protects VMA layout and related MM operations. Page tables and reverse
mappings have additional locks; mmap ownership does not protect every task field.

| Entry / source | Acquisition and protected work |
| --- | --- |
| `mmap()` → `vm_mmap_pgoff()`, `mm/util.c:507` | Write-killable lock around `do_mmap()`: validate/select addresses, create/merge VMAs, update Maple Tree and accounting; allocation and filesystem/security callbacks can occur. Optional population follows unlock. |
| `munmap()` → `__vm_munmap()`, `mm/mmap.c:2926` | Write-killable lock for VMA removal; `do_mas_align_munmap()` can downgrade before unmapping pages, freeing page tables and completing TLB work. Release mode depends on the path. |
| `mprotect()`, `mm/mprotect.c:702`; `mremap()`, `mm/mremap.c:943`; `brk()`, `mm/mmap.c:181` | Write-killable acquisition around validation and VMA changes, with path-dependent splitting/merging, allocation, page-table and TLB work |
| `/proc/PID/maps`, `fs/proc/task_mmu.c:141,186` | `m_start()` takes a killable read lock and `m_stop()` releases it; VMA traversal and record formatting span a seq-file batch, not necessarily the whole file |
| `/proc/PID/smaps`, `fs/proc/task_mmu.c:613`; `smaps_rollup`, `:877` | Mmap read ownership plus nested page-table locks; collect resident/PSS statistics and allow rescheduling. Rollup explicitly drops/reacquires mmap ownership when contended. |
| `cmdline` → `__access_remote_vm()`, `mm/memory.c:5700` | Read-killable acquisition; VMA lookup, possible stack expansion, page acquisition and remote copy. The later `copy_to_user()` to the observer is outside this helper's mmap lock. |
| User faults, `arch/x86/mm/fault.c:1312` | Mmap read ownership for VMA/fault work, with retry and stack-growth paths requiring explicit lock-state handling |

Opening `maps`/`smaps` also uses `mm_access()` (`kernel/fork.c:1405`), which
takes the separate `signal->exec_update_lock` rwsem around MM acquisition and
access checks. This is distinct from the mmap read batches and from the plain
`cmdline` path's `get_task_mm()`.

### What would be required for delegation

Replacing every Linux **mutex** with KD mutex does not replace `alloc_lock`,
`siglock`, raw spinlocks, seqlocks or the **rwsem** `mmap_lock`. The current
[mutex aliases](../include/kd_mutex_compat.h) operate on rebuilt KD mutex objects;
ordinary C aliases execute locally, while explicit clobber callers permit JIT.
The following requirements still apply under the KD-only mutex assumption:

- **Matching lock semantics.** Current [KD rwlock](../include/kd_rwlock.h)
  disables preemption, requires non-sleeping bodies and delegates only writers;
  readers execute locally. It is not a sleeping rwsem. Mmap uses concurrent
  readers, killable waits, trylocks, downgrade and release/reacquire paths.
  KD mutex is exclusive and does not provide that contract. KD rwsem supplies
  the ordinary sleeping APIs and a distinct delegated outer writer pair. Its
  phase admission drains readers before acquire-time combining can run, and
  excludes ordinary downgrade until all outer reservations retire. The outer
  pair itself cannot downgrade or cancel after publication. These APIs do not
  establish real mmap-lock replacement or arbitrary MM-body delegation.
- **All consumers and lifetime.** A private KD lock around proc readers cannot
  exclude native mapping writers, faults, exec or exit. All accesses must use
  one protocol, including implicit kernel users. Task/MM references keep
  allocations alive but do not freeze fields or thread membership. Permission
  checks, exit/exec handling and nested lock ordering remain required.
- **Execution context.** A KD mutex executor can sleep, so sleep alone is not
  a universal prohibition. However, full MM bodies include faults, allocation,
  callbacks, nested locks, MMU notifications and TLB operations. Logical
  `current` handling does not switch the hardware address space or reproduce
  arbitrary credentials, CPU, IRQ, RCU or scheduler context. The
  [context admission rules](../disassem/context_symbols.py) refuse many of these
  operations; an admitted bounded copy is not evidence for a complete MM path.
- **IRQ and accounting semantics.** [Explicit IRQ/BH spin interfaces](../include/kd_spin_direct.h)
  execute locally. Moving `siglock`, the stats fallback or raw accounting
  sections would need a new audited context contract. Current KD rwlock also
  lacks the IRQ variants needed for `tasklist_lock` writers.

### Candidate workload plan

The extracted snapshots below map to restored runner modes; the full procfs,
mmap and lifecycle labels remain proposals, not accepted runner options. None
is automatically added to the default full-catalog sweep. Native screening
identifies the expensive shared object before a real-object adapter is designed.

| Proposed case | Measured operation and controls | Feasibility |
| --- | --- | --- |
| `proc-arg-bounds` | Copy four words under one module-owned exclusive spinlock into stable worker-local kernel storage; optionally alternate valid tuples under the same lock. Distinct-record control remains an extension. | Implemented as `--lock-kind spin --workloads argbounds`; require fresh returned-body evidence for current delegation claims. |
| `proc-comm-snapshot` | Exact `strscpy_pad()` name copy, 16-byte source and 64-byte padded destination, with separately labelled mutations; distinct-record control remains an extension | Implemented as `--lock-kind spin --workloads taskname`, including KD local control. Exact KD delegation remains subject to helper/ABI admission. A different copy loop is a different payload. |
| `proc-stat` / `proc-status` | Independent observers read the same large thread group versus distinct groups; idle, CPU-active and exit/reaping variants kept separate | Native-only candidates requiring implementation; preserve actual seqlock/RCU/IRQ paths. No full-path KD adapter. |
| `proc-cmdline-mmap` | Read stable arguments while target threads map/unmap disjoint scratch regions in that same MM. Include a no-writer control; vary argument length and VMA count. | Native mmap-contention workload; current KD/TCLock sleeping-rwsem comparison unavailable |
| `proc-maps` / `proc-smaps` | Complete proc-file reads while a target changes separate mappings; vary actual VMA count and resident bytes independently | Native workloads; distinguish VMA formatting from page-table accounting and preserve allowed concurrent-update semantics |
| `mmap-churn` | Target threads perform matched map/unmap cycles or separately labelled protection changes; compare shared MM with independent processes and with/without observers | Native writer control; record map/unmap latency separately as well as cycle throughput. Full MM delegation unsupported. |
| `task-lifecycle` | Controlled process/thread creation, exit and reaping with/without proc observers | Native control for global task-list and statistics writers; no current KD IRQ-rwlock adapter |

The [historical proc snapshot report](../bench/results/10.176.26.71/bench/proc_snapshots/20261015/README.md)
records 93,229,983 complete delegated argument-boundary bodies across its timed
comparison. That is proof of feasibility for that frozen extracted spin workload,
not a current-version performance result or an end-to-end `ps` improvement.
The exact task-name helper was refused because `strscpy_pad+0x8` saved uncaptured
R13 under spin ABI1. Its KD timings used explicit local execution. Image
publication and an entry witness did not establish a complete delegated body.

For a future round, use the standard 1–8 and 12–60-by-four observer/worker grid
and three repetitions, keeping target population independent of worker count:

1. Compare one shared process/MM with the same total target tasks spread across
   independent processes. Vary containers/PID namespaces separately, recording
   procfs policy, kernel/procps versions, CPU placement and runnable population.
   Large sleeping target populations need not imply oversubscribed KD workers;
   arbitrary KD producer oversubscription remains unvalidated.
2. Vary observer and mapping-writer counts independently. Keep idle, CPU-active,
   mapping and lifecycle churn as separate cases. Record actual VMA count to
   catch automatic merging, mapped/resident bytes, and argument bytes.
3. Give each proc observer an independent open file description. Define one
   operation as a complete read from offset zero; state whether open/close or
   rewind is timed. Shared descriptions can add seq-file/file-position
   serialization. An end-to-end `ps` run additionally times userspace parsing,
   selection and formatting; report it separately from proc-file reads.
4. Record whole-scan latency, reads/second, p50/p95/p99 latency, CPU time,
   errors and target progress. Use separate profiling runs to attribute wait
   and hold intervals to a specific lock address/MM and call stack. High CPU
   traversal cost alone is not evidence of lock contention.
5. For extracted comparisons, require identical bodies, one protocol for all
   accesses, exact tuple/name validation, actual returned JIT-body counts,
   per-worker progress and complete drain. Keep refused/local controls separate
   from delegated results. Procfs lifecycle tests must handle expected exit
   races; maps/smaps across multiple reads are not one atomic snapshot.

The captured kernel has mmap start/acquired/released tracepoints but
`CONFIG_LOCK_STAT` is disabled. Pair events by task and MM, track failed
killable/trylock attempts and explicit drop/reacquire paths. Downgrade emits a
successful read-acquired event without a new start or write-release event, so
it needs an explicit write-to-read transition. Release events precede physical
unlock; account for that measurement boundary, non-owner releases and lost
events. Keep probe overhead out of the throughput comparison.

## Scope and evidence

The API adapter substitutes only selected functions on controlled objects. KD
mutex uses a private KD object and never casts or falls back to the embedded
Linux mutex. This tests scoped behavior, not a rebuilt kernel where every mutex
has been replaced. See the [API contract](../bench/real_api/README.md#contract-and-comparison-limits)
and [KD-only assumptions](design/kd_only_mutex.md).

The full process/mmap proposals are grounded in retained source and trace
evidence. The extracted snapshots and phase-admitted rwsem have their
own runner contracts. Historical snapshot delegation does not validate current
performance, live task/MM replacement or a large-container deployment. Full
procfs/mmap candidates still need implementation and fresh VM validation.
