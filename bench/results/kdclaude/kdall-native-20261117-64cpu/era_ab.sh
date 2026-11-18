#!/bin/bash
# era_ab.sh: in one boot of a kdall kernel, mmap1, mmap2 and brk1 (threads)
# with the mmap lock writers delegated, at 48, 60 and 64 workers, under
# three era settings, 3 rounds with the order rotated:
#   base      defaults (kd_rw_era_ns 200000, kd_rw_era_press 225)
#   era0      kd_rw_era_ns=0: no eras
#   press400  kd_rw_era_press=400: an era needs 4 callers of company
#   e500      kd_rw_era_ns=500000
#   e1000     kd_rw_era_ns=1000000
#   r200      kd_rwsem_era_ns=200000 (kernels with a separate rwsem bound)
# CFGS picks the settings (default: base era0 press400); PREFIX names the
# output files. Output: /root/mdiag/PREFIX-<round>-<cfg>.txt (mm_diag.sh format)
D=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
export TESTS=${TESTS:-"mmap1 mmap2 brk1"} WORKERS=${WORKERS:-"48 60 64"}
read -ra cfgs <<< "${CFGS:-base era0 press400}"
PREFIX=${PREFIX:-era}
n=${#cfgs[@]}
for r in 1 2 3; do
	for ((i = 0; i < n; i++)); do
		c=${cfgs[$(( (i + r - 1) % n ))]}
		case $c in
		base) bash $D/mm_diag.sh $PREFIX-$r-$c ;;
		era0) bash $D/mm_diag.sh $PREFIX-$r-$c kd_rw_era_ns=0 ;;
		press400) bash $D/mm_diag.sh $PREFIX-$r-$c kd_rw_era_press=400 ;;
		e500) bash $D/mm_diag.sh $PREFIX-$r-$c kd_rw_era_ns=500000 ;;
		e1000) bash $D/mm_diag.sh $PREFIX-$r-$c kd_rw_era_ns=1000000 ;;
		r200) bash $D/mm_diag.sh $PREFIX-$r-$c kd_rwsem_era_ns=200000 ;;
		esac
	done
done
echo ERA_AB_DONE > /root/mdiag/$PREFIX.done
