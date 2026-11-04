"""Fire-and-forget status client for the bot dashboard.

Copy this single file next to each bot and call init() once at startup:

    import botstatus
    status = botstatus.init("reddit-bot")
    status.event("OK", "posted something")
    status.update(last_post="Some title")

Configured by environment variables (a .env loaded before init() works):
    BOT_DASHBOARD_URL    e.g. http://192.168.1.50:8080   (unset = everything here is a no-op)
    BOT_DASHBOARD_TOKEN  shared secret, must match the dashboard's

Design rule: this must never be able to hurt the bot. Everything runs on a
daemon thread, network calls have short timeouts, failures are swallowed, and
unsent events are held in a bounded in-memory buffer and retried.
"""
import json
import os
import sys
import threading
import time
import urllib.request

HEARTBEAT_SECONDS = 30
MAX_BUFFERED_EVENTS = 1000
BATCH_SIZE = 200


class _NullStatus:
    def event(self, level, message):
        pass

    def update(self, **fields):
        pass


class _Status:
    def __init__(self, name, url, token, provider):
        self._name = name
        self._endpoint = url.rstrip('/') + '/api/ingest'
        self._token = token
        self._provider = provider
        self._started = time.time()
        self._fields = {}
        self._events = []
        self._seq = 0
        self._lock = threading.Lock()
        self._wake = threading.Event()
        self._reachable = True
        threading.Thread(target=self._run, daemon=True, name='botstatus').start()

    def event(self, level, message):
        with self._lock:
            self._seq += 1
            self._events.append({'id': self._seq, 'ts': time.time(),
                                 'level': str(level), 'msg': str(message)})
            if len(self._events) > MAX_BUFFERED_EVENTS:
                del self._events[:len(self._events) - MAX_BUFFERED_EVENTS]
        self._wake.set()

    def update(self, **fields):
        with self._lock:
            self._fields.update(fields)

    def _run(self):
        while True:
            woken = self._wake.wait(timeout=HEARTBEAT_SECONDS)
            self._wake.clear()
            if woken:
                time.sleep(1)  # let a burst of events batch up
            try:
                self._send()
            except Exception:
                pass  # never let the sender thread die

    def _send(self):
        with self._lock:
            batch = self._events[:BATCH_SIZE]
            fields = dict(self._fields)
        if self._provider:
            try:
                fields.update(self._provider())
            except Exception:
                pass
        body = json.dumps({
            'bot': self._name,
            'pid': os.getpid(),
            'started': self._started,
            'fields': fields,
            'events': batch,
        }, default=str).encode()
        request = urllib.request.Request(
            self._endpoint, data=body, method='POST',
            headers={'Content-Type': 'application/json', 'X-Token': self._token})
        try:
            with urllib.request.urlopen(request, timeout=5):
                pass
        except Exception as error:
            if self._reachable:
                print(f"[botstatus] dashboard unreachable ({error}); will keep retrying",
                      file=sys.stderr, flush=True)
            self._reachable = False
            return
        self._reachable = True
        if batch:
            last_id = batch[-1]['id']
            with self._lock:
                self._events = [e for e in self._events if e['id'] > last_id]
            if len(batch) == BATCH_SIZE:
                self._wake.set()  # more waiting


def init(name, provider=None):
    """Start reporting as `name`. `provider` is an optional callable returning a
    dict of extra fields, evaluated on every heartbeat (e.g. latency)."""
    url = os.getenv('BOT_DASHBOARD_URL')
    if not url:
        return _NullStatus()
    return _Status(name, url, os.getenv('BOT_DASHBOARD_TOKEN', ''), provider)
