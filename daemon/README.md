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

- `--mode 1`: compatible with the old `daemon1.c` layout. Each translated
  entry uses `./<RIP>/` as its workspace.
- `--mode 2`: compatible with the old `daemon2.c` layout. Each translated
  entry uses `./<RIP>/<tgid>/` as its workspace. This is the default.

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

Legacy source files `daemon1.c` and `daemon2.c` are kept for comparison. Use
`make legacy` only when you need to rebuild those old binaries.
