#!/bin/bash
# p23b_kd.sh: as p23_kd.sh, for the candidates that only the clean native
# pass (s5-w64) found (data/s5-candidates-added.txt), in a boot of its own
# with the daemon state p23_kd.sh left. Before and after: stress-ng seccomp
# five times without and with the daemon (the delegated pass of p23_kd.sh
# logged one SIGSYS kill of a seccomp child; the other passes none).
S=$(cd "$(dirname "$0")" && pwd)/screen.sh
O=/root/lkpres
G="fsx wis wisp sng unixbench wis2 wisp2 sng2"
export NS=64 DUR=6
for i in 1 2 3 4 5; do ONLY='^sng-seccomp$' bash $S off secc-off$i sng2 > $O/secc.out 2>&1; done
export ONLY='^(fsmark-btrfs-fsync|dbench-btrfs|wis-brk1|wis-brk2|wis-mmap1|wis-mmap2|wis-page_fault1|wis-signal1|wis-dup1|wis-lock2|wis-open1|wis-open3|wis-pread2|wis-pthread_mutex1|wis-pthread_mutex3|wisp-lock2|wisp-unlink1|wisp-pwrite2|sng-dir|sng-link|sng-rename|sng-getdent|sng-filerace|sng-open|sng-vfork|sng-zombie|sng-shm|sng-mmap|ub-execl|wis-open2|wis-pthread_mutex5|wisp-brk1|wisp-brk2|wisp-mmap1|wisp-mmap2|wisp-page_fault1|wisp-tlb_flush2|wisp-unlink2|wisp-writeseek2|wisp-writeseek3|sng-dynlib|sng-io-uring|sng-landlock)$'
bash $S off s4-w64 $G > $O/s4b-off.out 2>&1
echo "P23B_OFF_DONE $(date +%T)" >> $O/progress.txt
bash $S discover s4-w64 $G > $O/s4b-discover.out 2>&1
bash $S on learn-s4b $G > $O/s4b-learn.out 2>&1
bash $S on s4b-w64 $G > $O/s4b-on.out 2>&1
for i in 1 2 3 4 5; do ONLY='^sng-seccomp$' bash $S on secc-on$i sng2 > $O/secc.out 2>&1; done
cat /sys/kernel/debug/kdlock_stats > $O/s4b-on-stats.txt
echo "P23B_DONE $(date +%T)" >> $O/progress.txt
