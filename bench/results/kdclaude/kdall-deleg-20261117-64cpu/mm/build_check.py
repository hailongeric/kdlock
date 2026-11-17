#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Build, without loading, the images of the sites in a daemon state file.

For each site: instruction count, how many cond_resched() points are copied
behind the need_resched check (resched_point), how many stay frontiers, and
the generated code around the first resched point.

  build_check.py /root/kds_mm.json
"""
import json
import sys

sys.path.insert(0, "/root/host_fs/kdlock/jit")

import capstone  # noqa: E402

from kd_dryrun import describe  # noqa: E402
from kdjit.kernel import Device, KernelView  # noqa: E402
from kdjit.translator import Learned, Translator  # noqa: E402

dev = Device()
info = dev.info()
kv = KernelView(dev)
tr = Translator(kv, info)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
state = json.load(open(sys.argv[1]))
for site, data in state["sites"].items():
    site = int(site)
    learned = Learned.from_json(data)
    kv.sync()
    image = tr.build(site, learned)
    points = sorted(a for a, i in tr.ins.items() if i.kind == "resched_point")
    stops = sorted(a for a, i in tr.ins.items() if i.kind == "frontier" and a in tr.sched_sites)
    print("site %s: %d instructions (learned code %d), %d resched points, %d static-call frontiers" %
          (describe(kv, site), image.insns, len(learned.code), len(points), len(stops)))
    for a in points[:6]:
        print("    point", describe(kv, a))
    if points:
        base = 0xffffffffc0000000
        text, _entry = image.link(base)
        start = tr.asm.link(base)[1][("loc_%x" % points[0])]
        for i in md.disasm(text[start - base:start - base + 40], start):
            print("      %#x  %s %s" % (i.address, i.mnemonic, i.op_str))
            if i.mnemonic == "xor":
                break
