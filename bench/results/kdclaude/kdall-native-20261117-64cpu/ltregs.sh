#!/bin/bash
# ltregs.sh TAG [W]: locktorture mutex_lock with W writers (default 64), no
# daemon. Samples the interrupted registers (perf -I, no call graphs) and
# histograms %rdx, which holds the lock word in kd_q_lock_plain. The
# addresses are named from the locktorture mutex, and from the pi_lock and
# run queue lock addresses that /root/kdaddrs/kd_addrs.ko prints.
# Output: /root/ltw/TAG-regs.txt
TAG=${1:?tag}; W=${2:-64}; O=/root/ltw; mkdir -p $O; exec > $O/$TAG-regs.txt 2>&1
uname -rv
modprobe locktorture torture_type=mutex_lock nwriters_stress=$W stat_interval=0
sleep 4
tm=$(grep -E " torture_mutex\s+\[locktorture\]" /proc/kallsyms | cut -d" " -f1)
rq=$(grep -E " runqueues$" /proc/kallsyms | cut -d" " -f1)
echo "torture_mutex $tm runqueues $rq"
echo "ltregs: $TAG" > /dev/kmsg
insmod /root/kdaddrs/kd_addrs.ko rq_addr=0x$rq 2>/dev/null
dmesg | awk -v m="ltregs: $TAG" 'index($0,m){f=1} f' | grep "kd_addrs:" | sed 's/.*kd_addrs: //' > /tmp/ltr.map
echo "map entries $(wc -l < /tmp/ltr.map)"
perf record -a -I -F 999 -o /tmp/ltr.data -- sleep 3 > /dev/null 2>&1
sleep 1
rmmod locktorture
dmesg | grep "Writes:" | tail -1 | sed 's/.*Writes:/Writes:/; s/acq_writer.*//'
perf script -i /tmp/ltr.data -F cpu,sym,iregs 2>/dev/null > /tmp/ltr.txt
echo "samples $(wc -l < /tmp/ltr.txt)"
python3 - "$tm" <<'PY'
import re, sys, collections
tm = int(sys.argv[1], 16) if sys.argv[1] else 0
names = {}
if tm:
    names[tm] = 'torture_mutex.q'
    names[tm + 4] = 'torture_mutex.wait_lock'
for l in open('/tmp/ltr.map'):
    f = l.split()
    if f[0] == 'task':
        names[int(f[4], 16)] = 'pi_lock of %s %s' % (f[2], f[1])
    elif f[0] == 'rq':
        names[int(f[2], 16)] = 'rq lock of cpu %s' % f[1]
cnt = collections.Counter(); syms = collections.Counter(); tot = 0
kinds = collections.Counter()
for l in open('/tmp/ltr.txt'):
    tot += 1
    m = re.search(r'\]\s+(\S+)', l)
    s = m.group(1) if m else '?'
    syms[s] += 1
    if s != 'kd_q_lock_plain':
        continue
    r = re.search(r'\bDX:(0x[0-9a-f]+)', l)
    if r:
        a = int(r.group(1), 16)
        cnt[a] += 1
        n = names.get(a, '?')
        kinds[n.split(' of ')[0] if ' of ' in n else n] += 1
print("top symbols:", syms.most_common(6))
n = sum(cnt.values())
print("kd_q_lock_plain samples", n, "of", tot)
print("by kind:")
for k, c in kinds.most_common():
    print("  %-26s %6d %5.1f%%" % (k, c, 100.0 * c / max(n, 1)))
print("top addresses:")
for a, c in cnt.most_common(12):
    print("  %#x %6d %5.1f%%  %s" % (a, c, 100.0 * c / max(n, 1), names.get(a, '?')))
PY
echo REGS_DONE
