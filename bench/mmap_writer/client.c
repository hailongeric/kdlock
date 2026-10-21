// SPDX-License-Identifier: GPL-2.0
/* Native same-mm VMA transactions only: never access the mapped range. */
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
#include <sys/wait.h>
#include <unistd.h>
#include "mmap_writer_uapi.h"
#define MAX_WORKERS 60
static unsigned checks;
#define CHECK(x) do { checks++;if(!(x)) { fprintf(stderr,"FAIL line %d: %s errno=%d\n",__LINE__,#x,errno);exit(1); } } while(0)
static void pin(unsigned cpu)
{
	cpu_set_t set;CPU_ZERO(&set);CPU_SET(cpu,&set);
	CHECK(sched_setaffinity(0,sizeof(set),&set)==0 && sched_getcpu()==(int)cpu);
}
static struct mw_identity identity(int fd)
{
	struct mw_identity id;CHECK(ioctl(fd,MW_ID,&id)==0);
	CHECK(id.abi==MW_ABI && id.object && id.mm && id.mmap_lock && id.tgid==(uint64_t)getpid() && id.tid==(uint64_t)syscall(SYS_gettid));
	return id;
}
static struct mw_stats stats(int fd)
{
	struct mw_stats s;CHECK(ioctl(fd,MW_STATS,&s)==0);
	CHECK(!s.faults && !s.context_errors && s.maps+s.clones==s.closes+s.vmas);
	return s;
}
static void print_stats(const char *event,const struct mw_stats *s)
{
	printf("{\"event\":\"%s\",\"object\":%llu,\"maps\":%llu,\"clones\":%llu,\"closes\":%llu,\"vmas\":%llu,\"faults\":%llu,\"context_errors\":%llu,\"foreign_rejects\":%llu,\"contended_mmaps\":%llu,\"observe\":%llu}\n",event,
	 (unsigned long long)s->object,(unsigned long long)s->maps,(unsigned long long)s->clones,(unsigned long long)s->closes,
	 (unsigned long long)s->vmas,(unsigned long long)s->faults,(unsigned long long)s->context_errors,
	 (unsigned long long)s->foreign_rejects,(unsigned long long)s->contended_mmaps,(unsigned long long)s->observe);
}
static void print_identity(const char *event,const struct mw_identity *id)
{
	printf("{\"event\":\"%s\",\"object\":%llu,\"mm\":%llu,\"mmap_lock\":%llu,\"tgid\":%llu,\"tid\":%llu}\n",event,
	 (unsigned long long)id->object,(unsigned long long)id->mm,(unsigned long long)id->mmap_lock,
	 (unsigned long long)id->tgid,(unsigned long long)id->tid);
}
static void scope_checks(int fd)
{
	struct mw_stats before=stats(fd);
	/* A child has a new mm while retaining the same VFS file. Both paths
	 * must reject it; shared descriptor identity alone is not shared-mm proof. */
	pid_t child=fork();CHECK(child>=0);
	if(!child) {
		struct mw_identity id;int error=0;
		if(ioctl(fd,MW_ID,&id)!=-1 || errno!=EXDEV)error=1;
		void *p=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0);
		if(p!=MAP_FAILED || errno!=EXDEV)error=2;
		if(p!=MAP_FAILED)munmap(p,4096);
		if(close(fd))error=3;
		_exit(error);
	}
	int status;CHECK(waitpid(child,&status,0)==child && WIFEXITED(status) && !WEXITSTATUS(status));
	CHECK(mmap(NULL,4096,PROT_READ|PROT_WRITE,MAP_SHARED,fd,0)==MAP_FAILED && errno==EOPNOTSUPP);
	CHECK(mmap(NULL,4096,PROT_READ,MAP_PRIVATE,fd,0)==MAP_FAILED && errno==EOPNOTSUPP);
	CHECK(mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,MW_MAX_PAGES*4096)==MAP_FAILED && errno==EINVAL);
	void *p=mmap(NULL,8192,PROT_READ,MAP_SHARED,fd,0);CHECK(p!=MAP_FAILED);
	CHECK(mprotect(p,4096,PROT_READ|PROT_WRITE)==-1 && errno==EACCES);
	CHECK(mprotect(p,4096,PROT_NONE)==0); /* A real native VMA split, no access. */
	struct mw_stats split=stats(fd);
	CHECK(split.maps-before.maps==1 && split.clones-before.clones==1 && split.vmas==2);
	CHECK(munmap(p,4096)==0 && munmap((char *)p+4096,4096)==0);
	struct mw_stats after=stats(fd);
	CHECK(after.maps-before.maps==1 && after.clones-before.clones==1 && after.closes-before.closes==2 &&
	      after.foreign_rejects-before.foreign_rejects==2 && !after.vmas);
	print_stats("scope_after",&after);
}
struct worker {
	unsigned cpu;int fd,lifetime,error;uint64_t iterations,completed;
	_Atomic int done;
	struct mw_identity expected,observed;
	pthread_barrier_t *ready,*go;
};
static void barrier(pthread_barrier_t *b)
{
	int rc=pthread_barrier_wait(b);
	if(rc && rc!=PTHREAD_BARRIER_SERIAL_THREAD) { fprintf(stderr,"barrier failed %d\n",rc);exit(1); }
}
static void *worker(void *argument)
{
	struct worker *w=argument;void *vma=NULL;cpu_set_t set;
	CPU_ZERO(&set);CPU_SET(w->cpu,&set);
	if(sched_setaffinity(0,sizeof(set),&set) || sched_getcpu()!=(int)w->cpu ||
	   prctl(PR_SET_NAME,"mw_worker",0,0,0))w->error=1;
	if(ioctl(w->fd,MW_ID,&w->observed) || w->observed.abi!=MW_ABI ||
	   w->observed.mm!=w->expected.mm || w->observed.mmap_lock!=w->expected.mmap_lock ||
	   w->observed.object!=w->expected.object || w->observed.tgid!=(uint64_t)getpid() ||
	   w->observed.tid!=(uint64_t)syscall(SYS_gettid))w->error=2;
	if(w->lifetime && !w->error) {
		vma=mmap(NULL,4096,PROT_READ,MAP_SHARED,w->fd,(off_t)w->cpu*4096);
		if(vma==MAP_FAILED) { vma=NULL;w->error=3; }
	}
	if(w->lifetime && close(w->fd))w->error=4;
	barrier(w->ready);barrier(w->go);
	if(w->lifetime) {
		if(vma && munmap(vma,4096))w->error=5;
		if(!w->error)w->completed=1;
	} else {
		for(uint64_t i=0;i<w->iterations && !w->error;i++) {
			vma=mmap(NULL,4096,PROT_READ,MAP_SHARED,w->fd,(off_t)w->cpu*4096);
			if(vma==MAP_FAILED) { w->error=6;break; }
			if(munmap(vma,4096)) { w->error=7;break; }
			w->completed++;
		}
		if(close(w->fd))w->error=8;
	}
	if(sched_getcpu()!=(int)w->cpu)w->error=9;
	atomic_store_explicit(&w->done,1,memory_order_release);
	return NULL;
}

static void json_string(const char *text)
{
	putchar('"');
	for(;*text;text++) {
		if(*text=='\n')fputs("\\n",stdout);
		else if(*text=='"' || *text=='\\') { putchar('\\');putchar(*text); }
		else if((unsigned char)*text<32)printf("\\u%04x",(unsigned char)*text);
		else putchar(*text);
	}
	putchar('"');
}
static int writer_contention(struct worker *workers,unsigned n)
{
	/* A nonempty rwsem queue may contain readers. Capture a real blocked
	 * writer whose immediate native caller takes this mm's mmap_lock. */
	int found=0;unsigned observations[MAX_WORKERS]={0};
	for(;;) {
		unsigned done=0;
		for(unsigned i=0;i<n;i++) {
			if(atomic_load_explicit(&workers[i].done,memory_order_acquire)) { done++;continue; }
			char path[96],buffer[4096];
			snprintf(path,sizeof(path),"/proc/self/task/%llu/stack",(unsigned long long)workers[i].observed.tid);
			int fd=open(path,O_RDONLY|O_CLOEXEC);
			if(fd<0 && errno==ENOENT && atomic_load_explicit(&workers[i].done,memory_order_acquire))continue;
			CHECK(fd>=0);ssize_t bytes=read(fd,buffer,sizeof(buffer)-1);CHECK(close(fd)==0 && bytes>=0);
			buffer[bytes]=0;
			/* Retain bounded nonempty raw observations even when the expected
			 * stack shape is absent. A failed probe must remain diagnosable. */
			if(bytes && observations[i]<4) {
				printf("{\"event\":\"stack_observation\",\"tid\":%llu,\"raw_stack\":",(unsigned long long)workers[i].observed.tid);
				json_string(buffer);printf("}\n");observations[i]++;
			}
			char *lock=strstr(buffer,"down_write_killable+");
			char *caller=lock ? strchr(lock,'\n') : NULL;
			if(caller && strstr(buffer,"rwsem_down_write_slowpath+")) {
				caller++;
				char *end=strchr(caller,'\n');if(end)*end=0;
				const char *name=strstr(caller,"vm_mmap_pgoff+") ? "vm_mmap_pgoff" :
				                 strstr(caller,"__vm_munmap+") ? "__vm_munmap" : NULL;
				if(end)*end='\n';
				if(name && !found) {
					printf("{\"event\":\"writer_stack\",\"tid\":%llu,\"mm\":%llu,\"mmap_lock\":%llu,\"blocked\":\"rwsem_down_write_slowpath\",\"acquire\":\"down_write_killable\",\"caller\":\"%s\",\"raw_stack\":",
					 (unsigned long long)workers[i].observed.tid,(unsigned long long)workers[i].observed.mm,
					 (unsigned long long)workers[i].observed.mmap_lock,name);
					json_string(buffer);printf("}\n");
					found=1;
				}
			}
		}
		if(done==n || found)break;
		usleep(1000);
	}
	return found;
}
int main(int argc,char **argv)
{
	CHECK(argc==4);const char *mode=argv[1];unsigned n=strtoul(argv[2],NULL,10);
	uint64_t iterations=strtoull(argv[3],NULL,10);
	CHECK(n && n<=MAX_WORKERS && iterations && iterations<=10000000 && sysconf(_SC_PAGESIZE)==4096);
	CHECK(!strcmp(mode,"scope") || !strcmp(mode,"cycle") || !strcmp(mode,"lifetime") || !strcmp(mode,"exit"));
	pin(63);int fd=open("/dev/kd_mmap_writer_native",O_RDWR|O_CLOEXEC);CHECK(fd>=0);
	struct mw_identity id=identity(fd);print_identity("identity",&id);
	if(!strcmp(mode,"scope")) {
		scope_checks(fd);CHECK(close(fd)==0);
		printf("{\"event\":\"complete\",\"mode\":\"scope\",\"passed\":true,\"checks\":%u}\n",checks);return 0;
	}
	if(!strcmp(mode,"exit")) {
		void *vma=mmap(NULL,4096,PROT_READ,MAP_SHARED,fd,0);CHECK(vma!=MAP_FAILED);
		struct mw_stats s=stats(fd);CHECK(s.maps==s.vmas && s.vmas==1 && !s.closes && !s.clones);
		print_stats("before_exit",&s);CHECK(close(fd)==0);
		printf("{\"event\":\"complete\",\"mode\":\"exit\",\"passed\":true,\"checks\":%u}\n",checks);fflush(stdout);
		_exit(0); /* Native exit_mmap must close the sole VMA and final file. */
	}
	int lifetime=!strcmp(mode,"lifetime");if(lifetime)CHECK(iterations==1);
	struct worker w[MAX_WORKERS];pthread_t threads[MAX_WORKERS];pthread_barrier_t ready,go;
	CHECK(pthread_barrier_init(&ready,NULL,n+1)==0 && pthread_barrier_init(&go,NULL,n+1)==0);
	for(unsigned i=0;i<n;i++) {
		w[i]=(struct worker){.cpu=i,.fd=dup(fd),.lifetime=lifetime,.iterations=iterations,.expected=id,.ready=&ready,.go=&go};
		CHECK(w[i].fd>=0);
	}
	for(unsigned i=0;i<n;i++)CHECK(pthread_create(&threads[i],NULL,worker,&w[i])==0);
	barrier(&ready);
	struct mw_stats before=stats(fd);print_stats("before",&before);
	CHECK(!before.foreign_rejects && before.maps==(lifetime?n:0) && before.vmas==before.maps && !before.clones && !before.closes);
	for(unsigned i=0;i<n;i++)CHECK(!w[i].error);
	if(lifetime)CHECK(close(fd)==0); /* Every descriptor is now closed. */
	barrier(&go);uint64_t completed=0;
	int contention_ok=lifetime || n==1 || writer_contention(w,n);
	for(unsigned i=0;i<n;i++) {
		CHECK(pthread_join(threads[i],NULL)==0 && !w[i].error && w[i].completed==iterations);
		for(unsigned j=0;j<i;j++)CHECK(w[j].observed.tid!=w[i].observed.tid);
		completed+=w[i].completed;
	}
	CHECK(pthread_barrier_destroy(&ready)==0 && pthread_barrier_destroy(&go)==0);
	if(!lifetime) {
		struct mw_stats after=stats(fd);print_stats("after",&after);
		CHECK(after.maps==after.closes && after.maps==completed && !after.clones && !after.vmas && !after.foreign_rejects);
		if(after.observe && n>1)CHECK(after.contended_mmaps>0);
		CHECK(close(fd)==0);
	}
	printf("{\"event\":\"complete\",\"mode\":\"%s\",\"passed\":%s,\"joined\":%u,\"completed\":%llu,\"checks\":%u,\"workers\":[",mode,contention_ok?"true":"false",n,(unsigned long long)completed,checks);
	for(unsigned i=0;i<n;i++)printf("%s{\"cpu\":%u,\"tid\":%llu,\"tgid\":%llu,\"mm\":%llu,\"mmap_lock\":%llu,\"object\":%llu,\"completed\":%llu,\"errors\":%d}",i?",":"",i,
	 (unsigned long long)w[i].observed.tid,(unsigned long long)w[i].observed.tgid,(unsigned long long)w[i].observed.mm,
	 (unsigned long long)w[i].observed.mmap_lock,(unsigned long long)w[i].observed.object,(unsigned long long)w[i].completed,w[i].error);
	printf("]}\n");
	/* Join and retain exact teardown evidence before reporting a missing
	 * writer observation. Failure still fails the case and the campaign. */
	CHECK(contention_ok);return 0;
}
