"""
version_cache.py - Persistent local cache of winget/choco version lookups.

Purpose: version checks shell out to winget/choco, which is slow (each
call can take up to 60s, choco retries up to 3x). Without this, every
app launch and every catalog refresh re-scrapes every app from scratch,
even though most versions don't change between one launch and the next.

This cache is written to <base_dir>/version_cache.json. On load, it lets
the UI show the last-known version for every app *immediately*, then a
capped background refresh quietly updates anything that's gone stale
instead of the user staring at a blank column while dozens of
winget/choco processes spin up.
"""

import json
import os
import threading
import time

# How long a cached entry is considered "fresh enough" that a normal
# (non-forced) background refresh will skip re-querying it over the
# network. A manual "Check Version" click bypasses this via force=True.
DEFAULT_STALE_AFTER_SECONDS = 6 * 60 * 60  # 6 hours


class VersionCache:
    """Thread-safe get/set over a small JSON file. Multiple background
    fetch threads may call set() concurrently, so writes are guarded by
    a lock; save() is meant to be called from one place (e.g. once a
    refresh batch completes) rather than after every single lookup, to
    keep disk I/O sane."""

    def __init__(self, base_dir):
        self.path = os.path.join(base_dir, 'version_cache.json')
        self._lock = threading.Lock()
        self._data = self._load()

    def _load(self):
        if os.path.exists(self.path):
            try:
                with open(self.path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    @staticmethod
    def key_for(provider, identifier):
        """provider: 'winget' or 'choco'; identifier: the winget_id/choco_id."""
        return f"{provider}:{identifier}"

    def get(self, provider, identifier):
        """Returns {'version': str, 'timestamp': float} or None."""
        if not identifier:
            return None
        with self._lock:
            entry = self._data.get(self.key_for(provider, identifier))
            return dict(entry) if entry else None

    def set(self, provider, identifier, version):
        if not identifier:
            return
        with self._lock:
            self._data[self.key_for(provider, identifier)] = {
                'version': version,
                'timestamp': time.time(),
            }

    def is_stale(self, provider, identifier, stale_after=DEFAULT_STALE_AFTER_SECONDS):
        entry = self.get(provider, identifier)
        if not entry:
            return True
        return (time.time() - entry.get('timestamp', 0)) >= stale_after

    def save(self):
        """Best-effort atomic write; a failure here should never crash
        the app, it just means the next session re-fetches more."""
        with self._lock:
            try:
                tmp_path = self.path + '.tmp'
                with open(tmp_path, 'w', encoding='utf-8') as f:
                    json.dump(self._data, f, indent=2)
                os.replace(tmp_path, self.path)
            except OSError:
                pass
