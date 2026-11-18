"""Shared base helpers for live bridge services."""

import sys


class BridgeService:
    def __init__(self, ctx):
        self.ctx = ctx

    @staticmethod
    def _no_capture():
        return {
            "ok": False,
            "mode": "summary",
            "data": None,
            "err": {"code": "capture_not_loaded", "msg": "No capture loaded"},
            "meta": {"cap": None, "truncated": False},
        }

    @staticmethod
    def _warn_swallow(context, exc):
        print("[renderdoc-mcp-bridge] warn {}: {}".format(context, exc), file=sys.stderr)


def invoke_replay_checked(ctx, callback):
    """RenderDoc logs Python callback exceptions; explicitly relay them to the caller."""
    failure = []
    def invoke(controller):
        try:
            callback(controller)
        except Exception as exc:
            failure.append(exc)
    ctx.Replay().BlockInvoke(invoke)
    if failure:
        raise failure[0]


def invoke_bundle_replay(ctx, params, callback):
    """Opt-in capture-bound readback with one UI/replay scope."""
    expected = params.get("capture_guard")
    if expected is None:
        ctx.Replay().BlockInvoke(callback)
        return

    from .capture import CaptureStatusService

    def on_ui():
        if not ctx.IsCaptureLoaded() or expected != {
            "session_id": ctx.GetCaptureSessionID(), "edit_revision": ctx.EventEditRevision()
        }:
            raise ValueError("Capture session or edit revision changed before bundle readback")
        selected_event = ctx.CurEvent()

        def scoped(controller):
            try:
                callback(controller)
            finally:
                controller.SetFrameEvent(selected_event, True)

        invoke_replay_checked(ctx, scoped)

    CaptureStatusService(ctx)._invoke_on_ui_thread(on_ui, 120.0)
