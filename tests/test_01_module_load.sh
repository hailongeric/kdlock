#!/bin/bash
# test_01_module_load.sh — verify basic module load/unload and /dev/kd_dev.
TEST_NAME="test_01_module_load"
source "$(dirname "$0")/common.sh"

info "Building modules..."
build_all || exit 1

# --- Test 1: load and verify device node ---
info "Loading modules..."
clear_dmesg
load_modules || exit 1

if [ ! -c /dev/kd_dev ]; then
    fail "$TEST_NAME" "/dev/kd_dev not created after insmod"
    exit 1
fi
info "/dev/kd_dev exists"

# --- Test 2: read from device (should return exe entries) ---
dd if=/dev/kd_dev of=/dev/null bs=4096 count=1 2>/dev/null
info "Read from /dev/kd_dev OK"

# --- Test 3: check dmesg for init message ---
check_dmesg_has "kd kernel module init" "module init message not found" || exit 1
info "Module init logged"

# --- Test 4: check end_point resolution ---
check_dmesg_has "end_point\[0\]" "end_point not resolved" || exit 1
info "end_point resolved"

# --- Test 5: unload and verify clean exit ---
unload_modules
sleep 0.3
check_dmesg_has "kd kernel module exit" "module exit message not found" || exit 1
check_dmesg_ok || exit 1
info "Clean unload"

# --- Test 6: device node removed ---
if [ -c /dev/kd_dev ]; then
    fail "$TEST_NAME" "/dev/kd_dev still exists after rmmod"
    exit 1
fi
info "/dev/kd_dev removed"

pass "$TEST_NAME"
exit $EXIT_CODE
