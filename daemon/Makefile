# Build the userspace registry/translator bridge in the guest; no module load.
CC ?= gcc
CPPFLAGS += -I../include
CFLAGS ?= -O2
CFLAGS += -Wall -Wextra

.PHONY: all clean

all: daemon

daemon: daemon.c $(wildcard *.inc) ../include/exe_info.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@

clean:
	rm -f daemon
