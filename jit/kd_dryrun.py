#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""Build images without loading them, and print what was generated.

For each named function, every direct call to a delegable kd acquire entry
is a site (the call's return address). The translator builds the image for
that site exactly as the daemon would, links it at a placeholder address
near the site, and prints a summary and, with --disasm, the generated code.
Nothing is written to the kernel; only /dev/kdlock reads are used.

  kd_dryrun.py kmutex_w krwsem_w --disasm
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import capstone  # noqa: E402

from kdjit.kernel import KD_SYM_ACQUIRE, KD_SYM_NESTED, Device, KernelView  # noqa: E402
from kdjit.translator import Learned, TranslationError, Translator  # noqa: E402


def sites_in(kv, info, func, length=4096):
    """Return addresses following direct calls to acquire entries.

    Sleeping-family entries are KD_SYM_ACQUIRE; spin-class entries are
    KD_SYM_NESTED (they also have a `_jit` alternative). Both are sites.
    """
    start = kv.addr_of.get(func)
    if start is None:
        raise SystemExit("no symbol %s" % func)
    i = kv.text_syms.index(start)
    end = kv.text_syms[i + 1] if i + 1 < len(kv.text_syms) else start + length
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    out = []
    for cs in md.disasm(kv.read(start, end - start), start):
        if cs.mnemonic != "call" or not cs.op_str.startswith("0x"):
            continue
        sym = info.syms.get(int(cs.op_str, 16))
        if sym and sym[0] in (KD_SYM_ACQUIRE, KD_SYM_NESTED):
            out.append(cs.address + cs.size)
    return out


def describe(kv, addr):
    f = kv.func_of(addr)
    names = kv.names(f) if f is not None else ()
    return "%s+%#x" % (names[0], addr - f) if names else "%#x" % addr


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("funcs", nargs="+")
    ap.add_argument("--device", default="/dev/kdlock")
    ap.add_argument("--disasm", action="store_true")
    args = ap.parse_args()

    dev = Device(args.device)
    info = dev.info()
    kv = KernelView(dev)
    tr = Translator(kv, info, {})
    md = capstone.Cs(capstone.CS_ARCH_X86, capstone.CS_MODE_64)
    bad = 0
    for func in args.funcs:
        for site in sites_in(kv, info, func):
            try:
                image = tr.build(site, Learned())
                # Any address near the site satisfies rel32 for this check.
                base = (site & ~0xFFF) + 0x100000
                text, entry = image.link(base)
            except TranslationError as err:
                print("%s site %s: ERROR %s" % (func, describe(kv, site), err))
                bad += 1
                continue
            kinds = {}
            for ins in tr.ins.values():
                kinds[ins.kind] = kinds.get(ins.kind, 0) + 1
            print("%s site %s: %d insns, %d bytes, entry +%#x, kinds %s, missing %s" %
                  (func, describe(kv, site), image.insns, len(text), entry, kinds,
                   [describe(kv, a) for a in sorted(tr.missing)]))
            if args.disasm:
                for cs in md.disasm(text, base):
                    if cs.address == base + entry:
                        print("  ---- entry ----")
                    print("  %#x: %-40s %s %s" % (cs.address, cs.bytes.hex(), cs.mnemonic, cs.op_str))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
