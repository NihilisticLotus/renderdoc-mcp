import importlib.util
import json
from pathlib import Path
import queue
import sys
import tempfile
import threading
import time
import types
import unittest
import uuid
from unittest.mock import patch
from tests.test_capture_ui_thread import _module as dispatch
from tests.test_task_store import store_module as store

_package = 'host_test_package'
_path = Path(__file__).resolve().parents[1] / 'bridge_extension/renderdoc_mcp_bridge/task_host.py'
_spec = importlib.util.spec_from_file_location(_package + '.task_host', _path)
host = importlib.util.module_from_spec(_spec)
with patch.dict(sys.modules, {_package: types.ModuleType(_package),
                              _package + '.task_store': store,
                              _package + '.domains': types.ModuleType(_package + '.domains'),
                              _package + '.domains.capture': dispatch}):
    _spec.loader.exec_module(host)


class HostTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.queue = queue.Queue()
        self.calls = []
        self.session, self.revision = 'capture-one', 0
        self.helper = types.SimpleNamespace(InvokeOntoUIThread=self.queue.put)
        self.ctx = types.SimpleNamespace(IsCaptureLoaded=lambda: True,
            GetCaptureSessionID=lambda: self.session, EventEditRevision=lambda: self.revision,
            Extensions=lambda: types.SimpleNamespace(GetMiniQtHelper=lambda: self.helper))
        self.service = host.HostTaskService(self.ctx, {'edit': self.edit}, self.directory.name)
        self.host_id = self.service.command({'operation': 'enable'})['data']['host_id']

    def tearDown(self):
        self.service.shutdown()
        end = time.monotonic() + 3
        while self.service._active and time.monotonic() < end:
            time.sleep(.005)
        self.assertFalse(self.service._active)
        self.directory.cleanup()

    def edit(self, params):
        self.calls.append(params)
        return {'ok': True, 'data': {'undo_owner': 'native'}}

    def command(self, operation, **kwargs):
        result = self.service.command(dict(operation=operation, host_id=self.host_id, **kwargs))
        self.assertTrue(result['ok'], result)
        return result['data']

    def submit(self, **kwargs):
        params = dict(task_id=str(uuid.uuid4()), session_id=self.session, revision=self.revision,
                      method='edit', arguments={'value': 1}, queue_timeout=10)
        params.update(kwargs)
        self.command('submit', **params)
        return params

    def terminal(self, params):
        end = time.monotonic() + 3
        while time.monotonic() < end:
            result = self.command('get', task_id=params['task_id'])
            if result['state'] in store.TERMINAL:
                return result
            time.sleep(.005)
        self.fail(result)

    def test_default_off_and_wrong_host(self):
        fresh = host.HostTaskService(self.ctx, {}, self.directory.name)
        self.assertFalse(fresh.command({'operation': 'capabilities'})['data']['enabled'])
        self.assertFalse(fresh.command({'operation': 'submit'})['ok'])
        self.assertFalse(self.service.command({'operation': 'get', 'host_id': 'wrong'})['ok'])

    def test_immutable_snapshot_duplicate_and_reconnect(self):
        params = self.submit()
        callback = self.queue.get(timeout=1)
        params['arguments']['value'] = 2
        callback()
        record = self.terminal(params)
        self.assertEqual(record['state'], 'succeeded')
        self.assertEqual(self.calls, [{'value': 1}])
        params['arguments']['value'] = 1
        self.command('submit', **params)
        self.assertTrue(self.queue.empty())
        self.command('disable')
        self.command('enable')
        self.assertEqual(self.command('get', task_id=params['task_id']), record)
        self.command('submit', **params)
        self.assertEqual(len(self.calls), 1)
        params['arguments']['value'] = 3
        self.assertFalse(self.service.command(dict(operation='submit', host_id=self.host_id, **params))['ok'])

    def test_cancel_before_dequeue_never_edits(self):
        params = self.submit()
        callback = self.queue.get(timeout=1)
        self.assertEqual(self.command('cancel', task_id=params['task_id'])['state'], 'cancelled')
        callback()
        self.assertEqual(self.terminal(params)['state'], 'cancelled')
        self.assertEqual(self.calls, [])

    def test_queued_timeout_never_edits(self):
        params = self.submit(queue_timeout=0)
        callback = self.queue.get(timeout=1)
        self.assertEqual(self.terminal(params)['state'], 'cancelled')
        callback()
        self.assertEqual(self.calls, [])

    def test_running_timeout_and_cancel_are_not_rollback(self):
        entered, release = threading.Event(), threading.Event()
        def edit(params):
            entered.set()
            release.wait(3)
            return self.edit(params)
        self.service.handlers['edit'] = edit
        params = self.submit(queue_timeout=.03)
        worker = threading.Thread(target=self.queue.get(timeout=1))
        worker.start()
        try:
            self.assertTrue(entered.wait(1))
            time.sleep(.06)
            record = self.command('cancel', task_id=params['task_id'])
            self.assertEqual(record['state'], 'running')
            for _ in range(3):
                self.command('cancel', task_id=params['task_id'])
            record = self.command('get', task_id=params['task_id'])
            self.assertEqual([e['kind'] for e in record['events']],
                             ['queued', 'running', 'wait_timeout', 'cancel_requested'])
        finally:
            release.set()
            worker.join(2)
        self.assertEqual(self.terminal(params)['state'], 'succeeded')
        self.assertEqual(len(self.calls), 1)

    def test_capture_and_revision_rechecked_at_execution(self):
        for field in ('session', 'revision'):
            params = self.submit()
            callback = self.queue.get(timeout=1)
            setattr(self, field, 'capture-two' if field == 'session' else 1)
            callback()
            self.assertEqual(self.terminal(params)['state'], 'failed')
        self.assertEqual(self.calls, [])

    def test_base_exception_is_unknown_receipt(self):
        def fail(params):
            raise SystemExit('callback exited')
        self.service.handlers['edit'] = fail
        params = self.submit()
        self.queue.get(timeout=1)()
        record = self.terminal(params)
        self.assertEqual(record['state'], 'unknown')
        self.assertIn('callback exited', record['error'])

    def test_empty_exception_and_native_error_are_not_success(self):
        def fail(params):
            raise RuntimeError()
        for callback, expected in ((fail, 'unknown'), (lambda p: {'ok': False, 'err': {'code': 'native_failure'}}, 'failed')):
            self.service.handlers['edit'] = callback
            params = self.submit()
            self.queue.get(timeout=1)()
            self.assertEqual(self.terminal(params)['state'], expected)

    def test_unsupported_frontend_is_explicit(self):
        self.ctx.EventEditRevision = None
        params = self.submit()
        self.queue.get(timeout=1)()
        record = self.terminal(params)
        self.assertEqual(record['state'], 'failed')
        self.assertIn('does not support capture-bound', record['error'])

    def test_exception_after_mutation_is_unknown_and_never_retried(self):
        def mutate_then_fail(params):
            self.edit(params)
            raise ValueError('receipt lost after native mutation')
        self.service.handlers['edit'] = mutate_then_fail
        params = self.submit()
        self.queue.get(timeout=1)()
        self.assertEqual(self.terminal(params)['state'], 'unknown')
        self.command('submit', **params)
        self.command('disable')
        self.command('enable')
        self.command('submit', **params)
        self.assertEqual(len(self.calls), 1)

    def test_scheduler_throw_after_execution_observes_result(self):
        def dispatch_then_throw(callback):
            callback()
            raise RuntimeError('scheduler notification failure')
        self.helper.InvokeOntoUIThread = dispatch_then_throw
        params = self.submit()
        self.assertEqual(self.terminal(params)['state'], 'succeeded')
        self.assertEqual(len(self.calls), 1)

    def test_scheduler_failure_before_dequeue_never_edits(self):
        def fail(callback):
            self.queue.put(callback)
            raise RuntimeError('scheduler rejected')
        self.helper.InvokeOntoUIThread = fail
        params = self.submit()
        self.assertEqual(self.terminal(params)['state'], 'failed')
        self.queue.get(timeout=1)()
        self.assertEqual(self.calls, [])

    def test_completion_write_failure_reports_unknown_and_stops_new_work(self):
        params = self.submit()
        callback = self.queue.get(timeout=1)
        original = self.service._store.transition
        def transition(task_id, state, **kw):
            if state == 'succeeded':
                raise OSError('disk full')
            return original(task_id, state, **kw)
        with patch.object(self.service._store, 'transition', side_effect=transition):
            callback()
            record = self.terminal(params)
        self.assertEqual(record['state'], 'unknown')
        self.assertFalse(record['persisted'])
        self.assertEqual(len(self.calls), 1)
        self.assertEqual(self.command('list')[0]['state'], 'unknown')
        self.assertFalse(self.service.command(dict(operation='submit', host_id=self.host_id, **params))['ok'])
        self.command('disable')
        self.command('enable')
        self.assertEqual(self.command('get', task_id=params['task_id'])['state'], 'unknown')
        self.command('submit', **params)
        self.assertEqual(len(self.calls), 1)

    def test_shutdown_cancels_queued_callbacks(self):
        params = self.submit()
        callback = self.queue.get(timeout=1)
        self.service.shutdown()
        callback()
        end = time.monotonic() + 2
        while self.service._active and time.monotonic() < end:
            time.sleep(.005)
        self.assertEqual(self.calls, [])
        self.assertFalse(self.service.command({'operation': 'enable'})['ok'])
        self.service = host.HostTaskService(self.ctx, {'edit': self.edit}, self.directory.name)
        self.command('enable')
        self.assertEqual(self.command('get', task_id=params['task_id'])['state'], 'cancelled')


if __name__ == '__main__':
    unittest.main()
