#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <stdbool.h>
#include <string.h>
#include "exe.h"

#include <sys/types.h>
#include <sys/stat.h>
#include <fcntl.h>

char* sys_path = "/dev/kd_dev";
// char* sys_path = "/sys/kernel/zz_sys/etx_value";


//const unsigned long targets[] = {0x7ffff7fa1abb, 0x7ffff7de6487, 0x7ffff7df274e,  0x7ffff7de4fae, 0x7ffff7fa1437,  0x007ffff7fa76ca, 0x07ffff7ed116a, 0x007ffff7e5232f};
// const unsigned long targets[] = { 0x7ffff7fa7170, 0x7ffff7fa1e8b, 0x7ffff7fa15df, 0x7ffff7fa1f37, 0x7ffff7e58170, 0x7ffff7fa3376, 0x7ffff7e54376, 0x7ffff7e41cd7, 0x7ffff7e4b170, 0x7ffff7e47376, 0x7ffff7d5d95d, 0x7ffff7d5e95d, 0x7ffff7f96376, 0x7ffff7cda5cb, 0x7ffff7fa732f };
// const unsigned long targets[] = { 0x7ffff7fa7170, 0x7ffff7ead95d,0x7ffff7eac95d,0x7ffff7fa15df,0x7ffff7fa1e8b,0x7ffff7fa1f37,0x7ffff7fa2c8e,0x7ffff7fa2ceb };
const unsigned long targets[] = { 0x7ffff7fad170,0x7ffff7fa7170,0x7ffff7e5e170 ,0x7ffff7c7c170,0x7ffff7e5d170,0x7ffff7c7b170 , 0x7ffff7e5a170,0x7ffff7f5f170 ,0x7ffff7f53170,0x7ffff7fa9170,0x7ffff7fa3170,0x7ffff7fbf170,
0x7ffff7fa35df,0x7ffff7fa3f37,0x7ffff7fa3e8b,0x7ffff7fbec5f,0x7ffff7fc3060,
0x7ffff7fc023f,0x7ffff7ebc95d,0x555555555569 ,0x555555555319,0x5555555553db,0x555555555602,0x555555555589 };
// const unsigned long targets[] = { };

//0x7ffff7eb02cf
unsigned long records[1024] = {};
int cnts = 0;

int compile_count = 0;

int in_targets(unsigned long ip, int pid) {
	for (int i = 0;i < sizeof(targets) / sizeof(unsigned long);i++) {
		if (ip == targets[i]) {
			return 1;
		}
	}
	return 0;
}

int in_records(unsigned long ip, int pid) {
	for (int i = 0; i < sizeof(records) / sizeof(unsigned long);i++) {
		if (ip == records[i]) {
			return 1;
		}
	}
	return 0;
}

char* cmd_hist[1000];
unsigned int hash_hist[1000];
int cmd_cnt = 0;
int hash_cnt = 0;
int cmd_history(char* cmd) {
	int i;
	for (i = 0;i < cmd_cnt;i++)
		if (!strcmp(cmd, cmd_hist[i]))
			return 1;
	cmd_hist[i] = malloc(strlen(cmd) + 1);
	strcpy(cmd_hist[i], cmd);
	cmd_cnt++;
	// printf("cmd_cnt %d\n", cmd_cnt);
	return 0;
}

int hash_history(unsigned int hash) {
	int i;
	for (i = 0; i < hash_cnt; i++)
		if (hash == hash_hist[i])
			return 1;
	hash_hist[i] = hash;
	hash_cnt++;
	return 0;
}

int compile(int pid, void* entry) {
	char cmd[1024];
	// const char* pythonPaths =
	//     "/home/szq/.local/lib/python3.8/site-packages:/usr/local/lib/python3.8";
	// setenv("PYTHONPATH", pythonPaths, 1);

	// path to zz_disassem/disassem.py
	sprintf(cmd, "cd ./%p/ && python3 ../../disassem/disassem.py %d %p",
		entry, pid, entry);
	return system(cmd);
}

int read_sys(char* buffer) {
	int len;
	int fp = -1;
	while (fp == -1)
		fp = open(sys_path, O_RDONLY);
	if (fp == -1) {
		puts("Open sysfile Error\n");
		exit(-1);
	}
	// printf("open file success\n");
	len = read(fp, buffer, sizeof(char) * 4096 * 9);
	// if (len > 0)
	// 	printf("read sys len: %d buffer: %lx %lx %lx %lx\n", len, buffer[0], buffer[4], buffer[8], buffer[12]);
	close(fp);
	// printf("close file success\n");
	return len;
}

void write_sys(int pid, unsigned long RIP) {
	int rest_len;
	int to_copy_len;
	char i_buf[4096 * 256];
	char o_buf[4096 * 2];
	struct recv_pkt pkt;
	char jit_path[1024];
	const int max_pay = 4000;

	sprintf(jit_path, "./%p/asm/jit.bin", (void*)RIP);
	FILE* fp = fopen(jit_path, "rb");
	rest_len = fread(i_buf, 1, sizeof(i_buf), fp);
	fclose(fp);
	pkt.pid = pid;
	pkt.RIP = RIP;
	pkt.offset = 0;

	while (rest_len > 0) {
		fp = fopen(sys_path, "wb");
		pkt.status_code = (rest_len <= max_pay ? 0 : -1);
		to_copy_len = rest_len <= max_pay ? rest_len : max_pay;
		memcpy(o_buf, &pkt, sizeof(pkt));
		memcpy(o_buf + sizeof(pkt), i_buf + pkt.offset, to_copy_len);
		rest_len -= to_copy_len;
		pkt.offset += to_copy_len;
		// printf("%d.", pkt.status_code);
		fwrite(o_buf, 1, sizeof(pkt) + to_copy_len, fp);
		fclose(fp);
	}
}

int valid_address(unsigned long addr) {
	long iva[] = {};//,0x555555555420 };
	int length = sizeof(iva) / sizeof(iva[0]);
	for (int i = 0; i < length; i++) {
		if (addr == iva[i]) {
			return 0;
		}
	}
	return 1;
}

static inline unsigned int hash2(unsigned int pid, unsigned long ip) {
	return (((unsigned int)ip ^ 1674567091) + (pid ^ 569809));
}

static inline unsigned long hash3(long a, long b, long c) {
	unsigned long hash_value = a + b + c;
	return (unsigned int)hash_value;
}

void check() {
	int len, total_len, sz = sizeof(struct exe_info);
	struct exe_info* exe;
	FILE* fp;
	char cmd[1024], buffer[4096 * 256] = { 0 };

	// printf("buffer size: %d\n", sizeof(buffer));

	len = read_sys(buffer);
	// printf("read success\n");
	exe = (struct exe_info*)buffer;
	// printf("buffer size: %d\n", sizeof(buffer));

	int begin_pid = exe->pid;
	unsigned long begin_rip = exe->RIP;

	for (int i = 0;i < len / sz;i++, exe++) {
		int is_valid = 1;
		if (i > 0 && exe->pid == begin_pid && exe->RIP == begin_rip)
			break;
		cmd[0] = 0;
		// if (!in_targets(exe->RIP, exe->pid)) {
		// 	if (!in_records(exe->RIP, exe->pid)) {
		// 		printf("#### warning: syscall address %p is not in the white-list, it will not be boosted ####\n", (void*)exe->RIP);
		// 		records[cnts] = (unsigned long)exe->RIP;
		// 		cnts++;
		// 	}
		// 	continue;
		// }

		if (exe->status_code == 0 || exe->status_code == 4) {
			continue;
		}
		if (exe->status_code == F_UN_INIT) {
			sprintf(cmd, "mkdir -p ./%p && cp -rf ./asm/ ./%p/", (void*)exe->RIP, (void*)exe->RIP);
			// sprintf(cmd, "cp -rf ./asm/ ./%p/", (void*)exe->RIP);
			// sprintf(cmd, "echo F_UN_INIT");
			// printf("%5d %p Initialization", exe->pid, (void*)exe->RIP);
		}
		else if (exe->status_code == F_CALL_MISS) {
			if (valid_address(exe->tgt_addr) && valid_address(exe->RIP)) {
				sprintf(cmd, "echo %p >> ./%p/asm/callee_table.txt", (void*)exe->tgt_addr, (void*)exe->RIP);
				// printf("%5d %p Missing Call at: %p", exe->pid, (void*)exe->RIP, (void*)exe->tgt_addr);
			}
			else {
				is_valid = 0;
				if (!hash_history(hash2(exe->pid, exe->RIP))) {
					printf("F_CALL_MISS invalid address %p %p\n", (void*)exe->tgt_addr, (void*)exe->RIP);
				}
			}
		}
		else if (exe->status_code == F_IJ_MISS) {
			if (valid_address(exe->jump_from) && valid_address(exe->tgt_addr) && valid_address(exe->RIP)) {
				sprintf(cmd, "echo '%p %p' >> ./%p/asm/ij_table.txt", (void*)exe->jump_from, (void*)exe->tgt_addr, (void*)exe->RIP);
				// printf("%5d %p Indirect Jump at %p %p", exe->pid, (void*)exe->RIP, (void*)exe->jump_from, (void*)exe->tgt_addr);
			}
			else {
				is_valid = 0;
				if (!hash_history(hash3(exe->pid, exe->jump_from, exe->RIP))) {
					printf("F_IJ_MISS invalid address %p %p %p\n", (void*)exe->jump_from, (void*)exe->tgt_addr, (void*)exe->RIP);
				}
			}
		}
		else {
			printf("%5d %p Unrecognized Code %d", exe->pid, (void*)exe->RIP, exe->status_code);
			continue;
		}
		if (cmd[0] && !cmd_history(cmd)) {
			// printf(" Compiling");
			system(cmd);
			if (compile(exe->pid, (void*)exe->RIP) == -1)
				break;
		}
		else {
			if (cmd[0]) {
				// printf(" Compile saved");
			}
		}
		if (cmd[0]) {
			write_sys(exe->pid, exe->RIP);
			// printf("\n");
		}
		// if (is_valid == 0)
		//     write_sys(exe->pid, exe->RIP);
	}
}

int main() {
	system("rm -rf 0x*");
	// printf("%d\n", sizeof(struct exe_info));
	while (1) {
		check();
		usleep(100 * 1000);
	}
}