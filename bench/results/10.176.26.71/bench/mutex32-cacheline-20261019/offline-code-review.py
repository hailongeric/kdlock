#!/usr/bin/env python3
"""Read-only ELF review; never load or execute an archived kernel module.

Run on 380G10 after the VM has built and frozen the inputs. Hash validation
against the archives/source manifests is a separate archive-review duty.
This script verifies symbol/call facts and retains disassembly for the manual
head-retirement control-flow and ownership-check review.
"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess


def digest(data):
    return hashlib.sha256(data).hexdigest()


def command(argv):
    raw = subprocess.check_output(argv, timeout=60)
    return raw.decode(), {'command': argv, 'stdout_sha256': digest(raw)}


def inspect_elf(path):
    path = path.resolve()
    symbols, nm = command(['nm', '-S', '--defined-only', str(path)])
    assembly, objdump = command(['objdump', '-dr', '--no-show-raw-insn', str(path)])
    table = {}
    for line in symbols.splitlines():
        words = line.split()
        if len(words) == 4:
            address, size, kind, name = words
            table[name] = {'address': '0x' + address, 'size': int(size, 16), 'kind': kind}
    functions = {}
    current = None
    for line in assembly.splitlines():
        match = re.match(r'^([0-9a-f]+) <([^>]+)>:$', line)
        if match:
            current = match[2]
            functions[current] = [line]
        elif line.startswith('Disassembly of section '):
            current = None
        elif current is not None:
            functions[current].append(line)
    return {
        'path': str(path), 'elf_sha256': digest(path.read_bytes()),
        'nm': nm, 'objdump': objdump, 'symbols': table, 'functions': functions,
    }


def function(elf, name):
    if name not in elf['functions']:
        raise ValueError(f'{name} is absent from {elf["path"]}')
    return elf['functions'][name]


def target_sites(elf, target, only=None):
    sites = []
    # Unlinked module calls ordinarily carry relocations; direct intra-unit
    # calls may already resolve to a named address. Preserve either form.
    reloc = re.compile(r'\bR_X86_64_\w+\s+' + re.escape(target) + r'(?:[-+]|\s|$)')
    resolved = re.compile(r'\b(?:call\w*|jmp\w*)\s+.*<' + re.escape(target) + r'(?:\+[^>]*)?>')
    for name, lines in elf['functions'].items():
        if only is not None and name != only:
            continue
        for index, line in enumerate(lines):
            if reloc.search(line) or resolved.search(line):
                sites.append({'function': name,
                              'lines': lines[max(0, index - 2):index + 3]})
    return sites


def describe(elf):
    return {key: elf[key] for key in ('path', 'elf_sha256', 'nm', 'objdump')}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('baseline-provider', 'candidate-provider',
                 'baseline-workload', 'candidate-workload'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        raise ValueError('preserve the existing review; choose a new output')
    elfs = {name: inspect_elf(getattr(args, name)) for name in (
        'baseline_provider', 'candidate_provider', 'baseline_workload', 'candidate_workload')}
    baseline = elfs['baseline_provider']
    candidate = elfs['candidate_provider']
    owned = 'kd_mutex_delegation_owned'
    hint = 'kd_mutex_combiner_active'
    checks = []

    def check(name, passed, evidence):
        checks.append({'name': name, 'passed': bool(passed), 'evidence': evidence})

    definition = candidate['symbols'].get(owned)
    check('candidate retains global external ownership predicate',
          definition is not None and definition['kind'] == 'T', definition)
    baseline_retirement = target_sites(baseline, owned, 'kd_mutex_execute_cs')
    check('baseline body contains the ownership predicate call',
          bool(baseline_retirement), baseline_retirement)
    candidate_retirement = target_sites(candidate, owned, 'kd_mutex_execute_cs')
    check('candidate body has no ownership predicate call',
          not candidate_retirement, candidate_retirement)
    # Routing is compiled separately and must still resolve the external body.
    routing = target_sites(candidate, owned, '__kd_mutex_unlock')
    check('separate routing still calls the external ownership predicate',
          bool(routing), routing)
    baseline_hints = target_sites(elfs['baseline_workload'], hint)
    check('baseline workload contains the combiner hint call',
          bool(baseline_hints), baseline_hints)
    candidate_hints = target_sites(elfs['candidate_workload'], hint)
    check('candidate workload has no combiner hint call',
          not candidate_hints, candidate_hints)
    workload_functions = sorted({site['function'] for site in baseline_hints})
    for name in workload_functions:
        function(elfs['candidate_workload'], name)
    for name in ('kd_mutex_execute_cs', '__kd_mutex_lock_slowpath'):
        # A missing function cannot turn an absence check into a pass.
        function(baseline, name)
        function(candidate, name)
    slow = function(candidate, '__kd_mutex_lock_slowpath')
    cas_windows = []
    for index, line in enumerate(slow):
        if 'cmpxchg' in line:
            cas_windows.append(slow[max(0, index - 18):index + 15])
    check('candidate head retains a tail cmpxchg instruction',
          any('0x1c(' in line and 'cmpxchg' in line for line in slow), cas_windows)
    report = {
        'passed_automated_symbol_checks': all(item['passed'] for item in checks),
        'script_sha256': digest(Path(__file__).read_bytes()),
        'inputs': {name: describe(elf) for name, elf in elfs.items()},
        'checks': checks,
        'disassembly': {
            'baseline_provider': {name: function(baseline, name) for name in (
                'kd_mutex_delegation_owned', 'kd_mutex_execute_cs', '__kd_mutex_lock_slowpath')},
            'candidate_provider': {name: function(candidate, name) for name in (
                'kd_mutex_delegation_owned', 'kd_mutex_execute_cs', '__kd_mutex_lock_slowpath')},
            'baseline_workload': {name: function(elfs['baseline_workload'], name)
                                  for name in workload_functions},
            'candidate_workload': {name: function(elfs['candidate_workload'], name)
                                   for name in workload_functions},
        },
        'manual_review_required': [
            'Trace successor-link nonzero branch around all tail accesses.',
            'Trace sampled foreign tail around CAS into the delayed-link wait.',
            'Trace matching sampled tail through CAS and both success/failure branches.',
            'Confirm entry and retirement retain owner identity, PICKUP, phase and separate physical-owner probes.',
            'Confirm the workload inline phase hint still declines only COMBINER and never grants ownership.',
        ],
        'limitations': [
            'This checks static ELF instruction/symbol facts, not live execution or performance.',
            'Instruction matching does not prove memory ordering, node lifetime or a control-flow invariant.',
            'VM tests and source/ELF archive binding remain separate evidence.',
        ],
    }
    args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + '\n')
    print(json.dumps({'passed_automated_symbol_checks': report['passed_automated_symbol_checks'],
                      'checks': len(checks), 'output': str(args.output)}))
    if not report['passed_automated_symbol_checks']:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
