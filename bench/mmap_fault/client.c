// SPDX-License-Identifier: GPL-2.0
#define _GNU_SOURCE
#include <errno.h>
#include <fcntl.h>
#include <pthread.h>
#include <sched.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <sys/ioctl.h>
#include <sys/mman.h>
#include <sys/wait.h>
#include <unistd.h>
#include "mmap_fault_uapi.h"

static size_t page_size;
static unsigned checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr,"FAIL line %d: %s errno=%d\n",__LINE__,#x,errno); exit(1); } } while (0)
static void pin(unsigned cpu)
{
	cpu_set_t set;
	CPU_ZERO(&set); CPU_SET(cpu,&set);
	if (sched_setaffinity(0,sizeof(set),&set)) { perror("affinity"); exit(1); }
}
static int create(unsigned backend, unsigned features, unsigned pages, struct mf_create *reply)
{
	int fd=open("/dev/kd_mmap_fault",O_RDWR|O_CLOEXEC);
	CHECK(fd>=0);
	*reply=(struct mf_create){.abi=MF_ABI,.backend=backend,.features=features,.pages=pages};
	CHECK(ioctl(fd,MF_CREATE,reply)==0);
	printf("{\"event\":\"create\",\"requested\":%u,\"selected\":%u,\"features\":%u,\"fallback\":%u}\n",
	       backend,reply->selected_backend,features,reply->fallback);
	return fd;
}
static void cold(void *address) { CHECK(madvise(address,page_size,MADV_DONTNEED)==0); }
static void probe_report(const struct mf_probe *p)
{
	printf("{\"event\":\"probe\",\"action\":%u,\"result\":%lld,\"attempts\":%llu,\"acquisitions\":%llu,\"releases\":%llu,\"callbacks\":%llu,\"retries\":%llu,\"nowait\":%llu,\"completed\":%llu,\"revalidated\":%llu,\"stale\":%llu,\"pause_timeout\":%llu,\"final_held\":%llu}\n",
	       p->action,(long long)p->result,(unsigned long long)p->attempts,
	       (unsigned long long)p->acquisitions,(unsigned long long)p->releases,
	       (unsigned long long)p->callbacks,(unsigned long long)p->retries,
	       (unsigned long long)p->nowait,(unsigned long long)p->completed,
	       (unsigned long long)p->revalidated,(unsigned long long)p->stale,
	       (unsigned long long)p->pause_timeout,(unsigned long long)p->final_held);
}
struct retry_arg { int fd, rc; struct mf_probe p; };
static void *retry_worker(void *arg)
{
	struct retry_arg *a=arg;
	pin(0); a->rc=ioctl(a->fd,MF_PROBE,&a->p);
	return NULL;
}
struct stress_arg {
	int fd, error;
	unsigned cpu, loops;
	volatile uint64_t *address;
	pthread_barrier_t *barrier;
	int writer;
};
static void *stress_worker(void *arg)
{
	struct stress_arg *a=arg;
	pin(a->cpu);pthread_barrier_wait(a->barrier);
	for (unsigned i=0;i<a->loops;i++) {
		if (a->writer) {
			if (ioctl(a->fd,MF_MUTATE)) { a->error=1;break; }
		} else if (madvise((void *)a->address,page_size,MADV_DONTNEED) ||
			   *a->address!=MF_WORD+a->cpu) { a->error=2;break; }
	}
	return NULL;
}
static void negative_create(unsigned backend)
{
	int fd=open("/dev/kd_mmap_fault",O_RDWR|O_CLOEXEC);
	struct mf_create c={.abi=MF_ABI,.backend=backend,.features=MF_PRIVATE,.pages=1};
	CHECK(fd>=0);
	if (backend!=MF_NATIVE) CHECK(ioctl(fd,MF_CREATE,&c)==-1 && errno==EOPNOTSUPP);
	else { c.abi=999; CHECK(ioctl(fd,MF_CREATE,&c)==-1 && errno==EINVAL); }
	CHECK(close(fd)==0);
}
static void native_fallback(unsigned backend)
{
	struct mf_create c;
	int fd=create(backend,MF_PRIVATE|MF_WRITABLE|MF_INHERIT|MF_ALLOW_FALLBACK,1,&c);
	CHECK(c.selected_backend==MF_NATIVE && c.fallback==(backend!=MF_NATIVE));
	volatile uint64_t *p=mmap(NULL,page_size,PROT_READ|PROT_WRITE,MAP_PRIVATE,fd,0);
	CHECK(p!=MAP_FAILED && *p==MF_WORD);
	*p=0x1234;
	pid_t child=fork();CHECK(child>=0);
	if (!child) { *p=0x9876; _exit(*p==0x9876 ? 0 : 2); }
	int status; CHECK(waitpid(child,&status,0)==child && WIFEXITED(status) && WEXITSTATUS(status)==0);
	CHECK(*p==0x1234);
	volatile uint64_t *other=mmap(NULL,page_size,PROT_READ|PROT_WRITE,MAP_PRIVATE,fd,0);
	CHECK(other!=MAP_FAILED && *other==MF_WORD);
	CHECK(munmap((void *)other,page_size)==0);
	CHECK(munmap((void *)p,page_size)==0 && close(fd)==0);
}
static void vma_lifetime(unsigned backend)
{
	struct mf_create c;int fd=create(backend,0,1,&c);
	volatile uint64_t *p=mmap(NULL,page_size,PROT_READ,MAP_SHARED,fd,0);
	CHECK(p!=MAP_FAILED && *p==MF_WORD);
	CHECK(close(fd)==0); /* Only the VMA's file reference now protects callback storage. */
	cold((void *)p);CHECK(*p==MF_WORD);CHECK(munmap((void *)p,page_size)==0);
}
int main(int argc,char **argv)
{
	CHECK(argc==2);unsigned backend=strtoul(argv[1],NULL,10);CHECK(backend<=MF_TC);
	page_size=sysconf(_SC_PAGESIZE);CHECK(page_size==4096);pin(63);
	negative_create(backend);
	struct mf_create c;unsigned features=backend==MF_TC ? 0 : MF_DOWNGRADE;
	int fd=create(backend,features,8,&c);
	CHECK(c.selected_backend==backend && !c.fallback);
	CHECK(ioctl(fd,MF_CREATE,&c)==-1 && errno==EBUSY);
	void *base=mmap(NULL,8*page_size,PROT_READ,MAP_SHARED,fd,0);
	CHECK(base!=MAP_FAILED);
	CHECK(*(volatile uint64_t *)base==MF_WORD);
	CHECK(mprotect(base,page_size,PROT_READ|PROT_WRITE)==-1 && errno==EACCES);
	CHECK(mprotect(base,page_size,PROT_NONE)==0);
	CHECK(mprotect(base,page_size,PROT_READ)==0);
	for (unsigned action=MF_NORMAL;action<=MF_COMPLETED;action++) {
		void *address=(char *)base+(action+1)*page_size;
		cold(address);
		struct mf_probe p={.address=(uintptr_t)address,.action=action};
		CHECK(ioctl(fd,MF_PROBE,&p)==0);probe_report(&p);
		CHECK(p.final_held==0 && p.acquisitions==p.releases && p.pause_timeout==0 && p.stale==0);
		CHECK(p.result==(action==MF_NOWAIT ? -EAGAIN : 0));
		CHECK(p.attempts==(action==MF_RETRY ? 2U : 1U));
		CHECK(p.callbacks==p.attempts && p.acquisitions==p.attempts);
		CHECK(p.retries==(action==MF_RETRY) && p.nowait==(action==MF_NOWAIT) &&
		      p.completed==(action==MF_COMPLETED) && p.revalidated==(action==MF_RETRY));
		CHECK(*(volatile uint64_t *)address==MF_WORD+action+1);
	}
	void *replace=(char *)base+5*page_size;
	cold(replace);
	struct retry_arg retry={.fd=fd,.p={.address=(uintptr_t)replace,.action=MF_REVALIDATE}};
	pthread_t thread;CHECK(pthread_create(&thread,NULL,retry_worker,&retry)==0);
	CHECK(ioctl(fd,MF_WAIT_DROP)==0);
	CHECK(munmap(replace,page_size)==0);
	CHECK(mmap(replace,page_size,PROT_READ|PROT_WRITE,MAP_PRIVATE|MAP_ANONYMOUS|MAP_FIXED,-1,0)==replace);
	*(volatile uint64_t *)replace=0xcafef00d;
	CHECK(ioctl(fd,MF_RELEASE_DROP)==0 && pthread_join(thread,NULL)==0);
	probe_report(&retry.p);
	CHECK(retry.rc==0 && retry.p.result==-ESTALE && retry.p.acquisitions==2 && retry.p.releases==2 &&
	      retry.p.attempts==1 && retry.p.callbacks==1 && retry.p.retries==1 && retry.p.stale==1 &&
	      !retry.p.final_held && !retry.p.pause_timeout);
	CHECK(*(volatile uint64_t *)replace==0xcafef00d);
	CHECK(munmap(replace,page_size)==0);
	CHECK(mmap(replace,page_size,PROT_READ,MAP_SHARED|MAP_FIXED,fd,5*page_size)==replace);
	pthread_t workers[5];struct stress_arg args[5];pthread_barrier_t barrier;
	CHECK(pthread_barrier_init(&barrier,NULL,6)==0);
	for (unsigned i=0;i<5;i++) {
		args[i]=(struct stress_arg){.fd=fd,.cpu=i,.loops=i==4 ? 1000 : 100,.writer=i==4,
			.address=(volatile uint64_t *)((char *)base+i*page_size),.barrier=&barrier};
		CHECK(pthread_create(&workers[i],NULL,stress_worker,&args[i])==0);
	}
	pthread_barrier_wait(&barrier);
	for (unsigned i=0;i<5;i++) CHECK(pthread_join(workers[i],NULL)==0 && !args[i].error);
	CHECK(pthread_barrier_destroy(&barrier)==0);
	if (backend==MF_TC) CHECK(ioctl(fd,MF_DOWNGRADE_ONCE)==-1 && errno==EOPNOTSUPP);
	else CHECK(ioctl(fd,MF_DOWNGRADE_ONCE)==0);
	CHECK(munmap(base,8*page_size)==0);
	struct mf_stats s;CHECK(ioctl(fd,MF_STATS,&s)==0);
	CHECK(!s.vmas && !s.active_probe && !s.context_errors && !s.data_errors && !s.fallback);
	CHECK(s.reads==s.read_ends && s.writes==s.write_ends && s.scopes==5 && s.scope_ends==5);
	CHECK(s.epoch==(backend==MF_TC ? 1000U : 1001U) && s.downgrades==(backend!=MF_TC));
	CHECK(s.faults>=408);
	printf("{\"event\":\"joined\",\"backend\":%u,\"faults\":%llu,\"epoch\":%llu,\"reads\":%llu,\"read_ends\":%llu,\"writes\":%llu,\"write_ends\":%llu,\"scopes\":%llu,\"scope_ends\":%llu,\"downgrades\":%llu,\"vmas\":%llu,\"errors\":%llu}\n",backend,
	 (unsigned long long)s.faults,(unsigned long long)s.epoch,(unsigned long long)s.reads,
	 (unsigned long long)s.read_ends,(unsigned long long)s.writes,(unsigned long long)s.write_ends,
	 (unsigned long long)s.scopes,(unsigned long long)s.scope_ends,(unsigned long long)s.downgrades,
	 (unsigned long long)s.vmas,(unsigned long long)(s.context_errors+s.data_errors));
	CHECK(close(fd)==0);
	native_fallback(backend);vma_lifetime(backend);
	if (backend==MF_TC) {
		fd=create(backend,MF_DOWNGRADE|MF_ALLOW_FALLBACK,1,&c);
		CHECK(c.selected_backend==MF_NATIVE && c.fallback==1);
		CHECK(ioctl(fd,MF_DOWNGRADE_ONCE)==0 && close(fd)==0);
	}
	printf("{\"event\":\"complete\",\"passed\":true,\"backend\":%u,\"checks\":%u}\n",backend,checks);
	return 0;
}
