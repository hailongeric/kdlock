#!/usr/bin/env python3
"""Guest-only failure-path checks for the bounded held-session transport."""
import copy
import json
import os
import threading
import time
import unittest
from boundary_protocol import receive, validate_reply, host_hash


class BoundaryProtocol(unittest.TestCase):
    def exchange(self, pieces, **kwargs):
        read_fd, write_fd = os.pipe()
        def writer():
            try:
                for piece in pieces:
                    os.write(write_fd, piece)
                    time.sleep(.01)
            except BrokenPipeError:
                pass
            finally:
                os.close(write_fd)
        thread = threading.Thread(target=writer)
        thread.start()
        try:
            return receive(read_fd, **kwargs)
        finally:
            os.close(read_fd)
            thread.join()

    def test_partial_json_waits_for_complete_line(self):
        self.assertEqual(self.exchange([b'{"boundary_', b'ack":1}', b'\n']), {'boundary_ack': 1})

    def test_eof_partial_oversize_and_multiple_lines_refuse(self):
        for pieces, kwargs in [([], {}), ([b'{}'], {}), ([b'{bad}\n'], {}),
                               ([b'{}\n{}\n'], {}), ([b'12345'], {'maximum': 4})]:
            with self.subTest(pieces=pieces), self.assertRaises(ValueError):
                self.exchange(pieces, **kwargs)

    def test_live_silent_peer_has_bounded_timeout(self):
        read_fd, write_fd = os.pipe()
        try:
            with self.assertRaises(TimeoutError):
                receive(read_fd, seconds=.02)
        finally:
            os.close(read_fd)
            os.close(write_fd)

    def test_bound_snapshot_and_order(self):
        host = {'example': 1}
        reply = dict(boundary_ack=1, boundary_token='fresh', host_state=host,
            observations=[dict(capture='boundary-fresh-0', host_sha256=host_hash(host),
                capture_began_ns=20, capture_finished_ns=30, boundary_marker_ns=10,
                request_sent_ns=1, ack_received_ns=2)])
        self.assertEqual(validate_reply(reply, 'fresh'), reply)
        second = dict(reply, boundary_ack=2)
        self.assertEqual(validate_reply(second, 'fresh', 2), second)
        with self.assertRaises(ValueError):
            validate_reply(second, 'fresh', 1)
        with self.assertRaises(ValueError):
            validate_reply(reply, 'fresh', True)
        for key, value in [('boundary_ack', True), ('boundary_ack', 2),
                           ('boundary_token', 'stale'), ('observations', []), ('host_state', {'example': 2})]:
            changed = dict(reply, **{key: value})
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_reply(changed, 'fresh')
        for key, value in [('capture', 'boundary-stale-0'), ('capture_began_ns', 9),
                           ('capture_finished_ns', 19), ('request_sent_ns', 3)]:
            changed = copy.deepcopy(reply)
            changed['observations'][0][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                validate_reply(changed, 'fresh')


if __name__ == '__main__':
    unittest.main()
