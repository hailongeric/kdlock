"""Guest-only canonical mutex publication, terminal retirement and slot reuse.

The guarded queue publishes both links before becoming visible. Delayed MCS
predecessor publication is retired; six controls check the current obligations.
"""
from test_wait_queue import replace_function, replace_once, run_cases


def main():
    mutations = {
        'incomplete-singleton': lambda source: replace_once(
            source, 'node->next = node;', 'node->next = NULL;'),
        'missing-forward-publication': lambda source: replace_once(
            source, 'head->prev->next = node;', 'head->prev->next = head;'),
        'terminal-head-not-retired': lambda source: replace_once(
            source, 'WRITE_ONCE(*queue->head, NULL);', '(void)queue;'),
        'head-successor-lost': lambda source: replace_function(
            source, 'void kd_wait_unlink_locked(',
            'WRITE_ONCE(*queue->head, node->next);', 'WRITE_ONCE(*queue->head, NULL);'),
        'old-generation-matches-reuse': lambda source: replace_once(
            source, 'request->generation == generation && node->generation == generation', 'true'),
        'acquisition-membership-not-retired': lambda source: replace_function(
            source, 'void kd_wait_unlink_locked(',
            'if (request->acquisition == node)', 'if (false && request->acquisition == node)'),
    }
    run_cases(head_only=True, mutations=mutations)


if __name__ == '__main__':
    main()
