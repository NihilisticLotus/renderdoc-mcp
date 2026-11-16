"""Event edits use the native CaptureContext transaction owner, never ReplaceResource."""
import json
import math
import hashlib
import base64
import os
import tempfile
import struct
import renderdoc as rd
from .base import BridgeService, invoke_replay_checked
from .capture import CaptureStatusService


class EventEditService(BridgeService):
    STAGES = {"vs": rd.ShaderStage.Vertex, "hs": rd.ShaderStage.Hull,
              "ds": rd.ShaderStage.Domain, "gs": rd.ShaderStage.Geometry,
              "ps": rd.ShaderStage.Pixel, "cs": rd.ShaderStage.Compute}

    @staticmethod
    def response(data=None, error=None, code="event_edit_failed"):
        return {"ok": not error, "mode": "summary", "data": data,
                "err": {"code": code, "msg": str(error)} if error else None,
                "meta": {"cap": "active", "truncated": False}}

    def invoke(self, callback):
        try:
            return CaptureStatusService(self.ctx)._invoke_on_ui_thread(callback, 120.0)
        except Exception as exc:
            return self.response(error=str(exc))

    def validate(self, params, mutation=False):
        if not all(callable(getattr(self.ctx, name, None)) for name in (
            "GetCaptureSessionID", "EventEditRevision", "EditEventShader", "EditEventCBuffer", "UndoEventEdit")):
            raise RuntimeError("This frontend does not support shared event editing")
        if not self.ctx.IsCaptureLoaded():
            raise RuntimeError("No capture loaded")
        if mutation:
            if not params.get("session_id") or params["session_id"] != self.ctx.GetCaptureSessionID():
                raise RuntimeError("Capture session mismatch; read the event state again")
            if "revision" in params and params["revision"] != self.ctx.EventEditRevision():
                raise RuntimeError("Edit revision mismatch; read the event state again")

    def select(self, params):
        eid = params.get("eid")
        if eid is None:
            eid = self.ctx.CurEvent()
        if isinstance(eid, bool) or not isinstance(eid, int) or eid < 1 or self.ctx.GetAction(eid) is None:
            raise ValueError("eid must identify an existing event")
        self.ctx.SetEventID([], eid, eid, False)
        return eid

    def snapshot(self, stage_name="ps", x=0, y=0):
        if stage_name not in self.STAGES:
            raise ValueError("stage must be vs/hs/ds/gs/ps/cs")
        if any(isinstance(v, bool) or not isinstance(v, int) or v < 0 for v in (x, y)):
            raise ValueError("Pixel coordinates must be non-negative integers")
        stage = self.STAGES[stage_name]
        data = {"session_id": self.ctx.GetCaptureSessionID(), "revision": self.ctx.EventEditRevision(),
                "undo_count": self.ctx.EventEditUndoCount(), "eid": self.ctx.CurEvent(), "stage": stage_name,
                "enabled": rd.GetConfigSetting("Replay.EventOverrides").data.basic.b,
                "diagnostics": self.ctx.EventEditDiagnostics(), "cbuffers": []}
        native = {}
        def collect(r):
            pipe = r.GetPipelineState()
            shader = pipe.GetShader(stage)
            reflection = pipe.GetShaderReflection(stage)
            native.update(shader=shader, reflection=reflection, buffers={})
            data["shader"] = str(shader)
            active = r.GetEventShaderOverride(data["eid"], stage)
            data["shader_override"] = {"active": active.active, "replacement": str(active.replacement)}
            preview = r.GetEventShaderPreviewTexture(data["eid"], stage)
            data["preview"] = {"resource": str(preview.resourceId), "width": preview.width, "height": preview.height,
                               "format": str(preview.format.Name()) if preview.resourceId != rd.ResourceId.Null() else None}
            data["preview"]["pixel"] = None
            if preview.resourceId != rd.ResourceId.Null():
                if x >= preview.width or y >= preview.height:
                    raise ValueError("Pixel coordinates are outside the independent preview")
                value = r.PickPixel(preview.resourceId, x, y, rd.Subresource(), rd.CompType.Float)
                data["preview"]["pixel"] = {"x": x, "y": y, "rgba": [
                    float(v) if math.isfinite(v) else str(float(v)) for v in value.floatValue]}
            if not reflection:
                return
            # Copy all data consumed outside this replay callback; reflection is replay-owned.
            native.update(entry=reflection.entryPoint, encoding=reflection.encoding,
                          raw=bytes(reflection.rawBytes), flags=rd.ShaderCompileFlags(reflection.debugInfo.compileFlags))
            native.pop("reflection", None)
            for index, block in enumerate(reflection.constantBlocks):
                if not block.bufferBacked:
                    continue
                cb = pipe.GetConstantBlock(stage, index, 0).descriptor
                if cb.resource == rd.ResourceId.Null() or cb.flags & rd.DescriptorFlags.InlineData:
                    continue
                size = cb.byteSize
                if r.GetAPIProperties().pipelineType == rd.GraphicsAPI.D3D12:
                    for root in r.GetD3D12PipelineState().rootSignature.parameters:
                        if (root.descriptor.type == rd.DescriptorType.ConstantBuffer and root.reg == block.fixedBindNumber
                                and root.space == block.fixedBindSetOrSpace and root.descriptor.resource == cb.resource
                                and root.descriptor.byteOffset == cb.byteOffset):
                            size = (block.byteSize + 15) & ~15
                if not size or size > 65536 or size % 16:
                    continue
                binding = rd.EventCBufferOverrideState()
                binding.active = True
                binding.eventId, binding.stage = data["eid"], stage
                binding.slot, binding.registerSpace = block.fixedBindNumber, block.fixedBindSetOrSpace
                binding.expectedShader, binding.expectedBuffer = shader, cb.resource
                binding.expectedByteOffset, binding.expectedByteSize = cb.byteOffset, size
                current = r.GetEventCBufferOverride(data["eid"], stage, binding.slot, binding.registerSpace)
                binding.data = current.data if current.active else r.GetBufferData(cb.resource, cb.byteOffset, size)
                native["buffers"][(binding.slot, binding.registerSpace)] = binding
                data["cbuffers"].append({"name": block.name, "slot": binding.slot, "space": binding.registerSpace,
                    "buffer": str(cb.resource), "offset": cb.byteOffset, "size": size, "active": current.active})
        invoke_replay_checked(self.ctx, collect)
        return data, native

    def shader_workspace(self, params):
        # Native UI owns every document, compiler snapshot and runtime transaction.
        def run():
            if not callable(getattr(self.ctx, "ShaderWorkspaceCommand", None)):
                raise RuntimeError("This frontend does not support the B3 Shader workspace")
            request = {key: value for key, value in params.items() if value is not None and key != "show"}
            if request.get("operation") not in ("state", "create", "update", "compile", "apply", "save_draft", "attach_file", "decompile"):
                raise ValueError("Unknown workspace operation")
            if "stage" in request:
                if request["stage"] not in self.STAGES:
                    raise ValueError("Invalid Shader stage")
                request["stage"] = int(self.STAGES[request["stage"]])
            if params.get("show"):
                self.ctx.ShowShaderWorkspace()
            result = json.loads(self.ctx.ShaderWorkspaceCommand(json.dumps(request, ensure_ascii=False)))
            data = result.get("data", {})
            if "document" in result:
                data["document"] = result["document"]
            return self.response(data, result.get("error") if not result.get("ok") else None,
                                 "shader_workspace_failed")
        return self.invoke(run)

    def get_event_edit_state(self, params):
        def run():
            self.validate(params)
            self.select(params)
            if params.get("show"):
                self.ctx.ShowEventEditor()
            return self.response(self.snapshot(params.get("stage", "ps"), params.get("x", 0), params.get("y", 0))[0])
        return self.invoke(run)

    def set_event_editing_enabled(self, params):
        def run():
            self.validate(params, True)
            error = self.ctx.SetEventEditingEnabled(params["session_id"], params["enabled"])
            return self.response(self.snapshot()[0], error)
        return self.invoke(run)

    def apply_event_shader_edit(self, params):
        def run():
            self.validate(params, True)
            eid = self.select(params)
            data, native = self.snapshot(params.get("stage", "ps"))
            if data["shader"] != params["expected_shader"]:
                raise ValueError("Captured Shader identity mismatch")
            if "entry" not in native:
                raise ValueError("The selected stage has no Shader reflection")
            captured = params.get("captured_shader", False)
            if captured:
                source, encoding = native["raw"], native["encoding"]
            else:
                if bool(params.get("source")) == bool(params.get("source_path")):
                    raise ValueError("Supply exactly one of source or source_path")
                if params.get("source_path"):
                    with open(params["source_path"], "rb") as f:
                        source = f.read()
                else:
                    source = params["source"].encode("utf-8")
                encoding = rd.ShaderEncoding.HLSL
            b = rd.EventShaderOverrideState()
            b.active, b.eventId, b.stage = True, eid, self.STAGES[data["stage"]]
            b.expectedOriginal = native["shader"]
            b.independentFloatOutput = params.get("independent_float", True)
            b.outputTarget = params.get("output_target", 0) if b.independentFloatOutput else 4294967295
            error = self.ctx.EditEventShader(params["session_id"], params["revision"], b,
                    params.get("entry_point") or native["entry"], encoding, source, native["flags"])
            return self.response(self.snapshot(data["stage"])[0], error)
        return self.invoke(run)

    def apply_event_cbuffer_edit(self, params):
        def run():
            self.validate(params, True)
            self.select(params)
            data, native = self.snapshot(params.get("stage", "ps"))
            key = (params["slot"], params.get("space", 0))
            b = native["buffers"].get(key)
            if b is None:
                raise ValueError("No supported fixed CBuffer window at the requested slot/space")
            if (str(b.expectedShader) != params["expected_shader"] or str(b.expectedBuffer) != params["expected_buffer"]
                    or b.expectedByteOffset != params["expected_offset"] or b.expectedByteSize != params["expected_size"]):
                raise ValueError("Captured CBuffer identity or window mismatch")
            values, path = params.get("values"), params.get("data_path")
            if (values is None) == (path is None):
                raise ValueError("Supply exactly one of values or data_path")
            if path is not None:
                with open(path, "rb") as f:
                    payload = f.read()
                if len(payload) != b.expectedByteSize:
                    raise ValueError("File size must match the complete CBV window")
            else:
                offset = params.get("edit_offset", 0)
                if not values or offset < 0 or offset % 4 or offset + 4 * len(values) > b.expectedByteSize:
                    raise ValueError("Float edits must fit within the bound window at a four-byte aligned offset")
                if not all(math.isfinite(v) for v in values):
                    raise ValueError("Use a binary file for non-finite float bit patterns")
                payload = bytearray(b.data)
                payload[offset:offset + 4 * len(values)] = struct.pack("<%df" % len(values), *values)
            b.data = bytes(payload)
            error = self.ctx.EditEventCBuffer(params["session_id"], params["revision"], b)
            return self.response(self.snapshot(data["stage"])[0], error)
        return self.invoke(run)

    def clear_event_edit(self, params):
        def run():
            self.validate(params, True)
            eid = self.select(params)
            stage_name = params.get("stage", "ps")
            if stage_name not in self.STAGES:
                raise ValueError("Unsupported stage")
            if params["kind"] == "shader":
                b = rd.EventShaderOverrideState()
                b.eventId, b.stage = eid, self.STAGES[stage_name]
                error = self.ctx.EditEventShader(params["session_id"], params["revision"], b, "", rd.ShaderEncoding.HLSL, b"", rd.ShaderCompileFlags())
            elif params["kind"] == "cbuffer":
                b = rd.EventCBufferOverrideState()
                b.eventId, b.stage, b.slot, b.registerSpace = eid, self.STAGES[stage_name], params.get("slot", 0), params.get("space", 0)
                error = self.ctx.EditEventCBuffer(params["session_id"], params["revision"], b)
            else:
                raise ValueError("kind must be shader or cbuffer")
            return self.response(self.snapshot(stage_name)[0], error)
        return self.invoke(run)

    def undo_event_edit(self, params):
        def run():
            self.validate(params, True)
            error = self.ctx.UndoEventEdit(params["session_id"], params["revision"])
            return self.response(self.snapshot()[0], error)
        return self.invoke(run)

    def validate_b2(self, params):
        if isinstance(params.get("revision"), bool) or not isinstance(params.get("revision"), int):
            raise ValueError("B2 operations require an explicit integer edit revision")
        self.validate(params, True)
        if not callable(getattr(self.ctx, "EditSharedBufferRange", None)):
            raise RuntimeError("This frontend does not support B2 analysis or shared Buffer edits")

    @staticmethod
    def resource(r, name, textures=False):
        resources = r.GetTextures() if textures else r.GetBuffers()
        for item in resources:
            if str(item.resourceId) == name:
                return item
        raise ValueError("Resource does not identify a captured {}".format("texture" if textures else "buffer"))

    def shared_state(self):
        data = {"session_id": self.ctx.GetCaptureSessionID(), "revision": self.ctx.EventEditRevision(),
                "undo_count": self.ctx.EventEditUndoCount(), "eid": self.ctx.CurEvent(),
                "enabled": bool(rd.GetConfigSetting("Replay.SharedBufferEdits").data.basic.b), "patches": []}
        def collect(r):
            for patch in r.GetSharedBufferPatches():
                payload = bytes(patch.data)
                data["patches"].append({"buffer": str(patch.buffer), "offset": patch.byteOffset,
                    "length": len(payload), "sha256": hashlib.sha256(payload).hexdigest()})
        invoke_replay_checked(self.ctx, collect)
        return data

    def get_shared_buffer_state(self, params):
        def run():
            self.validate_b2(params)
            return self.response(self.shared_state())
        return self.invoke(run)

    def set_shared_buffer_editing_enabled(self, params):
        def run():
            self.validate_b2(params)
            if not isinstance(params.get("enabled"), bool):
                raise ValueError("enabled must be boolean")
            error = self.ctx.SetSharedBufferEditingEnabled(params["session_id"], params["enabled"])
            return self.response(self.shared_state(), error)
        return self.invoke(run)

    def apply_shared_buffer_edit(self, params):
        def run():
            self.validate_b2(params)
            offset, length = params["offset"], params["length"]
            if any(isinstance(v, bool) or not isinstance(v, int) for v in (offset, length)) or offset < 0 or not 0 < length <= 16777216:
                raise ValueError("Shared range requires a nonnegative offset and 1..16 MiB length")
            reset = params.get("reset", False)
            inputs = [params.get("data_hex") is not None, params.get("data_path") is not None]
            if (reset and any(inputs)) or (not reset and sum(inputs) != 1):
                raise ValueError("Supply exactly one byte source, or reset without a byte source")
            payload = b""
            if params.get("data_path") is not None:
                with open(params["data_path"], "rb") as f:
                    payload = f.read(length + 1)
            elif params.get("data_hex") is not None:
                if len(params["data_hex"]) > length * 3:
                    raise ValueError("Hex payload exceeds the requested range")
                payload = bytes.fromhex(params["data_hex"])
            if not reset and len(payload) != length:
                raise ValueError("Payload length must equal the requested shared range")
            native = []
            invoke_replay_checked(self.ctx, lambda r: native.append(self.resource(r, params["buffer"]).resourceId))
            error = self.ctx.EditSharedBufferRange(params["session_id"], params["revision"],
                                                   native[0], offset, length, payload)
            return self.response(self.shared_state(), error)
        return self.invoke(run)

    def get_rt_history(self, params):
        def run():
            self.validate_b2(params)
            data = {"session_id": self.ctx.GetCaptureSessionID(), "revision": self.ctx.EventEditRevision(),
                    "selected_eid": self.ctx.CurSelectedEvent(), "effective_eid": self.ctx.CurEvent()}
            def collect(r):
                texture = self.resource(r, params["texture"], True)
                data.update(texture=str(texture.resourceId), width=texture.width, height=texture.height,
                            mips=texture.mips, slices=texture.arraysize, samples=texture.msSamp,
                            format=str(texture.format.Name()), events=[{"eid": u.eventId, "usage": str(u.usage)}
                                for u in r.GetUsage(texture.resourceId)])
            invoke_replay_checked(self.ctx, collect)
            return self.response(data)
        return self.invoke(run)

    def get_rt_snapshot(self, params):
        def run():
            self.validate_b2(params)
            for name in ("eid", "mip", "slice"):
                value = params.get(name, 0)
                if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                    raise ValueError("{} must be a nonnegative integer".format(name))
            minimum, maximum = params.get("range_min", 0.0), params.get("range_max", 1.0)
            if not math.isfinite(minimum) or not math.isfinite(maximum) or minimum >= maximum:
                raise ValueError("Display range must be finite and increasing")
            selected, effective = self.ctx.CurSelectedEvent(), self.ctx.CurEvent()
            data = {"session_id": self.ctx.GetCaptureSessionID(), "revision": self.ctx.EventEditRevision()}
            native = []
            def collect(r):
                texture = self.resource(r, params["texture"], True)
                sub = rd.Subresource()
                sub.mip, sub.slice, sub.sample = params.get("mip", 0), params.get("slice", 0), 0
                snapshot = r.GetTextureSnapshotAtEvent(params["eid"], texture.resourceId, sub,
                                                        rd.CompType.Typeless, minimum, maximum)
                if snapshot.error:
                    raise RuntimeError(snapshot.error)
                payload, preview = bytes(snapshot.data), bytes(snapshot.preview)
                native.append(payload)
                data.update(eid=snapshot.eventId, texture=str(texture.resourceId),
                            mip=sub.mip, slice=sub.slice, format=str(texture.format.Name()),
                            byte_length=len(payload), sha256=hashlib.sha256(payload).hexdigest(),
                            prefix_hex=payload[:256].hex(),
                            preview={"encoding": "RGB8", "width": snapshot.width, "height": snapshot.height,
                                     "base64": base64.b64encode(preview).decode("ascii")})
            invoke_replay_checked(self.ctx, collect)
            self.validate_b2(params)
            if (selected, effective) != (self.ctx.CurSelectedEvent(), self.ctx.CurEvent()):
                raise RuntimeError("Selection changed during temporary analysis")
            data.update(selected_eid=selected, effective_eid=effective)
            path = params.get("raw_path")
            if path:
                path = os.path.abspath(path)
                fd, temporary = tempfile.mkstemp(prefix=".rt-snapshot-", dir=os.path.dirname(path))
                try:
                    with os.fdopen(fd, "wb") as f:
                        f.write(native[0])
                    os.replace(temporary, path)
                finally:
                    if os.path.exists(temporary):
                        os.unlink(temporary)
                data["raw_path"] = path
            return self.response(data)
        return self.invoke(run)
