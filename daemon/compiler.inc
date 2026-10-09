/* Translator child/lease execution and optional wall/CPU accounting.
 * Policy refusal stays distinct from launch, signal and I/O errors. */
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
			  exe->entry_abi == KD_ENTRY_ABI_RWLOCK_CLOBBER_V1 ? "3" :
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
