"""
results.py - Unified per-item result tracking across every engine
(apps, tweaks, scripts, activators, backup/restore).

Why this exists: each engine loop in install_engine.py only ever tracked
*aggregate* counts per operation category (e.g. "3 of 5 apps failed" on
self.status_list), overwriting the per-item message on every iteration.
The instant an item's turn passed, its individual result was gone except
as a line that had already scrolled by in the log. Both the post-run
HTML report and "Retry Failed" need one durable record per individual
item for the whole run - this is that record.

retry_data carries whatever InstallEngine needs to replay this exact
item later (the resolved command, the tweak dict, the script item, the
activator + switch, ...) so "Retry Failed" doesn't have to re-derive
anything from a display name string.
"""

from dataclasses import dataclass, field, asdict
import datetime
import json
import os
from typing import Optional, Any, Dict, List

STATUS_SUCCESS = 'success'
STATUS_FAILED = 'failed'
STATUS_SKIPPED = 'skipped'

_STATUS_TO_BADGE = {
    STATUS_SUCCESS: ('Success', 'good'),
    STATUS_FAILED: ('Failed', 'bad'),
    STATUS_SKIPPED: ('Skipped', 'warn'),
}


@dataclass
class ResultItem:
    category: str                       # "App", "Tweak", "Script", "Activator", "Backup Restore", ...
    name: str                           # display name shown to the user
    status: str                         # STATUS_SUCCESS | STATUS_FAILED | STATUS_SKIPPED
    message: str = ""                   # captured output / error / note (this is the thing that used to be lost)
    source: str = ""                    # e.g. "Winget: 7zip.7zip", a script path, a backup zip path
    dest: str = ""                      # e.g. restore destination, when that's meaningful for this category
    duration: Optional[float] = None
    timestamp: str = field(default_factory=lambda: datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'))
    retry_data: Optional[Dict[str, Any]] = None

    @property
    def success(self) -> bool:
        return self.status == STATUS_SUCCESS

    @property
    def is_retryable(self) -> bool:
        return self.status == STATUS_FAILED and self.retry_data is not None

    def badge(self):
        """Returns (label, css_class) for the HTML report renderer."""
        return _STATUS_TO_BADGE.get(self.status, ('Unknown', 'neutral'))


class ResultsCollector:
    """Accumulates ResultItems for one deployment run. Thread-agnostic by
    design - InstallEngine's deployment thread is the only writer during
    a run, so no locking here; if that ever changes, add a lock.

    Previously this was purely in-memory, so a crash mid-run lost every
    result even though the human-readable text log survived (the logger's
    FileHandler already flushes per line). reset(live_log_path=...) makes
    the structured results live too: each add() is written to an
    append-only JSONL file and flushed immediately, so what actually
    happened up to the crash is recoverable, and it's the foundation a
    future "resume this deployment" feature would read from."""

    def __init__(self):
        self.items: List[ResultItem] = []
        self.started_at: Optional[str] = None
        self.finished_at: Optional[str] = None
        self.live_log_path: Optional[str] = None
        self._live_file = None

    def reset(self, live_log_path: Optional[str] = None):
        self._close_live_file()
        self.items = []
        self.started_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.finished_at = None
        self.live_log_path = live_log_path
        if live_log_path:
            out_dir = os.path.dirname(live_log_path)
            if out_dir:
                os.makedirs(out_dir, exist_ok=True)
            try:
                self._live_file = open(live_log_path, 'a', encoding='utf-8')
                self._write_live_event({'event': 'run_started', 'started_at': self.started_at})
            except OSError:
                self._live_file = None

    def resume_live_log(self):
        """Reopens live_log_path in append mode without clearing self.items
        - used when a later retry pass wants its outcomes persisted into
        the same run's live log, since mark_finished() closes the file at
        the end of the original run."""
        if not self.live_log_path:
            return
        try:
            self._live_file = open(self.live_log_path, 'a', encoding='utf-8')
            self._write_live_event({'event': 'retry_started',
                                     'started_at': datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')})
        except OSError:
            self._live_file = None

    def mark_finished(self):
        self.finished_at = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self._write_live_event({'event': 'run_finished', 'finished_at': self.finished_at})
        self._close_live_file()

    def add(self, category, name, status, message="", source="", dest="",
            duration=None, retry_data=None) -> ResultItem:
        item = ResultItem(
            category=category, name=name, status=status, message=message,
            source=source, dest=dest, duration=duration, retry_data=retry_data,
        )
        self.items.append(item)
        self._write_live_event({'event': 'result', **asdict(item)})
        return item

    def _write_live_event(self, obj: dict):
        if not self._live_file:
            return
        try:
            self._live_file.write(json.dumps(obj, default=str) + '\n')
            self._live_file.flush()
        except OSError:
            pass  # best-effort - losing the live log must never crash a deployment

    def _close_live_file(self):
        if self._live_file:
            try:
                self._live_file.close()
            except OSError:
                pass
            self._live_file = None

    @staticmethod
    def load_from_jsonl(path: str) -> "ResultsCollector":
        """Reconstruct a collector from a live results file - e.g. to
        regenerate a report after a crash, or as the read side of a
        future resume feature. Malformed/partial trailing lines (as you'd
        get from a crash mid-write) are skipped rather than raising."""
        collector = ResultsCollector()
        if not path or not os.path.exists(path):
            return collector
        with open(path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                event = obj.get('event')
                if event == 'run_started':
                    collector.started_at = obj.get('started_at')
                elif event == 'run_finished':
                    collector.finished_at = obj.get('finished_at')
                elif event == 'result':
                    item_fields = {k: v for k, v in obj.items() if k != 'event'}
                    try:
                        collector.items.append(ResultItem(**item_fields))
                    except TypeError:
                        continue  # unknown/incompatible fields - skip rather than crash
        return collector

    def counts(self) -> Dict[str, int]:
        c = {STATUS_SUCCESS: 0, STATUS_FAILED: 0, STATUS_SKIPPED: 0}
        for item in self.items:
            c[item.status] = c.get(item.status, 0) + 1
        return c

    def failed_items(self) -> List[ResultItem]:
        return [i for i in self.items if i.status == STATUS_FAILED]

    def retryable_failed_items(self) -> List[ResultItem]:
        return [i for i in self.items if i.is_retryable]

    def by_category(self) -> Dict[str, List[ResultItem]]:
        cats: Dict[str, List[ResultItem]] = {}
        for item in self.items:
            cats.setdefault(item.category, []).append(item)
        return cats

    def is_empty(self) -> bool:
        return not self.items
