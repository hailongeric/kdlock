#!/bin/bash
# pf1_regs.sh TAG [THREADS]: will-it-scale page_fault1 (threads, default 16),
# no daemon. Samples the interrupted registers for 5 s (perf -I, no call
# graphs) and histograms %rdi, the lock argument, in the spinlock entries
# (kd_spin_lock* on kdall, _raw_spin_lock* and the queued slow path on
# kdnat). The addresses are classed by region: struct pages (vmemmap, where
# split PTE locks live), the direct map (slab and node data: lruvec, mm,
# zone), the kernel image. Output: /root/prof/TAG-pf1regs.txt
TAG=${1:?tag}; N=${2:-16}
O=/root/prof; mkdir -p $O; exec > $O/$TAG-pf1regs.txt 2>&1
uname -rv
cd /tmp
/root/wis/build/page_fault1_threads -t $N -s 12 -n 1 > /tmp/pf1.out 2>&1 &
p=$!
sleep 3
perf record -a -I -F 999 -o /tmp/pf1.data -- sleep 5 > /dev/null 2>&1
wait $p
tail -1 /tmp/pf1.out
perf script -i /tmp/pf1.data -F ip,sym,iregs 2>/dev/null > /tmp/pf1.txt
python3 - <<'PY'
import re, collections
regions = [
    (0xffd4000000000000, 0xffd6000000000000, "vmemmap (struct page: split PTE locks)"),
    (0xffea000000000000, 0xffeb000000000000, "vmemmap (struct page: split PTE locks)"),
    (0xff11000000000000, 0xff21000000000000, "direct map (slab, node data)"),
    (0xffff888000000000, 0xffffc88000000000, "direct map (slab, node data)"),
    (0xffffffff80000000, 0xffffffffc0000000, "kernel image (static)"),
]
def region(a):
    for lo, hi, n in regions:
        if lo <= a < hi:
            return n
    return "other %#x" % (a >> 40 << 40)
tot = 0
syms = collections.Counter(); kinds = collections.Counter(); addrs = collections.Counter()
for l in open('/tmp/pf1.txt'):
    m = re.match(r'\s*[0-9a-f]+\s+(\S+)', l)
    if not m:
        continue
    tot += 1
    s = m.group(1)
    syms[s] += 1
    if not (s.startswith('kd_spin_lock') or s.startswith('_raw_spin_lock') or
            s.startswith('kd_q_lock') or s == 'native_queued_spin_lock_slowpath'):
        continue
    r = re.search(r'\bDI:(0x[0-9a-f]+)', l)
    if r:
        a = int(r.group(1), 16)
        kinds[(s, region(a))] += 1
        addrs[(s, a)] += 1
print("samples", tot)
for s, c in syms.most_common(10):
    print("  %-34s %6d %5.1f%%" % (s, c, 100.0 * c / tot))
print("spinlock samples by function and region of %rdi:")
for (s, k), c in kinds.most_common(12):
    print("  %-26s %-40s %6d" % (s, k, c))
print("top %rdi values:")
for (s, a), c in addrs.most_common(10):
    print("  %-26s %#x %6d  %s" % (s, a, c, region(a)))
PY
echo PF1REGS_DONE
