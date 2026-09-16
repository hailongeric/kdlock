"""Capture guest CPU topology without inferring NUMA nodes from CPU numbers."""

import os
import re
from pathlib import Path


def online_cpus(text):
    cpus = set()
    for part in text.strip().split(","):
        bounds = [int(value) for value in part.split("-")]
        assert 1 <= len(bounds) <= 2 and bounds[0] >= 0
        first, last = bounds[0], bounds[-1]
        assert first <= last
        cpus.update(range(first, last + 1))
    return sorted(cpus)


def validate_topology(placement, role_count):
    cpus, nodes = placement["role_cpus"], placement["role_nodes"]
    assert isinstance(cpus, list) and isinstance(nodes, list)
    assert len(cpus) == len(nodes) == role_count
    for values in (cpus, nodes, placement["allowed_cpus"], placement["online_cpus"]):
        assert isinstance(values, list)
        assert all(type(value) is int and value >= 0 for value in values)
    assert len(set(cpus)) == len(cpus), "roles need distinct CPUs"
    assert set(cpus) <= set(placement["allowed_cpus"]), "CPU outside caller affinity"
    assert set(cpus) <= set(placement["online_cpus"]), "offline CPU"


def capture_topology(cpus, cpu_root=Path("/sys/devices/system/cpu"), allowed_cpus=None):
    allowed = sorted(os.sched_getaffinity(0) if allowed_cpus is None else allowed_cpus)
    online = online_cpus((cpu_root / "online").read_text())
    nodes = []
    for cpu in cpus:
        found = list((cpu_root / f"cpu{cpu}").glob("node[0-9]*"))
        assert len(found) == 1 and re.fullmatch(r"node\d+", found[0].name), (
            "missing or ambiguous CPU NUMA node",
            cpu,
            found,
        )
        nodes.append(int(found[0].name[4:]))
    result = {
        "role_cpus": cpus,
        "role_nodes": nodes,
        "allowed_cpus": allowed,
        "online_cpus": online,
    }
    validate_topology(result, len(cpus))
    return result
