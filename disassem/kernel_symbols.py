"""Reuse fixed core symbols for one translation; keep dynamic lookups live."""

from contextlib import contextmanager
from contextvars import ContextVar


_current = ContextVar('translation_core_symbols', default=None)


class CoreSymbols:
    def __init__(self):
        self._tokens = None
        self._attempted = False

    def _fill(self, opener):
        self._attempted = True
        tokens = {}
        complete = False
        try:
            with opener('/proc/kallsyms', 'r', encoding='utf-8', errors='ignore') as stream:
                for line in stream:
                    parts = line.split()
                    if len(parts) < 3:
                        continue
                    # A COMING module can briefly have an empty owner name.
                    # Only the built-in text endpoint proves this is still
                    # the fixed core prefix; an earlier owner disables reuse.
                    if len(parts) > 3:
                        return
                    tokens.setdefault(parts[2], parts[0])
                    if parts[2] == '_etext':
                        try:
                            start = int(tokens.get('_stext', '0'), 16)
                            end = int(tokens['_etext'], 16)
                        except ValueError:
                            return
                        complete = 0 < start < end
                        break
        except OSError:
            # Discard even a matched prefix if iteration or close failed.
            # The current and later calls use their own unchanged live scan.
            return
        if complete:
            self._tokens = tokens

    def lookup(self, name, default, *, opener, live):
        if not self._attempted:
            self._fill(opener)
        if self._tokens is not None:
            token = self._tokens.get(name)
            if token is not None:
                # Parsing remains name-local. A first zero blocks a later
                # duplicate, but zero results themselves always stay live.
                value = int(token, 16)
                if value:
                    return value
        return live(name, default)

    def discard(self):
        self._tokens = None
        self._attempted = True


def current():
    return _current.get()


@contextmanager
def translation_scope():
    """Create lazily used state on every call, including nested invocations."""
    cache = CoreSymbols()
    token = _current.set(cache)
    try:
        yield cache
    finally:
        cache.discard()
        _current.reset(token)
