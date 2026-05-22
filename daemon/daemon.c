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

static const char *sys_path = "/dev/kd_dev";
static const int max_payload = 4000;

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

static int append_cmd(char *cmd, size_t size, const char *fmt, ...)
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

static int cmd_history(const char *cmd)
{
	int i;

	for (i = 0; i < cmd_cnt; i++) {
		if (!strcmp(cmd, cmd_hist[i]))
			return 1;
	}
	if (cmd_cnt >= (int)ARRAY_SIZE(cmd_hist)) {
		fprintf(stderr, "daemon: command history is full\n");
		return 1;
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

static void workspace_path(char *buf, size_t size, const struct daemon_config *cfg,
			   const struct exe_info *exe)
{
	if (cfg->mode == MODE_V1)
		snprintf(buf, size, "./%p", (void *)exe->RIP);
	else
		snprintf(buf, size, "./%p/%d", (void *)exe->RIP, exe->tgid);
}

static int make_init_cmd(char *cmd, size_t size, const struct daemon_config *cfg,
			 const struct exe_info *exe)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	return append_cmd(cmd, size, "mkdir -p %s && cp -rf ./asm/ %s/",
			  workspace, workspace);
}

static int make_callee_cmd(char *cmd, size_t size, const struct daemon_config *cfg,
			   const struct exe_info *exe)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	return append_cmd(cmd, size, "echo %p >> %s/asm/callee_table.txt",
			  (void *)exe->tgt_addr, workspace);
}

static int make_ij_cmd(char *cmd, size_t size, const struct daemon_config *cfg,
		       const struct exe_info *exe)
{
	char workspace[256];

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	return append_cmd(cmd, size, "echo '%p %p' >> %s/asm/ij_table.txt",
			  (void *)exe->jump_from, (void *)exe->tgt_addr, workspace);
}

static int compile_entry(const struct daemon_config *cfg, const struct exe_info *exe)
{
	char cmd[1024];

	if (cfg->mode == MODE_V1) {
		if (append_cmd(cmd, sizeof(cmd),
			       "cd ./%p/ && python3 ../../disassem/disassem.py %d %p",
			       (void *)exe->RIP, exe->pid, (void *)exe->RIP))
			return -1;
	} else {
		if (append_cmd(cmd, sizeof(cmd),
			       "cd ./%p/%d/ && python3 ../../../disassem/disassem.py %d %p",
			       (void *)exe->RIP, exe->tgid, exe->pid, (void *)exe->RIP))
			return -1;
	}
	return system(cmd);
}

static int read_sys(char *buffer, size_t size)
{
	int fd = -1;
	int len;

	while (fd == -1)
		fd = open(sys_path, O_RDONLY);
	len = read(fd, buffer, size);
	if (len < 0) {
		perror("read /dev/kd_dev");
		close(fd);
		return len;
	}
	close(fd);
	return len;
}

static int write_sys(const struct daemon_config *cfg, const struct exe_info *exe)
{
	int rest_len;
	int to_copy_len;
	char i_buf[4096 * 256];
	char o_buf[4096 * 2];
	struct recv_pkt pkt;
	char jit_path[512];
	char workspace[256];
	FILE *fp;

	workspace_path(workspace, sizeof(workspace), cfg, exe);
	snprintf(jit_path, sizeof(jit_path), "%s/asm/jit.bin", workspace);

	fp = fopen(jit_path, "rb");
	if (!fp) {
		fprintf(stderr, "daemon: failed to open %s: %s\n", jit_path,
			strerror(errno));
		return -1;
	}
	rest_len = fread(i_buf, 1, sizeof(i_buf), fp);
	fclose(fp);

	pkt.pid = exe->pid;
	pkt.RIP = exe->RIP;
	pkt.offset = 0;

	while (rest_len > 0) {
		fp = fopen(sys_path, "wb");
		if (!fp) {
			perror("open /dev/kd_dev for write");
			return -1;
		}
		pkt.status_code = (rest_len <= max_payload ? 0 : -1);
		to_copy_len = rest_len <= max_payload ? rest_len : max_payload;
		memcpy(o_buf, &pkt, sizeof(pkt));
		memcpy(o_buf + sizeof(pkt), i_buf + pkt.offset, to_copy_len);
		rest_len -= to_copy_len;
		pkt.offset += to_copy_len;
		fwrite(o_buf, 1, sizeof(pkt) + to_copy_len, fp);
		fclose(fp);
	}
	return 0;
}

static int valid_address(unsigned long addr)
{
	static const unsigned long *invalid_addrs;
	static const size_t invalid_addr_count;
	size_t i;

	for (i = 0; i < invalid_addr_count; i++) {
		if (addr == invalid_addrs[i])
			return 0;
	}
	return 1;
}

static inline unsigned int hash2(unsigned int pid, unsigned long ip)
{
	return (((unsigned int)ip ^ 1674567091) + (pid ^ 569809));
}

static inline unsigned long hash3(long a, long b, long c)
{
	unsigned long hash_value = a + b + c;
	return (unsigned int)hash_value;
}

static void log_status(const struct daemon_config *cfg, const struct exe_info *exe,
		       const char *msg)
{
	if (cfg->verbose)
		printf("%5d %p %s", exe->pid, (void *)exe->RIP, msg);
}

static void check_once(const struct daemon_config *cfg)
{
	int len;
	int sz = sizeof(struct exe_info);
	struct exe_info *exe;
	char cmd[1024];
	char buffer[4096 * 256] = {0};
	int begin_pid;
	unsigned long begin_rip;

	len = read_sys(buffer, sizeof(buffer));
	if (len <= 0)
		return;

	exe = (struct exe_info *)buffer;
	begin_pid = exe->pid;
	begin_rip = exe->RIP;

	for (int i = 0; i < len / sz; i++, exe++) {
		cmd[0] = 0;

		if (i > 0 && exe->pid == begin_pid && exe->RIP == begin_rip)
			break;

		if (exe->status_code == F_NORMAL ||
		    (cfg->mode == MODE_V1 && exe->status_code == F_INST_LIMIT))
			continue;

		if (exe->status_code == F_UN_INIT) {
			if (make_init_cmd(cmd, sizeof(cmd), cfg, exe))
				continue;
			log_status(cfg, exe, "Initialization");
		} else if (exe->status_code == F_CALL_MISS) {
			if (valid_address(exe->tgt_addr) && valid_address(exe->RIP)) {
				if (make_callee_cmd(cmd, sizeof(cmd), cfg, exe))
					continue;
				if (cfg->verbose)
					printf("%5d %p Missing Call at: %p",
					       exe->pid, (void *)exe->RIP,
					       (void *)exe->tgt_addr);
			} else if (!hash_history(hash2(exe->pid, exe->RIP))) {
				printf("F_CALL_MISS invalid address %p %p\n",
				       (void *)exe->tgt_addr, (void *)exe->RIP);
			}
		} else if (exe->status_code == F_IJ_MISS) {
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
				printf("F_IJ_MISS invalid address %p %p %p\n",
				       (void *)exe->jump_from, (void *)exe->tgt_addr,
				       (void *)exe->RIP);
			}
		} else {
			printf("%5d %p Unrecognized Code %d", exe->pid,
			       (void *)exe->RIP, exe->status_code);
			continue;
		}

		if (cmd[0] && !cmd_history(cmd)) {
			if (cfg->verbose)
				printf(" Compiling");
			system(cmd);
			if (compile_entry(cfg, exe) == -1)
				break;
		} else if (cmd[0] && cfg->verbose) {
			printf(" Compile saved");
		}

		if (cmd[0]) {
			write_sys(cfg, exe);
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
		"  --mode 1     use legacy daemon1 layout: ./<RIP>/\n"
		"  --mode 2     use legacy daemon2 layout: ./<RIP>/<tgid>/ (default)\n"
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
			else if (!strcmp(argv[i], "2") || !strcmp(argv[i], "v2"))
				cfg->mode = MODE_V2;
			else
				return -1;
		} else if (!strcmp(argv[i], "--quiet") || !strcmp(argv[i], "-q")) {
			cfg->verbose = false;
		} else if (!strcmp(argv[i], "--verbose") || !strcmp(argv[i], "-v")) {
			cfg->verbose = true;
		} else if (!strcmp(argv[i], "--poll-us")) {
			if (++i >= argc)
				return -1;
			cfg->poll_us = (useconds_t)strtoul(argv[i], NULL, 10);
		} else if (!strcmp(argv[i], "--help") || !strcmp(argv[i], "-h")) {
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
		.mode = MODE_V1,
		.verbose = true,
		.poll_us = 100 * 1000,
	};

	if (parse_args(argc, argv, &cfg)) {
		usage(argv[0]);
		return EXIT_FAILURE;
	}

	system("rm -rf 0x*");
	while (1) {
		check_once(&cfg);
		usleep(cfg.poll_us);
	}
}
