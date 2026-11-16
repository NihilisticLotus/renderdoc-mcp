"""Bounded original numeric samples for a frozen RT annotation; no event selection."""
import math
import struct
import renderdoc as rd
from .base import BridgeService, invoke_replay_checked
from .capture import CaptureStatusService


def integer(params, key, default=None):
    value = params.get(key, default)
    if isinstance(value, bool) or not isinstance(value, int) or value < 0:
        raise ValueError('{} must be a nonnegative integer'.format(key))
    return value


class TextureRegionService(BridgeService):
    def run(self, params):
        try:
            data = CaptureStatusService(self.ctx)._invoke_on_ui_thread(lambda:self.collect(params),120.0)
            return dict(ok=True,mode='summary',data=data,err=None,meta=dict(cap='active',truncated=False))
        except Exception as exc:
            return dict(ok=False,mode='summary',data=None,
                        err=dict(code='texture_region_failed',msg='{}: {}'.format(type(exc).__name__,exc)),
                        meta=dict(cap='active',truncated=False))

    def collect(self, params):
        if not self.ctx.IsCaptureLoaded():
            raise RuntimeError('No capture loaded')
        def identity():
            return self.ctx.GetCaptureSessionID(),self.ctx.EventEditRevision(),self.ctx.CurEvent(),self.ctx.CurSelectedEvent()
        before=identity()
        eid=integer(params,'eid')
        revision=integer(params,'revision')
        if (params.get('session_id'),revision,eid) != before[:3]:
            raise ValueError('Capture identity/revision/event mismatch; refresh annotation')
        mip,layer,sample=(integer(params,k,0) for k in ('mip','slice','sample'))
        x,y,width,height=(integer(params,k) for k in ('x','y','width','height'))
        if not width or not height:
            raise ValueError('Region must not be empty')
        cast_name=params.get('type_cast','Typeless')
        casts={name:getattr(rd.CompType,name) for name in ('Typeless','Float','UInt','SInt','UNorm','SNorm','Depth','UNormSRGB')}
        if cast_name not in casts:
            raise ValueError('Unsupported type cast')
        result=dict(session_id=before[0],revision=before[1],eid=eid,selected_eid=before[3],
                    rid=params.get('rid'),mip=mip,slice=layer,sample=sample,
                    region=dict(x=x,y=y,width=width,height=height),sampling='unique 3x3 grid, not an exhaustive region statistic',
                    coordinate_space='original subresource texels; display flip/range/channels are not applied')
        def collect(controller):
            if controller.GetAPIProperties().pipelineType not in (rd.GraphicsAPI.D3D11,rd.GraphicsAPI.D3D12):
                raise RuntimeError('RT region numeric evidence currently supports D3D11/D3D12 only')
            texture=next((t for t in controller.GetTextures() if str(t.resourceId)==params.get('rid')),None)
            if texture is None and callable(getattr(controller,'GetEventShaderPreviewTexture',None)):
                for stage in (rd.ShaderStage.Vertex,rd.ShaderStage.Pixel,rd.ShaderStage.Compute):
                    candidate=controller.GetEventShaderPreviewTexture(eid,stage)
                    if str(candidate.resourceId)==params.get('rid') and candidate.width and candidate.height:
                        texture=candidate;break
            if texture is None:
                raise ValueError('Texture is not in this capture or the current independent preview')
            if mip >= texture.mips:
                raise ValueError('Mip outside texture bounds')
            tw,th=max(1,texture.width>>mip),max(1,texture.height>>mip)
            layers=max(1,texture.depth>>mip) if texture.dimension==3 else texture.arraysize
            if layer>=layers or sample>=max(1,texture.msSamp):
                raise ValueError('Slice/sample outside texture bounds; choose an explicit MSAA sample')
            if x+width>tw or y+height>th:
                raise ValueError('Region outside subresource bounds')
            kind=casts[cast_name] if cast_name!='Typeless' else texture.format.compType
            if kind==rd.CompType.Typeless:
                raise ValueError('A concrete type cast is required for typeless textures')
            sub=rd.Subresource();sub.mip,sub.slice,sub.sample=mip,layer,sample
            pixels=[]
            for py in sorted(set((y,y+(height-1)//2,y+height-1))):
                for px in sorted(set((x,x+(width-1)//2,x+width-1))):
                    value=controller.PickPixel(texture.resourceId,px,py,sub,casts[cast_name])
                    if kind in (rd.CompType.UInt,rd.CompType.SInt):
                        rgba=[int(v) for v in (value.uintValue if kind==rd.CompType.UInt else value.intValue)]
                        bits=None
                    else:
                        rgba=[float(v) if math.isfinite(v) else str(float(v)) for v in value.floatValue]
                        bits=[struct.pack('<f',v).hex() for v in value.floatValue]
                    pixels.append(dict(x=px,y=py,rgba=rgba,float32_le_hex=bits))
            result.update(format=str(texture.format.Name()),type_cast=cast_name,value_type=str(kind),
                          subresource_width=tw,subresource_height=th,pixels=pixels,
                          evidence='IReplayController.PickPixel; original resource, no display remap')
        invoke_replay_checked(self.ctx,collect)
        if identity()!=before:
            raise RuntimeError('Capture or selection changed while sampling; discard annotation evidence')
        return result
