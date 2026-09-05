# kdlock daemon

`daemon` is the userspace bridge between `/dev/kd_dev` and the Python
translator in `../disassem/disassem.py`.

Run it from this directory:

```sh
cd daemon
make
./daemon --mode 2
```

Modes:

- `--mode 1`: use one flat workspace per translated entry: `./<RIP>/`.
- `--mode 2`: isolate workspaces by process: `./<RIP>/<tgid>/`. This is the
  default.

These select workspace layout, not benchmark mode or hostcall policy. Kernel
lock entries use `pid=0` as their lookup key, but retain the registering task's
`tgid`. Their mode-2 workspace is still `./<RIP>/<tgid>/`, not `./<RIP>/0/`.

Useful options:

- `--quiet`: suppress normal progress output.
- `--verbose`: print initialization, miss, and compile messages.
- `--poll-us N`: set the polling interval in microseconds. The default is
  `100000`.

For each new entry the daemon creates an isolated `asm/` workspace and empty
`callee_table.txt` and `ij_table.txt` files. It updates those tables when the
kernel reports a missing call or indirect jump, invokes the translator, and
writes the generated `jit.bin` back through `/dev/kd_dev`. No pre-created
workspace template is required.

The daemon rejects empty images and images larger than the shared 640 KiB code
block. It streams the artifact in chunks of at most 4000 bytes, checks every
file and device transfer, and marks the entry `KD_EXE_NORMAL` only on the final
complete chunk. The kernel validates the entry key, destination offset, payload
length, and status before copying each chunk.

This relies on a trusted, single daemon completing the transfer. The kernel
does not track total image length, chunk continuity, image generation, or live
executors. Recompilation overwrites the same executable block; release/acquire
publication does not protect an old execution from those writes. The
`install JIT chunk` diagnostic is emitted before key validation and payload
copy, so even `status=0` is not a completed-install acknowledgment. Versioned
publication and coherent miss snapshots remain open work in
[`docs/TODO.md`](../docs/TODO.md).

Each translation emits one concise input summary containing the entry RIP and
nonzero target, region, and kernel-text byte counts. Tests use this line as
evidence that translation read `/proc/kcore`; raw kernel bytes are not logged.

Allowlisted JIT hostcalls are not translation misses. The translator emits a
dedicated hostcall exit stub, and the kernel executes and resumes that service
without changing the entry status or appending the target to
`asm/callee_table.txt`.

For x86 kernel critical sections, the translator also resolves the per-CPU
`current_task` offset from `/proc/kallsyms`. Generic `%gs:` memory operands are
lowered to explicit addressing through the waiter GS base supplied by the
kernel; `%gs:current_task` is replaced by the logical waiter task. `%fs:`, direct
FS/GS-base operations, and unsupported `current_task` forms produce a minimal
`KD_EXE_ERROR_INST` artifact instead of a partially executable translation.

That rejection guarantee covers segment preflight in fetched code ranges only.
It is not a general instruction verifier: some unsupported special operations
only warn, and `INT` is currently lowered to NOP. Do not translate arbitrary
kernel callees on the assumption that every unsafe instruction will be rejected.
