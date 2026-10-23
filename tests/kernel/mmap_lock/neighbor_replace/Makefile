CC ?= gcc
CFLAGS ?= -O2 -Wall -Wextra -Werror
.PHONY: all
all: client-missing client-empty client-zero client-private
client-missing: client.c client.inc ../boundary_edge/client.c
	$(CC) $(CFLAGS) -pthread $< -o $@
client-empty: client.c client.inc ../boundary_edge/client.c
	$(CC) $(CFLAGS) -pthread -DKD_BOUNDARY_EMPTY=1 $< -o $@
client-zero: client.c client.inc ../boundary_edge/client.c
	$(CC) $(CFLAGS) -pthread -DKD_BOUNDARY_ZERO=1 $< -o $@
client-private: client.c client.inc ../boundary_edge/client.c
	$(CC) $(CFLAGS) -pthread -DKD_BOUNDARY_PRIVATE=1 $< -o $@
