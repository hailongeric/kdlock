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

static int format_cmd(char *cmd, size_t size, const char *fmt, ...)
{
	va_list ap;
	int ret;

	va_start(ap, fmt);
	ret = vsnprintf(cmd, size, fmt, ap);
	va_end(ap);

	if (ret < 0 || (size_t)ret >= size) {
		fprintf(stderr, "daemon: command buffer overflow\n");
		return -1;
	}
	return 0;
}

static int cmd_seen(const char *cmd, int *result)
{
	int i;

	for (i = 0; i < cmd_cnt; i++) {
		if (!strcmp(cmd, cmd_hist[i])) {
			*result = cmd_results[i];
			return 1;
		}
	}
	return 0;
}

static int remember_cmd(const char *cmd, int result)
{
	if (cmd_cnt >= (int)ARRAY_SIZE(cmd_hist)) {
		fprintf(stderr, "daemon: command history is full\n");
		return -1;
	}
	cmd_hist[cmd_cnt] = malloc(strlen(cmd) + 1);
	if (!cmd_hist[cmd_cnt]) {
		perror("malloc");
		exit(EXIT_FAILURE);
	}
	strcpy(cmd_hist[cmd_cnt], cmd);
	cmd_results[cmd_cnt] = result;
	cmd_cnt++;
	return 0;
}

static int compile_result(int status)
{
	if (status >= 0 && WIFEXITED(status)) {
		int code = WEXITSTATUS(status);

		if (code == 0 || code == TRANSLATOR_NATIVE_ONLY)
			return code;
	}
	return -1;
}

static int run_cmd(const char *cmd, const char *label)
{
	int ret = system(cmd);

	if (ret) {
		fprintf(stderr, "daemon: %s command failed (%d): %s\n", label,
			ret, cmd);
		return -1;
	}
	return 0;
}

static int hash_history(unsigned int hash)
{
	int i;

	for (i = 0; i < hash_cnt; i++) {
		if (hash == hash_hist[i])
			return 1;
	}
	if (hash_cnt >= (int)ARRAY_SIZE(hash_hist))
		return 1;
	hash_hist[hash_cnt++] = hash;
	return 0;
}

static void workspace_path(char *buf, size_t size,
			   const struct daemon_config *cfg,
			   const struct kd_exe_info *exe)
{
	if (cfg->mode == MODE_V1)
		snprintf(buf, size, "./%p", (void *)exe->RIP);
	else
		snprintf(buf, size, "./%p/%d", (void *)exe->RIP, exe->tgid);
}

static int make_init_cmd(char *cmd, size_t size,
			 const struct daemon_config *cfg,
			 const struct kd_exe_info *exe)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	return format_cmd(cmd, size,
			  "mkdir -p %s/asm && "
			  ": > %s/asm/callee_table.txt && "
			  ": > %s/asm/ij_table.txt",
			  workspace, workspace, workspace);
}

static int make_callee_cmd(char *cmd, size_t size,
			   const struct daemon_config *cfg,
			   const struct kd_exe_info *exe)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	return format_cmd(
		cmd, size,
		"mkdir -p %s/asm && touch %s/asm/ij_table.txt && echo %p >> %s/asm/callee_table.txt",
		workspace, workspace, (void *)exe->tgt_addr, workspace);
}

static int make_ij_cmd(char *cmd, size_t size, const struct daemon_config *cfg,
		       const struct kd_exe_info *exe)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	return format_cmd(
		cmd, size,
		"mkdir -p %s/asm && touch %s/asm/callee_table.txt && echo '%p %p' >> %s/asm/ij_table.txt",
		workspace, workspace, (void *)exe->jump_from,
		(void *)exe->tgt_addr, workspace);
}

/* Share CLOCK_MONOTONIC with the paired observer, without wall-clock jumps. */
static int monotonic_ns(uint64_t *value)
{
	struct timespec now;

	if (clock_gettime(CLOCK_MONOTONIC, &now) || now.tv_sec < 0 ||
	    now.tv_nsec < 0 || now.tv_nsec >= 1000000000L ||
	    (uint64_t)now.tv_sec > (UINT64_MAX - now.tv_nsec) / 1000000000) {
		fprintf(stderr, "daemon: invalid translation monotonic clock\n");
		return -1;
	}
	*value = (uint64_t)now.tv_sec * 1000000000 + now.tv_nsec;
	return 0;
}

/* Keep the kernel's microsecond CPU resolution; reject invalid/overflowed
 * counters instead of publishing a plausible but wrapped duration. */
static int usage_ns(struct timeval value, uint64_t *result)
{
	if (value.tv_sec < 0 || value.tv_usec < 0 || value.tv_usec >= 1000000 ||
	    (uint64_t)value.tv_sec >
		    (UINT64_MAX - (uint64_t)value.tv_usec * 1000) / 1000000000)
		return -1;
	*result = (uint64_t)value.tv_sec * 1000000000 + value.tv_usec * 1000;
	return 0;
}

/* wait4 accounts for this translator and its reaped compiler descendants,
 * not daemon polling, workspace setup, upload, or kernel JIT execution. RSS
 * is Linux's largest-process high-water mark, never a summed memory peak.
 * Emit failed/refused child results too; do not select only successes. */
static int report_translation(const struct kd_exe_info *exe, pid_t child,
			      int status, int result, uint64_t start,
			      uint64_t end, const struct rusage *usage)
{
	uint64_t user, system;

	if (end <= start || usage_ns(usage->ru_utime, &user) ||
	    usage_ns(usage->ru_stime, &system) || usage->ru_maxrss < 0 ||
	    usage->ru_minflt < 0 || usage->ru_majflt < 0 ||
	    usage->ru_nvcsw < 0 || usage->ru_nivcsw < 0) {
		fprintf(stderr, "daemon: invalid translation resource record\n");
		return -1;
	}
	return fprintf(stderr,
		       "KD_TRANSLATION_METRICS {\"schema\":1,\"pid\":%d,\"tgid\":%d,"
		       "\"entry\":\"0x%lx\",\"lock_kind\":%d,\"child\":%d,"
		       "\"started_ns\":%" PRIu64 ",\"finished_ns\":%" PRIu64 ","
		       "\"wall_ns\":%" PRIu64 ",\"user_ns\":%" PRIu64 ","
		       "\"system_ns\":%" PRIu64 ",\"maxrss_kib\":%ld,"
		       "\"minor_faults\":%ld,\"major_faults\":%ld,"
		       "\"voluntary_cs\":%ld,\"involuntary_cs\":%ld,"
		       "\"status\":%d,\"result\":%d}\n",
		       exe->pid, exe->tgid, exe->RIP, exe->lock_kind, child,
		       start, end, end - start, user, system, usage->ru_maxrss,
		       usage->ru_minflt, usage->ru_majflt, usage->ru_nvcsw,
		       usage->ru_nivcsw, status, result) < 0 ? -1 : 0;
}

/* Only the translator child inherits the writer description. It must not
 * reopen a different provider if inheritance or capability checks fail. */
static int compile_entry(const struct daemon_config *cfg,
			 const struct kd_exe_info *exe)
{
	/* Direct Python file-open errors and shell cd failures also exit 2.
	 * runpy makes a missing script an ordinary exception (exit 1), so only
	 * the translator's deliberate exit 2 means policy rejection. */
	static const char bootstrap[] =
		"import os, runpy, sys; script = sys.argv.pop(1); "
		"sys.path.insert(0, os.path.dirname(script)); "
		"runpy.run_path(script, run_name='__main__')";
	const char *script = cfg->mode == MODE_V1 ?
				     "../../disassem/disassem.py" :
				     "../../../disassem/disassem.py";
	const char *abi = exe->entry_abi == KD_ENTRY_ABI_SPIN_CLOBBER_V1 ? "1" :
			  exe->entry_abi == KD_ENTRY_ABI_MUTEX_CLOBBER_V1 ? "2" :
			  exe->entry_abi == KD_ENTRY_ABI_LEGACY ? "0" : "invalid";
	const char *kind = exe->lock_kind == KD_EXE_LOCK_SPIN  ? "spin" :
			   exe->lock_kind == KD_EXE_LOCK_MUTEX ? "mutex" :
								 "unknown";
	char workspace[256], pid_text[32], rip_text[32], fd_text[32];
	struct rusage usage;
	uint64_t started = 0, finished;
	pid_t child, waited;
	int status, result;

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	snprintf(pid_text, sizeof(pid_text), "%d", exe->pid);
	snprintf(rip_text, sizeof(rip_text), "%p", (void *)exe->RIP);
	snprintf(fd_text, sizeof(fd_text), "%d", sys_fd);
	/* Opt-in observation starts before fork and ends after reaping. A broken
	 * clock is an experiment/launch error, never a native-only CS verdict. */
	if (cfg->metrics && monotonic_ns(&started))
		return -1;
	child = fork();
	if (child < 0) {
		perror("fork translator");
		return -1;
	}
	if (!child) {
		/* Only the translator inherits the session. Workspace shell commands
		 * retain CLOEXEC; an orphaned translator must keep its provider alive. */
		if (fcntl(sys_fd, F_SETFD, 0) < 0 ||
		    setenv("KD_DEVICE_FD", fd_text, 1)) {
			perror("inherit translator device session");
			_exit(126);
		}
		if (chdir(workspace)) {
			perror("chdir translator workspace");
			_exit(126);
		}
		execlp("python3", "python3", "-c", bootstrap, script, pid_text,
		       rip_text, kind, abi, (char *)NULL);
		perror("exec translator");
		_exit(127);
	}
	do {
		waited = cfg->metrics ? wait4(child, &status, 0, &usage) :
				       waitpid(child, &status, 0);
	} while (waited < 0 && errno == EINTR);
	if (waited < 0) {
		perror("wait translator");
		return -1;
	}
	result = compile_result(status);
	if (cfg->metrics &&
	    (monotonic_ns(&finished) ||
	     report_translation(exe, child, status, result, started, finished,
				&usage)))
		return -1;
	if (result < 0)
		fprintf(stderr,
			"daemon: translator failed: workspace=%s status=%d\n",
			workspace, status);
	return result;
}

static int write_native_only(const struct kd_exe_info *exe)
{
	const struct kd_recv_pkt pkt = {
		.status_code = KD_EXE_NATIVE_ONLY,
		.pid = exe->pid,
		.RIP = exe->RIP,
		.offset = 0,
	};
	ssize_t written;

	do {
		written = write(sys_fd, &pkt, sizeof(pkt));
	} while (written < 0 && errno == EINTR);
	if (written != sizeof(pkt)) {
		fprintf(stderr,
			"daemon: native-only status write failed: %zd\n",
			written);
		return -1;
	}
	return 0;
}

static ssize_t read_sys(void *buffer, size_t size)
{
	ssize_t len;

	do {
		len = read(sys_fd, buffer, size);
	} while (len < 0 && errno == EINTR);
	if (len < 0) {
		int error = errno;

		perror("read /dev/kd_dev");
		return -error;
	}
	return len;
}

/* Transfer bounded payload chunks on the original device. Final status marks
 * readiness, not protection for an executor of a previous in-place image. */
static int write_sys(const struct daemon_config *cfg,
		     const struct kd_exe_info *exe)
{
	unsigned char buffer[sizeof(struct kd_recv_pkt) + MAX_PAYLOAD];
	struct kd_recv_pkt pkt;
	char jit_path[512];
	char workspace[256];
	size_t remaining;
	long image_size;
	FILE *fp;

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	snprintf(jit_path, sizeof(jit_path), "%s/asm/jit.bin", workspace);

	fp = fopen(jit_path, "rb");
	if (!fp) {
		fprintf(stderr, "daemon: failed to open %s: %s\n", jit_path,
			strerror(errno));
		return -1;
	}
	if (fseek(fp, 0, SEEK_END)) {
		fprintf(stderr, "daemon: failed to seek %s\n", jit_path);
		fclose(fp);
		return -1;
	}
	image_size = ftell(fp);
	if (image_size <= 0 || (unsigned long)image_size > KD_CODE_BLOCK_SIZE ||
	    fseek(fp, 0, SEEK_SET)) {
		fprintf(stderr, "daemon: invalid JIT image size for %s\n",
			jit_path);
		fclose(fp);
		return -1;
	}
	{
		unsigned char header[46];
		bool directory;

		if (fread(header, 1, sizeof(header), fp) != sizeof(header)) {
			fclose(fp);
			return -1;
		}
		directory = !memcmp(header + 25, "KDWC001", 7) &&
		            !memcmp(header + 41, "KDAB", 4);
		if (!kd_entry_abi_valid(exe->lock_kind, exe->entry_abi) ||
		    (kd_entry_abi_clobber(exe->entry_abi) && !directory) ||
		    (directory && header[45] != exe->entry_abi) || fseek(fp, 0, SEEK_SET)) {
			fprintf(stderr, "daemon: JIT entry ABI mismatch\n");
			fclose(fp);
			return -1;
		}
	}
	remaining = (size_t)image_size;

	pkt.pid = exe->pid;
	pkt.RIP = exe->RIP;
	pkt.offset = 0;

	while (remaining) {
		size_t chunk = remaining < MAX_PAYLOAD ? remaining :
							 MAX_PAYLOAD;
		size_t packet_size = sizeof(pkt) + chunk;
		ssize_t written;

		if (fread(buffer + sizeof(pkt), 1, chunk, fp) != chunk) {
			fprintf(stderr, "daemon: failed to read %s\n",
				jit_path);
			goto error;
		}
		pkt.status_code = remaining == chunk ? KD_EXE_NORMAL :
						       KD_EXE_UNINIT;
		memcpy(buffer, &pkt, sizeof(pkt));

		do {
			written = write(sys_fd, buffer, packet_size);
		} while (written < 0 && errno == EINTR);
		if (written != (ssize_t)packet_size) {
			if (written < 0)
				perror("write /dev/kd_dev");
			else
				fprintf(stderr,
					"daemon: short device write: %zd of %zu bytes\n",
					written, packet_size);
			goto error;
		}

		remaining -= chunk;
		pkt.offset += chunk;
	}

	fclose(fp);
	return 0;

error:
	fclose(fp);
	return -1;
}

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
