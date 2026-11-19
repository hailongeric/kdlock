#!/usr/bin/env python3
"""kdsym.py ADDR...: guest helper, print symbol+offset for kernel addresses
(hex, as in dmesg or kd_daemon.py -v), through /dev/kdlock's symbol view."""
import sys
sys.path.insert(0, "/root/host_fs/kdlock/jit")
from kdjit.kernel import Device, KernelView
import kd_dryrun
kv = KernelView(Device("/dev/kdlock"))
for a in sys.argv[1:]:
    print(a, kd_dryrun.describe(kv, int(a, 16)))
