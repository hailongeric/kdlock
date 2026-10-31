#!/usr/bin/env python3
"""VM-only replay of exact retained baseline writer sites and positive chains."""
import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import types

sys.dont_write_bytecode = True
BASELINE_COMMIT = '7814c61a0be20f5db3b9fb41b6079ef6d2938b5f'
CANDIDATE_COMMIT = '9d10ae77290873df23804293f364862a2b55f385'
ARCHIVE_SHA = '6b11ca66a1c785cf4a450bf79d9700b858a56efd3260849054e1e19ebcf9d955'
PINS = {'baseline_source': {'bench/mmap_writer/sites.py': '0ccaddc017a9fa77e2ebfb59da0c787a6d45779aec4ccc52c6a3ceacf4ee60c0', 'bench/mmap_writer/client.c': 'edfd54bc5419238df07f69ed2c7a69332b5c30d95ece2525d17297ff5d1a7ab2', 'tests/kernel/mmap_lock/mapping.py': '349d02f2933a945f66c3961f5371b8c4aa42f0962bb5edfac3b8b3b9a961b882', 'workload_modules/mmap_writer/mmap_writer_uapi.h': 'ddc60bcc7fcbcd0f083612fae02cc6140e6841c8a431f03d0d3fbceeba119699'}, 'candidate_source': {'bench/mmap_writer/sites.py': '7ff361262b68dab48d75062a9f0d5f3ebbd6fdd7986626420d71faf269061fe4', 'bench/mmap_writer/client.c': 'd2011b7d84268388ec74308607ae6ceaa6676731b4e492da469277aef2910a92', 'tests/kernel/mmap_lock/mapping.py': '1794da4a7a541f8420a8705bbbc05a5b840c2a919c77b32bf23edfe209725936', 'workload_modules/mmap_writer/mmap_writer_uapi.h': 'ddc60bcc7fcbcd0f083612fae02cc6140e6841c8a431f03d0d3fbceeba119699'}, 'baseline_files': {'sites/run/writer-sites.json': '488a6a489caca01bac974a7ce09c0f5faa7cc20c3248e7c73d936ec5d3282491', 'mapping/run/result.json': '3cfc1375ce781dd41e725073985f1f29346f0b5ddf6ddfa18da9ca471ca00cc5', 'strict-hold/run/result.json': 'bc28387235e74aaf25b881e43b4b7e0d159b1b53877d875a04a93df99ce073f8', 'mapping/run/00-scope-1.jsonl': '1e4c2f5e8a219b47e444009a62a53e2dc65c1c4990f60239b6989fceffe64e8e', 'mapping/run/01-cycle-1.jsonl': '67f67ce0ebda46152f62a2909daa8ad1fed708e4d40a5ba566a8a6c72ff7893f', 'mapping/run/02-cycle-16.jsonl': '85d5a19dfb652b3c13549de6a4f8995eeb28d88975485d57606e503d7b3fcdea', 'mapping/run/03-lifetime-1.jsonl': 'de7f81697b0bd01a34f4a3e7aaa3be0a1fedc11f67feb5361457a930858cb17a', 'mapping/run/04-lifetime-16.jsonl': 'f8cfd77cc138ed5ff005cc5d16aa1b67eb299be635e9f9e4e1bdc66312cc5e6f', 'mapping/run/05-exit-1.jsonl': '04d2415c6639f122453edf5c102f7c4339486db29bfb3985c28e398d6c904f9c', 'strict-hold/run/mmap.jsonl': '3749c50c2a813ff2d0d898f9a405c117e1673462202c5779f34c269a8f798259', 'strict-hold/run/munmap.jsonl': '4110f5d7a0376cb3169085b2b95898f5d9d6f00d4a6ec6c27a4f3c345b6177a8'}}


def need(condition, message):
    if not condition:
        raise RuntimeError(message)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_functions(path, names, context):
    tree = ast.parse(path.read_text())
    nodes = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
    need({node.name for node in nodes} == set(names), 'exact function extraction differs')
    exec(compile(ast.Module(body=nodes, type_ignores=[]), str(path), 'exec'), context)
    return context


def ast_function(path, name):
    return ast.dump(next(node for node in ast.parse(path.read_text()).body
                        if isinstance(node, ast.FunctionDef) and node.name == name))


PROC = r'''
static const char *fixture_samples[7];
static struct worker *fixture_worker;
static unsigned fixture_reads;
static int proc_text(uint64_t tid,const char *name,char *buffer,size_t size)
{
    static const char *names[]={"stat","wchan","schedstat","stack","schedstat","wchan","stat"};
    CHECK(fixture_reads<7 && tid==fixture_worker->observed.tid && !strcmp(name,names[fixture_reads]));
    CHECK(strlen(fixture_samples[fixture_reads])<size);
    strcpy(buffer,fixture_samples[fixture_reads]);
    if(++fixture_reads==7)atomic_store_explicit(&fixture_worker->done,1,memory_order_release);
    return 1;
}
'''
MAIN = r'''
#undef main
int main(int argc,char **argv)
{
    CHECK(argc==18);
    struct worker w={0};fixture_worker=&w;
    chain_waiter=argv[1];chain_acquire=argv[5];chain_adapter=strtoul(argv[4],NULL,10);
    chain_wait[0]=strtoul(argv[2],NULL,10);chain_wait[1]=strtoul(argv[3],NULL,10);
    w.observed.tid=strtoull(argv[8],NULL,10);w.observed.mm=strtoull(argv[9],NULL,10);
    w.observed.mmap_lock=strtoull(argv[10],NULL,10);
    for(unsigned i=0;i<7;i++)fixture_samples[i]=argv[11+i];
    int accepted=writer_contention(&w,1,strtoul(argv[6],NULL,10),strtoul(argv[7],NULL,10));
    printf("{\"event\":\"fixture_result\",\"accepted\":%s,\"reads\":%u}\n",accepted?"true":"false",fixture_reads);
    return accepted?0:1;
}
'''


def main():
    p = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-source', 'source', 'baseline-arm', 'baseline-archive-index', 'output'):
        p.add_argument('--'+name, type=Path, required=True)
    p.add_argument('--boot-id', required=True)
    a = p.parse_args()
    need(os.geteuid() == 0 and os.uname().release == '7.0.0-38-kdscope3' and
         Path('/proc/sys/kernel/random/boot_id').read_text().strip() == a.boot_id,
         'actual candidate VM boot required')
    out = a.output.resolve()
    need(not out.exists() and not any(out.is_relative_to(root.resolve()) for root in
         (a.source, a.baseline_source, a.baseline_arm)), 'new external replay output required')
    out.mkdir(parents=True)
    result = dict(schema=1, kind='writer-sites-baseline-compatibility', completed=False,
        passed=False, drained=False, final_idle=False, drain_unknown=False, replay_only=True,
        timing=False, baseline_scores_repeated=False, performance_accepted=False,
        baseline_harness_commit=BASELINE_COMMIT, candidate_harness_commit=CANDIDATE_COMMIT,
        baseline_archive_sha256=ARCHIVE_SHA, boot_id=a.boot_id, script_sha256=sha(__file__),
        final_idle_scope='replay compiler and classifier children only', started=time.time())
    def save():
        (out/'result.json').write_text(json.dumps(result, sort_keys=True, indent=2)+'\n')
    def run(argv, name, timeout):
        with (out/(name+'.stdout')).open('xb') as stdout, (out/(name+'.stderr')).open('xb') as stderr:
            child = subprocess.Popen(list(map(str, argv)), stdout=stdout, stderr=stderr)
            result['child_pid'] = child.pid; result['drain_unknown'] = True; save()
            try:
                code = child.wait(timeout=timeout)
            except subprocess.TimeoutExpired:
                result['drain_unknown'] = True
                raise RuntimeError('replay child deadline; process retained')
        result['drain_unknown'] = False
        result['child_returncode'] = code
        need(code == 0, 'replay child failed: '+name)
        return (out/(name+'.stdout')).read_text()
    save()
    try:
        need(sha(a.baseline_archive_index) == ARCHIVE_SHA, 'original baseline archive index differs')
        for label, root in (('baseline_source', a.baseline_source), ('candidate_source', a.source)):
            for name, digest in PINS[label].items():
                need(sha(root/name) == digest, 'source leaf differs: '+label+'/'+name)
        for name, digest in PINS['baseline_files'].items():
            need(sha(a.baseline_arm/name) == digest, 'original baseline bytes differ: '+name)
        result['input_sha256'] = PINS
        sites = json.loads((a.baseline_arm/'sites/run/writer-sites.json').read_bytes())
        mapping = json.loads((a.baseline_arm/'mapping/run/result.json').read_bytes())
        strict = json.loads((a.baseline_arm/'strict-hold/run/result.json').read_bytes())
        need(mapping['passed'] and mapping['drained'] and strict['passed'] and strict['drained'] and
             mapping['boot_id'] == strict['boot_id'] == '971baf1a-f9b2-4689-9937-62ab79f4ade2',
             'original completed functional receipts differ')
        result.update(mapping_result_sha256=sha(a.baseline_arm/'mapping/run/result.json'),
            strict_hold_result_sha256=sha(a.baseline_arm/'strict-hold/run/result.json'),
            writer_sites_sha256=sha(a.baseline_arm/'sites/run/writer-sites.json'))
        functions = {'function_rows','call_returns','call_return','linked_edge','waiter_argument',
                     'gate_chain','derive_shared'}
        contexts = {}
        for label, root in (('baseline', a.baseline_source), ('candidate', a.source)):
            names = functions | ({'wait_arguments'} if label == 'candidate' else set())
            context = dict(re=re, rt=types.SimpleNamespace(require=need, digest=sha),
                CALLERS=('vm_mmap_pgoff','__vm_munmap'), ACQUIRE='down_write_killable',
                SUPPORT=('down_write_killable','rwsem_down_write_slowpath','in_sched_functions',
                         'stack_trace_consume_entry_nosched','stack_trace_save_tsk'))
            source_functions(root/'bench/mmap_writer/sites.py', names, context)
            target = out/(label+'-assembly'); target.mkdir()
            def saved_assembly(argv, path, timeout=120):
                name = Path(path).name
                original = a.baseline_arm/'sites/run'/name
                need(name in sites['outputs'] and sha(original) == sites['outputs'][name],
                     'captured assembly differs: '+name)
                Path(path).write_bytes(original.read_bytes())
                return original.read_text()
            derived = context['derive_shared']('saved-baseline-vmlinux-not-executed', target, saved_assembly)
            need(derived == {key: sites[key] for key in derived}, 'baseline site replay changed')
            contexts[label] = context
        chain = sites['chains']['kd']
        legacy_args = list(map(str, chain['wait_returns']))
        need(len(legacy_args) == 2 and contexts['candidate']['wait_arguments'](chain) == legacy_args,
             'baseline argument form changed')
        for name in ('chain_proof','validate','reject_mutations'):
            need(ast_function(a.baseline_source/'tests/kernel/mmap_lock/mapping.py', name) ==
                 ast_function(a.source/'tests/kernel/mmap_lock/mapping.py', name), 'proof function changed: '+name)
        old_client = (a.baseline_source/'bench/mmap_writer/client.c').read_text()
        new_client = (a.source/'bench/mmap_writer/client.c').read_text()
        for start, end in (('static void json_string(', 'static int proc_text('),
                           ('static int chain_frame(', 'static const char *writer_chain_tail('),
                           ('static void writer_observation(', '/* Called only after successful joins')):
            need(old_client[old_client.index(start):old_client.index(end)] ==
                 new_client[new_client.index(start):new_client.index(end)], 'observation body changed: '+start)
        need(old_client.split('static char task_state(', 1)[1].split('\n}', 1)[0] ==
             new_client.split('static char task_state(', 1)[1].split('\n}', 1)[0], 'state decoder changed')
        proof = source_functions(a.source/'tests/kernel/mmap_lock/mapping.py', {'chain_proof'},
            dict(re=re, rt=types.SimpleNamespace(require=need), SITES=sites))['chain_proof']
        positives = []
        for name in PINS['baseline_files']:
            if name.endswith('.jsonl'):
                rows = [json.loads(line) for line in (a.baseline_arm/name).read_text().splitlines()]
                for row in rows:
                    if row.get('event') == 'writer_stack':
                        proof(row, 'kd')
                        observation = next((r for r in rows if r.get('event') == 'stack_observation' and
                            r.get('classifier_accepts') and r['raw_stack'] == row['raw_stack'] and r['tid'] == row['tid']), None)
                        positives.append((name, row, observation))
        need(len(positives) == 3, 'exact three original positive chains required')
        need(sum(observation is not None for _, _, observation in positives) == 2,
             'exact two complete original proc observations required')
        python_checked = [dict(input=name, caller=row['caller'], waiter=row['waiter'],
            wait_return_offset=row['wait_return_offset'], full_proc_input_retained=observation is not None)
            for name, row, observation in positives]
        binaries = {}
        for label, root in (('baseline', a.baseline_source), ('candidate', a.source)):
            text = (root/'bench/mmap_writer/client.c').read_text()
            start, end = 'static int proc_text(', 'static char task_state('
            need(text.count(start) == text.count(end) == 1, 'proc-input extraction differs')
            source = out/(label+'-classifier.c')
            main_body = MAIN
            if label == 'candidate':
                main_body = main_body.replace(
                    'chain_wait[0]=strtoul(argv[2],NULL,10);chain_wait[1]=strtoul(argv[3],NULL,10);',
                    'CHECK(chain_wait_arguments(argv[2],argv[3]));')
            source.write_text('#define main original_client_main\n'+text[:text.index(start)]+PROC+text[text.index(end):]+main_body)
            binary = out/(label+'-classifier')
            run(['gcc','-O2','-Wall','-Wextra','-Werror','-pthread',
                 '-I'+str(root/'workload_modules/mmap_writer'),source,'-o',binary],label+'-build',60)
            binaries[label] = binary
        checked = []
        for index, (name, row, observation) in enumerate(positives):
            if observation is None:
                continue
            sample = [observation[key] for key in ('stat_before','wchan_before','schedstat_before',
                'raw_stack','schedstat_after','wchan_after','stat_after')]
            args = [contexts['candidate']['waiter_argument'](chain), *legacy_args,
                chain['adapter_return'], sites['adapter'], sites['sites']['vm_mmap_pgoff']['return_offset'],
                sites['sites']['__vm_munmap']['return_offset'], row['tid'], row['mm'], row['mmap_lock'], *sample]
            outputs = {label: run([binary, *args], f'{index}-{label}', 10) for label, binary in binaries.items()}
            need(outputs['baseline'] == outputs['candidate'], 'original positive classifier outputs differ')
            replay = [json.loads(line) for line in outputs['candidate'].splitlines()]
            need(replay[-1] == dict(event='fixture_result', accepted=True, reads=7), 'classifier did not finish')
            actual = next(r for r in replay if r.get('event') == 'writer_stack')
            need(actual == row, 'positive writer record differs from original')
            checked.append(dict(input=name, caller=row['caller'], waiter=row['waiter'],
                wait_return_offset=row['wait_return_offset'], output_sha256=hashlib.sha256(outputs['candidate'].encode()).hexdigest()))
        need(Path('/proc/sys/kernel/random/boot_id').read_text().strip() == a.boot_id, 'boot changed')
        result.update(completed=True, passed=True, drained=True, final_idle=True,
            legacy_argument_form_unchanged=True, observation_functions_unchanged=True,
            complete_site_receipt_unchanged=True, replayed_python_positive_chains=python_checked,
            replayed_c_positive_chains=checked,
            original_receipts_unchanged=True, timing_reused_without_modification=True)
        for name, digest in PINS['baseline_files'].items():
            need(sha(a.baseline_arm/name) == digest, 'baseline input changed during replay')
    except BaseException as error:
        result.update(error=repr(error), completed=False, passed=False)
        raise
    finally:
        result['finished'] = time.time(); save()
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
