#!/bin/bash
# p23_kd.sh: phases 2 and 3 of the reduced round on a kdall kernel, one boot:
# the candidates of the native screening (data/s4-candidates.txt: lock share
# at 64 workers at least 30%, or at least 10% for the application groups) at
# 64 workers, 6 s per point: kd off, discover (empty allow list, one daemon
# per point), a learning pass and kd on with the allow lists api, torture, mm
# and lkp (kd_vdown at its default 1). Output in /root/lkpres, tag s4-w64.
S=$(cd "$(dirname "$0")" && pwd)/screen.sh
O=/root/lkpres
G="perfb sysbench filebench fio vms2 fsx wis wisp sng vms hackbench fsmark wis2 wisp2 sng2"
export NS=64 DUR=6
export ONLY='^(pbe-wait|pbe-ctl|sysbench-threads|filebench-fileserver|filebench-varmail|filebench-webserver|filebench-webproxy|fio-randwrite-shared|vms-lru-file-mmap-read|vms-lru-file-mmap-read-rand|vms-mmap-pread-rand-mt|vms-mmap-xread-rand-mt|vms-mremap-xread-rand-mt|fsmark-ext4-fsync|dbench-ext4|fsmark-xfs-fsync|fsmark-btrfs-nosync|wis-unlink1|wis-pwrite2|wis-pwrite3|wis-writeseek3|wis-readseek2|wis-lseek2|wis-pthread_mutex4|wis-sched_yield|wisp-pwrite3|wisp-futex1|sng-dentry|sng-unlink|sng-clone|sng-exit-group|sng-wait|sng-msg|sng-shm-sysv|sng-udp|sng-epoll|sng-mmapfork|sng-mremap|sng-flock|sng-fcntl|vms-small-allocs|hb-pipe-process|fsmark|wis-fallocate1|wis-fallocate2|wis-lock1|wis-unlink2|wis-writeseek2|wisp-fallocate1|wisp-fallocate2|wisp-pread2|wisp-readseek2|sng-affinity|sng-clock|sng-cpu-sched|sng-dev-shm|sng-env|sng-fault|sng-fd-abuse|sng-filehole|sng-full|sng-forkheavy|sng-membarrier|sng-memfd|sng-mlock|sng-msync|sng-munmap|sng-mmapmany|sng-mmapcow|sng-netlink-task|sng-schedpolicy|sng-seal|sng-seccomp|sng-secretmem|sng-session|sng-sigchld|sng-sigstop|sng-sleep|sng-sockdiag|sng-sockfd|sng-sockmany|sng-sysinfo|sng-umask|sng-vforkmany|sng-chmod|sng-chown|sng-copy-file|sng-dirdeep|sng-dirmany|sng-dnotify|sng-file-ioctl|sng-filename|sng-fpunch|sng-fsize|sng-fstat|sng-handle|sng-io|sng-ioprio|sng-mknod|sng-procfs|sng-xattr|sng-chattr|sng-touch|sng-epollmany|sng-rawpkt|sng-rawsock|sng-rawudp|sng-physpage|sng-pidfd|sng-ptrace|sng-pty|sng-ramfs|sng-rlimit)$'
rm -f /root/kds_lkp.json
bash $S off s4-w64 $G > $O/s4-off.out 2>&1
echo "P23_OFF_DONE $(date +%T)" >> $O/progress.txt
bash $S discover s4-w64 $G > $O/s4-discover.out 2>&1
echo "P23_DISCOVER_DONE $(date +%T)" >> $O/progress.txt
bash $S on learn-s4 $G > $O/s4-learn.out 2>&1
bash $S on s4-w64 $G > $O/s4-on.out 2>&1
cat /sys/kernel/debug/kdlock_stats > $O/s4-on-stats.txt
echo "P23_DONE $(date +%T)" >> $O/progress.txt
