#!/bin/bash
# drive.sh STEP...: run on 380G10. Each STEP is KERNEL:MODE[,MODE...]:TAG.
# For every step: boot the guest into KERNEL once (grub-reboot, the default
# entry stays), check the running release, then run suite.sh for each MODE
# in order, detached in the guest, and wait for it.
#   drive.sh kdall1:on,on:learn kdnat1:native:b1 kdall1:off,on:b2 ...
# Stops at the first kernel complaint, wrong release or failed suite.
VM=${VM:-/tmp/claude-1000/-home-eric-vm-vm-shared-kdlock/076f9fc5-5a3b-48ba-90ef-073f0a89b53f/scratchpad/vm.sh}
R=/root/host_fs/kdlock/bench/results/kdclaude/kdall-native-20261117-64cpu
SUITE=${SUITE:-suite.sh}
U=aa0bde06-47f6-4049-aaaf-13d052e53961
log() { echo "$(date +%T) $*"; }

boot() {	# boot KERNEL: reboot into 7.0.0-38-KERNEL and wait for it
	local k=$1 i
	$VM "sync; grub-reboot 'gnulinux-advanced-$U>gnulinux-7.0.0-38-$k-advanced-$U' && (sleep 1; systemctl reboot) > /dev/null 2>&1 &" || return 1
	sleep 30
	for i in $(seq 60); do
		VM_TIMEOUT=10 $VM true 2> /dev/null && break
		sleep 5
	done
	[ "$(VM_TIMEOUT=20 $VM uname -r)" = "7.0.0-38-$k" ] || { log "booted $(VM_TIMEOUT=20 $VM uname -r), wanted $k"; return 1; }
	sleep 20	# let boot-time services settle
}

suite() {	# suite MODE TAG: run suite.sh detached and wait for its end
	local m=$1 t=$2 i
	$VM "rm -f /root/cmp/suite-$t-$m.out; setsid nohup bash $R/$SUITE $m $t > /root/cmp/suite-$t-$m.out 2>&1 < /dev/null &" || return 1
	for i in $(seq 240); do	# up to 40 min
		sleep 10
		VM_TIMEOUT=20 $VM "grep -q SUITE_DONE /root/cmp/suite-$t-$m.out" 2> /dev/null && break
		VM_TIMEOUT=20 $VM "ps -e -o cmd | grep -q '^bash $R/$SUITE'" 2> /dev/null && continue
		VM_TIMEOUT=20 $VM true 2> /dev/null || continue
		# It may have finished between the two checks above.
		VM_TIMEOUT=20 $VM "grep -q SUITE_DONE /root/cmp/suite-$t-$m.out" 2> /dev/null && break
		log "suite $t $m stopped: $(VM_TIMEOUT=20 $VM "tail -3 /root/cmp/suite-$t-$m.out")"; return 1
	done
	c=$(VM_TIMEOUT=20 $VM "grep '^$t $m complaints' /root/cmp/complaints.txt | tail -1")
	log "suite $t $m done: $c"
	case "$c" in *" complaints 0") return 0;; esac
	return 1
}

$VM "mkdir -p /root/cmp"
for step in "$@"; do
	IFS=: read -r k modes t <<< "$step"
	log "step $t: boot $k"
	boot $k || exit 1
	for m in ${modes//,/ }; do
		suite $m $t || exit 1
	done
done
log DRIVE_DONE
