import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_event_edit
from bridge_extension.renderdoc_mcp_bridge.domains.event_edit import EventEditService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService


class ShaderProjectTests(unittest.TestCase):
    def invoke(self, ctx, request):
        with patch.object(CaptureStatusService, '_invoke_on_ui_thread', lambda self, fn, timeout: fn()):
            return EventEditService(ctx).shader_project(request)

    def test_open_only_routes_to_native_open_without_applying(self):
        seen = []
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda req: seen.append(json.loads(req)) or json.dumps({'ok': True, 'data': {'project': {'pending_edits': True}}}))
        result = self.invoke(ctx, dict(operation='open', path='project', discard_unsaved=False))
        self.assertTrue(result['ok'])
        self.assertEqual(seen, [dict(operation='project_open', path='project', discard_unsaved=False)])
        self.assertTrue(result['data']['project']['pending_edits'])

    def test_apply_preserves_both_revisions_and_native_errors(self):
        seen = []
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda req: seen.append(json.loads(req)) or json.dumps({'ok': False, 'error': 'rollback failed', 'data': {'edit_revision': 7}}))
        result = self.invoke(ctx, dict(operation='apply', project_revision=4, edit_revision=6, session_id='capture'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['err']['msg'], 'rollback failed')
        self.assertEqual(result['data']['edit_revision'], 7)
        self.assertEqual(seen[0]['project_revision'], 4)
        self.assertEqual(seen[0]['edit_revision'], 6)

    def test_unsupported_and_unknown_operations_do_not_mutate(self):
        self.assertFalse(self.invoke(SimpleNamespace(), dict(operation='state'))['ok'])
        def fail(req): self.fail('unknown operation reached the native owner')
        self.assertFalse(self.invoke(SimpleNamespace(ShaderWorkspaceCommand=fail), dict(operation='replace'))['ok'])
