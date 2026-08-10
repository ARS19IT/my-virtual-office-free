"""Durable, file-backed outbox for task-board handoff requests."""
import json
import os
import tempfile
from contextlib import contextmanager

try:
    import fcntl
except ImportError:  # pragma: no cover - the server is deployed on Unix
    fcntl = None


class TaskBoardOutbox:
    """Store handoff records with idempotent create/update operations."""

    def __init__(self, path):
        self.path = os.path.abspath(path)
        self.lock_path = self.path + ".lock"
        os.makedirs(os.path.dirname(self.path), exist_ok=True)

    @contextmanager
    def _locked(self):
        os.makedirs(os.path.dirname(self.lock_path), exist_ok=True)
        with open(self.lock_path, "a+", encoding="utf-8") as lock:
            if fcntl:
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
            try:
                yield
            finally:
                if fcntl:
                    fcntl.flock(lock.fileno(), fcntl.LOCK_UN)

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as source:
                data = json.load(source)
            return data if isinstance(data, list) else []
        except (FileNotFoundError, json.JSONDecodeError, OSError):
            return []

    def _write(self, records):
        directory = os.path.dirname(self.path)
        fd, temporary = tempfile.mkstemp(prefix=".task-board-outbox-", dir=directory)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as target:
                json.dump(records, target, ensure_ascii=False, indent=2)
                target.write("\n")
                target.flush()
                os.fsync(target.fileno())
            os.replace(temporary, self.path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)

    def list(self):
        with self._locked():
            return self._read()

    def lookup(self, idempotency_key):
        with self._locked():
            return next((r for r in self._read() if r.get("idempotencyKey") == idempotency_key), None)

    def create(self, record):
        with self._locked():
            records = self._read()
            existing = next((r for r in records if r.get("idempotencyKey") == record.get("idempotencyKey")), None)
            if existing:
                return existing, False
            records.append(dict(record))
            self._write(records)
            return records[-1], True

    def update(self, idempotency_key, **changes):
        with self._locked():
            records = self._read()
            for record in records:
                if record.get("idempotencyKey") == idempotency_key:
                    record.update(changes)
                    self._write(records)
                    return record
            return None

    def claim_pending(self, now=None, retry_after=0):
        """Atomically claim one pending/failed command for delivery.

        A claim changes the record to active before any external transport is
        called. If the process dies, a later consumer can reclaim an active
        record once its lease expires.
        """
        now = float(now if now is not None else __import__("time").time())
        with self._locked():
            records = self._read()
            for record in records:
                status = record.get("status", "pending")
                if status == "pending":
                    eligible = True
                elif status == "failed":
                    eligible = float(record.get("nextAttemptAt", 0) or 0) <= now
                elif status == "active":
                    eligible = float(record.get("leaseUntil", 0) or 0) <= now
                else:
                    eligible = False
                if not eligible:
                    continue
                record["status"] = "active"
                record["attempts"] = int(record.get("attempts", 0) or 0) + 1
                record["claimedAt"] = now
                record["leaseUntil"] = now + max(1, float(retry_after or 30))
                self._write(records)
                return dict(record)
            return None

    def remove(self, idempotency_key):
        """Remove a record, returning whether a record was removed."""
        with self._locked():
            records = self._read()
            kept = [r for r in records if r.get("idempotencyKey") != idempotency_key]
            if len(kept) == len(records):
                return False
            self._write(kept)
            return True
