#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Check the static-call frontier of the translator on the running kernel.

1. Lists the inline sites of each scheduling static call that the
   translator now treats as a frontier, and what the live text holds at
   each (call, NOP, or `xor %eax,%eax`).
2. Builds, without loading, the image of each lock site in the named
   functions twice: with the static-call frontier and without it. Then it
   prints how many decoded instructions are such sites, and which ones.

  sc_check.py __do_sys_brk unmap_page_range
"""

import collections
import os
import sys

sys.path.insert(0, "/root/host_fs/kdlock/jit")

import capstone  # noqa: E402

from kd_dryrun import describe, sites_in  # noqa: E402
from kdjit.kernel import Device, KernelView  # noqa: E402
from kdjit.translator import DEFAULT_CONFIG, Learned, Translator  # noqa: E402

dev = Device()
info = dev.info()
kv = KernelView(dev)
md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)

print("== static call sites")
for name in DEFAULT_CONFIG["frontier_static_call"]:
    sites = kv.static_call_sites(name)
    forms = collections.Counter()
    for a in sorted(sites):
        if not kv.in_text(a):
            forms["not in live text"] += 1
            continue
        cs = next(md.disasm(kv.read(a, 15), a, 1), None)
        if cs is None:
            forms["undecodable"] += 1
        elif cs.mnemonic == "call":
            t = int(cs.op_str, 16)
            forms["call " + (kv.names(t) or ["%#x" % t])[0]] += 1
        else:
            forms["%s %s (%d bytes)" % (cs.mnemonic, cs.op_str, cs.size)] += 1
    print("%-26s %6d sites" % (name, len(sites)))
    for form, n in forms.most_common():
        print("    %6d  %s" % (n, form))

for func in sys.argv[1:]:
    start = kv.addr_of[func]
    i = kv.text_syms.index(start)
    end = kv.text_syms[i + 1]
    hits = {n: sorted(a for a in kv.static_call_sites(n) if start <= a < end)
            for n in DEFAULT_CONFIG["frontier_static_call"]}
    print("== %s: %s" % (func, ", ".join("%s %s" % (n, [describe(kv, a) for a in v])
                                       for n, v in hits.items() if v) or "no sites"))

old = Translator(kv, info, {"frontier_static_call": []})
new = Translator(kv, info)
for func in sys.argv[1:]:
    try:
        sites = sites_in(kv, info, func)
    except SystemExit as err:
        print(err)
        continue
    for site in sites:
        kv.sync()
        old.build(site, Learned())
        n_old = len(old.ins)
        kv.sync()
        new.build(site, Learned())
        stops = sorted(a for a, ins in new.ins.items()
                       if ins.kind == "frontier" and a in new.sched_sites)
        print("site %s: %d instructions without, %d with; %d static-call frontiers%s" %
              (describe(kv, site), n_old, len(new.ins), len(stops),
               "".join("\n    " + describe(kv, a) for a in stops)))
os.close(dev.fd)
