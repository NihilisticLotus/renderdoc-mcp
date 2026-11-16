from types import SimpleNamespace
from unittest.mock import patch
import unittest

# Install the same replay-module fixture used by event-edit tests.
from tests.test_shader_source_placeholder import shader_module
from bridge_extension.renderdoc_mcp_bridge.domains.workflow import WorkflowService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService
from renderdoc_mcp.server.workflow import register_workflow_tools


class WorkflowTests(unittest.TestCase):
    def query(self, ctx):
        with patch.object(CaptureStatusService, '_invoke_on_ui_thread', lambda self, fn, timeout: fn()), \
             patch('bridge_extension.renderdoc_mcp_bridge.domains.workflow.rd.GetConfigSetting',
                   lambda _: SimpleNamespace(data=SimpleNamespace(basic=SimpleNamespace(b=False))), create=True):
            return WorkflowService(ctx).capabilities({})

    def test_old_frontend_reports_missing_surface_without_mutating(self):
        data = self.query(SimpleNamespace(IsCaptureLoaded=lambda: False))['data']
        self.assertFalse(data['event_editing']['frontend_supported'])
        self.assertFalse(data['event_editing']['capture_eligible'])
        self.assertIn('UndoEventEdit', data['event_editing']['missing_methods'])

    def test_supported_surface_does_not_claim_remote_or_other_api_support(self):
        ctx = SimpleNamespace(**{name: lambda: None for name in WorkflowService.EVENT_METHODS})
        ctx.IsCaptureLoaded = lambda: True
        ctx.GetCaptureFilename = lambda: 'capture.rdc'
        ctx.GetCaptureSessionID = lambda: 'session'
        ctx.EventEditRevision = lambda: 9
        ctx.APIProps = lambda: SimpleNamespace(pipelineType='GraphicsAPI.D3D12')
        ctx.IsCaptureLocal = lambda: True
        ctx.Replay = lambda: SimpleNamespace(CurrentRemote=lambda: SimpleNamespace(IsConnected=lambda: False))
        data = self.query(ctx)['data']
        self.assertTrue(data['event_editing']['capture_eligible'])
        self.assertFalse(data['event_editing']['enabled'])
        self.assertEqual(data['workflow_adapters']['B3_project_workspace'], 'unsupported_frontend')
        ctx.Replay = lambda: SimpleNamespace(CurrentRemote=lambda: SimpleNamespace(IsConnected=lambda: True))
        self.assertFalse(self.query(ctx)['data']['event_editing']['capture_eligible'])
        ctx.Replay = lambda: SimpleNamespace(CurrentRemote=lambda: SimpleNamespace(IsConnected=lambda: False))
        ctx.IsCaptureLocal = lambda: False
        self.assertFalse(self.query(ctx)['data']['event_editing']['capture_eligible'])
        ctx.IsCaptureLocal = lambda: True
        ctx.APIProps = lambda: SimpleNamespace(pipelineType='Vulkan')
        self.assertFalse(self.query(ctx)['data']['event_editing']['capture_eligible'])

    def test_gateway_routes_only_to_explicit_window(self):
        functions = {}
        app = SimpleNamespace(tool=lambda: lambda f: functions.setdefault(f.__name__, f))
        calls = []
        live = SimpleNamespace(client=SimpleNamespace(call=lambda *a, **kw: calls.append((a, kw))))
        register_workflow_tools(app, live)
        functions['get_workflow_capabilities']('window-a')
        self.assertEqual(calls, [(('get_workflow_capabilities', {}), {'window_id': 'window-a'})])
        with self.assertRaises(ValueError):
            functions['get_workflow_capabilities']('')

    def test_b3_b4_discovery_uses_actual_frontend_surface_without_starting_models(self):
        ctx=SimpleNamespace(IsCaptureLoaded=lambda:False)
        for name in ('GetCaptureSessionID','EventEditRevision','Extensions','CurRootActions',
                     'GetResources','GetResourceName','GetStructuredFile','GetAction',
                     'CurEvent','CurSelectedEvent','Replay','ShaderWorkspaceCommand'):
            setattr(ctx,name,lambda:None)
        ctx.Config=lambda:SimpleNamespace(AI_CodexExecutable='')
        adapters=self.query(ctx)['data']['workflow_adapters']
        self.assertEqual(adapters['B3_project_workspace'],'available')
        self.assertEqual(adapters['B4_frame_graph'],'available')
        self.assertEqual(adapters['B4_embedded_ai_mcp_host'],'codex_host_available')
        ctx.Config=lambda:SimpleNamespace()
        self.assertEqual(self.query(ctx)['data']['workflow_adapters']['B4_embedded_ai_mcp_host'],'host_only')
