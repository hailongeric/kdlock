// SPDX-License-Identifier: GPL-2.0
/* Fixed-duration mmap-only or fault-cycle operations. All setup, sample storage,
 * joins and result output are outside the measured operation. Each process has
 * its own native mm; backing readers share one object and never become writers. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/wait.h>
#include <time.h>
#include <unistd.h>
#include "mmap_fault_uapi.h"

#define MAX_WORKERS 60
#define LATENCY_CAP 65536
#define SAMPLE_CAP 512
struct worker_state {
	_Alignas(64) _Atomic uint64_t progress;
	uint64_t completed,errors,pid,cpu,active_started_ns,kernel_finished_ns,finished_ns,cpu_ns;
	uint64_t latency_count,latency[LATENCY_CAP];
};
struct shared { uint64_t started_ns,deadline_ns;struct worker_state workers[]; };
struct sample { uint64_t started_ns,finished_ns,completed[MAX_WORKERS]; };
static void fail(const char *what) { perror(what);exit(1); }
static void require(int ok,const char *what) { if(!ok) { fprintf(stderr,"FAIL: %s\n",what);exit(1); } }
static uint64_t clock_ns(clockid_t clock)
{
	struct timespec t;if(clock_gettime(clock,&t))fail("clock");
	return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;
}
static uint64_t now(void) { return clock_ns(CLOCK_MONOTONIC); }
static void until(uint64_t ns)
{
	struct timespec t={.tv_sec=ns/1000000000ULL,.tv_nsec=ns%1000000000ULL};
	int rc;do { rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&t,NULL); } while(rc==EINTR);
	require(!rc,"absolute sleep");
}
static void transfer(int fd,void *buffer,size_t bytes,int writing)
{
	char *p=buffer;while(bytes) {
		ssize_t n=writing ? write(fd,p,bytes) : read(fd,p,bytes);
		if(n<0 && errno==EINTR)continue;
		if(n<=0)fail("pipe transfer");
		p+=n;bytes-=n;
	}
}
static void pin(unsigned cpu)
{
	cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
	if(sched_setaffinity(0,sizeof(set),&set))fail("affinity");
	require(sched_getcpu()==(int)cpu,"CPU placement");
}
static void worker(int fd,int mapping,unsigned id,int sampled,struct shared *s,int ready,int start)
{
	struct worker_state *w=&s->workers[id];
	volatile uint64_t *address=NULL;
	pin(id);w->pid=getpid();w->cpu=id;
	if(prctl(PR_SET_NAME,"mf_time_worker",0,0,0))fail("comm");
	if(!mapping) {
		address=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,(off_t)id*4096);
		if(address==MAP_FAILED)fail("setup mmap");
	}
	char token='R';transfer(ready,&token,1,1);close(ready);
	transfer(start,&token,1,0);close(start);require(token=='G',"start token");
	until(s->started_ns);
	uint64_t cpu_start=clock_ns(CLOCK_PROCESS_CPUTIME_ID);
	w->active_started_ns=now();
	uint64_t check=w->active_started_ns;
	while(check<s->deadline_ns) {
		int take=sampled && ((w->completed+id)%64==0);
		uint64_t begin=take ? now() : 0;
		if(mapping) {
			void *vma=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,(off_t)id*4096);
			if(vma==MAP_FAILED || munmap(vma,4096)) { w->errors++;break; }
		} else {
			if(madvise((void *)address,4096,MADV_DONTNEED)) { w->errors++;break; }
			if(*address!=MF_WORD+id) { w->errors++;break; }
		}
		uint64_t end=take ? now() : 0;
		w->completed++;
		if(take) {
			if(w->latency_count==LATENCY_CAP) { w->errors++;break; }
			w->latency[w->latency_count++]=end-begin;
		}
		if(!(w->completed%256))atomic_store_explicit(&w->progress,w->completed,memory_order_release);
		/* Equal stop-clock frequency in both observation modes. */
		if(!(w->completed%32))check=now();
	}
	w->kernel_finished_ns=now();
	atomic_store_explicit(&w->progress,w->completed,memory_order_release);
	w->cpu_ns=clock_ns(CLOCK_PROCESS_CPUTIME_ID)-cpu_start;
	require(sched_getcpu()==(int)id,"final CPU placement");
	if(address && munmap((void *)address,4096))fail("teardown munmap");
	if(close(fd))fail("close");
	w->finished_ns=now();_exit(w->errors!=0);
}
static void read_stats(int fd,struct mf_stats *s) { if(ioctl(fd,MF_STATS,s))fail("stats"); }
static void print_stats(const struct mf_stats *s)
{
	uint64_t v[16];memcpy(v,s,sizeof(v));
	const char *names[]={"backend","features","vmas","active_probe","epoch","faults","reads","read_ends","writes","write_ends","downgrades","context_errors","data_errors","fallback","scopes","scope_ends"};
	_Static_assert(sizeof(*s)==16*sizeof(uint64_t),"stats ABI");
	printf("{");for(unsigned i=0;i<16;i++)printf("%s\"%s\":%llu",i?",":"",names[i],(unsigned long long)v[i]);printf("}");
}
int main(int argc,char **argv)
{
	if(argc!=5) { fprintf(stderr,"usage: %s BACKEND mmap|fault WORKERS plain|sampled\n",argv[0]);return 2; }
	unsigned backend=strtoul(argv[1],NULL,10),workers=strtoul(argv[3],NULL,10);
	int mapping=!strcmp(argv[2],"mmap"),sampled=!strcmp(argv[4],"sampled");
	require(backend<=MF_TC && workers && workers<=MAX_WORKERS && (mapping || !strcmp(argv[2],"fault")) &&
	        (sampled || !strcmp(argv[4],"plain")),"arguments");
	require(!mapping || backend==MF_NATIVE,"mmap-only has no selectable private lock");
	require(sysconf(_SC_PAGESIZE)==4096,"page size");pin(63);
	int fd=open("/dev/kd_mmap_fault",O_RDWR|O_CLOEXEC);if(fd<0)fail("open");
	struct mf_create c={.abi=MF_ABI,.backend=backend,.pages=64};
	if(ioctl(fd,MF_CREATE,&c))fail("create");
	require(c.selected_backend==backend && !c.fallback && !c.features,"object contract");
	size_t bytes=sizeof(struct shared)+workers*sizeof(struct worker_state);
	struct shared *s=mmap(NULL,bytes,PROT_READ|PROT_WRITE,MAP_SHARED|MAP_ANONYMOUS,-1,0);
	if(s==MAP_FAILED)fail("shared receipts");
	memset(s,0,bytes);
	struct sample *samples=calloc(SAMPLE_CAP,sizeof(*samples));if(!samples)fail("samples");
	/* Prefault observer storage equally for both modes, before worker creation. */
	for(unsigned i=0;i<SAMPLE_CAP;i++)samples[i].started_ns=1;
	int ready[2],start[2];pid_t children[MAX_WORKERS];
	if(pipe(ready)||pipe(start))fail("pipes");
	for(unsigned i=0;i<workers;i++) {
		children[i]=fork();if(children[i]<0)fail("fork");
		if(!children[i]) { close(ready[0]);close(start[1]);worker(fd,mapping,i,sampled,s,ready[1],start[0]); }
	}
	close(ready[1]);close(start[0]);char tokens[MAX_WORKERS];
	transfer(ready[0],tokens,workers,0);close(ready[0]);
	for(unsigned i=0;i<workers;i++)require(tokens[i]=='R',"ready token");
	struct mf_stats before,after;read_stats(fd,&before);
	require(!before.faults && !before.reads && !before.writes && before.vmas==(mapping?0:workers),"cold untouched setup");
	printf("{\"event\":\"ready\",\"pids\":[");for(unsigned i=0;i<workers;i++)printf("%s%d",i?",":"",children[i]);printf("]}\n");fflush(stdout);
	s->started_ns=now()+100000000;s->deadline_ns=s->started_ns+2000000000ULL;
	memset(tokens,'G',workers);transfer(start[1],tokens,workers,1);close(start[1]);
	unsigned count=0;uint64_t next=s->started_ns;
	while(next<=s->deadline_ns) {
		until(next);require(count<SAMPLE_CAP,"progress sample capacity");
		struct sample *p=&samples[count++];p->started_ns=now();
		for(unsigned i=0;i<workers;i++)p->completed[i]=atomic_load_explicit(&s->workers[i].progress,memory_order_acquire);
		p->finished_ns=now();next+=10000000;
	}
	uint64_t completed=0,finished=0,cpu_ns=0;
	for(unsigned i=0;i<workers;i++) {
		int status;require(waitpid(children[i],&status,0)==children[i] && WIFEXITED(status) && !WEXITSTATUS(status),"exact worker join");
		struct worker_state *w=&s->workers[i];
		require(w->pid==(uint64_t)children[i] && w->cpu==i && !w->errors && w->completed,"worker result");
		completed+=w->completed;cpu_ns+=w->cpu_ns;if(w->finished_ns>finished)finished=w->finished_ns;
	}
	read_stats(fd,&after);
	require(!after.vmas && !after.active_probe && !after.epoch && !after.writes && !after.write_ends &&
	        !after.scopes && !after.scope_ends && !after.context_errors && !after.data_errors && !after.fallback,"joined object state");
	require(after.faults==(mapping?0:completed) && after.reads==after.faults && after.read_ends==after.faults,"exact callback and reader counts");
	if(close(fd))fail("final close");
	printf("{\"event\":\"measurement\",\"complete\":true,\"data_ok\":true,\"backend\":%u,\"workload\":\"%s\",\"observation\":\"%s\",\"threads\":%u,\"joined\":%u,\"completed\":%llu,\"started_ns\":%llu,\"deadline_ns\":%llu,\"finished_ns\":%llu,\"wall_ns\":%llu,\"worker_cpu_ns\":%llu,\"duration_ns\":2000000000,\"peak_window_ns\":300000000,\"peak_settle_ns\":300000000,\"sample_period_ns\":10000000,\"progress_batch\":256,\"collector_cpu\":63,\"collector_observed_cpu\":%d,\"collector_error\":0,\"before\":",
	 backend,argv[2],argv[4],workers,workers,(unsigned long long)completed,(unsigned long long)s->started_ns,(unsigned long long)s->deadline_ns,
	 (unsigned long long)finished,(unsigned long long)(finished-s->started_ns),(unsigned long long)cpu_ns,sched_getcpu());
	print_stats(&before);printf(",\"after\":");print_stats(&after);printf(",\"workers\":[");
	for(unsigned i=0;i<workers;i++) {
		struct worker_state *w=&s->workers[i];
		printf("%s{\"cpu\":%u,\"observed_cpu\":%llu,\"pid\":%llu,\"completed\":%llu,\"error\":%llu,\"active_started_ns\":%llu,\"kernel_finished_ns\":%llu,\"finished_ns\":%llu,\"cpu_ns\":%llu,\"latency_ns\":[",i?",":"",i,(unsigned long long)w->cpu,(unsigned long long)w->pid,(unsigned long long)w->completed,(unsigned long long)w->errors,
		 (unsigned long long)w->active_started_ns,(unsigned long long)w->kernel_finished_ns,(unsigned long long)w->finished_ns,(unsigned long long)w->cpu_ns);
		for(uint64_t j=0;j<w->latency_count;j++)printf("%s%llu",j?",":"",(unsigned long long)w->latency[j]);
		printf("]}");
	}
	printf("],\"samples\":[");
	for(unsigned i=0;i<count;i++) {
		struct sample *p=&samples[i];printf("%s{\"started_ns\":%llu,\"finished_ns\":%llu,\"completed\":[",i?",":"",(unsigned long long)p->started_ns,(unsigned long long)p->finished_ns);
		for(unsigned j=0;j<workers;j++)printf("%s%llu",j?",":"",(unsigned long long)p->completed[j]);
		printf("]}");
	}
	printf("]}\n");free(samples);require(!munmap(s,bytes),"receipt unmap");return 0;
}
