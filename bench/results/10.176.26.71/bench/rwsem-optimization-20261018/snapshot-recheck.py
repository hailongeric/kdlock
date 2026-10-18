#!/usr/bin/env python3
"""Read-only QEMU monitor check; closes its own client without sending quit."""
import json
import re
import socket
import time


tag = 'before-mutex-kdonly-20261017T140354Z'
deadline = time.monotonic() + 10


def read_prompt(client):
    chunks = []
    while time.monotonic() < deadline:
        chunk = client.recv(65536)
        if not chunk:
            raise RuntimeError('Monitor closed before returning a prompt')
        chunks.append(chunk)
        if b'(qemu)' in b''.join(chunks):
            return b''.join(chunks)
    raise TimeoutError('Monitor prompt deadline exceeded')


with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
    client.settimeout(3)
    client.connect('/tmp/qemu-monitor.sock')
    banner = read_prompt(client)
    client.sendall(b'info snapshots\n')
    response = read_prompt(client).decode(errors='replace')
clean = re.sub(r'\x1b\[[0-9;?]*[A-Za-z]', '', response).replace('\r', '')
rows = [line for line in clean.splitlines() if tag in line]
found = any(re.match(r'^\s*(?:\d+|--)\s+' + re.escape(tag) + r'\s', line) for line in rows)
print(json.dumps(dict(command='info snapshots', snapshot=tag, listed_snapshot=found,
    banner=banner.decode(errors='replace'), response=response, matching_rows=rows,
    scope='Read-only after-run recheck of the existing recovery snapshot; no save, load, stop or quit command.'),
    indent=2))
raise SystemExit(0 if found else 1)
