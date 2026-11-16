"""Capture-bound asynchronous Host over the existing bridge handlers and UI queue."""
import copy
import json
import math
import os
import threading
import uuid

from .task_store import TaskStore, TERMINAL, MAX_JOURNAL_BYTES, canonical_id
from .domains.capture import UIDispatchTask, UIDispatchTimeout


class HostOutcomeUnknown(RuntimeError):
    """A handler was entered but did not return a serializable native receipt."""


class HostTaskService:
    EXCLUDED = frozenset(("ping", "open_capture", "close_capture", "find_latest_capture",
                          "load_latest_capture", "wait_for_new_capture", "host_tasks"))

    def __init__(self, ctx, handlers, root=None):
        self.ctx = ctx
        self.handlers = {k: v for k, v in handlers.items() if k not in self.EXCLUDED}
        self.root = root or os.environ.get("RENDERTEST_MCP_TASK_STORE") or os.path.join(
            os.environ.get("LOCALAPPDATA", os.path.expanduser("~")), "RenderTest", "mcp-tasks")
        self._lock = threading.RLock()
        self._store = None
        self._active = {}
        self._closing = False
        self._shutdown = False
        self._fault = None
        self._volatile = {}

    @staticmethod
    def response(data=None, error=None):
        return {"ok": error is None, "mode": "summary", "data": data,
                "err": {"code": "host_task_error", "msg": str(error)} if error else None,
                "meta": {"cap": "active", "truncated": False}}

    def capabilities(self):
        with self._lock:
            return {"protocol": 1, "enabled": self._store is not None and not self._closing,
                    "host_id": self._store.host_id if self._store else None,
                    "methods": sorted(self.handlers), "durable_receipts": True,
                    "undo_owner": "CaptureContext", "replay_queue": "native",
                    "automatic_write_retry": False, "storage_error": self._fault,
                    "max_journal_bytes": MAX_JOURNAL_BYTES,
                    "max_active_tasks": 32, "max_tasks_per_host": 256}

    def command(self, params):
        try:
            op = params.get("operation")
            if op == "capabilities":
                return self.response(self.capabilities())
            with self._lock:
                if op == "enable":
                    if self._shutdown:
                        raise RuntimeError("Task Host has shut down")
                    requested = params.get("host_id")
                    if self._store is not None:
                        if self._closing or (requested and requested != self._store.host_id):
                            raise RuntimeError("A different host is active or draining")
                    else:
                        self._store = TaskStore(self.root, requested or str(uuid.uuid4()), create=not requested)
                        self._closing = False
                        self._fault = None
                        self._volatile = {}
                    return self.response(self.capabilities())
                if self._store is None:
                    raise RuntimeError("Task Host is disabled; enable it explicitly first")
                if params.get("host_id") != self._store.host_id:
                    raise ValueError("Task host identity mismatch")
                if op == "disable":
                    if self._active:
                        raise RuntimeError("Tasks are still active; cancel queued tasks and await running receipts")
                    self._store.close()
                    self._store = None
                    return self.response(self.capabilities())
                if op == "submit":
                    return self.response(self._submit(params))
                if op == "get":
                    return self.response(self._get(params["task_id"]))
                if op == "list":
                    return self.response([self._summary(self._volatile.get(r["task_id"], r))
                                          for r in self._store.summaries()])
                if op == "cancel":
                    task_id = canonical_id(params["task_id"])
                    record = self._get(task_id)
                    task = self._active.get(task_id)
                    if task is not None:
                        if task.cancel_queued():
                            if record["state"] == "queued":
                                record = self._store.transition(task_id, "cancelled")
                        elif record["state"] not in TERMINAL and not any(
                                e["kind"] == "cancel_requested" for e in record["events"]):
                            record = self._store.event(task_id, "cancel_requested")
                    return self.response(record)
                raise ValueError("Unknown task Host operation")
        except Exception as exc:
            return self.response(error=exc)

    @staticmethod
    def _summary(record):
        return {key: record.get(key) for key in ("host_id", "task_id", "state", "error", "created_at", "updated_at")}

    def _get(self, task_id):
        canonical_id(task_id)
        return copy.deepcopy(self._volatile[task_id]) if task_id in self._volatile else self._store.get(task_id)

    def _submit(self, params):
        if self._closing or self._fault:
            raise RuntimeError("Task Host is closing or its journal is unavailable")
        task_id = canonical_id(params["task_id"])
        session = params.get("session_id")
        revision = params.get("revision")
        method = params.get("method")
        arguments = params.get("arguments")
        timeout = params.get("queue_timeout", 120.0)
        if not isinstance(session, str) or not session:
            raise ValueError("A capture session ID is required")
        if isinstance(revision, bool) or not isinstance(revision, int) or revision < 0:
            raise ValueError("A non-negative capture edit revision is required")
        if method not in self.handlers or not isinstance(arguments, dict):
            raise ValueError("Unsupported Host method or invalid arguments")
        if "session_id" in arguments and arguments["session_id"] != session:
            raise ValueError("Tool arguments refer to a different capture")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not math.isfinite(timeout) or not 0 <= timeout <= 3600:
            raise ValueError("queue_timeout must be finite and between 0 and 3600 seconds")
        request = {"session_id": session, "revision": revision, "method": method,
                   "arguments": copy.deepcopy(arguments), "queue_timeout": timeout}
        # Identity is caller-generated, so a lost submit reply is recoverable by get/re-submit.
        try:
            existing = self._store.get(task_id)
        except KeyError:
            existing = None
        if existing is not None:
            return self._store.create(task_id, request)[0]
        if len(self._active) >= 32:
            raise RuntimeError("Too many active Host tasks")
        record, _ = self._store.create(task_id, request)
        task = UIDispatchTask(lambda: self._execute(task_id, request))
        self._active[task_id] = task
        worker = threading.Thread(target=self._run, args=(task_id, task, timeout),
                                  name="rendertest_host_task", daemon=True)
        try:
            worker.start()
        except BaseException as exc:
            task.cancel_queued()
            self._active.pop(task_id, None)
            self._store.transition(task_id, "failed", error=str(exc))
            raise
        return record

    def _execute(self, task_id, request):
        # Called only by MiniQtHelper on the GUI thread; native services own replay/undo.
        with self._lock:
            self._store.transition(task_id, "running")
        if not all(callable(getattr(self.ctx, name, None)) for name in
                   ("IsCaptureLoaded", "GetCaptureSessionID", "EventEditRevision")):
            raise RuntimeError("This frontend does not support capture-bound Host tasks")
        if (not self.ctx.IsCaptureLoaded() or self.ctx.GetCaptureSessionID() != request["session_id"]):
            raise RuntimeError("Capture changed before task execution")
        if self.ctx.EventEditRevision() != request["revision"]:
            raise RuntimeError("Capture edit revision changed before task execution")
        try:
            result = self.handlers[request["method"]](copy.deepcopy(request["arguments"]))
            # Match the bridge JSON boundary without persisting Python/GPU handles.
            return json.loads(json.dumps(result, ensure_ascii=False, allow_nan=False, default=str))
        except BaseException as exc:
            # An exception after entering a handler is not proof that it did not
            # mutate native state. Preserve uncertainty instead of inviting retry.
            raise HostOutcomeUnknown("{}: {}".format(type(exc).__name__, exc))

    def _run(self, task_id, task, timeout):
        result, failure, outcome_unknown = None, None, False
        try:
            try:
                self.ctx.Extensions().GetMiniQtHelper().InvokeOntoUIThread(task.invoke)
            except BaseException:
                # A scheduler may throw after dequeue. Only queued cancellation
                # proves that no native operation started.
                if task.cancel_queued():
                    raise
            try:
                result = task.wait(timeout)
            except UIDispatchTimeout as exc:
                if exc.cancelled:
                    with self._lock:
                        if self._store.get(task_id)["state"] == "queued":
                            self._store.transition(task_id, "cancelled")
                    return
                with self._lock:
                    try:
                        self._store.event(task_id, "wait_timeout")
                    except Exception as storage_error:
                        self._fault = str(storage_error)
                result = task.wait(None)  # Observe actual completion; never execute a retry.
        except BaseException as exc:
            task.cancel_queued()
            outcome_unknown = isinstance(exc, HostOutcomeUnknown)
            failure = "{}: {}".format(type(exc).__name__, exc)
        finally:
            with self._lock:
                try:
                    record = self._store.get(task_id)
                    if record["state"] not in TERMINAL:
                        unsuccessful = isinstance(result, dict) and result.get("ok") is False
                        error = failure or (str(result.get("err")) if unsuccessful else None)
                        target = "unknown" if outcome_unknown else ("failed" if error else "succeeded")
                        # A dispatcher failure before dequeue cannot produce succeeded.
                        if record["state"] == "queued" and not error:
                            target, error = "failed", "Task did not enter the UI queue"
                        self._store.transition(task_id, target, result=result, error=error)
                except BaseException as exc:
                    # Native work may already have applied. Keep its receipt in memory,
                    # stop accepting new tasks, and leave durable 'running' for recovery.
                    self._fault = str(exc)
                    record = self._store.get(task_id)
                    record.update(state="unknown", result=result, error=str(exc), persisted=False)
                    self._volatile[task_id] = record
                finally:
                    self._active.pop(task_id, None)
                    if self._closing and not self._active:
                        self._store.close()
                        self._store = None

    def shutdown(self):
        with self._lock:
            self._shutdown = True
            self._closing = True
            for task_id, task in list(self._active.items()):
                if task.cancel_queued() and self._store.get(task_id)["state"] == "queued":
                    try:
                        self._store.transition(task_id, "cancelled")
                    except Exception as exc:
                        self._fault = str(exc)
            if self._store is not None and not self._active:
                self._store.close()
                self._store = None
