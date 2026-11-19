#!/usr/bin/env python3
# pcpu.py SYM...: print the first byte (local_trylock_t.acquired) of each
# per-CPU symbol on every CPU, read from /proc/kcore (read only).
import struct, sys
syms = {}
for l in open('/proc/kallsyms'):
    a, t, n = l.split()[:3]
    syms[n] = int(a, 16)
f = open('/proc/kcore', 'rb')
eh = f.read(64)
phoff, = struct.unpack_from('<Q', eh, 32)
phentsize, phnum = struct.unpack_from('<HH', eh, 54)
segs = []
for i in range(phnum):
    f.seek(phoff + i * phentsize)
    p = f.read(phentsize)
    ptype, flags, off, vaddr, paddr, filesz, memsz, align = struct.unpack('<IIQQQQQQ', p)
    if ptype == 1:
        segs.append((vaddr, off, memsz))
def read(addr, n):
    for v, o, m in segs:
        if v <= addr < v + m:
            f.seek(o + addr - v)
            return f.read(n)
    raise ValueError(hex(addr))
ncpu = int(open('/sys/devices/system/cpu/possible').read().strip().split('-')[-1]) + 1
offs = struct.unpack('<%dQ' % ncpu, read(syms['__per_cpu_offset'], 8 * ncpu))
for s in sys.argv[1:]:
    vals = [read((syms[s] + offs[c]) & 0xffffffffffffffff, 1)[0] for c in range(ncpu)]
    stuck = [c for c, v in enumerate(vals) if v]
    print("%s: acquired set on %d of %d CPUs: %s" % (s, len(stuck), ncpu, stuck))
