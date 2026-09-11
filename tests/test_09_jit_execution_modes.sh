#!/bin/bash
# test_09_jit_execution_modes.sh - require real translated execution for
# modes 0 through 5. GS-context modes 10 and 11 require native-only rejection.
# Modes 2 and 5 additionally
# require complete native hostcall cycles. Mutex JIT modes are recovery-only.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# A compatibility entry point must not turn a no-argument invocation into a
# baseline sweep. Use the common read-only catalog until modes are explicit.
if [ "$#" -eq 0 ]; then
    exec bash "$SCRIPT_DIR/run_all.sh" --list
fi

# Validate the whole request before loading anything and keep first-use order.
# Deduplicate only identical modes; an explicitly requested diagnostic still
# runs even if another requested mode covers its ordinary success path.
declare -A seen=()
modes=()
for mode in "$@"; do
    case "$mode" in
        0|1|2|3|4|5|10|11) ;;
        *)
            echo "[FAIL] test_09_jit_execution_modes: unsupported mode $mode"
            exit 1
            ;;
    esac
    if [ -z "${seen[$mode]:-}" ]; then
        modes+=("$mode")
        seen[$mode]=1
    fi
done

if [ "${KDLOCK_RECOVERY_CONFIRMED:-0}" != "1" ]; then
    echo "[FAIL] test_09_jit_execution_modes: set KDLOCK_RECOVERY_CONFIRMED=1 after confirming a recoverable VM snapshot"
    exit 1
fi

run_mode() {
    local mode="$1"

    echo "------------------------------------------------------------"
    echo "Verifying mode $mode admission and execution"
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
        5)
            bash "$SCRIPT_DIR/test_08_mutex_jit_modes.sh" 5
            ;;
        10|11)
            bash "$SCRIPT_DIR/test_12_context_native_only.sh" "$mode"
            echo "[PASS] mode $mode: native-only rejection and native execution"
            return
            ;;
        *)
            echo "[FAIL] test_09_jit_execution_modes: unsupported mode $mode"
            return 1
            ;;
    esac
    echo "[PASS] mode $mode: translated instructions executed"
}

for mode in "${modes[@]}"; do
    run_mode "$mode"
done

echo "[PASS] test_09_jit_execution_modes"
