"""Entry and returned-body evidence for matched real API benchmarks."""


def jit_evidence(entries, completed, eligible, *, enabled):
    """A published image or an entry witness alone is not a returned body."""
    if not 0 <= completed <= entries <= eligible:
        raise ValueError('invalid JIT entry/completion accounting')
    if not enabled and (entries or completed):
        raise ValueError('non-KD control executed JIT')
    return dict(jit_bodies=entries, jit_completions=completed,
                jit_eligible_operations=eligible,
                jit_share=entries / eligible if eligible else 0,
                jit_complete_share=completed / eligible if eligible else 0,
                jit_status=('PASS' if completed else 'PARTIAL_JIT' if entries else 'NO_JIT')
                    if enabled else 'NOT_APPLICABLE')


def helper_ready(registry, evidence):
    return (len(registry) == 1 and registry[0]['status'] == 0 and
            evidence['jit_completions'] > 0)
