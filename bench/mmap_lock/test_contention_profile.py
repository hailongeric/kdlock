"""VM-only checks of recorder failures and the frozen diagnostic command."""
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

import contention_profile as profile


class ProfileTests(unittest.TestCase):
    def test_command_keeps_frozen_work_and_placement(self):
        args = profile.perf_args('/frozen/client',Path('/evidence'))
        self.assertEqual(args[:3],['taskset','-c','63'])
        self.assertEqual(args[args.index('--')+1:],['/frozen/client','16','plain'])
        for key,value in (('--clockid','mono'),('-F','99'),('-e','cpu-clock:k'),('--call-graph','fp')):
            self.assertEqual(args[args.index(key)+1],value)
        self.assertIn('--inherit',args)
        self.assertIn('--kernel-callchains',args)
        self.assertIn('--strict-freq',args)
        self.assertIn('--no-buildid-cache',args)

    def test_timeout_does_not_signal_or_claim_drain(self):
        child = Mock(pid=123)
        child.wait.side_effect = subprocess.TimeoutExpired('perf',120)
        with tempfile.TemporaryDirectory() as folder, patch.object(profile.subprocess,'Popen',return_value=child):
            out = Path(folder)
            with self.assertRaises(profile.rt.Failure) as raised:
                profile.record_client(['perf'],out)
            self.assertTrue(raised.exception.unsafe)
            self.assertEqual(json.loads((out/'record-command.json').read_text())['state'],'UNKNOWN_DRAIN')
        child.kill.assert_not_called()
        child.terminate.assert_not_called()
        child.send_signal.assert_not_called()

    def test_recorder_failure_is_not_client_success(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(profile.subprocess,'Popen',return_value=Mock(pid=123,wait=Mock(return_value=1))):
            out = Path(folder)
            with self.assertRaises(profile.rt.Failure):
                profile.record_client(['perf'],out)
            self.assertEqual(json.loads((out/'record-command.json').read_text())['returncode'],1)

    def test_success_retains_exit_receipt_and_separate_logs(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(profile.subprocess,'Popen',return_value=Mock(pid=123,wait=Mock(return_value=0))) as launch:
            out = Path(folder)
            profile.record_client(['perf','--','client'],out)
            row = json.loads((out/'record-command.json').read_text())
            self.assertEqual((row['state'],row['returncode']),('EXITED',0))
            self.assertGreaterEqual(row['finished_ns'],row['started_ns'])
            self.assertNotEqual(launch.call_args.kwargs['stdout'].name,launch.call_args.kwargs['stderr'].name)


if __name__ == '__main__':
    unittest.main(verbosity=2)
