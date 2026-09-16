"""Hold a production inherited device lease after the compiler parent exits.

This is the compiler's substituted script, not a successful translation. Real
kcore reads and refused publication run through the actual source-control API.
"""

import errno
import hashlib
import json
import os
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "disassem"))
sys.path.insert(0, str(ROOT / "tests/protocols"))
import device_session as source
import memread
from native_only_protocol import NATIVE_ONLY, Packet


def publish(path, value):
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value))
    temporary.replace(path)


def main():
    out = Path(os.environ["KD_SESSION_PROBE"])
    inspected = False
    with source.session() as fd:
        # Capture the same inherited description's immutable contract before
        # parent exit; draining must neither revoke nor silently change it.
        stack_bytes = source.mutex_stack_bytes()
        assert stack_bytes == 256
        publish(
            out / "child.json",
            {"pid": os.getpid(), "fd": fd, "mutex_stack_bytes": stack_bytes},
        )
        deadline = time.monotonic() + 30
        while not (out / "release").exists():
            if time.monotonic() >= deadline:
                raise RuntimeError("orphan writer release timed out")
            if not inspected and (out / "inspect.json").exists():
                request = json.loads((out / "inspect.json").read_text())
                info = source.info(fd)
                assert info["state"] == source.DRAINING and info["writers"] == 1
                cached_bytes = source.mutex_stack_bytes()
                queried_bytes = source.query_mutex_stack_bytes(fd)
                assert cached_bytes == queried_bytes == stack_bytes
                data = memread.read_kernel_addr_data(request["address"], 16)
                assert len(data) == 16
                # A header-only refusal is a real publication request, without
                # uploading arbitrary instructions into a live executable block.
                try:
                    os.write(fd, bytes(Packet(NATIVE_ONLY, 0, request["entry"], 0)))
                except OSError as error:
                    assert error.errno == errno.ESHUTDOWN, error
                else:
                    raise AssertionError("publication accepted while draining")
                publish(
                    out / "inspected.json",
                    {
                        "info": source.info(fd),
                        "bytes": len(data),
                        "address": request["address"],
                        "entry": request["entry"],
                        "sha256": hashlib.sha256(data).hexdigest(),
                        "publication_errno": errno.ESHUTDOWN,
                        "mutex_stack_bytes": cached_bytes,
                        "queried_mutex_stack_bytes": queried_bytes,
                    },
                )
                inspected = True
            time.sleep(0.01)
        assert inspected, "writer released before draining inspection"
    publish(out / "closed.json", {"pid": os.getpid(), "closed": True})


if __name__ == "__main__":
    main()
