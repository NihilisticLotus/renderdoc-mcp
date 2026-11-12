from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from tests.test_shader_source_placeholder import shader_module
from bridge_extension.renderdoc_mcp_bridge.domains.event_edit import EventEditService
from bridge_extension.renderdoc_mcp_bridge.domains.capture import CaptureStatusService
from bridge_extension.renderdoc_mcp_bridge.domains.base import invoke_replay_checked

class EventEditTests(unittest.TestCase):
    def test_replay_callback_error_is_relayed_even_if_runtime_swallows_it(self):
        def block(fn):
            try:fn(object())
            except Exception:pass
        def callback(controller):raise ValueError("invalid pixel")
        ctx=SimpleNamespace(Replay=lambda:SimpleNamespace(BlockInvoke=block))
        with self.assertRaisesRegex(ValueError,"invalid pixel"):
            invoke_replay_checked(ctx,callback)
    def context(self):
        return SimpleNamespace(GetCaptureSessionID=lambda:'capture-2', EventEditRevision=lambda:7,
            IsCaptureLoaded=lambda:True, EditEventShader=lambda *a:None, EditEventCBuffer=lambda *a:None,
            UndoEventEdit=lambda *a:None, CurEvent=lambda:12, GetAction=lambda eid:object() if eid==12 else None,
            SetEventID=lambda *a:None)
    def test_capture_and_revision_checked_before_selection(self):
        service=EventEditService(self.context())
        with self.assertRaisesRegex(RuntimeError,'session mismatch'):
            service.validate({'session_id':'capture-1','revision':7},True)
        with self.assertRaisesRegex(RuntimeError,'revision mismatch'):
            service.validate({'session_id':'capture-2','revision':6},True)
        service.validate({'session_id':'capture-2','revision':7},True)
    def test_optional_event_and_invalid_event(self):
        service=EventEditService(self.context())
        self.assertEqual(service.select({'eid':None}),12)
        for eid in (True,0,-1,13,'12'):
            with self.assertRaises(ValueError):service.select({'eid':eid})
    def test_preview_coordinates_rejected_before_readback(self):
        service=EventEditService(self.context())
        for x,y in [(-1,0),(0,-1),(True,0),(1.5,0)]:
            with self.assertRaisesRegex(ValueError,'non-negative integers'):
                service.snapshot(x=x,y=y)
    def test_old_frontend_explicitly_unsupported(self):
        with self.assertRaisesRegex(RuntimeError,'does not support'):
            EventEditService(SimpleNamespace()).validate({})
    def test_global_cleanup_failure_still_registers_native_state(self):
        ctx=self.context();seen=[]
        ctx.HasEventEdits=lambda:False
        ctx.RegisterReplacement=lambda a,b:seen.append((a,b))
        service=shader_module.ShaderServiceMixin();service.ctx=ctx
        def legacy(params):
            service._pending_global_binding=('original','replacement')
            raise RuntimeError('cleanup failed')
        service._apply_shader_edit_legacy=legacy
        with patch.object(CaptureStatusService,'_invoke_on_ui_thread',lambda self,fn,timeout:fn()):
            with self.assertRaisesRegex(RuntimeError,'cleanup failed'):service.apply_shader_edit({})
        self.assertEqual(seen,[('original','replacement')])
    def test_global_maps_reset_on_new_capture_and_conflict_prevents_native_work(self):
        ctx=self.context();ctx.HasEventEdits=lambda:True
        service=shader_module.ShaderServiceMixin();service.ctx=ctx
        service._global_edit_session='capture-1';service._shader_replacements={'old':'target'}
        service._replacement_to_original={'target':'old'}
        with patch.object(CaptureStatusService,'_invoke_on_ui_thread',lambda self,fn,timeout:fn()):
            result=service.apply_shader_edit({})
        self.assertFalse(result['ok']);self.assertEqual(result['err']['code'],'event_edits_active')
        self.assertEqual(service._shader_replacements,{})
        self.assertEqual(service._replacement_to_original,{})

if __name__=='__main__':unittest.main()
