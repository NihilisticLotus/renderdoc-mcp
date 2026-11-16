"""Workflow discovery is additive; unsupported bridges fail explicitly."""


def register_workflow_tools(app, live):
    @app.tool()
    def get_texture_region(window_id: str, session_id: str, revision: int, eid: int, rid: str,
                           x: int, y: int, width: int, height: int, mip: int = 0, slice: int = 0,
                           sample: int = 0, type_cast: str = 'Typeless') -> dict:
        """Read up to nine original typed numeric samples on a 3x3 grid in an explicit RT region at the current effective event. Requires capture UUID/revision and exact subresource texel coordinates; does not select/replay another event. Includes FP32 bit evidence, not display-remapped values or exhaustive statistics. D3D11/D3D12 only; invalid bounds, implicit MSAA resolve and unknown textures fail explicitly."""
        if not window_id:
            raise ValueError('Explicit window_id required')
        return live.client.call('get_texture_region', dict(session_id=session_id,revision=revision,eid=eid,
            rid=rid,x=x,y=y,width=width,height=height,mip=mip,slice=slice,sample=sample,type_cast=type_cast),window_id=window_id)

    @app.tool()
    def get_frame_graph(window_id: str, session_id: str, revision: int,
                        after_eid: int = 0, limit: int = 64, rid: str | None = None) -> dict:
        """Page captured action/marker facts or actual GetUsage roles for one resource. Never selects/replays events. Requires capture identity/revision. Edges express captured usage, not inferred GPU dependencies or edited Shader access. limit 1..256; continue with next_after_eid when has_more. No AI inference is silently promoted to fact."""
        if not window_id:
            raise ValueError('Explicit window_id required')
        return live.client.call('get_frame_graph', dict(session_id=session_id, revision=revision,
            after_eid=after_eid, limit=limit, rid=rid), window_id=window_id)

    @app.tool()
    def get_workflow_capabilities(window_id: str) -> dict:
        """Read actual frontend/capture capabilities before Bread-style workflows. Does not select an event, enable editing or change replay state. Requires updated bridge; availability is not proof a particular edit will succeed. B2-B6 adapters report not_integrated explicitly."""
        if not window_id:
            raise ValueError('Explicit window_id required')
        return live.client.call('get_workflow_capabilities', {}, window_id=window_id)
