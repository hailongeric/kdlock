/* One device session bridges registry snapshots to Python translation/upload.
 * Workspace mode controls paths only, not spin/mutex benchmark mode. A compile
 * result of 2 is policy-native-only; launch/I/O errors must remain retry errors.
 * Source leases survive compiler children, while code publication still lacks
 * immutable generations. Use drained learning waves for manual experiments. */
#include <errno.h>
#include <fcntl.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>

#include "exe_info.h"

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define X86_KERNEL_ADDRESS_MIN 0xffff800000000000UL
#define MAX_PAYLOAD 4000
#define TRANSLATOR_NATIVE_ONLY 2

static const char *sys_path = "/dev/kd_dev";
/* One provider reference binds cached artifacts to this daemon session. Never
 * reopen after an I/O error: a new device could belong to a different module. */
static int sys_fd = -1;

enum daemon_mode {
	MODE_V1 = 1,
	MODE_V2 = 2,
};

struct daemon_config {
	enum daemon_mode mode;
	bool verbose;
	bool metrics;
	useconds_t poll_us;
};

static unsigned int hash_hist[1000];
static int hash_cnt;

static char *cmd_hist[1000];
static int cmd_results[1000];
static int cmd_cnt;

#include "workspace.inc"

#include "compiler.inc"

#include "publication.inc"

static int valid_address(unsigned long addr)
{
	return addr >= X86_KERNEL_ADDRESS_MIN;
}

static inline unsigned int hash2(unsigned int pid, unsigned long ip)
{
	return (((unsigned int)ip ^ 1674567091) + (pid ^ 569809));
}

static inline unsigned int hash3(unsigned long a, unsigned long b,
				 unsigned long c)
{
	unsigned long hash_value = a + b + c;

	return (unsigned int)hash_value;
}

static void log_status(const struct daemon_config *cfg,
		       const struct kd_exe_info *exe, const char *msg)
{
	if (cfg->verbose)
		printf("%5d %p %s", exe->pid, (void *)exe->RIP, msg);
}

/* Poll, classify status, update learned targets, compile, then publish. A miss
 * informs future images; this daemon never resumes a waiter already native. */
static void check_once(const struct daemon_config *cfg)
{
	static struct kd_exe_info entries[KD_MAX_EXE];
	const size_t entry_size = sizeof(entries[0]);
	ssize_t len;
	char cmd[1024];
	size_t count;
	size_t i;

	len = read_sys(entries, sizeof(entries));
	if (len <= 0)
		return;
	if ((size_t)len % entry_size) {
		fprintf(stderr, "daemon: malformed kd_dev read: %zd bytes\n",
			len);
		return;
	}

	count = (size_t)len / entry_size;
	for (i = 0; i < count; i++) {
		struct kd_exe_info *exe = &entries[i];
		int result = 0;

		cmd[0] = 0;

		if (exe->status_code == KD_EXE_NATIVE_ONLY ||
		    exe->status_code == KD_EXE_NORMAL ||
		    (cfg->mode == MODE_V1 &&
		     exe->status_code == KD_EXE_INST_LIMIT))
			continue;

		if (exe->status_code == KD_EXE_UNINIT) {
			if (make_init_cmd(cmd, sizeof(cmd), cfg, exe))
				continue;
			log_status(cfg, exe, "Initialization");
		} else if (exe->status_code == KD_EXE_CALL_MISS) {
			if (valid_address(exe->tgt_addr) &&
			    valid_address(exe->RIP)) {
				if (make_callee_cmd(cmd, sizeof(cmd), cfg, exe))
					continue;
				if (cfg->verbose)
					printf("%5d %p Missing Call at: %p",
					       exe->pid, (void *)exe->RIP,
					       (void *)exe->tgt_addr);
			} else if (!hash_history(hash2(exe->pid, exe->RIP))) {
				printf("KD_EXE_CALL_MISS invalid address %p %p\n",
				       (void *)exe->tgt_addr, (void *)exe->RIP);
			}
		} else if (exe->status_code == KD_EXE_IJ_MISS) {
			if (valid_address(exe->jump_from) &&
			    valid_address(exe->tgt_addr) &&
			    valid_address(exe->RIP)) {
				if (make_ij_cmd(cmd, sizeof(cmd), cfg, exe))
					continue;
				if (cfg->verbose)
					printf("%5d %p Indirect Jump at %p %p",
					       exe->pid, (void *)exe->RIP,
					       (void *)exe->jump_from,
					       (void *)exe->tgt_addr);
			} else if (!hash_history(hash3(exe->pid, exe->jump_from,
						       exe->RIP))) {
				printf("KD_EXE_IJ_MISS invalid address %p %p %p\n",
				       (void *)exe->jump_from,
				       (void *)exe->tgt_addr, (void *)exe->RIP);
			}
		} else {
			printf("%5d %p Unrecognized Code %d", exe->pid,
			       (void *)exe->RIP, exe->status_code);
			continue;
		}

		if (cmd[0]) {
			if (!cmd_seen(cmd, &result)) {
				if (cfg->verbose)
					printf(" Compiling");
				if (run_cmd(cmd, "workspace update")) {
					if (cfg->verbose)
						printf("\n");
					continue;
				}
				result = compile_entry(cfg, exe);
				if (result < 0) {
					if (cfg->verbose)
						printf("\n");
					continue;
				}
				if (remember_cmd(cmd, result)) {
					if (cfg->verbose)
						printf("\n");
					continue;
				}
			} else if (cfg->verbose) {
				printf(" Compile saved");
			}

			if (result == TRANSLATOR_NATIVE_ONLY) {
				if (!write_native_only(exe))
					fprintf(stderr,
						"daemon: native-only pid=%d entry=0x%lx\n",
						exe->pid, exe->RIP);
				continue;
			}
			if (write_sys(cfg, exe)) {
				if (cfg->verbose)
					printf("\n");
				continue;
			}
			if (cfg->verbose)
				printf("\n");
		}
	}
}

static void usage(const char *prog)
{
	fprintf(stderr,
		"Usage: %s [--mode flat|per-tgid|1|2|v1|v2] [--quiet|--verbose] "
		"[--poll-us N] [--metrics]\n"
		"\n"
		"  --mode flat     use flat layout: ./<RIP>/\n"
		"  --mode per-tgid use per-tgid layout: ./<RIP>/<tgid>/ (default)\n"
		"  --mode 1|v1    legacy alias for flat layout\n"
		"  --mode 2|v2    legacy alias for per-tgid layout\n"
		"  --quiet      suppress normal progress logs\n"
		"  --verbose    print normal progress logs\n"
		"  --metrics    record translator child wall/CPU/RSS to stderr\n"
		"  --poll-us N  polling interval in microseconds, default 100000\n",
		prog);
}

static int parse_args(int argc, char **argv, struct daemon_config *cfg)
{
	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--mode") || !strcmp(argv[i], "-m")) {
			if (++i >= argc)
				return -1;
			if (!strcmp(argv[i], "flat") ||
			    !strcmp(argv[i], "1") ||
			    !strcmp(argv[i], "v1"))
				cfg->mode = MODE_V1;
			else if (!strcmp(argv[i], "2") ||
				 !strcmp(argv[i], "v2") ||
				 !strcmp(argv[i], "per-tgid"))
				cfg->mode = MODE_V2;
			else
				return -1;
		} else if (!strcmp(argv[i], "--quiet") ||
			   !strcmp(argv[i], "-q")) {
			cfg->verbose = false;
		} else if (!strcmp(argv[i], "--verbose") ||
			   !strcmp(argv[i], "-v")) {
			cfg->verbose = true;
		} else if (!strcmp(argv[i], "--metrics")) {
			cfg->metrics = true;
		} else if (!strcmp(argv[i], "--poll-us")) {
			if (++i >= argc)
				return -1;
			cfg->poll_us = (useconds_t)strtoul(argv[i], NULL, 10);
		} else if (!strcmp(argv[i], "--help") ||
			   !strcmp(argv[i], "-h")) {
			usage(argv[0]);
			exit(EXIT_SUCCESS);
		} else {
			return -1;
		}
	}
	return 0;
}

int main(int argc, char **argv)
{
	struct daemon_config cfg = {
		.mode = MODE_V2,
		.verbose = true,
		.poll_us = 100 * 1000,
	};

	if (parse_args(argc, argv, &cfg)) {
		usage(argv[0]);
		return EXIT_FAILURE;
	}

	/* The device fops owner keeps this provider resident until the parent and
	 * any translating children exit. This does not pin source text or protect
	 * independent guest hook readers; those lifetimes need their own protocol. */
	sys_fd = open(sys_path, O_RDWR | O_CLOEXEC);
	if (sys_fd < 0) {
		perror("open /dev/kd_dev session");
		return EXIT_FAILURE;
	}
	if (run_cmd("rm -rf -- 0x*", "workspace cleanup")) {
		close(sys_fd);
		sys_fd = -1;
		return EXIT_FAILURE;
	}
	while (1) {
		check_once(&cfg);
		usleep(cfg.poll_us);
	}
}
