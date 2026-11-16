import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_event_edit
from bridge_extension.renderdoc_mcp_bridge.domains.event_edit import EventEditService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService


class MeshWorkspaceTests(unittest.TestCase):
    def invoke(self, ctx, request):
        with patch.object(CaptureStatusService, '_invoke_on_ui_thread', lambda self, fn, timeout: fn()):
            return EventEditService(ctx).mesh_workspace(request)

    def test_selection_preserves_identity_and_native_topology_rejection(self):
        seen = []
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda req: seen.append(json.loads(req)) or json.dumps({'ok': False, 'error': 'Mesh topology changed', 'data': {'ready': False}}))
        result = self.invoke(ctx, dict(operation='select', session_id='capture', edit_revision=9, topology_hash='old', selection=['18446744073709551615']))
        self.assertFalse(result['ok'])
        self.assertEqual(result['err']['msg'], 'Mesh topology changed')
        self.assertEqual(seen[0]['selection'], ['18446744073709551615'])
        self.assertEqual(seen[0]['operation'], 'mesh_select')
        self.assertEqual(seen[0]['edit_revision'], 9)

    def test_unsupported_and_unknown_paths_are_errors(self):
        self.assertFalse(self.invoke(SimpleNamespace(), dict(operation='show'))['ok'])
        def fail(req): self.fail('invalid operation reached native code')
        self.assertFalse(self.invoke(SimpleNamespace(ShaderWorkspaceCommand=fail), dict(operation='replace'))['ok'])
