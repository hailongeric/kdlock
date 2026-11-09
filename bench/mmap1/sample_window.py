"""Line-delivered sample boundaries for the unchanged mmap1 executable."""
import errno
import os
import pty
import re
import select
import threading
import time


class SampleWindow:
    def __init__(self, log, warmup, measured, observer=None):
        self.master, self.slave = pty.openpty()
        # The reader owns its descriptor even if the caller's context exits.
        try:
            self.log = os.fdopen(os.dup(log.fileno()), 'w')
        except BaseException:
            os.close(self.master)
            os.close(self.slave)
            raise
        self.warmup, self.measured = warmup, measured
        self.observer = observer
        self.samples, self.events, self.errors = 0, [], []
        self.stop = threading.Event()
        self.thread = threading.Thread(target=self.read, name='mmap1-samples', daemon=True)

    def start(self):
        os.close(self.slave)
        self.slave = None
        self.thread.start()

    def line(self, raw):
        line = raw.decode('ascii').rstrip('\r')
        self.log.write(line + '\n')
        self.log.flush()
        if not re.fullmatch(r'min:\d+ max:\d+ total:\d+', line):
            return
        self.samples += 1
        if self.samples not in (self.warmup, self.warmup + self.measured):
            return
        event = dict(boundary='begin' if self.samples == self.warmup else 'end',
                     sample=self.samples, line_received_ns=time.monotonic_ns())
        if self.observer is not None:
            event['observation'] = self.observer()
        event['observation_finished_ns'] = time.monotonic_ns()
        self.events.append(event)

    def read(self):
        pending = b''
        try:
            while not self.stop.is_set():
                if not select.select([self.master], [], [], 0.1)[0]:
                    continue
                try:
                    data = os.read(self.master, 65536)
                except OSError as error:
                    if error.errno == errno.EIO:
                        break
                    raise
                if not data:
                    break
                pending += data
                while b'\n' in pending:
                    line, pending = pending.split(b'\n', 1)
                    self.line(line)
            if pending:
                raise ValueError('incomplete final upstream line')
        except BaseException as error:
            self.errors.append(repr(error))
        finally:
            os.close(self.master)
            self.log.close()

    def abort(self):
        if self.slave is not None:
            os.close(self.slave)
            self.slave = None
        if self.thread.ident is None:
            os.close(self.master)
            self.log.close()
            return True
        self.stop.set()
        self.thread.join(5)
        return not self.thread.is_alive()

    def finish(self):
        self.thread.join(5)
        if self.thread.is_alive() or self.errors or self.samples != self.warmup + self.measured:
            raise ValueError('sample observation incomplete: ' + repr(self.errors))
        if [event['boundary'] for event in self.events] != ['begin', 'end']:
            raise ValueError('sample boundaries incomplete')
        return dict(transport='pty', samples=self.samples, events=self.events,
                    scope='after delivered last warmup line through delivered final measured line',
                    limit='transport and callback latency; counters are not sampled atomically with application counters')
