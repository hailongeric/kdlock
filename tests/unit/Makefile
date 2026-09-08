CC ?= gcc
PYTHON ?= python3
CFLAGS ?= -g -O0
CFLAGS += -Wall -Wextra -std=gnu11 -I../../include

TESTS := \
	test_tail_encoding \
	test_mutex_count \
	test_mutex_shadow \
	test_mutex_transition \
	test_jit_call_policy \
	test_exec_frame \
	test_spin_node_count \
	test_control_call \
	test_daemon_policy
PY_TESTS := test_hostcall_codegen.py test_segment_codegen.py test_jit_diagnostics.py test_context_policy.py test_spin_shadow.py test_cs_oracle.py test_text_regions.py test_spin_gate.py test_spin_entry.py test_spin_routing.py test_mutex_signal_protocol.py test_native_ooo_protocol.py test_native_after_outer.py test_hotlock_sampling.py test_mutex_outer_progress.py test_spin_outer_progress.py test_remote_outer.py test_remote_outer_protocol.py
PY_TESTS += test_remote_depth_protocol.py
PY_TESTS += test_remote_deferred_protocol.py
PY_TESTS += test_spin_frame_protocol.py
PY_TESTS += test_exec_capacity.py
PY_TESTS += test_spin_node_protocol.py
PY_TESTS += test_kernel_baseline.py
PY_TESTS += test_native_registers.py
PY_TESTS += test_jit_body_witness.py
PY_TESTS += test_context_spill_audit.py
PY_TESTS += test_context_memory.py
PY_TESTS += test_context_guards.py
PY_TESTS += test_jit_entry_scope.py
PY_TESTS += test_exe_registry.py

.PHONY: all clean run

all: $(TESTS)

test_daemon_policy: ../../daemon/daemon.c ../../include/exe_info.h
test_control_call: ../../include/kd_call.h

test_%: test_%.c mock_kernel.h test_harness.h
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
