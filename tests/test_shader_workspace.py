import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_event_edit  # supplies the embedded RenderDoc test doubles
from bridge_extension.renderdoc_mcp_bridge.domains.event_edit import EventEditService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService


class ShaderWorkspaceTests(unittest.TestCase):
    def invoke(self, ctx, request):
        with patch.object(CaptureStatusService, '_invoke_on_ui_thread', lambda self, fn, timeout: fn()):
            return EventEditService(ctx).shader_workspace(request)

    def test_old_frontend_rejected_explicitly(self):
        result = self.invoke(SimpleNamespace(), {'operation': 'state'})
        self.assertFalse(result['ok'])
        self.assertIn('does not support', result['err']['msg'])

    def test_native_errors_and_document_are_preserved(self):
        seen = []
        def execute(request):
            seen.append(json.loads(request))
            return json.dumps({'ok': False, 'error': 'stale document', 'data': {'edit_revision': 9},
                               'document': {'id': 'doc1', 'revision': 4}})
        result = self.invoke(SimpleNamespace(ShaderWorkspaceCommand=execute),
                             {'operation': 'compile', 'id': 'doc1', 'revision': 3,
                              'session_id': 'capture1', 'files': None, 'show': False})
        self.assertFalse(result['ok'])
        self.assertEqual(result['err']['msg'], 'stale document')
        self.assertEqual(result['data']['document']['revision'], 4)
        self.assertEqual(len(seen), 1)
        self.assertNotIn('files', seen[0])
        self.assertNotIn('show', seen[0])

    def test_state_remains_available_without_capture(self):
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda request: json.dumps(
            {'ok': True, 'data': {'documents': [{'id': 'retained'}], 'session_id': ''}}))
        result = self.invoke(ctx, {'operation': 'state'})
        self.assertTrue(result['ok'])
        self.assertEqual(result['data']['session_id'], '')

    def test_unknown_operation_cannot_call_native(self):
        def execute(_):
            self.fail('unknown operation reached native service')
        result = self.invoke(SimpleNamespace(ShaderWorkspaceCommand=execute), {'operation': 'replace_global'})
        self.assertFalse(result['ok'])

    def test_compile_never_routes_to_legacy_replacement(self):
        calls = []
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda request: calls.append(json.loads(request)) or
                              json.dumps({'ok': True, 'data': {'edit_revision': 0}}))
        self.assertTrue(self.invoke(ctx, {'operation': 'compile', 'id': 'doc', 'revision': 1})['ok'])
        self.assertEqual([c['operation'] for c in calls], ['compile'])
