# Benchmark workloads and critical sections

This document describes the shared objects, protected operations and workload
parameters in the synthetic and real-world API benchmarks. Use the
[benchmark guide](../bench/README.md) for runner selection and measurement rules,
and [performance status](PERFORMANCE.md) for measured outcomes.

Each synthetic worker executes repeated kernel bodies within one ioctl per
phase. Real API workers issue syscalls individually. The bodies below describe
the protected payload; throughput also includes the surrounding timed work
defined by each runner.

The [all-lock/API comparison](../bench/results/10.176.26.71/bench/comparison/workloads-20261015T180603Z/README.md)
and [expanded mutex comparison](../bench/results/10.176.26.71/bench/comparison/mutex-expanded-20261016T040928Z/README.md)
record three repetitions at 1–8 workers by one and 12–60 by four. The latter
adds fresh Native/TCLock/KD measurements for all six synthetic mutex payloads
and five pipe/file API variants. Earlier KD mutex omissions remain part of the
first report's captured scope. Xattr and the proposed process/mmap workloads
below remain outside accepted KD coverage.

## Synthetic cacheline updates

Each counter is a 64-bit value padded to a 64-byte slot. All workers access the
same selected counters under one lock. The bodies contain explicit updates:

| Label | Updates per operation | Selected payload footprint |
| --- | --- | ---: |
| `c01` | Increment counter 0 | 64 bytes |
| `c02` | Increment counters 0–1 | 128 bytes |
| `c04` | Increment counters 0–3 | 256 bytes |
| `c08` | Increment counters 0–7 | 512 bytes |
| `c16` | Increment counters 0–15 | 1,024 bytes |

These sizes apply to spin, mutex and rwlock cacheline cases. The
experimental [owned-v1 mutex runner](../bench/tclock_compare/README.md#workloads-and-backends)
supports all five sizes and RCUHT through its explicit KD-owned object.

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

The current owned synthetic comparison places a 128-byte KD mutex in its
64-byte-aligned lock slot, separate from the counter. Native retains its 32-byte
mutex. Historical comparisons through the expanded 2026-10-16 round used a
32-byte KD object; the adaptive experiment changes this geometry. The c01
name still means one payload cacheline, not one total cacheline. Spin/mutex loops currently include 64 dependent arithmetic rounds
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
| Cacheline `c01`–`c16` | Load the first counter and compare every selected counter against it; c01 also reloads its sole counter | Increment all selected counters |
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

## Process inspection and mmap candidates

**Investigation status, 2026-10-15:** these are proposed workloads, not new
`bench/real_api/run.py` kinds or measured KD results. The audit inspected
`/root/linux-6.1.159-kdclobber2` on the benchmark guest and traced three ordinary
`ps` invocations. The running kernel and source-tree `vmlinux` both had Build ID
`5ca28058e156f34a2c7fe91e8e0fbf92f4e51960`, matching the recorded
`mutex-clobber2-20260919` baseline; the configuration hash also matched.
[Audit metadata](proc_mmap_source_audit.json) records source hashes, commands,
procfs access counts and the local raw archive. These checks establish source
and syscall-path evidence, not contention, throughput or JIT admission.

### What many containers and threads change

Linux has no single lock protecting every field of every `task_struct`.
`task_lock(task)` takes that task's `alloc_lock`; signal state and accumulated
statistics have separate locks, and the task's address space has
`mm->mmap_lock`, a **sleeping reader/writer semaphore**. Ordinary threads of one
process share an `mm_struct`, `signal_struct` and `sighand_struct`, but have
distinct task structures and `alloc_lock`s. Independent processes normally have
different address spaces, even when they are in the same container. Container
count is therefore not the number of contenders on one mmap lock.

A host PID-namespace scan can inspect processes in descendant containers.
A scan through a container's own procfs mount normally sees that PID namespace
and its descendants; sharing the host PID namespace changes this scope. Keep
container count, processes per container, threads per process and concurrent
observers as separate parameters. More processes increase enumeration and procfs
work; more threads increase whole-process accounting traversal. Repeated scans
of the same process can contend on its shared signal/accounting locks. Mapping
writers in that process can also delay observers taking its mmap read lock.

The guest has procps-ng 3.3.17. The following diagnostic commands were traced
with `openat`, `getdents64` and raw-address `read` logging, with command output
discarded:

| Command | Observed process files |
| --- | --- |
| `ps -e -o pid=,comm=` | `/proc/PID/stat` and `/proc/PID/status` |
| `ps -e -o pid=,args=` | `stat`, `status` and `/proc/PID/cmdline` |
| `ps -eL -o pid=,tid=,comm=` | Process `stat`/`status`, `/proc/PID/task` enumeration and per-thread `stat`/`status` |

None of these commands opened `maps` or `smaps`. Command selection and procps
version matter: a process-name-only query and a full command-line query do not
exercise identical kernel paths. The kernel's [procfs documentation](https://docs.kernel.org/6.1/filesystems/proc.html)
describes these interfaces and distinguishes inexpensive memory counters from
the page-table inspection used for `smaps`.
In this guest, the basic memory-counter helpers used by `stat`, `statm` and
`status` do not take `mmap_lock`; acquiring a reference with `get_task_mm()` is
also distinct from taking that lock. The `cmdline` page-access path is the
relevant mmap-lock connection for the traced argument-displaying command.

### Locks reached by process inspection

The paths and line numbers below refer to the hashed guest sources in the audit
archive. They describe the relevant task/MM locks, not every VFS, security-module
or scheduler lock that a complete syscall could reach.

| Operation and source | Lock and scope | Protected work / scaling |
| --- | --- | --- |
| Enumerate `/proc`: `fs/proc/base.c:3536`, `next_tgid()` | RCU and task references, using the procfs PID namespace | Find the next TGID and pin its task. It does not hold global `tasklist_lock` across the scan. `first_tid()` / `next_tid()` also use RCU for thread enumeration. |
| Read names, task pointers and selected status fields: `fs/exec.c:1219`, `kernel/fork.c:1388`, `fs/proc/array.c:147` | `task->alloc_lock`, through ordinary `task_lock()` | Copy `comm`; obtain and reference `task->mm`; snapshot `fs`/`files` fields. These are per-task acquisitions. Access checks in `kernel/ptrace.c:359` also take this lock, but run a more complex credential/LSM body. |
| Read signal fields in `stat`/`status`: `fs/proc/array.c:505` / `:275`, `kernel/signal.c:1389` | `sighand->siglock`, acquired with `spin_lock_irqsave()` after RCU lookup and pointer revalidation | Snapshot signal dispositions, thread count, limits and process identifiers; the stat path may also query a TTY. Threads normally share this lock. |
| Aggregate whole-process statistics: `fs/proc/array.c:532`, `kernel/sched/cputime.c:308` | `signal->stats_lock`, a seqlock, plus RCU traversal | First attempt reads without taking the seqlock's spinlock; a retry can take its exclusive IRQ-saving lock. Fault/guest-time and CPU-time aggregation visit live threads, so traversal grows with thread count even without lock contention. |
| Adjust CPU accounting: `kernel/sched/cputime.c:554` / `:644` | `signal->prev_cputime.lock` for process totals, or `task->prev_cputime.lock` for a thread; raw spinlock with IRQ saving | Keep returned user/system times monotonic. This path is present with the guest's tick accounting configuration; it is separate from the long thread traversal. |
| Snapshot command-line boundaries: `fs/proc/base.c:291`, `get_mm_cmdline()` | `mm->arg_lock`, ordinary exclusive spinlock, shared by an address space | Copy four words: `arg_start`, `arg_end`, `env_start`, `env_end`. The lock does not cover fetching the argument bytes. |
| Fetch command-line bytes: `fs/proc/base.c:336` / `:358` → `mm/memory.c:5700` | Target `mm->mmap_lock`, acquired for reading with a killable wait | `access_remote_vm()` looks up a VMA and obtains/copies remote pages. Missing pages can fault; stack expansion can change the lock mode. Kernel-buffer-to-observer `copy_to_user()` follows this helper, outside its mmap lock. |

There is an important kernel-version distinction. Older `do_task_stat()` code
summed thread statistics while holding `sighand->siglock` with interrupts
disabled. Upstream commit `7601df8031fd` moved that traversal to `stats_lock`
with a normally lockless first attempt; the
[maintainer patch and rationale](https://kernel.googlesource.com/pub/scm/linux/kernel/git/stable/stable-queue/+/refs/tags/v6.12.41/releases/5.15.181/fs-proc-do_task_stat-use-sig-stats_lock-to-gather-the-threads-children-stats.patch)
describe the excessive waiting caused by many concurrent observers of a large
thread group. The inspected 6.1.159 source already contains this change. A
benchmark that puts the entire scan under one exclusive spinlock would not model
this guest's normal path. Thread exit and child reaping can still update
`stats_lock` and force retries; read-only observers alone do not invalidate its
sequence counter.

Global `tasklist_lock` remains relevant to fork, exit, reparenting and wait
operations (`kernel/fork.c`, `kernel/exit.c`). It is a system-wide `rwlock_t`,
including write acquisitions with IRQs disabled. A container creation/exit storm
can exercise it, but the ordinary procfs enumeration above is not a global
task-list read-lock benchmark.

### mmap critical-section boundaries

`include/linux/mm_types.h` declares `mmap_lock` as `struct rw_semaphore`.
`include/linux/mmap_lock.h` maps its read/write/killable/trylock/downgrade
interfaces to rwsem operations. This protects VMA layout and associated address
space operations, not all task fields or all page-table changes. Page tables and
reverse mappings have additional locks.

| Entry / source | mmap acquisition and protected work |
| --- | --- |
| `mmap()` → `vm_mmap_pgoff()`, `mm/util.c:505` | Write-killable lock around `do_mmap()`: choose/validate addresses, merge/create VMAs and update the Maple Tree and accounting. Allocation and filesystem/security callbacks can occur. Requested population is performed after this wrapper unlocks. |
| `munmap()` → `__vm_munmap()`, `mm/mmap.c:2926` | Write-killable lock around `do_mas_munmap()`, including VMA changes and unmapping work. The syscall path can downgrade to read ownership before release. |
| `mprotect()`, `mm/mprotect.c:702`; `mremap()`, `mm/mremap.c:943`; `brk()`, `mm/mmap.c:181` | Write-killable acquisitions around VMA validation/mutation; paths can split/merge VMAs, allocate, change page tables and perform TLB/MMU-notifier work. Their bodies are not fixed-size metadata copies. |
| `/proc/PID/maps`, `fs/proc/task_mmu.c:141` / `:186` | `m_start()` takes a killable read lock; `m_stop()` releases it. A seq-file iteration batch walks VMAs and formats records while protected, rather than one acquisition necessarily covering the complete file. Opening the file also uses the task/MM access-check and lifetime machinery. |
| `/proc/PID/smaps` and `smaps_rollup`, `fs/proc/task_mmu.c:613` / `:877` | Read mmap ownership plus page-table locks while collecting resident/PSS/etc. statistics. Page-table walks call `cond_resched()`; rollup explicitly releases/reacquires mmap read ownership when contended. Cost depends on mapped/resident pages as well as VMA count. |
| User faults, `arch/x86/mm/fault.c:1312`; remote argument reads, `mm/memory.c:5700` | Stabilize VMAs under mmap read ownership before fault/page lookup work; retry and stack-growth paths need their own lock-state handling. Remote reads can therefore wait behind a target's mapping writer even when `ps` never opens `maps`. |

### What KD can delegate

The current provider has no rwsem backend. Its
[reader/writer lock](design/rwlock_implementation.md) disables preemption,
requires non-sleeping bodies and delegates **writers only**. Its reader path
runs locally. The UTS experiment's bounded copy under a private lock does not
establish that a real `mmap_lock` can be replaced in the same way.

The decisive constraints are:

- **Lock protocol and callers.** A private KD lock cannot exclude fault, exec,
  exit or other native users of the real rwsem. KD mutexes are exclusive, with
  different storage and ownership rules; the KD mutex does not supply mmap's
  concurrent readers, killable waits, trylock, downgrade and release/reacquire
  semantics. A new backend or an audited cooperating adapter would be required.
- **Execution context.** Allocation, page faults, scheduling, nested MM locks,
  callbacks and TLB operations cannot be treated as a bounded spinning payload.
  KD's support for a logical `current` load does not switch the hardware address
  space or reproduce arbitrary task/CPU context. A mutex combiner may sleep, so
  sleep alone is not a universal prohibition on delegation; it does not solve
  these rwsem and context requirements.
- **IRQ and RCU boundaries.** The explicit IRQ/BH spin APIs in
  [kd_spin_direct.h](../include/kd_spin_direct.h) deliberately execute locally.
  This excludes delegating the real `siglock`, statistics fallback and raw CPU
  accounting sections through those APIs. The translator also screens IRQ,
  scheduler and RCU operations in
  [context_symbols.py](../disassem/context_symbols.py). RCU traversal and task
  exit/reclamation cannot simply be moved to a different executor.
- **Whole-body admission.** The small plain-spin snapshots below are candidates,
  not established JIT successes. Pointer lifetime, helper translation and alias
  checks still apply. An ordinary untranslated call can return execution to the
  original caller; that native continuation is not evidence that the full body
  was delegated. Record actual returned-body JIT counts and refusals.

Consequently, neither full mmap operations nor full `ps` statistics collection
are supported KD delegation workloads today. This is a limit of the current
implementation and integration contract, not a claim that such delegation is
impossible with a new design. Also, combining a short snapshot does not remove
the surrounding PID enumeration, thread traversal or userspace formatting cost.

### Proposed benchmark additions

Start with native measurements to identify which shared object is expensive,
then use an extracted body only where a controlled lock comparison is meaningful.
The labels below are proposals and are not accepted runner options.

| Proposed case | Setup and measured operation | KD status |
| --- | --- | --- |
| `proc-stat` | Multiple observers repeatedly read one live group's `stat`; vary threads per group and compare with observers assigned distinct groups. Add a separately labelled thread-exit/child-reaping variant to study retries. | Useful native scaling workload. Preserve the seqlock/RCU first attempt; no current full-body delegation adapter. |
| `proc-comm-snapshot` | Extract the bounded, NUL-terminated/zero-padded task-name copy under an ordinary exclusive spinlock; use module-owned records and stable per-worker kernel output buffers. Vary shared versus distinct records and separately add controlled name updates. | Plausible KD spin candidate after compiled-body admission. It models the `alloc_lock` payload, not the whole procfs syscall. Trace/perf side effects of real name setters remain outside this extracted experiment. |
| `proc-arg-bounds` | Extract the four-word `arg_lock` snapshot into a controlled module-owned record. Readers copy one complete tuple; optional writers alternate valid tuples under the same selected lock. | Plausible KD spin candidate, including delegation of reads because the original lock is exclusive. It does not benchmark fetching `cmdline` pages or the mmap rwsem. |
| `proc-cmdline-mmap` | Observers read a target's `cmdline` while its threads map/unmap disjoint scratch regions in the same address space. Vary observer count, mapping-writer count, argument bytes and VMA count. | Useful native mmap contention workload; current KD backend unsupported. Keep a stable-arguments oracle and a no-writer control. |
| `proc-maps` / `proc-smaps` | Read maps or memory-accounting records while a target changes separate mappings. Vary actual VMA count, resident bytes and target count independently. | Native workload; current KD backend unsupported. Report maps and smaps separately. |
| `task-lifecycle` | Controlled fork/thread creation and exit/reaping, with and without concurrent procfs observers. | Native control for global `tasklist_lock` and accounting writers. Current KD rwlock has no required IRQ variant; ordinary read acquisitions would not delegate anyway. |

For procfs cases, give every observer an independent open file description;
sharing one can introduce seq-file or file-position serialization unrelated to
the target lock. Define an operation as a complete read from offset zero and
record whether open/close or rewind costs are timed. For the name-copy payload,
preserve the source and destination sizes: the audited proc display uses a
64-byte temporary for a task name stored in `TASK_COMM_LEN` (16) bytes.

For extracted-body comparisons, all participants must use one selected lock
protocol. Do not redirect only procfs readers to a KD lock while real task/MM
writers retain Linux locks, or install a private lock over live VMAs. Task and
MM references pin allocations but do not freeze fields, thread membership or
the target's exec/exit state. A future real-object adapter needs a complete
consumer, lifetime and permission-check audit.

A useful native screening matrix separates these dimensions:

1. **Sharing:** one observed process versus many independent processes; many
   threads in one address space versus the same total tasks spread across
   address spaces. Keep total task count fixed for the comparison that isolates
   sharing. Then vary container/PID-namespace count separately.
2. **Observers and activity:** vary concurrent readers independently of target
   threads and mapping writers. Compare idle targets, CPU activity, mapping
   churn and lifecycle churn in separate cases; sleeping target threads can
   provide a large population without making every target runnable.
3. **Payload:** distinguish `comm` from `args`; vary VMA count independently of
   thread count and distinguish VMA traversal from resident-page traversal.
   Avoid unintended VMA merging in setup and record the actual map count.
4. **Measurement:** retain whole-scan latency, reads/second, CPU time, tail
   latency, errors and target progress. Attribute lock wait and hold time to
   lock address/target `mm` and call stack rather than only to a lock class.
   The guest source provides `mmap_lock_start_locking`,
   `mmap_lock_acquire_returned` and `mmap_lock_released` tracepoints. Pair by
   caller and `mm`, check success, and account for trylock, downgrade and retry
   paths. Use separate profiling runs so probe cost is not counted as lock
   performance; the captured configuration has `CONFIG_LOCK_STAT` disabled.

Use the existing 64-vCPU recovery guest and measurement rules for future runs.
Keep fixed worker/coordinator placement distinct from the number of observed
tasks, and do not interpret arbitrary container oversubscription as validated KD
operation. Native lifecycle tests must tolerate documented procfs exit races;
stable snapshot tests should validate exact tuples/names. Matched extracted-body
tests need identical payloads, successful JIT execution and complete drain.
No large-container run, new kernel hook, module/JIT experiment or performance
comparison was performed for this audit.

## Source references

| Description | Maintained source |
| --- | --- |
| Synthetic counter sizes and bodies | [ABI constants](../workload_modules/spin_cacheline/api.h), [cacheline payload](../workload_modules/spin_cacheline/payload.h) |
| Hash move attempts and final structure checks | [Hash payload](../workload_modules/spin_cacheline/hash_payload.h) |
| Reader bodies and per-worker write mix | [Rwlock payload](../workload_modules/rwlock_bench/payload.h), [worker loop](../workload_modules/rwlock_bench/module.c) |
| Real API object setup, queries and result checks | [Userspace client](../bench/real_api/client.c) |
| Xattr, OFD and descriptor-flag adapters | [Spin API module](../workload_modules/real_api/module.c) |
| Pipe and file-position adapters | [Mutex API module](../workload_modules/real_api/mutex.c) |
| UTS reads, writes and notification placement | [UTS API module](../workload_modules/real_api/uts.c) |
| Session labels, parameter validation and plot filenames | [Runner](../bench/real_api/run.py), [reporter](../bench/real_api/report.py) |

The [spin API run record](../bench/results/10.176.26.71/bench/real_api/20261011/README.md)
and [mutex/UTS run record](../bench/results/10.176.26.71/bench/real_api/20261011-sync/README.md)
retain the archive locations and source hashes for the original kernel helpers.
Their raw archives include `kernel-inputs/` copies of `fs/locks.c`, `fs/file.c`,
`fs/fcntl.c`, `fs/pipe.c`, `fs/read_write.c`, `fs/xattr.c`, `mm/shmem.c` and
`kernel/sys.c` for the relevant sessions. Consult each run's frozen source when
interpreting historical results.
