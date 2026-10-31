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
/* Optional exact integration chain, independently decoded from its kernel ELF.
 * The six-argument recovery-kernel interface retains its original proof. */
static const char *chain_waiter, *chain_acquire;
static unsigned long chain_wait[2], chain_adapter;
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
static int proc_text(uint64_t tid,const char *name,char *buffer,size_t size)
{
	char path[128];snprintf(path,sizeof(path),"/proc/self/task/%llu/%s",(unsigned long long)tid,name);
	int fd=open(path,O_RDONLY|O_CLOEXEC);
	if(fd<0 && errno==ENOENT)return 0;
	CHECK(fd>=0);ssize_t bytes=read(fd,buffer,size-1);int saved=errno;
	CHECK(close(fd)==0);if(bytes<0 && saved==ESRCH)return 0;
	CHECK(bytes>=0);buffer[bytes]=0;return 1;
}
static char task_state(const char *text)
{
	const char *end=strrchr(text,')');return end && end[1]==' ' ? end[2] : '?';
}
static int chain_frame(const char **text, char symbol[64], unsigned long *offset)
{
	const char *top = strstr(*text, "] ");
	if (!top || sscanf(top + 2, "%63[^+]+0x%lx/", symbol, offset) != 2)
		return 0;
	const char *next = strchr(top, '\n');
	*text = next ? next + 1 : top + strlen(top);
	return 1;
}
static const char *writer_chain_tail(const char **remaining, char symbol[64],
		unsigned long *offset, const char *waiter, unsigned long wait_offset)
{
	/* A bounded ELF-derived extension carries real intermediate CALL returns.
	 * Tail jumps have no return word and are absent from this stack description.
	 * The same parser serves the retained diagnostic and positive classifier. */
	size_t length=strcspn(chain_waiter,"|");
	if(strlen(waiter)!=length || strncmp(waiter,chain_waiter,length) ||
	   (wait_offset!=chain_wait[0] && wait_offset!=chain_wait[1]))
		return "waiter_symbol_or_return";
	const char *next=chain_waiter+length;
	unsigned depth=0;
	while(*next) {
		if(*next++!='|' || ++depth>6)return "intermediate_description";
		const char *at=strchr(next,'@');
		if(!at || at==next || (size_t)(at-next)>=64)return "intermediate_description";
		char expected[64];memcpy(expected,next,(size_t)(at-next));expected[at-next]=0;
		for(const char *p=expected;*p;p++)
			if(!((*p>='a' && *p<='z') || (*p>='A' && *p<='Z') ||
			     (*p>='0' && *p<='9') || *p=='_'))return "intermediate_description";
		unsigned long returns[2];unsigned count=0;
		next=at+1;
		do {
			char *end;errno=0;
			if(count==2 || *next<'0' || *next>'9')return "intermediate_description";
			returns[count]=strtoul(next,&end,10);
			if(errno || !returns[count++])return "intermediate_description";
			next=end;
			if(*next!=':')break;
			next++;
		} while(1);
		if(*next && *next!='|')return "intermediate_description";
		if(!chain_frame(remaining,symbol,offset) || strcmp(symbol,expected) ||
		   (*offset!=returns[0] && (count!=2 || *offset!=returns[1])))
			return "intermediate_symbol_or_return";
	}
	if(strcmp(waiter,chain_acquire)) {
		if(!chain_frame(remaining,symbol,offset) || strcmp(symbol,chain_acquire) || *offset!=chain_adapter)
			return "adapter_symbol_or_return";
	}
	if(!chain_frame(remaining,symbol,offset))return "caller_frame";
	return NULL;
}
static void writer_observation(uint64_t tid,const char *first,const char *last,
		const char *chan1,const char *chan2,const char *sched1,const char *sched2,
		const char *buffer,unsigned long mmap_site,unsigned long munmap_site)
{
	/* Diagnostic replay of already captured bytes only. The original classifier
	 * below remains authoritative; these fields neither admit nor retry work.
	 * Keep the existing four nonempty observations per worker output bound. */
	char symbol[64]={0},waiter[64]={0};unsigned long offset=0,wait_offset=0;
	const char *remaining=buffer,*chain_error=NULL,*reasons[10];unsigned count=0;
	int site=0;
	if(!chain_frame(&remaining,symbol,&offset)) { chain_error="first_frame";goto emit; }
	strcpy(waiter,symbol);wait_offset=offset;
	if(chain_waiter) {
		chain_error=writer_chain_tail(&remaining,symbol,&offset,waiter,wait_offset);
		if(chain_error)goto emit;
	}
	site=(!strcmp(symbol,"vm_mmap_pgoff") && offset==mmap_site) ||
	     (!strcmp(symbol,"__vm_munmap") && offset==munmap_site);
emit:
	if(chain_error)reasons[count++]=chain_error;
	if(!site)reasons[count++]="caller_site";
	if(task_state(first)!='D')reasons[count++]="state_before";
	if(task_state(last)!='D')reasons[count++]="state_after";
	if(strcmp(chan1,waiter))reasons[count++]="wchan_before";
	if(strcmp(chan2,waiter))reasons[count++]="wchan_after";
	if(strcmp(sched1,sched2))reasons[count++]="schedstat_changed";
	if(!*sched1)reasons[count++]="schedstat_empty";
	printf("{\"event\":\"stack_observation\",\"tid\":%llu,\"diagnostic_only\":true,\"classifier_accepts\":%s,\"rejections\":[",
	 (unsigned long long)tid,count?"false":"true");
	for(unsigned i=0;i<count;i++) { if(i)putchar(',');json_string(reasons[i]); }
	printf("],\"state_before\":\"%c\",\"state_after\":\"%c\",\"stat_before\":",task_state(first),task_state(last));
	json_string(first);printf(",\"stat_after\":");json_string(last);
	printf(",\"wchan_before\":");json_string(chan1);printf(",\"wchan_after\":");json_string(chan2);
	printf(",\"schedstat_before\":");json_string(sched1);printf(",\"schedstat_after\":");json_string(sched2);
	printf(",\"waiter\":");json_string(waiter);
	printf(",\"wait_return_offset\":%lu,\"last_parsed_symbol\":",wait_offset);json_string(symbol);
	printf(",\"last_parsed_offset\":%lu,\"expected_mmap_return\":%lu,\"expected_munmap_return\":%lu,\"raw_stack\":",
	 offset,mmap_site,munmap_site);json_string(buffer);printf("}\n");
}
static int writer_contention(struct worker *workers,unsigned n,unsigned long mmap_site,unsigned long munmap_site)
{
	/* /proc stacks deliberately omit __sched lock helpers. Bind the first
	 * remaining return PC to an independently decoded down_write_killable
	 * call in this exact kernel ELF. Bracket it with sleeping task state,
	 * the same wait channel, and unchanged scheduler execution counters.
	 * A generic rwsem queue, arbitrary mmap frame, or running task fails. */
	unsigned observations[MAX_WORKERS]={0};
	for(;;) {
		unsigned done=0;
		for(unsigned i=0;i<n;i++) {
			struct worker *w=&workers[i];
			if(atomic_load_explicit(&w->done,memory_order_acquire)) { done++;continue; }
			uint64_t tid=w->observed.tid;
			char first[4096],last[4096],chan1[128],chan2[128],sched1[256],sched2[256],buffer[4096];
			if(!proc_text(tid,"stat",first,sizeof(first)) || !proc_text(tid,"wchan",chan1,sizeof(chan1)) ||
			   !proc_text(tid,"schedstat",sched1,sizeof(sched1)) || !proc_text(tid,"stack",buffer,sizeof(buffer)) ||
			   !proc_text(tid,"schedstat",sched2,sizeof(sched2)) || !proc_text(tid,"wchan",chan2,sizeof(chan2)) ||
			   !proc_text(tid,"stat",last,sizeof(last))) {
				CHECK(atomic_load_explicit(&w->done,memory_order_acquire));continue;
			}
			if(*buffer && observations[i]<4) {
				writer_observation(tid,first,last,chan1,chan2,sched1,sched2,buffer,mmap_site,munmap_site);
				observations[i]++;
			}
			char symbol[64], waiter[64];unsigned long offset=0,wait_offset=0;
			const char *remaining=buffer;
			if(!chain_frame(&remaining,symbol,&offset))continue;
			strcpy(waiter,symbol);wait_offset=offset;
			if(chain_waiter) {
				if(writer_chain_tail(&remaining,symbol,&offset,waiter,wait_offset))continue;
			}
			int site=(!strcmp(symbol,"vm_mmap_pgoff") && offset==mmap_site) ||
			         (!strcmp(symbol,"__vm_munmap") && offset==munmap_site);
			if(!site || task_state(first)!='D' || task_state(last)!='D' ||
			   strcmp(chan1,waiter) || strcmp(chan2,waiter) || strcmp(sched1,sched2) || !*sched1)continue;
			printf("{\"event\":\"writer_stack\",\"proof\":\"%s\",\"tid\":%llu,\"mm\":%llu,\"mmap_lock\":%llu,\"acquire\":\"%s\",\"caller\":\"%s\",\"return_offset\":%lu,\"state_before\":\"D\",\"state_after\":\"D\",\"wchan_before\":",
			 chain_waiter?"EXACT_MMAP_WRITER_CHAIN":"FILTERED_SCHED_RETURN_SITE",
			 (unsigned long long)tid,(unsigned long long)w->observed.mm,(unsigned long long)w->observed.mmap_lock,
			 chain_acquire?chain_acquire:"down_write_killable",symbol,offset);
			json_string(chan1);printf(",\"wchan_after\":");json_string(chan2);
			if(chain_waiter) {
				printf(",\"waiter\":");json_string(waiter);
				printf(",\"wait_return_offset\":%lu,\"adapter_return_offset\":%lu",wait_offset,chain_adapter);
			}
			printf(",\"schedstat_before\":");json_string(sched1);printf(",\"schedstat_after\":");json_string(sched2);
			printf(",\"raw_stack\":");json_string(buffer);printf("}\n");return 1;
		}
		if(done==n)return 0;
		usleep(1000);
	}
}

/* Called only after successful joins, callback checks and final close. The
 * prospective policy changes the observational verdict, never those checks. */
static int emit_completion(const char *mode, int contention_ok, int functional,
		struct worker *w, unsigned n, uint64_t completed)
{
	int passed=contention_ok || functional;
	printf("{\"event\":\"complete\",\"mode\":\"%s\",\"passed\":%s,\"joined\":%u,\"completed\":%llu,\"checks\":%u,",
	 mode,passed?"true":"false",n,(unsigned long long)completed,checks);
	if(functional)printf("\"eligibility_policy\":\"mmap-functional-v1\",\"functional_complete\":true,\"writer_observation\":\"%s\",",
	 contention_ok?"observed":"inconclusive");
	printf("\"workers\":[");
	for(unsigned i=0;i<n;i++)printf("%s{\"cpu\":%u,\"tid\":%llu,\"tgid\":%llu,\"mm\":%llu,\"mmap_lock\":%llu,\"object\":%llu,\"completed\":%llu,\"errors\":%d}",i?",":"",i,
	 (unsigned long long)w[i].observed.tid,(unsigned long long)w[i].observed.tgid,(unsigned long long)w[i].observed.mm,
	 (unsigned long long)w[i].observed.mmap_lock,(unsigned long long)w[i].observed.object,(unsigned long long)w[i].completed,w[i].error);
	printf("]}\n");fflush(stdout);return passed;
}

int main(int argc,char **argv)
{
	CHECK(argc==6 || argc==11 || argc==13);
	int functional=argc==13;
	if(functional)CHECK(!strcmp(argv[11],"--eligibility-policy") && !strcmp(argv[12],"mmap-functional-v1"));
	const char *mode=argv[1];unsigned n=strtoul(argv[2],NULL,10);
	if(argc>=11) {
		chain_waiter=argv[6];chain_wait[0]=strtoul(argv[7],NULL,0);chain_wait[1]=strtoul(argv[8],NULL,0);
		chain_adapter=strtoul(argv[9],NULL,0);chain_acquire=argv[10];
		CHECK(*chain_waiter && *chain_acquire && chain_wait[0] && chain_wait[1] && chain_adapter);
	}
	uint64_t iterations=strtoull(argv[3],NULL,10);
	CHECK(n && n<=MAX_WORKERS && iterations && iterations<=10000000 && sysconf(_SC_PAGESIZE)==4096);
	CHECK(!strcmp(mode,"scope") || !strcmp(mode,"cycle") || !strcmp(mode,"lifetime") || !strcmp(mode,"exit"));
	if(functional)CHECK(!strcmp(mode,"cycle") && n>1);
	unsigned long mmap_site=strtoul(argv[4],NULL,0),munmap_site=strtoul(argv[5],NULL,0);
	CHECK(mmap_site && munmap_site);
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
	int contention_ok=lifetime || n==1 || writer_contention(w,n,mmap_site,munmap_site);
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
	/* Join and retain exact teardown evidence before reporting a missing
	 * writer observation. Strict mode still fails the case and campaign. */
	int completion_ok=emit_completion(mode,contention_ok,functional,w,n,completed);
	if(functional)CHECK(completion_ok);else CHECK(contention_ok);return 0;
}
