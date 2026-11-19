#!/usr/bin/env python3
"""drop_sites.py STATE...: drop the images of every site named in the
daemon state files, so that the next daemon starts from no images (a
daemon that exits leaves its images loaded)."""
import json
import sys

sys.path.insert(0, "/root/host_fs/kdlock/jit")
from kdjit.kernel import Device  # noqa: E402

dev = Device("/dev/kdlock")
n = 0
for path in sys.argv[1:]:
    for site in json.load(open(path))["sites"]:
        try:
            dev.site_drop(int(site))
            n += 1
        except OSError:
            pass
print("dropped %d sites" % n)
