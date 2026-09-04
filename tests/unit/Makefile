CC ?= gcc
CFLAGS = -Wall -Wextra -g -O0 -std=gnu11
TESTS = test_tail_encoding test_exe_hash test_hotlock_state test_mutex_count test_mutex_shadow test_mutex_transition test_jit_call_policy test_exec_frame test_spin_node_count

.PHONY: all clean run

all: $(TESTS)

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
	echo ""; \
	echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━"; \
	echo "Unit tests: $$passed passed, $$failed failed"; \
	if [ $$failed -gt 0 ]; then exit 1; fi

clean:
	rm -f $(TESTS)
