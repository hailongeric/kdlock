#!/usr/bin/env python3
# mon.py CMD...: send QEMU monitor commands one at a time in one session.
import socket, sys, time
s = socket.socket(socket.AF_UNIX); s.connect("/tmp/qemu-claude-monitor.sock"); s.settimeout(2)
def drain():
    out = b""
    try:
        while True:
            d = s.recv(65536)
            if not d: break
            out += d
            if out.endswith(b"(qemu) "): break
    except socket.timeout:
        pass
    return out.decode(errors="replace")
drain()
for c in sys.argv[1:]:
    s.sendall((c + "\n").encode()); time.sleep(0.3)
    o = drain()
    import re; print("##", c); print(re.sub(r"\x1b\[[0-9;]*[A-Za-z]", "", o).replace("\r", ""))
