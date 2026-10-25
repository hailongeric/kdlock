"""IPC fixture only: no mmap, ioctl, module, observer or timing workload."""
import json
import os
import socket
import sys

mode = sys.argv[1]
control = socket.socket(fileno=int(sys.argv[-1]))
control.settimeout(2)
source = control.makefile('rb', buffering=0)
print(json.dumps(dict(event='ready', identity={})), flush=True)
control.sendall(b'MW1 PREPARED\n')
if source.readline() != b'MW1 GO\n':
    sys.exit(2)
control.sendall(b'MW1 STARTED\n')
if mode == 'premature':
    print(json.dumps(dict(event='measurement')), flush=True)
    sys.exit(1)
token = '0123456789abcdef'
control.sendall(('MW1 FINISHED ' + token + '\n').encode())
if mode == 'ambiguous':
    print(json.dumps(dict(event='measurement', complete=True)), flush=True)
if source.readline() != ('MW1 EXPORT ' + token + '\n').encode():
    sys.exit(3)
if mode == 'large':
    print('x' * (1024 * 1024 + 1), flush=True)
else:
    print(json.dumps(dict(event='measurement', complete=True)), flush=True)
control.close()
