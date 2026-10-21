#!/usr/bin/env python3
"""VM-only control tests; no host/guest connection or reboot is performed."""
import importlib.util
import json
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import Mock, patch

spec=importlib.util.spec_from_file_location('campaign',Path(__file__).with_name('campaign.py'))
c=importlib.util.module_from_spec(spec);spec.loader.exec_module(c)


class CampaignTests(unittest.TestCase):
    def test_reboot_disconnect_waits_for_changed_boot_without_resend(self):
        calls=[]
        def guest(command,path,*args,**kwargs):
            calls.append(command)
            path.write_text('old\n' if path.name in ('boot-before.log','boot-reachable-0.log') else 'new\n')
            return 255 if ' request ' in command else 0
        request=dict(passed=True,reboot_requested=True,mode='native',boot_id='old')
        with tempfile.TemporaryDirectory() as tmp, patch.object(c,'guest',side_effect=guest), \
             patch.object(c,'capture'),patch.object(c,'copy_in'),patch.object(c.time,'sleep'), \
             patch.object(c,'fetch',side_effect=[request,dict(boot_id='new')]):
            self.assertEqual(c.boot('native','/evidence/new',Path(tmp)),dict(boot_id='new'))
        self.assertEqual(sum(' request ' in x for x in calls),1)
        self.assertEqual(sum(' verify ' in x for x in calls),1)
        self.assertEqual(sum('cat /proc/sys/kernel/random/boot_id'==x for x in calls),3)

    def test_unchanged_boot_never_consumes_verify_path(self):
        calls=[]
        def guest(command,path,*args,**kwargs):
            calls.append(command);path.write_text('old\n');return 0
        with tempfile.TemporaryDirectory() as tmp, patch.object(c,'guest',side_effect=guest), \
             patch.object(c,'capture'),patch.object(c,'copy_in'),patch.object(c.time,'sleep'):
            with self.assertRaisesRegex(RuntimeError,'boot change unconfirmed'):
                c.boot('native','/evidence/new',Path(tmp))
        self.assertEqual(sum(' request ' in x for x in calls),1)
        self.assertFalse(any(' verify ' in x for x in calls))

    def test_timeout_retains_pid_and_never_kills(self):
        child=Mock(pid=123,returncode=None)
        child.communicate.side_effect=subprocess.TimeoutExpired(['test-child'],1)
        with tempfile.TemporaryDirectory() as tmp,patch.object(c.subprocess,'Popen',return_value=child):
            path=Path(tmp)/'command.log'
            with self.assertRaises(subprocess.TimeoutExpired):c.command(['test-child'],path,1)
            receipt=json.loads(path.with_suffix('.log.command.json').read_text())
        self.assertEqual(receipt['state'],'UNKNOWN_DRAIN')
        self.assertEqual(receipt['pid'],123)
        self.assertEqual(receipt['argv'],['test-child'])
        child.kill.assert_not_called();child.terminate.assert_not_called()

    def test_nonzero_requires_explicit_observation_mode(self):
        child=Mock(pid=123,returncode=255)
        with tempfile.TemporaryDirectory() as tmp,patch.object(c.subprocess,'Popen',return_value=child):
            with self.assertRaises(RuntimeError):c.command(['test-child'],Path(tmp)/'failed.log')
            self.assertEqual(c.command(['test-child'],Path(tmp)/'observed.log',allow_failure=True),255)


if __name__=='__main__':unittest.main()
