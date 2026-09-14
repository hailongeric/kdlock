# Guest userspace unit programs only: production C, codegen and oracles.
# No target here loads modules; generated-machine-code tests still belong in VM.
CC ?= gcc
PYTHON ?= python3
CFLAGS ?= -g -O0
CFLAGS += -Wall -Wextra -std=gnu11 -I../../include

TESTS := \
	test_control_call \
	test_daemon_policy
# Override TESTS and PY_TESTS on the command line for an affected-only run.
# Keep the full inventory here for initial acceptance and explicit full runs.
# Production tail/node/routing, frame/ledger and CALL policy fixtures below
# replace copied models; select those drivers when their underlying code changes.
PY_TESTS := \
	test_hostcall_codegen.py \
	test_segment_codegen.py \
	test_jit_diagnostics.py \
	test_context_policy.py \
	test_spin_shadow.py \
	test_cs_oracle.py \
	test_benchmark.py \
	test_text_regions.py \
	test_spin_gate.py \
	test_spin_entry.py \
	test_spin_routing.py \
	test_mutex_signal_protocol.py \
	test_native_ooo_protocol.py \
	test_native_after_outer.py \
	test_hotlock_sampling.py \
	test_mutex_outer_progress.py \
	test_spin_outer_progress.py \
	test_remote_outer.py \
	test_remote_outer_protocol.py \
	test_remote_depth_protocol.py \
	test_remote_deferred_protocol.py \
	test_spin_frame_protocol.py \
	test_exec_capacity.py \
	test_spin_node_protocol.py \
	test_kernel_baseline.py \
	test_native_registers.py \
	test_jit_body_witness.py \
	test_context_spill_audit.py \
	test_context_memory.py \
	test_context_guards.py \
	test_jit_entry_scope.py \
	test_exe_registry.py \
	test_source_lifetime.py \
	test_source_depth_protocol.py \
	test_mutex_resources.py \
	test_mutex_parallel_protocol.py \
	test_mutex_stack_protocol.py \
	test_regression.py

.PHONY: all clean run

all: $(TESTS)

test_daemon_policy: ../../daemon/daemon.c ../../include/exe_info.h
test_control_call: ../../include/kd_call.h

test_%: test_%.c
	$(CC) $(CFLAGS) -o $@ $<

run: $(TESTS)
	@passed=0; failed=0; \
	for t in $(TESTS); do \
		echo ""; \
		if ./$$t; then \
			passed=$$((passed + 1)); \
		else \
			failed=$$((failed + 1)); \
		fi; \
	done; \
	for t in $(PY_TESTS); do \
		echo ""; \
		if $(PYTHON) ./$$t; then \
			passed=$$((passed + 1)); \
		else \
			failed=$$((failed + 1)); \
		fi; \
	done; \
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "Unit tests: $$passed passed, $$failed failed"; \
	if [ $$failed -gt 0 ]; then exit 1; fi

clean:
	rm -f $(TESTS)
