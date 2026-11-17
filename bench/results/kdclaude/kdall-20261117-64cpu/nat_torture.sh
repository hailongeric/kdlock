O=/root/kda; exec > $O/kdclaude1-torture.log 2>&1
D=/root/kdc_torture
mark() { echo "kda: $*" > /dev/kmsg; echo "== $* $(date +%T)"; }
since() { dmesg | awk -v m="kda: $1" 'index($0, m) {f=1} f'; }
uname -rv; pgrep -af kd_daemon || echo "no daemon"; cat /sys/module/kernel/parameters/kd_mm /sys/module/kernel/parameters/kd_api
insmod $D/torture.ko
for t in lock_busted spin_lock spin_lock_irq raw_spin_lock raw_spin_lock_irq rw_lock rw_lock_irq \
	 mutex_lock ww_mutex_lock rwsem_lock rtmutex_lock percpu_rwsem_lock; do
	mark "torture $t"
	insmod $D/locktorture_ext.ko torture_type=$t stat_interval=0 || { echo "insmod failed"; continue; }
	sleep 60
	rmmod locktorture_ext
	since "torture $t" | grep -E "End of test|Writes:|Reads:" | sed 's/^\[[^]]*\] //' | sed 's/acq_writer_lim.*//' | tail -3
done
for i in 1 2 3; do
	mark "wwrep $i"
	insmod $D/test-ww_mutex.ko; echo "insmod rc=$?"; rmmod test_ww_mutex
	echo "run $i: $(since "wwrep $i" | grep -E "failed|passed|Beginning" | sed 's/^\[[^]]*\] //' | tr '\n' '|')"
done
echo "complaints:"; dmesg | grep -iE "BUG:|WARNING:|lockup|hung_task|rcu.*stall" | head
echo NAT_DONE
