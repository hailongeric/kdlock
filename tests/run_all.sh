#!/bin/bash
# run_all.sh — run all kdlock module tests in sequence.
#
# Usage: bash tests/run_all.sh
# Must run inside the VM at /root/host_fs/kdlock
set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PASSED=0
FAILED=0
RESULTS=()

run_test() {
    local script="$1"
    local name
    name=$(basename "$script" .sh)

    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
    echo "Running: $name"
    echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    if bash "$script"; then
        PASSED=$((PASSED + 1))
        RESULTS+=("[PASS] $name")
    else
        FAILED=$((FAILED + 1))
        RESULTS+=("[FAIL] $name")
    fi
    echo ""
}

echo "╔══════════════════════════════════════════════╗"
echo "║         kdlock Test Suite                    ║"
echo "╚══════════════════════════════════════════════╝"
echo ""

run_test "$SCRIPT_DIR/test_01_module_load.sh"
run_test "$SCRIPT_DIR/test_02_jit_engine.sh"
run_test "$SCRIPT_DIR/test_03_hotlock.sh"
run_test "$SCRIPT_DIR/test_04_spinlock.sh"
run_test "$SCRIPT_DIR/test_05_mutex.sh"
run_test "$SCRIPT_DIR/test_06_daemon.sh"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "Summary:"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
for r in "${RESULTS[@]}"; do
    echo "  $r"
done
echo ""
echo "  $PASSED passed, $FAILED failed (total $((PASSED + FAILED)))"

if [ $FAILED -gt 0 ]; then
    exit 1
fi
exit 0
