// SPDX-License-Identifier: GPL-2.0
/* Origin-process CPU faults through a shared backing object, with independent
 * native mmap locks. Parent/child pipes retain exact startup and join receipts. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <unistd.h>
#include "mmap_fault_uapi.h"

#define MAX_WORKERS 60
struct receipt { uint64_t worker, pid, cpu, completed, errors, last_sequence; };
static void fail(const char *what) { perror(what); exit(1); }
static void exact_write(int fd,const void *buffer,size_t bytes)
{
	const char *p=buffer;
	while (bytes) { ssize_t n=write(fd,p,bytes);if(n<0 && errno==EINTR)continue;if(n<=0)fail("write");p+=n;bytes-=n; }
}
static void exact_read(int fd,void *buffer,size_t bytes)
{
	char *p=buffer;
	while(bytes) { ssize_t n=read(fd,p,bytes);if(n<0 && errno==EINTR)continue;if(n<=0)fail("read");p+=n;bytes-=n; }
}
static void pin(unsigned cpu)
{
	cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
	if(sched_setaffinity(0,sizeof(set),&set))fail("affinity");
}
static void worker(int fd,const char *mode,unsigned id,unsigned workers,uint64_t iterations,
		   int ready,int start,int results)
{
	struct receipt r={.worker=id,.pid=getpid(),.cpu=id};
	int query=!strcmp(mode,"queries") || !strcmp(mode,"fallback");
	int writer=!strcmp(mode,"concurrent") && id==workers-1;
	int lifetime=!strcmp(mode,"lifetime");
	volatile uint64_t *mapped=NULL;
	struct mf_stats before;
	pin(id);
	if(prctl(PR_SET_NAME,"mf_worker",0,0,0))fail("comm");
	if(ioctl(fd,MF_STATS,&before))fail("stats");
	/* All test objects have 64 resident pages; each process owns one VMA. */
	if(!query && !writer) {
		mapped=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,(off_t)id*4096);
		if(mapped==MAP_FAILED)fail("mmap");
	}
	if(lifetime && close(fd))fail("close VMA-only descriptor");
	exact_write(ready,"R",1);
	char go;exact_read(start,&go,1);
	if(go!='G')fail("barrier");
	if(query) {
		struct mf_work work={.iterations=iterations};
		if(ioctl(fd,!strcmp(mode,"fallback") ? MF_LOCAL_LOOKUPS : MF_LOOKUPS,&work))fail("lookup batch");
		r.completed=work.completed;r.errors=work.errors;r.last_sequence=work.last_sequence;
	} else for(uint64_t i=0;i<iterations;i++) {
		if(writer) {
			if(ioctl(fd,MF_MUTATE)) { r.errors++;break; }
		} else {
			if(madvise((void *)mapped,4096,MADV_DONTNEED)) { r.errors++;break; }
			if(*mapped!=MF_WORD+id)r.errors++;
		}
		r.completed++;
	}
	if(mapped && munmap((void *)mapped,4096))fail("munmap");
	if(!lifetime && close(fd))fail("close");
	exact_write(results,&r,sizeof(r));
	_exit(r.errors || r.completed!=iterations);
}
int main(int argc,char **argv)
{
	if(argc!=5) { fprintf(stderr,"usage: %s FD queries|fallback|faults|concurrent|lifetime WORKERS ITERATIONS\n",argv[0]);return 2; }
	int fd=atoi(argv[1]);const char *mode=argv[2];unsigned workers=strtoul(argv[3],NULL,10);
	uint64_t iterations=strtoull(argv[4],NULL,10);
	if(fd<3 || !workers || workers>MAX_WORKERS || !iterations || iterations>10000000 ||
	   (strcmp(mode,"queries") && strcmp(mode,"fallback") && strcmp(mode,"faults") && strcmp(mode,"concurrent") && strcmp(mode,"lifetime")))return 2;
	if(sysconf(_SC_PAGESIZE)!=4096)return 2;
	pin(63);
	int ready[2],start[2],results[2];pid_t children[MAX_WORKERS];
	if(pipe(ready)||pipe(start)||pipe(results))fail("pipe");
	for(unsigned i=0;i<workers;i++) {
		children[i]=fork();if(children[i]<0)fail("fork");
		if(!children[i]) {
			close(ready[0]);close(start[1]);close(results[0]);
			worker(fd,mode,i,workers,iterations,ready[1],start[0],results[1]);
		}
	}
	close(ready[1]);close(start[0]);close(results[1]);
	char tokens[MAX_WORKERS];exact_read(ready[0],tokens,workers);close(ready[0]);
	if(!strcmp(mode,"lifetime") && close(fd))fail("close parent descriptor");
	printf("{\"event\":\"ready\",\"pid\":%d,\"workers\":%u,\"mode\":\"%s\",\"vma_only\":%s}\n",getpid(),workers,mode,!strcmp(mode,"lifetime")?"true":"false");fflush(stdout);
	char go;exact_read(STDIN_FILENO,&go,1);if(go!='G')return 2;
	memset(tokens,'G',workers);exact_write(start[1],tokens,workers);close(start[1]);
	struct receipt receipts[MAX_WORKERS];unsigned seen=0;uint64_t seen_mask=0;int errors=0;
	for(unsigned i=0;i<workers;i++) {
		struct receipt r;exact_read(results[0],&r,sizeof(r));
		if(r.worker>=workers || (seen_mask & (1ULL<<r.worker)))fail("worker identity");
		seen_mask|=1ULL<<r.worker;
		receipts[r.worker]=r;seen++;
	}
	close(results[0]);
	for(unsigned i=0;i<workers;i++) {
		int status;if(waitpid(children[i],&status,0)!=children[i])fail("join");
		if(!WIFEXITED(status)||WEXITSTATUS(status))errors++;
		if(receipts[i].worker!=i || receipts[i].pid!=(uint64_t)children[i] || receipts[i].cpu!=i || receipts[i].completed!=iterations || receipts[i].errors)errors++;
	}
	printf("{\"event\":\"joined\",\"mode\":\"%s\",\"iterations\":%llu,\"errors\":%d,\"workers\":[",mode,(unsigned long long)iterations,errors);
	for(unsigned i=0;i<workers;i++) {
		struct receipt *r=&receipts[i];
		printf("%s{\"worker\":%llu,\"pid\":%llu,\"cpu\":%llu,\"completed\":%llu,\"errors\":%llu,\"last_sequence\":%llu}",i?",":"",
		 (unsigned long long)r->worker,(unsigned long long)r->pid,(unsigned long long)r->cpu,
		 (unsigned long long)r->completed,(unsigned long long)r->errors,(unsigned long long)r->last_sequence);
	}
	printf("],\"joined\":%u,\"passed\":%s}\n",seen,errors?"false":"true");
	return errors?1:0;
}
