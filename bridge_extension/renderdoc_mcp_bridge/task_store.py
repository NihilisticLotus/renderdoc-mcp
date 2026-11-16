"""Atomic, single-writer task receipts. Compatible with the bundled Python 3.6.

No replay handles or undo state are stored here. A surviving task receipt is not
proof that its capture is still open: the native invocation must revalidate it.
"""
import copy
import hashlib
import json
import os
import tempfile
import time
import uuid


TERMINAL = frozenset(("succeeded", "failed", "cancelled", "interrupted", "unknown"))
TRANSITIONS = {
    "queued": frozenset(("running", "cancelled", "failed", "interrupted")),
    "running": frozenset(("succeeded", "failed", "unknown")),
}
MAX_RECORD_BYTES = 8 * 1024 * 1024
MAX_TASKS = 256
MAX_JOURNAL_BYTES = 64 * 1024 * 1024


def canonical_id(value):
    if not isinstance(value, str) or str(uuid.UUID(value)) != value:
        raise ValueError("Task and host IDs must be canonical UUID strings")
    return value


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False).encode("utf-8")


class TaskStore:
    """One host directory, protected for its entire lifetime against other writers."""
    def __init__(self, root, host_id, create=False):
        self.host_id = canonical_id(host_id)
        self.path = os.path.join(os.path.abspath(root), self.host_id)
        self._lock_file = None
        self._records = {}
        self._sizes = {}
        if create:
            os.makedirs(self.path, exist_ok=True)
        elif not os.path.isdir(self.path):
            raise ValueError("Task host journal does not exist")
        try:
            self._acquire()
            header = os.path.join(self.path, "host.json")
            if os.path.isfile(header):
                value = self._read(header)
                if value != {"schema": 1, "host_id": self.host_id}:
                    raise ValueError("Unsupported or mismatched task journal")
            elif create:
                self._atomic(header, {"schema": 1, "host_id": self.host_id})
            else:
                raise ValueError("Task journal header is missing")
            # Validate the entire store before publishing recovery transitions.
            for name in os.listdir(self.path):
                if not name.endswith(".task.json"):
                    continue
                task_id = canonical_id(name[:-10])
                path = os.path.join(self.path, name)
                size = os.path.getsize(path)
                if sum(self._sizes.values()) + size > MAX_JOURNAL_BYTES:
                    raise ValueError("Task journal exceeds total size limit")
                record = self._read(path)
                self._validate(record, task_id)
                self._records[task_id] = record
                self._sizes[task_id] = size
            if len(self._records) > MAX_TASKS:
                raise ValueError("Task journal exceeds the task limit")
            for task_id in list(self._records):
                previous = self._records[task_id]["state"]
                if previous in ("queued", "running"):
                    self.transition(task_id, "interrupted" if previous == "queued" else "unknown",
                                    error="Previous host ended before a durable completion receipt")
        except BaseException:
            self.close()
            raise

    def _acquire(self):
        handle = open(os.path.join(self.path, "writer.lock"), "a+b")
        try:
            if os.path.getsize(handle.name) == 0:
                handle.write(b"0")
                handle.flush()
            handle.seek(0)
            if os.name == "nt":
                import msvcrt
                msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BaseException:
            handle.close()
            raise RuntimeError("Task journal is already owned or cannot be locked")
        self._lock_file = handle

    def close(self):
        if self._lock_file is not None:
            self._lock_file.close()
            self._lock_file = None

    @staticmethod
    def _read(path):
        with open(path, "rb") as handle:
            raw = handle.read(MAX_RECORD_BYTES + 1)
        if len(raw) > MAX_RECORD_BYTES:
            raise ValueError("Task record exceeds size limit")
        envelope = json.loads(raw.decode("utf-8"))
        if (not isinstance(envelope, dict) or set(envelope) != {"payload", "sha256"} or
                hashlib.sha256(encode(envelope["payload"])).hexdigest() != envelope["sha256"]):
            raise ValueError("Task journal checksum does not match")
        return envelope["payload"]

    @staticmethod
    def _atomic(path, value):
        raw = encode({"payload": value, "sha256": hashlib.sha256(encode(value)).hexdigest()})
        if len(raw) > MAX_RECORD_BYTES:
            raise ValueError("Task record exceeds size limit")
        fd, temp = tempfile.mkstemp(prefix=".pending-", dir=os.path.dirname(path))
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(raw)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temp, path)
        finally:
            if os.path.exists(temp):
                os.remove(temp)

    def _validate(self, record, task_id):
        if (not isinstance(record, dict) or record.get("schema") != 1 or
                record.get("task_id") != task_id or record.get("host_id") != self.host_id or
                record.get("state") not in TERMINAL | frozenset(TRANSITIONS)):
            raise ValueError("Invalid task record identity or state")
        request = record.get("request")
        if not isinstance(request, dict) or hashlib.sha256(encode(request)).hexdigest() != record.get("request_hash"):
            raise ValueError("Task request fingerprint does not match")
        events = record.get("events")
        if (not isinstance(events, list) or not events or len(events) > 1024 or
                any(not isinstance(e, dict) or e.get("sequence") != i + 1 for i, e in enumerate(events))):
            raise ValueError("Invalid task event sequence")

    def _publish(self, record):
        if self._lock_file is None:
            raise RuntimeError("Task journal is closed")
        task_id = record["task_id"]
        size = len(encode({"payload": record, "sha256": hashlib.sha256(encode(record)).hexdigest()}))
        if sum(self._sizes.values()) - self._sizes.get(task_id, 0) + size > MAX_JOURNAL_BYTES:
            raise ValueError("Task journal exceeds total size limit")
        self._atomic(os.path.join(self.path, task_id + ".task.json"), record)
        self._records[task_id] = record
        self._sizes[task_id] = size
        return copy.deepcopy(record)

    def create(self, task_id, request):
        task_id = canonical_id(task_id)
        request = copy.deepcopy(request)
        fingerprint = hashlib.sha256(encode(request)).hexdigest()
        if task_id in self._records:
            existing = self._records[task_id]
            if existing["request_hash"] != fingerprint:
                raise ValueError("Task ID was already used for a different request")
            return copy.deepcopy(existing), False
        if len(self._records) >= MAX_TASKS:
            raise ValueError("Task journal is full; create a new host journal")
        now = time.time()
        record = {"schema": 1, "host_id": self.host_id, "task_id": task_id,
                  "request": request, "request_hash": fingerprint, "state": "queued",
                  "created_at": now, "updated_at": now, "result": None, "error": None,
                  "events": [{"sequence": 1, "time": now, "kind": "queued"}]}
        return self._publish(record), True

    def get(self, task_id):
        return copy.deepcopy(self._records[canonical_id(task_id)])

    def list(self):
        return [self.get(key) for key in sorted(self._records,
                key=lambda key: (self._records[key]["created_at"], key))]

    def summaries(self):
        # Listing a full journal must not copy every large Shader/result payload.
        keys = ("host_id", "task_id", "state", "error", "created_at", "updated_at")
        return [{key: record.get(key) for key in keys} for record in self._records.values()]

    def transition(self, task_id, state, **updates):
        record = self.get(task_id)
        if state not in TRANSITIONS.get(record["state"], ()):
            raise ValueError("Invalid task transition: {} -> {}".format(record["state"], state))
        return self._update(record, state, updates)

    def event(self, task_id, kind, **details):
        record = self.get(task_id)
        if kind not in ("cancel_requested", "wait_timeout"):
            raise ValueError("Unsupported task observation event")
        return self._update(record, kind, {"details": details}, change_state=False)

    def _update(self, record, kind, updates, change_state=True):
        if set(updates) - {"result", "error", "details"}:
            raise ValueError("Unsupported receipt fields")
        if len(record["events"]) >= 1024:
            raise ValueError("Task event limit reached")
        now = time.time()
        if change_state:
            record["state"] = kind
            record.update(updates)
        record["updated_at"] = now
        record["events"].append({"sequence": len(record["events"]) + 1,
                                 "time": now, "kind": kind, "details": updates.get("details", {})})
        return self._publish(record)
