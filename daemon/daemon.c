#include <errno.h>
#include <fcntl.h>
#include <stdbool.h>
#include <stdarg.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/stat.h>
#include <sys/types.h>
#include <unistd.h>

#include "exe_info.h"

#define ARRAY_SIZE(x) (sizeof(x) / sizeof((x)[0]))
#define X86_KERNEL_ADDRESS_MIN 0xffff800000000000UL
#define MAX_PAYLOAD 4000

static const char *sys_path = "/dev/kd_dev";

enum daemon_mode {
	MODE_V1 = 1,
	MODE_V2 = 2,
};

struct daemon_config {
	enum daemon_mode mode;
	bool verbose;
	useconds_t poll_us;
};

static unsigned int hash_hist[1000];
static int hash_cnt;

static char *cmd_hist[1000];
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

static int cmd_seen(const char *cmd)
{
	int i;

	for (i = 0; i < cmd_cnt; i++) {
		if (!strcmp(cmd, cmd_hist[i]))
			return 1;
	}
	return 0;
}

static int remember_cmd(const char *cmd)
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
	cmd_cnt++;
	return 0;
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

static int compile_entry(const struct daemon_config *cfg,
			 const struct kd_exe_info *exe)
{
	char cmd[1024];

	if (cfg->mode == MODE_V1) {
		if (format_cmd(
			    cmd, sizeof(cmd),
			    "cd ./%p/ && python3 ../../disassem/disassem.py %d %p",
			    (void *)exe->RIP, exe->pid, (void *)exe->RIP))
			return -1;
	} else {
		if (format_cmd(
			    cmd, sizeof(cmd),
			    "cd ./%p/%d/ && python3 ../../../disassem/disassem.py %d %p",
			    (void *)exe->RIP, exe->tgid, exe->pid,
			    (void *)exe->RIP))
			return -1;
	}
	return run_cmd(cmd, "compile");
}

static ssize_t read_sys(void *buffer, size_t size)
{
	ssize_t len;
	int fd;

	fd = open(sys_path, O_RDONLY);
	if (fd == -1)
		return -errno;
	len = read(fd, buffer, size);
	if (len < 0) {
		perror("read /dev/kd_dev");
		close(fd);
		return len;
	}
	close(fd);
	return len;
}

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
	int fd;

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
	remaining = (size_t)image_size;

	fd = open(sys_path, O_WRONLY);
	if (fd == -1) {
		perror("open /dev/kd_dev for write");
		fclose(fp);
		return -1;
	}

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
			written = write(fd, buffer, packet_size);
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

	close(fd);
	fclose(fp);
	return 0;

error:
	close(fd);
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

		cmd[0] = 0;

		if (exe->status_code == KD_EXE_NORMAL ||
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
			if (!cmd_seen(cmd)) {
				if (cfg->verbose)
					printf(" Compiling");
				if (run_cmd(cmd, "workspace update")) {
					if (cfg->verbose)
						printf("\n");
					continue;
				}
				if (compile_entry(cfg, exe)) {
					if (cfg->verbose)
						printf("\n");
					continue;
				}
				if (remember_cmd(cmd)) {
					if (cfg->verbose)
						printf("\n");
					continue;
				}
			} else if (cfg->verbose) {
				printf(" Compile saved");
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
		"Usage: %s [--mode 1|2] [--quiet|--verbose] [--poll-us N]\n"
		"\n"
		"  --mode 1     use flat layout: ./<RIP>/\n"
		"  --mode 2     use per-tgid layout: ./<RIP>/<tgid>/ (default)\n"
		"  --quiet      suppress normal progress logs\n"
		"  --verbose    print normal progress logs\n"
		"  --poll-us N  polling interval in microseconds, default 100000\n",
		prog);
}

static int parse_args(int argc, char **argv, struct daemon_config *cfg)
{
	for (int i = 1; i < argc; i++) {
		if (!strcmp(argv[i], "--mode") || !strcmp(argv[i], "-m")) {
			if (++i >= argc)
				return -1;
			if (!strcmp(argv[i], "1") || !strcmp(argv[i], "v1"))
				cfg->mode = MODE_V1;
			else if (!strcmp(argv[i], "2") ||
				 !strcmp(argv[i], "v2"))
				cfg->mode = MODE_V2;
			else
				return -1;
		} else if (!strcmp(argv[i], "--quiet") ||
			   !strcmp(argv[i], "-q")) {
			cfg->verbose = false;
		} else if (!strcmp(argv[i], "--verbose") ||
			   !strcmp(argv[i], "-v")) {
			cfg->verbose = true;
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

	if (run_cmd("rm -rf -- 0x*", "workspace cleanup"))
		return EXIT_FAILURE;
	while (1) {
		check_once(&cfg);
		usleep(cfg.poll_us);
	}
}
