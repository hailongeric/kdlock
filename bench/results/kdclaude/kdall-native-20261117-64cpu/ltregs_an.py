#!/usr/bin/env python3
# ltregs_an.py TORTURE_MUTEX_HEX: name the lock words that perf -I samples
# show in kd_q_lock_plain (%rdx holds the lock word for its whole body).
# Inputs: /tmp/ltr.txt (perf script -F cpu,iregs), /tmp/ltr.map (kd_addrs.ko).
import re, sys, bisect, collections
tm = int(sys.argv[1], 16) if len(sys.argv) > 1 and sys.argv[1] else 0
syms = []
for l in open('/proc/kallsyms'):
    f = l.split()
    if len(f) >= 3 and f[1] in 'tTwW':
        syms.append((int(f[0], 16), f[2]))
syms.sort()
addrs = [a for a, _ in syms]
def sym(ip):
    i = bisect.bisect_right(addrs, ip) - 1
    return syms[i][1] if i >= 0 else '?'
names = {}
if tm:
    names[tm] = 'torture_mutex.q'
    names[tm + 4] = 'torture_mutex.wait_lock'
for l in open('/tmp/ltr.map'):
    f = l.split()
    if f and f[0] == 'task':
        names[int(f[4], 16)] = 'pi_lock of %s %s' % (f[2], f[1])
    elif f and f[0] == 'rq':
        names[int(f[2], 16)] = 'rq lock of cpu %s' % f[1]
tot = 0
bysym = collections.Counter(); cnt = collections.Counter(); kinds = collections.Counter()
for l in open('/tmp/ltr.txt'):
    ip = re.search(r'\bIP:(0x[0-9a-f]+)', l)
    if not ip:
        continue
    tot += 1
    s = sym(int(ip.group(1), 16))
    bysym[s] += 1
    if s != 'kd_q_lock_plain':
        continue
    dx = int(re.search(r'\bDX:(0x[0-9a-f]+)', l).group(1), 16)
    cnt[dx] += 1
    n = names.get(dx, '?')
    kinds[n.split(' of ')[0] if ' of ' in n else n] += 1
print('samples', tot)
for s, c in bysym.most_common(8):
    print('  %-32s %6d %5.1f%%' % (s, c, 100.0 * c / tot))
n = sum(cnt.values())
print('kd_q_lock_plain samples by lock kind (%d):' % n)
for k, c in kinds.most_common():
    print('  %-26s %6d %5.1f%%' % (k, c, 100.0 * c / max(n, 1)))
print('top lock words:')
for a, c in cnt.most_common(10):
    print('  %#x %6d %5.1f%%  %s' % (a, c, 100.0 * c / max(n, 1), names.get(a, '?')))
