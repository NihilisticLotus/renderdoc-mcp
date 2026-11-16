from types import SimpleNamespace as NS
from unittest.mock import patch
import unittest
from tests.test_shader_source_placeholder import shader_module
from bridge_extension.renderdoc_mcp_bridge.domains import texture_region as module


class TextureRegionTests(unittest.TestCase):
    def setUp(self):
        self.rd=NS(CompType=NS(**{name:name for name in ('Typeless','Float','UInt','SInt','UNorm','SNorm','Depth','UNormSRGB')}),
                   GraphicsAPI=NS(D3D11='d11',D3D12='d12'),ShaderStage=NS(Vertex='vs',Pixel='ps',Compute='cs'),Subresource=NS)
        self.patch=patch.object(module,'rd',self.rd);self.patch.start();self.addCleanup(self.patch.stop)
        self.sid,self.rev,self.eid,self.selected='sid',4,7,9
        self.texture=NS(resourceId='ResourceId::2',width=15,height=11,mips=4,arraysize=2,msSamp=2,depth=1,dimension=2,
                        format=NS(compType='Float',Name=lambda:'RGBA32_FLOAT'))
        self.calls=[]
        def pixel(rid,x,y,sub,cast):
            self.calls.append((rid,x,y,sub.mip,sub.slice,sub.sample,cast))
            return NS(floatValue=[-.25,.5,2.,float('inf')],uintValue=[2**32-1,0,2,3],intValue=[-2**31,0,2,3])
        self.controller=NS(GetTextures=lambda:[self.texture],GetAPIProperties=lambda:NS(pipelineType='d12'),PickPixel=pixel)
        self.ctx=NS(IsCaptureLoaded=lambda:True,GetCaptureSessionID=lambda:self.sid,EventEditRevision=lambda:self.rev,
                    CurEvent=lambda:self.eid,CurSelectedEvent=lambda:self.selected,
                    Replay=lambda:NS(BlockInvoke=lambda fn:fn(self.controller)))
        self.service=module.TextureRegionService(self.ctx)
        self.params=dict(session_id='sid',revision=4,eid=7,rid='ResourceId::2',x=1,y=1,width=5,height=3,mip=1,slice=1,sample=1)

    def test_odd_mip_slice_sample_exact_float_and_sparse_grid(self):
        result=self.service.collect(self.params)
        self.assertEqual((result['subresource_width'],result['subresource_height']),(7,5))
        self.assertEqual(len(result['pixels']),9)
        self.assertEqual(result['pixels'][0]['rgba'],[-.25,.5,2.,'inf'])
        self.assertEqual(result['pixels'][0]['float32_le_hex'],['000080be','0000003f','00000040','0000807f'])
        self.assertTrue(all(c[3:6]==(1,1,1) for c in self.calls))
        self.assertEqual((self.eid,self.selected),(7,9))

    def test_integer_does_not_round_through_float(self):
        result=self.service.collect(dict(self.params,type_cast='UInt',width=1,height=1))
        self.assertEqual(len(result['pixels']),1)
        self.assertEqual(result['pixels'][0]['rgba'][0],4294967295)
        self.assertIsNone(result['pixels'][0]['float32_le_hex'])

    def test_stale_capture_event_revision_and_bad_bounds_never_pick(self):
        for update in [dict(session_id='old'),dict(revision=3),dict(revision=True),dict(eid=8),dict(mip=4),dict(slice=2),
                       dict(sample=4294967295),dict(x=-1),dict(width=0),dict(width=20),dict(x=True),dict(type_cast='guess')]:
            with self.assertRaises((ValueError,RuntimeError)):
                self.service.collect(dict(self.params,**update))
        self.assertEqual(self.calls,[])

    def test_volume_slice_bounds_and_unknown_texture(self):
        self.texture.dimension=3;self.texture.depth=8
        self.service.collect(dict(self.params,slice=3))
        with self.assertRaisesRegex(ValueError,'Slice/sample'):
            self.service.collect(dict(self.params,slice=4))
        with self.assertRaisesRegex(ValueError,'Texture is not'):
            self.service.collect(dict(self.params,rid='ResourceId::99'))

    def test_error_and_capture_change_are_not_success(self):
        def fail(*args):raise RuntimeError('readback failure')
        self.controller.PickPixel=fail
        with self.assertRaisesRegex(RuntimeError,'readback failure'):self.service.collect(self.params)
        self.controller.GetAPIProperties=lambda:NS(pipelineType='metal')
        with self.assertRaisesRegex(RuntimeError,'supports D3D11/D3D12'):self.service.collect(self.params)

    def test_identity_change_during_read_rejects_copied_values(self):
        pick=self.controller.PickPixel
        def changed(*args):
            self.rev+=1
            return pick(*args)
        self.controller.PickPixel=changed
        with self.assertRaisesRegex(RuntimeError,'Capture or selection changed'):
            self.service.collect(self.params)
