/* Workspace names, command deduplication and learned-target commands.
 * Included by daemon.c; share its session state and config without a C ABI. */
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

static int cmd_seen(const char *cmd, unsigned long generation, int *result)
{
	int i;

	provenance_current = (struct provenance_compile){ 0 };
	for (i = 0; i < cmd_cnt; i++) {
		if (cmd_generations[i] == generation && !strcmp(cmd, cmd_hist[i])) {
			*result = cmd_results[i];
			provenance_current = cmd_provenance[i];
			return 1;
		}
	}
	return 0;
}

static int remember_cmd(const char *cmd, unsigned long generation, int result)
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
	cmd_generations[cmd_cnt] = generation;
	cmd_provenance[cmd_cnt] = provenance_current;
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
