import importlib.util
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
import uuid
from unittest.mock import patch

SOURCE = Path(__file__).resolve().parents[1] / 'bridge_extension/renderdoc_mcp_bridge/task_store.py'
spec = importlib.util.spec_from_file_location('task_store_test_module', SOURCE)
store_module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(store_module)
TaskStore = store_module.TaskStore


class TaskStoreTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.host_id = str(uuid.uuid4())
        self.store = TaskStore(self.root.name, self.host_id, create=True)
        self.addCleanup(self.store.close)
        self.task_id = str(uuid.uuid4())
        self.request = dict(session_id='capture-a', revision=7, method='undo_event_edit', params={})

    def test_total_budget_rejects_new_payload_without_changing_receipts(self):
        self.store.create(self.task_id, self.request)
        previous = self.store.get(self.task_id)
        with patch.object(store_module, 'MAX_JOURNAL_BYTES', sum(self.store._sizes.values())):
            with self.assertRaisesRegex(ValueError, 'total size limit'):
                self.store.create(str(uuid.uuid4()), self.request)
            with self.assertRaisesRegex(ValueError, 'total size limit'):
                self.store.transition(self.task_id, 'running')
        self.assertEqual(self.store.get(self.task_id), previous)
        self.assertNotIn('request', self.store.summaries()[0])

    def test_idempotent_task_identity_and_defensive_snapshots(self):
        first, created = self.store.create(self.task_id, self.request)
        self.assertTrue(created)
        first['request']['revision'] = 99
        again, created = self.store.create(self.task_id, self.request)
        self.assertFalse(created)
        self.assertEqual(again['request']['revision'], 7)
        with self.assertRaisesRegex(ValueError, 'different request'):
            self.store.create(self.task_id, dict(self.request, session_id='capture-b'))

    def test_completed_receipt_and_ordered_events_survive_reopen(self):
        self.store.create(self.task_id, self.request)
        self.store.transition(self.task_id, 'running')
        self.store.event(self.task_id, 'wait_timeout')
        self.store.transition(self.task_id, 'succeeded', result={'revision': 8})
        self.store.close()
        with_store = TaskStore(self.root.name, self.host_id)
        self.addCleanup(with_store.close)
        record = with_store.get(self.task_id)
        self.assertEqual(record['state'], 'succeeded')
        self.assertEqual(record['result'], {'revision': 8})
        self.assertEqual([e['sequence'] for e in record['events']], [1, 2, 3, 4])
        with self.assertRaises(ValueError):
            with_store.transition(self.task_id, 'running')

    def test_recovery_does_not_retry_queued_or_running_work(self):
        running = str(uuid.uuid4())
        self.store.create(self.task_id, self.request)
        self.store.create(running, self.request)
        self.store.transition(running, 'running')
        self.store.close()
        recovered = TaskStore(self.root.name, self.host_id)
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.get(self.task_id)['state'], 'interrupted')
        self.assertEqual(recovered.get(running)['state'], 'unknown')
        self.assertFalse(recovered.create(running, self.request)[1])
        self.assertEqual(len(recovered.list()), 2)

    def test_failed_atomic_write_keeps_previous_receipt_and_memory(self):
        self.store.create(self.task_id, self.request)
        path = Path(self.store.path) / (self.task_id + '.task.json')
        before = path.read_bytes()
        with patch.object(store_module.os, 'replace', side_effect=OSError('disk failure')):
            with self.assertRaisesRegex(OSError, 'disk failure'):
                self.store.transition(self.task_id, 'running')
        self.assertEqual(path.read_bytes(), before)
        self.assertEqual(self.store.get(self.task_id)['state'], 'queued')
        self.assertEqual(list(Path(self.store.path).glob('.pending-*')), [])

    def test_corrupt_receipt_is_rejected_and_writer_lock_is_released(self):
        self.store.create(self.task_id, self.request)
        path = Path(self.store.path) / (self.task_id + '.task.json')
        good = path.read_bytes()
        content = json.loads(good)
        content['payload']['state'] = 'succeeded'
        path.write_text(json.dumps(content), encoding='utf-8')
        self.store.close()
        with self.assertRaisesRegex(ValueError, 'checksum'):
            TaskStore(self.root.name, self.host_id)
        path.write_bytes(good)
        reopened = TaskStore(self.root.name, self.host_id)
        self.addCleanup(reopened.close)
        self.assertEqual(reopened.get(self.task_id)['state'], 'interrupted')

    def test_abrupt_process_exit_recovers_unknown_without_execution(self):
        host_id, queued_id, running_id = (str(uuid.uuid4()) for _ in range(3))
        script = """import importlib.util, os, sys
spec=importlib.util.spec_from_file_location('store',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
s=m.TaskStore(sys.argv[2],sys.argv[3],create=True)
s.create(sys.argv[4],{'method':'edit'});s.create(sys.argv[5],{'method':'edit'});s.transition(sys.argv[5],'running')
os._exit(23)
"""
        proc = subprocess.run([sys.executable, '-c', script, str(SOURCE), self.root.name,
                               host_id, queued_id, running_id], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 23, proc.stderr)
        recovered = TaskStore(self.root.name, host_id)
        self.addCleanup(recovered.close)
        self.assertEqual(recovered.get(queued_id)['state'], 'interrupted')
        self.assertEqual(recovered.get(running_id)['state'], 'unknown')
        self.assertFalse(recovered.create(running_id, {'method': 'edit'})[1])

    def test_other_process_cannot_open_live_host_journal(self):
        script = '''import importlib.util, sys
s=importlib.util.spec_from_file_location('store', sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
try:
 m.TaskStore(sys.argv[2],sys.argv[3])
except RuntimeError:
 sys.exit(0)
sys.exit(1)
'''
        proc = subprocess.run([sys.executable, '-c', script, str(SOURCE), self.root.name, self.host_id], capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)

    def test_invalid_ids_and_nonfinite_payload_do_not_write(self):
        for task_id in ('../outside', '', True):
            with self.assertRaises((ValueError, TypeError, AttributeError)):
                self.store.create(task_id, self.request)
        with self.assertRaises(ValueError):
            self.store.create(self.task_id, {'value': float('nan')})
        self.assertEqual(self.store.list(), [])

    def test_schema_and_closed_writer_reject_changes(self):
        self.store.create(self.task_id, self.request)
        self.store.close()
        with self.assertRaisesRegex(RuntimeError, 'closed'):
            self.store.transition(self.task_id, 'running')


if __name__ == '__main__':
    unittest.main()
