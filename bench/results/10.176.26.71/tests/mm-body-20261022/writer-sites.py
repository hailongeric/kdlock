#!/usr/bin/env python3
"""Source-host static ELF inspection; emit exact mmap writer-chain bindings."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--elf', type=Path, required=True)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    a = parser.parse_args()
    assert os.uname().nodename == '380G10'
    manifest = json.loads(a.manifest.read_text())
    assert sha(a.elf) == manifest['build_files']['vmlinux']
    assert not a.output.exists()
    a.output.mkdir()
    names = ('kd_mmap_write_lock_killable', 'kd_mmap_down_write_killable',
             'vm_mmap_pgoff', '__vm_munmap')
    calls, hashes = {}, {}
    for name in names:
        raw = subprocess.check_output(['objdump', '-dr', '--disassemble=' + name, str(a.elf)])
        path = a.output / (name + '.asm')
        path.write_bytes(raw)
        hashes[path.name] = sha(path)
        text = raw.decode()
        entries = re.findall(r'^([0-9a-f]+) <' + re.escape(name) + r'>:$', text, re.M)
        assert len(entries) == 1, name
        base = int(entries[0], 16)
        rows = []
        for line in text.splitlines():
            match = re.match(r'\s*([0-9a-f]+):\s*((?:[0-9a-f]{2} )+)\s*callq?\s+[0-9a-f]+ <([^>]+)>', line)
            if match:
                address, encoded, target = match.groups()
                end = int(address, 16) + len(encoded.split())
                rows.append(dict(instruction=line.strip(), return_address=hex(end),
                                 return_offset=end - base, target=target))
        calls[name] = rows

    def selected(name, target, count):
        rows = [r for r in calls[name] if r['target'] == target]
        assert len(rows) == count, (name, target, rows)
        return rows

    adapter = names[0]
    kd = selected(adapter, names[1], 1)[0]
    native = selected(adapter, 'down_write_killable', 1)[0]
    waits = selected(names[1], 'schedule', 2)
    result = dict(source_host_only=True, vmlinux_sha256=sha(a.elf),
                  kernel_build_id=manifest['running']['build_id'], adapter=adapter,
                  disassembly_sha256=hashes,
                  sites={name: selected(name, adapter, 1)[0] for name in names[2:]},
                  chains=dict(kd=dict(adapter_return=kd['return_offset'], waiter=names[1],
                                      wait_returns=[r['return_offset'] for r in waits],
                                      instructions=waits + [kd]),
                              native=dict(adapter_return=native['return_offset'], waiter=adapter,
                                          wait_returns=[native['return_offset']] * 2,
                                          instructions=[native])))
    (a.output / 'writer-sites.json').write_text(json.dumps(result, indent=2, sort_keys=True) + '\n')
    print(json.dumps(result, indent=2))


if __name__ == '__main__':
    main()
