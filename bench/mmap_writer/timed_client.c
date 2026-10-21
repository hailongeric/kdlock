// SPDX-License-Identifier: GPL-2.0
/* Shared-mm Native mmap/munmap cycles. Never touch the mapped payload range. */
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdatomic.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/prctl.h>
#include <sys/syscall.h>
#include <time.h>
#include <unistd.h>
#include "mmap_writer_uapi.h"
#define MAX_WORKERS 60
#define LATENCY_CAP 65536
#define SAMPLE_CAP 512
struct worker {
	_Alignas(64) _Atomic uint64_t progress;
	uint64_t completed,errors,cpu,active_started_ns,kernel_finished_ns,finished_ns,cpu_ns;
	uint64_t latency_count,latency[LATENCY_CAP];
	struct mw_identity identity;
	int fd,sampled;
};
struct sample { uint64_t started_ns,finished_ns,completed[MAX_WORKERS]; };
static pthread_barrier_t ready,go;
static uint64_t started_ns,deadline_ns;
static void require(int ok,const char *what)
{
	if(!ok) { fflush(stdout);fprintf(stderr,"FAIL %s errno=%d\n",what,errno);exit(1); }
}
static uint64_t clock_ns(clockid_t clock)
{
	struct timespec t;require(!clock_gettime(clock,&t),"clock");
	return (uint64_t)t.tv_sec*1000000000ULL+t.tv_nsec;
}
static uint64_t now(void) { return clock_ns(CLOCK_MONOTONIC); }
static void until(uint64_t ns)
{
	struct timespec t={.tv_sec=ns/1000000000ULL,.tv_nsec=ns%1000000000ULL};
	int rc;do { rc=clock_nanosleep(CLOCK_MONOTONIC,TIMER_ABSTIME,&t,NULL); } while(rc==EINTR);
	require(!rc,"absolute sleep");
}
static void pin(unsigned cpu)
{
	cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
	require(!sched_setaffinity(0,sizeof(set),&set) && sched_getcpu()==(int)cpu,"CPU placement");
}
static void barrier(pthread_barrier_t *b)
{
	int rc=pthread_barrier_wait(b);require(!rc || rc==PTHREAD_BARRIER_SERIAL_THREAD,"barrier");
}
static struct mw_identity identity(int fd)
{
	struct mw_identity id;require(!ioctl(fd,MW_ID,&id),"identity");
	require(id.abi==MW_ABI && id.mm && id.mmap_lock && id.object &&
	        id.tgid==(uint64_t)getpid() && id.tid==(uint64_t)syscall(SYS_gettid),"exact task/mm");return id;
}
static struct mw_stats stats(int fd)
{
	struct mw_stats s;require(!ioctl(fd,MW_STATS,&s),"stats");
	require(!s.faults && !s.context_errors && !s.foreign_rejects && !s.observe && !s.contended_mmaps &&
	        !s.clones && !s.vmas && s.maps==s.closes,"quiescent untouched Native object");return s;
}
static void print_identity(const struct mw_identity *id)
{
	printf("{\"object\":%llu,\"mm\":%llu,\"mmap_lock\":%llu,\"tgid\":%llu,\"tid\":%llu}",
	 (unsigned long long)id->object,(unsigned long long)id->mm,(unsigned long long)id->mmap_lock,
	 (unsigned long long)id->tgid,(unsigned long long)id->tid);
}
static void print_stats(const struct mw_stats *s)
{
	const char *keys[]={"object","maps","clones","closes","vmas","faults","context_errors","foreign_rejects","contended_mmaps","observe"};
	uint64_t values[10];_Static_assert(sizeof(*s)==sizeof(values),"stats ABI");memcpy(values,s,sizeof(values));
	printf("{");for(unsigned i=0;i<10;i++)printf("%s\"%s\":%llu",i?",":"",keys[i],(unsigned long long)values[i]);printf("}");
}
static void *worker(void *arg)
{
	struct worker *w=arg;pin(w->cpu);require(!prctl(PR_SET_NAME,"mw_time_worker",0,0,0),"comm");
	w->identity=identity(w->fd);barrier(&ready);barrier(&go);until(started_ns);
	uint64_t cpu_start=clock_ns(CLOCK_THREAD_CPUTIME_ID);w->active_started_ns=now();
	uint64_t check=w->active_started_ns;
	while(check<deadline_ns) {
		int take=w->sampled && ((w->completed+w->cpu)%64==0);uint64_t begin=take?now():0;
		void *vma=mmap(NULL,4096,PROT_READ,MAP_SHARED,w->fd,(off_t)w->cpu*4096);
		if(vma==MAP_FAILED || munmap(vma,4096)) { w->errors++;break; }
		uint64_t end=take?now():0;w->completed++;
		if(take) {
			if(w->latency_count==LATENCY_CAP) { w->errors++;break; }
			w->latency[w->latency_count++]=end-begin;
		}
		if(!(w->completed%256))atomic_store_explicit(&w->progress,w->completed,memory_order_release);
		if(!(w->completed%32))check=now();
	}
	w->kernel_finished_ns=now();atomic_store_explicit(&w->progress,w->completed,memory_order_release);
	w->cpu_ns=clock_ns(CLOCK_THREAD_CPUTIME_ID)-cpu_start;
	require(sched_getcpu()==(int)w->cpu && !close(w->fd),"worker close/CPU");
	w->finished_ns=now();return NULL;
}
int main(int argc,char **argv)
{
	require(argc==3,"WORKERS plain|sampled");unsigned n=strtoul(argv[1],NULL,10);int sampled=!strcmp(argv[2],"sampled");
	require(n && n<=MAX_WORKERS && (sampled || !strcmp(argv[2],"plain")) && sysconf(_SC_PAGESIZE)==4096,"arguments");pin(63);
	int fd=open("/dev/kd_mmap_writer_native",O_RDWR|O_CLOEXEC);require(fd>=0,"open");
	struct mw_identity id=identity(fd);struct worker *w=NULL;
	require(!posix_memalign((void **)&w,64,n*sizeof(*w)),"worker storage");memset(w,0,n*sizeof(*w));
	struct sample *samples=calloc(SAMPLE_CAP,sizeof(*samples));require(samples!=NULL,"sample storage");
	for(unsigned i=0;i<SAMPLE_CAP;i++)samples[i].started_ns=1;
	require(!pthread_barrier_init(&ready,NULL,n+1) && !pthread_barrier_init(&go,NULL,n+1),"barrier init");
	pthread_t threads[MAX_WORKERS];
	/* Allocate all descriptor ownership before starting any worker. */
	for(unsigned i=0;i<n;i++) { w[i].cpu=i;w[i].sampled=sampled;w[i].fd=dup(fd);require(w[i].fd>=0,"dup"); }
	for(unsigned i=0;i<n;i++)require(!pthread_create(&threads[i],NULL,worker,&w[i]),"pthread create");
	barrier(&ready);struct mw_stats before=stats(fd);require(!before.maps,"untouched setup");
	for(unsigned i=0;i<n;i++) {
		struct mw_identity *v=&w[i].identity;
		require(v->mm==id.mm && v->mmap_lock==id.mmap_lock && v->object==id.object && v->tgid==id.tgid && v->tid!=id.tid,"shared exact mm/lock");
		for(unsigned j=0;j<i;j++)require(w[j].identity.tid!=v->tid,"unique TID");
	}
	printf("{\"event\":\"ready\",\"identity\":");print_identity(&id);printf("}\n");fflush(stdout);
	started_ns=now()+100000000ULL;deadline_ns=started_ns+2000000000ULL;barrier(&go);
	unsigned count=0;uint64_t next=started_ns;
	while(next<=deadline_ns) {
		until(next);require(count<SAMPLE_CAP,"sample capacity");struct sample *s=&samples[count++];s->started_ns=now();
		for(unsigned i=0;i<n;i++)s->completed[i]=atomic_load_explicit(&w[i].progress,memory_order_acquire);
		s->finished_ns=now();next+=10000000;
	}
	uint64_t completed=0,finished=0,cpu_ns=0;
	for(unsigned i=0;i<n;i++) {
		require(!pthread_join(threads[i],NULL) && !w[i].errors && w[i].completed,"exact worker join");
		completed+=w[i].completed;cpu_ns+=w[i].cpu_ns;if(w[i].finished_ns>finished)finished=w[i].finished_ns;
	}
	require(!pthread_barrier_destroy(&ready) && !pthread_barrier_destroy(&go),"barrier destroy");
	struct mw_stats after=stats(fd);require(after.maps==completed && after.object==id.object,"exact VMA callback count");
	require(!close(fd),"final close");
	printf("{\"event\":\"measurement\",\"complete\":true,\"data_ok\":true,\"workload\":\"mmap-shared-mm\",\"observation\":\"%s\",\"threads\":%u,\"joined\":%u,\"completed\":%llu,\"started_ns\":%llu,\"deadline_ns\":%llu,\"finished_ns\":%llu,\"wall_ns\":%llu,\"worker_cpu_ns\":%llu,\"duration_ns\":2000000000,\"peak_window_ns\":300000000,\"peak_settle_ns\":300000000,\"sample_period_ns\":10000000,\"progress_batch\":256,\"collector_cpu\":63,\"collector_observed_cpu\":%d,\"collector_error\":0,\"before\":",
	 argv[2],n,n,(unsigned long long)completed,(unsigned long long)started_ns,(unsigned long long)deadline_ns,
	 (unsigned long long)finished,(unsigned long long)(finished-started_ns),(unsigned long long)cpu_ns,sched_getcpu());
	print_stats(&before);printf(",\"after\":");print_stats(&after);printf(",\"workers\":[");
	for(unsigned i=0;i<n;i++) {
		struct worker *v=&w[i];
		printf("%s{\"cpu\":%u,\"observed_cpu\":%llu,\"identity\":",i?",":"",i,(unsigned long long)v->cpu);print_identity(&v->identity);
		printf(",\"completed\":%llu,\"error\":%llu,\"active_started_ns\":%llu,\"kernel_finished_ns\":%llu,\"finished_ns\":%llu,\"cpu_ns\":%llu,\"latency_ns\":[",
		 (unsigned long long)v->completed,(unsigned long long)v->errors,(unsigned long long)v->active_started_ns,
		 (unsigned long long)v->kernel_finished_ns,(unsigned long long)v->finished_ns,(unsigned long long)v->cpu_ns);
		for(uint64_t j=0;j<v->latency_count;j++)printf("%s%llu",j?",":"",(unsigned long long)v->latency[j]);
		printf("]}");
	}
	printf("],\"samples\":[");
	for(unsigned i=0;i<count;i++) {
		struct sample *s=&samples[i];printf("%s{\"started_ns\":%llu,\"finished_ns\":%llu,\"completed\":[",i?",":"",(unsigned long long)s->started_ns,(unsigned long long)s->finished_ns);
		for(unsigned j=0;j<n;j++)printf("%s%llu",j?",":"",(unsigned long long)s->completed[j]);
		printf("]}");
	}
	printf("]}\n");free(samples);free(w);return 0;
}
