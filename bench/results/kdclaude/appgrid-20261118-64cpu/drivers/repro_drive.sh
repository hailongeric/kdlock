#!/bin/bash
# repro_drive.sh NAME VDOWN XCHG FUNC...: run on 380G10. Force-restarts the
# guest into kdall10 (a hung exit cannot shut down), runs
# repro_variant.sh there and prints its result.
VM=${VM:?vm helper}
U=aa0bde06-47f6-4049-aaaf-13d052e53961
R=/root/host_fs/kdlock/bench/results/kdclaude/appgrid-20261118-64cpu
VM_TIMEOUT=30 $VM "sync; grub-reboot 'gnulinux-advanced-$U>gnulinux-7.0.0-38-kdall10-advanced-$U'" || exit 1
ssh -o ConnectTimeout=8 eric@10.176.26.71 'echo quit | nc -U -N /tmp/qemu-claude-monitor.sock > /dev/null; sleep 8; /home/eric/vm/qemu-scripts/run_claude_vm.sh start > /tmp/claude-vm-start.log 2>&1; sleep 20; /home/eric/vm/qemu-scripts/run_claude_vm.sh pin >> /tmp/claude-vm-start.log 2>&1'
for i in $(seq 60); do r=$(VM_TIMEOUT=8 $VM 'uname -r' 2>/dev/null) && break; sleep 5; done
[ "$r" = "7.0.0-38-kdall10" ] || { echo "booted $r"; exit 1; }
sleep 15
VM_TIMEOUT=30 $VM "setsid nohup bash $R/repro_variant.sh $* > /dev/null 2>&1 < /dev/null &"
for i in $(seq 120); do
	sleep 10
	VM_TIMEOUT=15 $VM "grep -qE '^(HUNG|CLEAN)$' /root/appgrid/repro-$1.txt" 2>/dev/null && break
done
VM_TIMEOUT=30 $VM "cat /root/appgrid/repro-$1.txt"
