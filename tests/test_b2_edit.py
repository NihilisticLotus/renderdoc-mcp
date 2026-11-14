from types import SimpleNamespace
from unittest.mock import patch
import unittest
from tests import test_event_edit
from bridge_extension.renderdoc_mcp_bridge.domains.event_edit import EventEditService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService


class B2Tests(unittest.TestCase):
    def service(self):
        ctx = test_event_edit.EventEditTests().context()
        ctx.EditSharedBufferRange = lambda *args: "native dependency rejected"
        ctx.Replay = lambda: SimpleNamespace(BlockInvoke=lambda fn: fn(
            SimpleNamespace(GetBuffers=lambda: [SimpleNamespace(resourceId="Buffer42")],
                            GetSharedBufferPatches=lambda: [])))
        service = EventEditService(ctx)
        service.shared_state = lambda: {"revision": 7}
        return service

    def invoke(self, name, params):
        with patch.object(CaptureStatusService, "_invoke_on_ui_thread", lambda self, fn, timeout: fn()):
            return getattr(self.service(), name)(dict(session_id="capture-2", revision=7, **params))

    def test_revision_is_mandatory_and_not_boolean(self):
        for value in (None, True, "7"):
            with self.assertRaises(ValueError):
                self.service().validate_b2({"session_id": "capture-2", "revision": value})

    def test_payload_and_range_fail_before_native_mutation(self):
        for extra in ({"data_hex": "00"}, {"data_hex": "gg"}, {"reset": True, "data_hex": "00"},
                      {"length": 0}, {"offset": -1}, {"length": 16777217}):
            args = dict(buffer="Buffer42", offset=0, length=16)
            args.update(extra)
            self.assertFalse(self.invoke("apply_shared_buffer_edit", args)["ok"])

    def test_native_dependency_failure_is_reported(self):
        result = self.invoke("apply_shared_buffer_edit", dict(buffer="Buffer42", offset=0,
                             length=4, data_hex="0000803f"))
        self.assertFalse(result["ok"])
        self.assertIn("native dependency rejected", result["err"]["msg"])
        self.assertEqual(result["data"]["revision"], 7)

    def test_invalid_analysis_cannot_start_replay(self):
        for extra in ({"eid": True}, {"mip": -1}, {"range_min": float("nan")},
                      {"range_min": 2.0, "range_max": 1.0}):
            args = dict(texture="Texture42", eid=12)
            args.update(extra)
            self.assertFalse(self.invoke("get_rt_snapshot", args)["ok"])

    def test_b1_only_frontend_is_explicitly_unsupported(self):
        with self.assertRaisesRegex(RuntimeError, "does not support B2"):
            EventEditService(test_event_edit.EventEditTests().context()).validate_b2(
                {"session_id": "capture-2", "revision": 7})
