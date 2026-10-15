cd /root/host_fs/kdlock
export PATH=/root/kdlock-evidence/clobber-20260918/venv/bin:$PATH LC_ALL=C PYTHONDONTWRITEBYTECODE=1
export KDLOCK_RECOVERY_CONFIRMED=1 KDLOCK_SNAPSHOT_TAG=rwlock-c01-grid-20261015
timeout 7200s python3 bench/rwlock_compare/run.py --lock-kind rwlock --backends native tclock kdlock --workloads cacheline --cachelines 1 --write-percent 1 20 --threads 1 2 3 4 5 6 7 8 12 16 20 24 28 32 36 40 44 48 52 56 60 --collector-cpu 63 --repeats 3 --duration-ms 2000 --output /root/kdlock-evidence/10.176.26.71/bench/rwlock-c01-grid-20261015 > /root/kdlock-evidence/10.176.26.71/bench/rwlock-c01-grid-20261015.log 2>&1
result=$?
printf '%s\n' "$result" > /root/kdlock-evidence/10.176.26.71/bench/rwlock-c01-grid-20261015.exit
exit "$result"
