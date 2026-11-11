#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-2.0
"""kdlock translator daemon.

Drains events from /dev/kdlock, keeps cumulative per-site knowledge, and
publishes one image per contended lock call site.

  REQUEST          a site is contended and has no image: build one.
  MISS_CODE/IND/RET  generated code met a target it does not know: add it
                   to the site's knowledge and rebuild.
  SITE_OFF         the kernel switched a site off because most sections
                   were handed back; a rebuild with new knowledge switches
                   it on again, otherwise it stays off.
  TEXT_GONE        module text went away and the kernel dropped every
                   image: forget what was learned about that range and
                   republish the rest.

Every build is based on one text generation; if modules come or go before
the image is loaded, the kernel refuses it and the site is built again.

The kernel never waits for this process. A section that meets unknown code
is handed back to its own task; the daemon only improves later runs.

Knowledge is stored per kernel release in a JSON file, so a restart resumes
with everything learned so far. It is keyed by text address and therefore
discarded when the release string changes.
"""

import argparse
import errno
import json
import os
import signal
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from kdjit.kernel import (Device, KernelView, KD_EV_MISS_CODE, KD_EV_MISS_IND,  # noqa: E402
                          KD_EV_MISS_RET, KD_EV_REQUEST, KD_EV_SITE_OFF, KD_EV_TEXT_GONE)
from kdjit.translator import Learned, TranslationError, Translator  # noqa: E402


class Daemon:
    def __init__(self, args):
        self.args = args
        self.dev = Device(args.device)
        self.info = self.dev.info()
        self.kv = KernelView(self.dev)
        config = {}
        if args.config:
            with open(args.config) as f:
                config = json.load(f)
        self.translator = Translator(self.kv, self.info, config)
        self.release = os.uname().release
        self.sites = {}         # site -> Learned
        self.dirty = {}         # site -> time of first unprocessed change
        self.failed = set()     # sites the translator could not handle
        self.stop = False
        self._load_state()

    # ---- persistent knowledge -------------------------------------------------

    def _load_state(self):
        path = self.args.state
        if not path or not os.path.exists(path):
            return
        with open(path) as f:
            data = json.load(f)
        if data.get("release") != self.release:
            print("state file is for %s, ignoring" % data.get("release"))
            return
        for site, learned in data.get("sites", {}).items():
            self.sites[int(site)] = Learned.from_json(learned)
        # Republish everything known: images do not survive a reboot.
        now = time.monotonic()
        for site in self.sites:
            self.dirty[site] = now - self.args.settle

    def _save_state(self):
        path = self.args.state
        if not path:
            return
        data = {"release": self.release,
                "sites": {str(s): l.to_json() for s, l in self.sites.items()}}
        tmp = path + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f)
        os.replace(tmp, path)

    # ---- events ---------------------------------------------------------------

    def _mark(self, site):
        self.dirty.setdefault(site, time.monotonic())

    def _text_gone(self, start, end):
        """The kernel dropped all images; [start, end) no longer exists."""
        def keep(a):
            return not start <= a < end

        for site in list(self.sites):
            if not keep(site):
                del self.sites[site]
                self.dirty.pop(site, None)
                continue
            learned = self.sites[site]
            learned.code = {a for a in learned.code if keep(a)}
            for table in (learned.ind, learned.ret):
                for k in list(table):
                    table[k] = {a for a in table[k] if keep(a)}
                    if not keep(k) or not table[k]:
                        del table[k]
            self._mark(site)
        self.failed = {s for s in self.failed if keep(s)}
        if self.args.verbose:
            print("text %#x-%#x gone; republishing %d sites" % (start, end, len(self.sites)))

    def _where(self, addr):
        if not addr:
            return "-"
        f = self.kv.func_of(addr)
        names = self.kv.names(f) if f is not None else ()
        return "%s+%#x" % (names[0], addr - f) if names else "%#x" % addr

    def handle(self, event):
        kind, _cpu, site, ip, target = event
        if kind == KD_EV_TEXT_GONE:
            self._text_gone(site, ip)
            return
        if site in self.failed:
            return
        if kind == KD_EV_REQUEST:
            # The kernel only asks for a site that has no image (new, or
            # dropped with its text), so always build it.
            self.sites.setdefault(site, Learned())
            self._mark(site)
            return
        learned = self.sites.setdefault(site, Learned())
        if self.args.verbose and kind in (KD_EV_MISS_CODE, KD_EV_MISS_IND, KD_EV_MISS_RET):
            names = {KD_EV_MISS_CODE: "code", KD_EV_MISS_IND: "ind", KD_EV_MISS_RET: "ret"}
            print("site %#x: miss %s at %s -> %s" %
                  (site, names[kind], self._where(ip), self._where(target)))
        if kind == KD_EV_MISS_CODE:
            if ip not in learned.code:
                learned.code.add(ip)
                self._mark(site)
        elif kind == KD_EV_MISS_IND:
            if target not in learned.ind[ip]:
                learned.ind[ip].add(target)
                self._mark(site)
        elif kind == KD_EV_MISS_RET:
            if target not in learned.ret[ip]:
                learned.ret[ip].add(target)
                self._mark(site)
        elif kind == KD_EV_SITE_OFF and self.args.verbose:
            print("site %#x switched off by the kernel" % site)

    # ---- publication ----------------------------------------------------------

    def publish(self, site, gen):
        """Build, link for the kernel-chosen address, and load one image."""
        try:
            image = self.translator.build(site, self.sites[site])
            image_id, base = self.dev.image_alloc(image.size)
            text, entry = image.link(base)
            self.dev.image_load(image_id, site, entry, text, gen)
        except OSError as err:
            if err.errno == errno.ESTALE:
                # Modules came or went during the build: build again.
                self._mark(site)
                return
            if err.errno == errno.ENOENT:
                # The site's text is gone; TEXT_GONE also reports it.
                self.sites.pop(site, None)
                return
            print("site %#x: %s" % (site, err))
            self.failed.add(site)
            return
        except TranslationError as err:
            print("site %#x: %s" % (site, err))
            self.failed.add(site)
            return
        if self.args.verbose:
            print("site %#x: %d instructions, %d bytes at %#x" %
                  (site, image.insns, len(text), base))

    def run(self):
        if self.args.enable:
            self.dev.enable(True)
        while not self.stop:
            events = self.dev.events()
            for event in events:
                self.handle(event)

            # Let a burst of reports for one site settle into a single build.
            now = time.monotonic()
            ready = [s for s, t in self.dirty.items() if now - t >= self.args.settle]
            if ready:
                # Text may have been patched or modules may have changed.
                gen = self.kv.sync()
                for site in ready:
                    del self.dirty[site]
                    if site in self.sites and site not in self.failed:
                        self.publish(site, gen)
                self._save_state()
            if not events:
                time.sleep(self.args.poll)
        if self.args.enable:
            self.dev.enable(False)
        self._save_state()


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--device", default="/dev/kdlock")
    ap.add_argument("--state", default="/var/lib/kdlock/learned.json",
                    help="cumulative knowledge file ('' to disable)")
    ap.add_argument("--config", help="JSON overriding translator policy lists and budgets")
    ap.add_argument("--poll", type=float, default=0.01, help="idle poll interval, seconds")
    ap.add_argument("--settle", type=float, default=0.05,
                    help="delay between a site's first new report and its rebuild")
    ap.add_argument("--no-enable", dest="enable", action="store_false",
                    help="do not switch delegation on at start / off at exit")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    if args.state:
        os.makedirs(os.path.dirname(args.state) or ".", exist_ok=True)
    daemon = Daemon(args)

    def stop(_sig, _frame):
        daemon.stop = True

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)
    daemon.run()


if __name__ == "__main__":
    main()
