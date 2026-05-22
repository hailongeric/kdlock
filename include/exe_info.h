#ifndef EXE_INFO_H
#define EXE_INFO_H

#define F_UN_USED -2
#define F_UN_INIT -1
#define F_NORMAL 0
#define F_CALL_MISS 1
#define F_IJ_MISS 2
#define F_ERROR_INST 3
#define F_INST_LIMIT 4

struct exe_info {
	int status_code;
	int pid;
	int tgid;
	unsigned long RIP;
	void* code_block;
	unsigned long jump_from;
	unsigned long tgt_addr;
	// unsigned long fsbase;
	unsigned long gsbase;
	int success_cnt;
	int fail_cnt;
}__attribute__((aligned(64)));


struct recv_pkt {
	int status_code;
	int pid;
	unsigned long RIP;
	unsigned long offset;
};

#endif