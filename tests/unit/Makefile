# Guest userspace unit programs only: production C, codegen and oracles.
# No target here loads modules; generated-machine-code tests still belong in VM.
CC ?= gcc
PYTHON ?= python3
CFLAGS ?= -g -O0
CFLAGS += -Wall -Wextra -std=gnu11 -I../../include

# Default: two basic C programs. Add only affected Python drivers via PY_TESTS.
BASIC_TESTS := basic/test_control_call basic/test_daemon_policy
TESTS ?= $(BASIC_TESTS)
PY_TESTS ?=
ALL_PY_TESTS := $(sort $(wildcard */test_*.py))

.PHONY: all clean run run-all list

all: $(TESTS)

basic/test_daemon_policy: ../../daemon/daemon.c $(wildcard ../../daemon/*.inc) ../../include/exe_info.h ../../include/kd_learning_api.h ../../include/kd_source_api.h
basic/test_daemon_provenance: ../../daemon/daemon.c $(wildcard ../../daemon/*.inc) ../../include/exe_info.h ../../include/kd_learning_api.h ../../include/kd_source_api.h
basic/test_control_call: ../../include/kd_call.h

basic/test_%: basic/test_%.c
	$(CC) $(CFLAGS) -o $@ $<

# Full runs are opt-in; a plain run never discovers and executes every driver.
run-all:
	$(MAKE) run TESTS='$(BASIC_TESTS)' PY_TESTS='$(ALL_PY_TESTS)'

list:
	@printf '%s\n' $(BASIC_TESTS) $(ALL_PY_TESTS)

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
		if $(PYTHON) run.py "$$t"; then \
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
	rm -f $(BASIC_TESTS) basic/test_daemon_provenance
