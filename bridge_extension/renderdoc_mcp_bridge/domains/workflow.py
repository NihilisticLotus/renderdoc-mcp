"""Read-only frontend capability negotiation; never enables replay features."""
import renderdoc as rd

from .base import BridgeService
from .capture import CaptureStatusService
from ..runtime_identity import describe_runtime


class WorkflowService(BridgeService):
    EVENT_METHODS = (
        'GetCaptureSessionID', 'EventEditRevision', 'EventEditUndoCount',
        'EventEditDiagnostics', 'HasEventEdits', 'SetEventEditingEnabled',
        'EditEventShader', 'EditEventCBuffer', 'UndoEventEdit', 'ShowEventEditor',
    )

    def capabilities(self, params):
        def read():
            loaded = bool(self.ctx.IsCaptureLoaded())
            missing = [name for name in self.EVENT_METHODS if not callable(getattr(self.ctx, name, None))]
            api = str(self.ctx.APIProps().pipelineType) if loaded else None
            local = bool(self.ctx.IsCaptureLocal()) if loaded and callable(getattr(self.ctx, 'IsCaptureLocal', None)) else None
            remote = None
            if loaded and callable(getattr(self.ctx, 'Replay', None)):
                manager = self.ctx.Replay()
                if callable(getattr(manager, 'CurrentRemote', None)):
                    remote = bool(manager.CurrentRemote().IsConnected())
            # SWIG enums stringify as GraphicsAPI.D3D11 in the embedded frontend.
            api_name = api.rsplit('.', 1)[-1] if api else None
            eligible = loaded and not missing and local is True and remote is False and api_name in ('D3D11', 'D3D12')
            enabled = bool(rd.GetConfigSetting('Replay.EventOverrides').data.basic.b) if not missing else None
            return {
                'ok': True, 'data': {
                    'protocol_version': 1, 'runtime': describe_runtime(),
                    'capture': {'loaded': loaded, 'path': self.ctx.GetCaptureFilename() if loaded else None,
                                'session_id': self.ctx.GetCaptureSessionID() if loaded and not missing else None,
                                'api': api, 'local': local, 'remote_replay': remote},
                    'event_editing': {'frontend_supported': not missing, 'missing_methods': missing,
                                      'capture_eligible': eligible, 'enabled': enabled,
                                      'revision': self.ctx.EventEditRevision() if loaded and not missing else None,
                                      'active': self.ctx.HasEventEdits() if loaded and not missing else None,
                                      'undo_count': self.ctx.EventEditUndoCount() if loaded and not missing else None,
                                      'semantics': 'event-local override; shared GUI/MCP undo',
                                      'operation_validation_required': True},
                    'workflow_adapters': {
                        'B1_event_editing': 'available' if not missing else 'unsupported_frontend',
                        'B2_shared_buffer_persistent_edit': 'not_integrated',
                        'B2_analysis_state_restore': 'not_integrated',
                        'B3_project_workspace': 'not_integrated',
                        'B4_embedded_ai_mcp_host': 'not_integrated',
                        'B5_engine_effect_reconstruction': 'not_integrated',
                        'B6_checkpoint': 'not_integrated',
                        'Metal_backend_acceptance': 'not_verified',
                    },
                }, 'err': None,
                'meta': {'truncated': False},
            }
        try:
            return CaptureStatusService(self.ctx)._invoke_on_ui_thread(read, 30.0)
        except Exception as exc:
            return {'ok': False, 'data': None, 'err': {'code': 'capability_query_failed', 'msg': str(exc)}}
