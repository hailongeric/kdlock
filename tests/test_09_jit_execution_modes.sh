#!/bin/bash
# test_09_jit_execution_modes.sh - require real translated execution for
# modes 0, 1, 2, 3, and 4. Mode 2 additionally requires a complete native
# hostcall exit/execute/resume cycle. Mode 3/4 mutex JIT is recovery-only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

if [ "${KDLOCK_RECOVERY_CONFIRMED:-0}" != "1" ]; then
    echo "[FAIL] test_09_jit_execution_modes: set KDLOCK_RECOVERY_CONFIRMED=1 after confirming a recoverable VM snapshot"
    exit 1
fi

run_mode() {
    local mode="$1"

    echo "------------------------------------------------------------"
    echo "Verifying mode $mode translates and executes JIT code"
    echo "------------------------------------------------------------"
    case "$mode" in
        0|1|2)
            bash "$SCRIPT_DIR/test_04_spinlock.sh" "$mode"
            ;;
        3)
            bash "$SCRIPT_DIR/test_07_mutex_jit.sh"
            ;;
        4)
            bash "$SCRIPT_DIR/test_08_mutex_jit_modes.sh" 4
            ;;
        *)
            echo "[FAIL] test_09_jit_execution_modes: unsupported mode $mode"
            return 1
            ;;
    esac
    echo "[PASS] mode $mode: translated instructions executed"
}

if [ "$#" -eq 0 ]; then
    set -- 0 1 2 3 4
fi

for mode in "$@"; do
    run_mode "$mode"
done

echo "[PASS] test_09_jit_execution_modes"
