// SPDX-License-Identifier: GPL-2.0
/* Separate VMA creation from real CPU faults. Each process owns its native mm;
 * fault readers share one immutable backing object and retain reader ownership.
 * No writer is inserted into a page lookup to manufacture delegation. */
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
struct receipt { uint64_t worker, pid, cpu, completed, errors; };
static void fail(const char *what) { perror(what); exit(1); }
static void require(int ok,const char *what) { if(!ok) { fprintf(stderr,"FAIL: %s\n",what);exit(1); } }
static void transfer(int fd,void *buffer,size_t bytes,int writing)
{
	char *p=buffer;
	while(bytes) {
		ssize_t n=writing ? write(fd,p,bytes) : read(fd,p,bytes);
		if(n<0 && errno==EINTR)continue;
		if(n<=0)fail(writing ? "write" : "read");
		p+=n;bytes-=n;
	}
}
static void pin(unsigned cpu)
{
	cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
	if(sched_setaffinity(0,sizeof(set),&set))fail("affinity");
	require(sched_getcpu()==(int)cpu,"CPU placement");
}
static void worker(int fd,const char *mode,unsigned id,unsigned workers,uint64_t iterations,
		   int ready,int start,int results)
{
	struct receipt r={.worker=id,.pid=getpid(),.cpu=id};
	int mapping=!strcmp(mode,"mmap"),lifetime=!strcmp(mode,"lifetime");
	int writer=!strcmp(mode,"concurrent") && id==workers-1;
	volatile uint64_t *address=NULL;
	pin(id);
	if(prctl(PR_SET_NAME,"mf_split_worker",0,0,0))fail("comm");
	if(!mapping && !writer) {
		address=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,(off_t)id*4096);
		if(address==MAP_FAILED)fail("setup mmap");
	}
	if(lifetime && close(fd))fail("close VMA-only descriptor");
	char token='R';transfer(ready,&token,1,1);transfer(start,&token,1,0);
	require(token=='G',"start barrier");
	for(uint64_t i=0;i<iterations;i++) {
		if(mapping) {
			/* No MAP_POPULATE, access, mlock, advice or fault-in helper. */
			void *vma=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,(off_t)id*4096);
			if(vma==MAP_FAILED || munmap(vma,4096)) { r.errors++;break; }
		} else if(writer) {
			if(ioctl(fd,MF_MUTATE)) { r.errors++;break; }
		} else {
			if(madvise((void *)address,4096,MADV_DONTNEED)) { r.errors++;break; }
			if(*address!=MF_WORD+id)r.errors++;
		}
		r.completed++;
	}
	require(sched_getcpu()==(int)id,"final CPU placement");
	if(address && munmap((void *)address,4096))fail("munmap");
	if(!lifetime && close(fd))fail("close");
	transfer(results,&r,sizeof(r),1);
	_exit(r.errors || r.completed!=iterations);
}
static void stats(int fd,struct mf_stats *s)
{
	if(ioctl(fd,MF_STATS,s))fail("stats");
}
static void print_stats(const char *event,const struct mf_stats *s)
{
	printf("{\"event\":\"%s\",\"backend\":%llu,\"features\":%llu,\"vmas\":%llu,\"active_probe\":%llu,\"epoch\":%llu,\"faults\":%llu,\"reads\":%llu,\"read_ends\":%llu,\"writes\":%llu,\"write_ends\":%llu,\"context_errors\":%llu,\"data_errors\":%llu,\"scopes\":%llu,\"scope_ends\":%llu,\"fallback\":%llu}\n",
	 event,(unsigned long long)s->backend,(unsigned long long)s->features,(unsigned long long)s->vmas,
	 (unsigned long long)s->active_probe,(unsigned long long)s->epoch,(unsigned long long)s->faults,
	 (unsigned long long)s->reads,(unsigned long long)s->read_ends,(unsigned long long)s->writes,
	 (unsigned long long)s->write_ends,(unsigned long long)s->context_errors,(unsigned long long)s->data_errors,
	 (unsigned long long)s->scopes,(unsigned long long)s->scope_ends,(unsigned long long)s->fallback);
}
int main(int argc,char **argv)
{
	if(argc!=5) { fprintf(stderr,"usage: %s BACKEND mmap|fault|concurrent|lifetime WORKERS ITERATIONS\n",argv[0]);return 2; }
	unsigned backend=strtoul(argv[1],NULL,10),workers=strtoul(argv[3],NULL,10);
	const char *mode=argv[2];uint64_t iterations=strtoull(argv[4],NULL,10);
	require(backend<=MF_TC && workers && workers<=MAX_WORKERS && iterations && iterations<=10000000,"arguments");
	require(!strcmp(mode,"mmap") || !strcmp(mode,"fault") || !strcmp(mode,"concurrent") || !strcmp(mode,"lifetime"),"workload");
	require(strcmp(mode,"concurrent") || workers>1,"concurrent readers and writer");
	require(sysconf(_SC_PAGESIZE)==4096,"page size");pin(63);
	int fd=open("/dev/kd_mmap_fault",O_RDWR|O_CLOEXEC);
	if(fd<0)fail("open");
	struct mf_create c={.abi=MF_ABI,.backend=backend,.pages=64};
	if(ioctl(fd,MF_CREATE,&c))fail("create");
	require(c.selected_backend==backend && !c.fallback && !c.features,"backend and features");
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
	char tokens[MAX_WORKERS];transfer(ready[0],tokens,workers,0);close(ready[0]);
	for(unsigned i=0;i<workers;i++)require(tokens[i]=='R',"ready token");
	struct mf_stats before,after;stats(fd,&before);print_stats("before",&before);
	require(!before.faults && !before.reads && !before.writes && !before.scopes,"untouched mappings before workload");
	int lifetime=!strcmp(mode,"lifetime");
	if(lifetime && close(fd))fail("close last descriptor");
	printf("{\"event\":\"ready\",\"mode\":\"%s\",\"workers\":%u,\"vma_only\":%s,\"pids\":[",mode,workers,lifetime?"true":"false");
	for(unsigned i=0;i<workers;i++)printf("%s%d",i?",":"",children[i]);
	printf("]}\n");fflush(stdout);
	memset(tokens,'G',workers);transfer(start[1],tokens,workers,1);close(start[1]);
	struct receipt rows[MAX_WORKERS];uint64_t seen=0,completed=0;
	for(unsigned i=0;i<workers;i++) {
		struct receipt r;transfer(results[0],&r,sizeof(r),0);
		require(r.worker<workers && !(seen & (1ULL<<r.worker)),"distinct worker receipt");
		seen|=1ULL<<r.worker;rows[r.worker]=r;
		require(r.cpu==r.worker && r.pid==(uint64_t)children[r.worker] && !r.errors && r.completed==iterations,"worker result");
		completed+=r.completed;
	}
	close(results[0]);
	for(unsigned i=0;i<workers;i++) {
		int status;require(waitpid(children[i],&status,0)==children[i] && WIFEXITED(status) && !WEXITSTATUS(status),"worker join");
	}
	if(!lifetime) {
		stats(fd,&after);print_stats("after",&after);
		uint64_t fault_count=!strcmp(mode,"mmap") ? 0 : iterations*(workers-(!strcmp(mode,"concurrent")));
		uint64_t writes=!strcmp(mode,"concurrent") ? iterations : 0;
		require(!after.vmas && !after.active_probe && !after.scopes && !after.scope_ends && !after.context_errors && !after.data_errors && !after.fallback,"joined object state");
		require(after.faults==fault_count && after.reads==fault_count && after.read_ends==fault_count,"exact CPU fault and reader counts");
		require(after.writes==writes && after.write_ends==writes && after.epoch==writes,"exact writer counts");
		if(close(fd))fail("close object");
	}
	printf("{\"event\":\"complete\",\"passed\":true,\"backend\":%u,\"mode\":\"%s\",\"iterations\":%llu,\"completed\":%llu,\"joined\":%u,\"workers\":[",
	 backend,mode,(unsigned long long)iterations,(unsigned long long)completed,workers);
	for(unsigned i=0;i<workers;i++)printf("%s{\"worker\":%u,\"pid\":%llu,\"cpu\":%llu,\"completed\":%llu,\"errors\":%llu}",i?",":"",i,
	 (unsigned long long)rows[i].pid,(unsigned long long)rows[i].cpu,(unsigned long long)rows[i].completed,(unsigned long long)rows[i].errors);
	printf("]}\n");return 0;
}
