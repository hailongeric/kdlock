# kdlock

Kernel-space lock experiments and user-space tooling.

This repo contains Linux kernel modules for lock-related experiments, plus
user-space helpers for driving tests and analyzing behavior.

**Contents**
1. `kernel_module/` Kernel module implementing the core lock logic and helpers.
1. `klock_module/` Simple character device module used by test tools.
1. `bench/` User-space benchmarks and test programs.
1. `daemon/` User-space daemons/helpers.
1. `disassem/` Python tooling for disassembly/analysis.
1. `include/` Shared headers.
1. `test_tools/` Misc test scripts.

**Prerequisites**
1. Linux with kernel headers installed.
1. `gcc`, `make`.
1. Python 3 (for tools in `disassem/` and `test_tools/`).

**Build**
1. Kernel module:
   ```sh
   cd kernel_module
   make
   ```
1. Lock device module:
   ```sh
   cd klock_module
   make
   ```
1. User-space daemons:
   ```sh
   cd daemon
   make
   ```

**Load / Setup (requires root)**
1. Load the lock device module:
   ```sh
   sudo insmod klock_module/klock_module.ko
   ```
1. Optional sysctl tuning (see `setup.sh`):
   ```sh
   sudo ./setup.sh
   ```

**Example: build a benchmark**
```sh
gcc -Iinclude bench/klock_test.c -o bench/klock_test -lpthread
```

**Clean**
```sh
cd kernel_module && make clean
cd klock_module && make clean
cd daemon && make clean
```

**Notes**
1. Kernel modules require matching kernel headers and root privileges.
1. `setup.sh` disables ASLR and NUMA balancing; only run it if that matches
   your testing needs.
