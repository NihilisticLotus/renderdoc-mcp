"""Request routing for the qrenderdoc bridge extension."""

from .observe import CaptureStatusService, ObserveService
from .domains.camera import ReplayCameraService
from .domains.event_edit import EventEditService
from .domains.workflow import WorkflowService
from .domains.frame_graph import FrameGraphService
from .runtime_identity import describe_runtime
from .task_host import HostTaskService


class RequestHandler:
    """Routes bridge requests to compact extension services."""

    def __init__(self, ctx, runtime_version=None):
        capture_service = CaptureStatusService(ctx)
        observe_service = ObserveService(ctx)
        camera_service = ReplayCameraService(ctx)
        event_edit_service = EventEditService(ctx)
        self._handlers = {
            "get_frame_graph": FrameGraphService(ctx).run,
            "get_workflow_capabilities": WorkflowService(ctx).capabilities,
            "shader_workspace": event_edit_service.shader_workspace,
            "shader_parameters": event_edit_service.shader_parameters,
            "shader_project": event_edit_service.shader_project,
            "mesh_workspace": event_edit_service.mesh_workspace,
            "get_event_edit_state": event_edit_service.get_event_edit_state,
            "get_shared_buffer_state": event_edit_service.get_shared_buffer_state,
            "set_shared_buffer_editing_enabled": event_edit_service.set_shared_buffer_editing_enabled,
            "apply_shared_buffer_edit": event_edit_service.apply_shared_buffer_edit,
            "get_rt_history": event_edit_service.get_rt_history,
            "get_rt_snapshot": event_edit_service.get_rt_snapshot,
            "set_event_editing_enabled": event_edit_service.set_event_editing_enabled,
            "apply_event_shader_edit": event_edit_service.apply_event_shader_edit,
            "apply_event_cbuffer_edit": event_edit_service.apply_event_cbuffer_edit,
            "clear_event_edit": event_edit_service.clear_event_edit,
            "undo_event_edit": event_edit_service.undo_event_edit,

            "ping": lambda _params: {"status": "ok", "message": "pong"},
            "get_capture_status": capture_service.run,
            "get_replay_camera_state": camera_service.get_replay_camera_state,
            "configure_replay_camera": camera_service.configure_replay_camera,
            "reset_replay_camera": camera_service.reset_replay_camera,
            "configure_replay_camera_recipe": camera_service.configure_replay_camera_recipe,
            "apply_replay_camera_recipe": camera_service.apply_replay_camera_recipe,
            "open_capture": capture_service.open_capture,
            "close_capture": capture_service.close_capture,
            "find_latest_capture": capture_service.find_latest_capture,
            "load_latest_capture": capture_service.load_latest_capture,
            "wait_for_new_capture": capture_service.wait_for_new_capture,
            "find_events": observe_service.run,
            "list_passes": observe_service.list_passes,
            "get_frame_packet": observe_service.get_frame_packet,
            "get_pass_packet": observe_service.get_pass_packet,
            "get_draw_packet": observe_service.get_draw_packet,
            "debug_resource_ctx": observe_service.debug_resource_ctx,
            "debug_resource_info": observe_service.debug_resource_info,
            "debug_save_texture": observe_service.debug_save_texture,
            "export_buffer": observe_service.export_buffer,
            "export_texture_raw": observe_service.export_texture_raw,
            "save_event_output_texture": observe_service.save_event_output_texture,
            "debug_save_overlay": observe_service.debug_save_overlay,
            "inspect_pipeline_state": observe_service.inspect_pipeline_state,
            "inspect_shader": observe_service.inspect_shader,
            "get_target_shader_encodings": observe_service.get_target_shader_encodings,
            "apply_shader_edit": observe_service.apply_shader_edit,
            "revert_shader_edit": observe_service.revert_shader_edit,
            "export_shader_raw_bytes": observe_service.export_shader_raw_bytes,
            "inspect_cbuffer_values": observe_service.inspect_cbuffer_values,
            "read_buffer": observe_service.read_buffer,
            "get_shader_disasm": observe_service.get_shader_disasm,
            "get_shader_source": observe_service.get_shader_source,
            "get_shader_code": observe_service.get_shader_code,
            "inspect_texture_usage": observe_service.inspect_texture_usage,
            "inspect_mesh": observe_service.inspect_mesh,
            "export_mesh": observe_service.export_mesh,
            "export_postvs": observe_service.export_postvs,
            "export_capture_inventory": observe_service.export_capture_inventory,
            "export_pixel_history": observe_service.export_pixel_history,
            "export_shader_debug_trace": observe_service.export_shader_debug_trace,
            "debug_shader_invocation": observe_service.debug_shader_invocation,
        }
        self._capture_service = capture_service
        self._runtime_version = runtime_version
        self._task_host = HostTaskService(ctx, self._handlers)
        self._handlers["host_tasks"] = self._task_host.command

    def shutdown(self):
        self._task_host.shutdown()

    def describe_instance(self):
        """Return lightweight metadata for bridge discovery."""
        try:
            status = self._capture_service.run({})
            data = status.get("data") or {}
            return {
                "loaded": bool(data.get("loaded")),
                "capture_path": data.get("path"),
                "api": data.get("api"),
                "runtime": describe_runtime(self._runtime_version),
            }
        except Exception as exc:
            return {
                "loaded": False,
                "status_error": str(exc),
            }

    def handle(self, request):
        request_id = request.get("id")
        method = request.get("method")
        params = request.get("params", {})

        if method not in self._handlers:
            return {
                "id": request_id,
                "error": {
                    "code": "method_not_found",
                    "message": "Unknown method: {}".format(method),
                },
            }

        try:
            result = self._handlers[method](params)
            return {"id": request_id, "result": result}
        except Exception as exc:
            return {
                "id": request_id,
                "error": {
                    "code": "request_failed",
                    "message": str(exc),
                },
            }
