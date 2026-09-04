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

Useful options:

- `--quiet`: suppress normal progress output.
- `--verbose`: print initialization, miss, and compile messages.
- `--poll-us N`: set the polling interval in microseconds. The default is
  `100000`.

The daemon expects the template `asm/` directory to exist under `daemon/`.
For each entry it copies that template, updates `asm/callee_table.txt` or
`asm/ij_table.txt` when the kernel reports a missing call or indirect jump,
invokes the translator, and writes the generated `asm/jit.bin` back through
`/dev/kd_dev`.

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
