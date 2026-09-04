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
