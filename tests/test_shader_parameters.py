import json
import unittest
from types import SimpleNamespace
from unittest.mock import patch
from tests import test_event_edit
from bridge_extension.renderdoc_mcp_bridge.domains.event_edit import EventEditService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService


class ShaderParameterTests(unittest.TestCase):
    def invoke(self, ctx, request):
        with patch.object(CaptureStatusService, '_invoke_on_ui_thread', lambda self, fn, timeout: fn()):
            return EventEditService(ctx).shader_parameters(request)

    def test_native_owner_keeps_precise_integer_strings_and_scopes(self):
        seen = []
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda req: seen.append(json.loads(req)) or json.dumps({'ok': True, 'data': {'edit_revision': 9}}))
        for scope in ('event', 'shared'):
            result = self.invoke(ctx, dict(operation='write', id='doc', revision=2, identity='hash', field='m0/a3', scope=scope, value='18446744073709551615', edit_revision=8, session_id='session'))
            self.assertTrue(result['ok'])
            self.assertEqual(seen[-1]['value'], '18446744073709551615')
            self.assertEqual(seen[-1]['operation'], 'parameter_write')
            self.assertEqual(seen[-1]['scope'], scope)

    def test_native_identity_failure_is_not_hidden(self):
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda req: json.dumps({'ok': False, 'error': 'layout mismatch', 'data': {'edit_revision': 8}}))
        result = self.invoke(ctx, dict(operation='read', identity='wrong'))
        self.assertFalse(result['ok'])
        self.assertEqual(result['err']['msg'], 'layout mismatch')

    def test_unsupported_frontend_and_unknown_operation(self):
        self.assertFalse(self.invoke(SimpleNamespace(), dict(operation='list'))['ok'])
        def fail(req): self.fail('unknown operation reached native owner')
        self.assertFalse(self.invoke(SimpleNamespace(ShaderWorkspaceCommand=fail), dict(operation='global_replace'))['ok'])

    def test_alias_is_metadata_only_native_command(self):
        seen = []
        ctx = SimpleNamespace(ShaderWorkspaceCommand=lambda req: seen.append(json.loads(req)) or json.dumps({'ok': True, 'data': {}}))
        self.invoke(ctx, dict(operation='alias', alias='强度', alias_revision=3, value=None))
        self.assertEqual(seen, [dict(operation='parameter_alias', alias='强度', alias_revision=3)])
