#!/bin/bash
# Pipeline diagnostic: promotion, translation and upload without executing JIT.
# Consolidates the former hotlock/daemon smoke cases into one preparation.
TEST_NAME="test_02_jit_engine"
source "$(dirname "$0")/common.sh"

build_all || exit 1
clear_dmesg
load_modules || exit 1

# --- Test 1: end_point dynamic resolution ---
check_dmesg_has "end_point\[0\]" "end_point[0] not resolved" || exit 1
check_dmesg_has "end_point\[1\]" "end_point[1] (mutex_unlock) not resolved" || exit 1
info "end_point resolved for spin_unlock and mutex_unlock"

# --- Test 2: trigger exe_add after hot-lock promotion ---
# kd_hotlock_record() ignores the first 1e9 TSC cycles after the first observed
# lock. Prime that timer before the real workload, otherwise this test can pass
# through the original spinlock path and never allocate an exe entry.
info "Priming hot-lock timer..."
run_with_timeout 10 "$BENCH_BIN" 1 1 1 1 0 >/dev/null 2>&1
sleep 1

info "Running single-thread spinlock workload to trigger exe_add..."
run_with_timeout 20 "$BENCH_BIN" 1 12000 10 1 0 >/dev/null 2>&1
sleep 0.5

check_dmesg_has "exe added" "kd_exe_add was not triggered" || exit 1
check_dmesg_has "begin delegate" "hot-lock promotion did not trigger" || exit 1
info "kd_exe_add triggered"

# --- Test 3: daemon reads kernel text, translates, and writes back ---
info "Starting daemon for translation..."
DAEMON_LOG="$(mktemp /tmp/kdlock-test02-daemon.XXXXXX.log)"
start_daemon 2

# The daemon polls /dev/kd_dev and translates the UNINIT entry created above.
# Do not run the same lock again after write-back here: that would execute the
# translated spinlock critical section and belongs in the spinlock integration
# tests, not this pipeline smoke test.
if ! asm_dir="$(wait_for_jit_artifacts 20)"; then
    fail "$TEST_NAME" "daemon did not produce complete JIT artifacts"
    exit 1
fi

check_daemon_read_kernel_text "$DAEMON_LOG" || exit 1
info "Daemon read kernel text for translation"

check_jit_artifacts "$asm_dir" || exit 1

# File creation precedes device upload. Observe this RIP/TGID becoming NORMAL
# before accepting write-back; a sleep or instantaneous log check races upload.
PYTHONPATH="$KDLOCK_DIR/tests" python3 - "$asm_dir" \
    "${DAEMON_LOG%.log}.published.json" <<'PY'
import json
import sys
from pathlib import Path
from mutex_signal_protocol import wait_ready

Path(sys.argv[2]).write_text(json.dumps(wait_ready(sys.argv[1], lock_kind=1)))
PY
check_dmesg_has "$JIT_INSTALL_PATTERN" "daemon did not write JIT back" || exit 1
info "Daemon wrote JIT binary back to kernel"

stop_daemon
unload_modules

# Artifact validation already proves workspace creation. Check cleanup only
# after callers/daemon are gone and both modules actually unloaded.
if pgrep -x 'klock_test|daemon' >/dev/null ||
    lsmod | grep -E '^(kdlock_km|klock_module) ' >/dev/null; then
    fail "$TEST_NAME" "not drained; retain artifacts for diagnosis"
    exit 1
fi
rm -rf -- "$DAEMON_DIR"/0x*
if compgen -G "$DAEMON_DIR/0x*" >/dev/null; then
    fail "$TEST_NAME" "workspace cleanup failed"
    exit 1
fi
check_dmesg_stat_equals jit_success 0 || exit 1
check_dmesg_not_has 'JIT body witness:.*body=1' || exit 1
check_dmesg_ok || exit 1

pass "$TEST_NAME"
exit "$EXIT_CODE"
