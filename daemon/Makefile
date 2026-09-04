CC ?= gcc
CPPFLAGS += -I../include
CFLAGS ?= -O2
CFLAGS += -Wall -Wextra

.PHONY: all clean

all: daemon

daemon: daemon.c ../include/exe_info.h
	$(CC) $(CPPFLAGS) $(CFLAGS) $< -o $@

clean:
	rm -f daemon
