"""Versioned shader-debug evidence; values retain exact bits, including NaN payloads."""
import hashlib
import json
import math
import os
import struct
import renderdoc as rd


def _variable(value):
    raw = b"".join(struct.pack("<Q", int(word)) for word in value.value.u64v)
    count = min(16, int(value.rows) * int(value.columns))
    floats = struct.unpack("<" + "f" * count, raw[:count * 4]) if count else []
    return {"name": value.name, "type": str(value.type), "rows": int(value.rows), "columns": int(value.columns),
            "raw_hex": raw.hex(), "float32_view": [v if math.isfinite(v) else str(v) for v in floats],
            "members": [_variable(member) for member in value.members]}


class ShaderDebugServiceMixin:
    def debug_shader_invocation(self, params):
        return self.export_shader_debug_trace(params)

    def export_shader_debug_trace(self, params):
        if not self.ctx.IsCaptureLoaded():
            return self._no_capture()
        stage = str(params.get("stage", "ps")).lower()
        if stage not in ("ps", "vs", "cs"):
            raise ValueError("Debug stage must be ps, vs or cs")
        eid = int(params["eid"])
        x, y = int(params.get("x", 0)), int(params.get("y", 0))
        if stage == "ps" and not all(k in params for k in ("x", "y")):
            raise ValueError("Pixel debugging requires x and y")
        if stage == "vs" and not all(k in params for k in ("vertex", "index", "instance")):
            raise ValueError("Vertex debugging requires vertex ID, index position and instance ID")
        if stage == "cs":
            for key in ("group", "thread"):
                if len(params.get(key, [])) != 3 or any(int(v) < 0 for v in params[key]):
                    raise ValueError("Compute debugging requires nonnegative three-component group/thread")
        maximum = int(params.get("max_steps", 100000))
        if min(eid, x, y) < 0 or not 1 <= maximum <= 1000000:
            raise ValueError("Invalid event, pixel coordinate or max_steps")
        path = os.path.abspath(params["dest"])
        if os.path.exists(path) and not params.get("overwrite", False):
            raise FileExistsError(path)
        payload = {"schema_version": 1, "capture_path": self.ctx.GetCaptureFilename(), "eid": eid,
                   "stage": stage.upper(), "invocation": {k: params[k] for k in ("x", "y", "sample", "primitive", "vertex", "index", "instance", "view", "group", "thread") if k in params},
                   "pixel": {"x": x, "y": y} if stage == "ps" else None, "coordinate_origin": "top-left",
                   "interpretation": "RenderDoc shader debugger simulation, separately compare to actual hardware output",
                   "states": [], "complete": False, "errors": []}

        def collect(controller):
            trace = None
            try:
                controller.SetFrameEvent(eid, False)
                pipeline = controller.GetPipelineState()
                stage_enum = getattr(rd.ShaderStage, {"ps": "Pixel", "vs": "Vertex", "cs": "Compute"}[stage])
                reflection = pipeline.GetShaderReflection(stage_enum)
                if reflection is None:
                    raise RuntimeError("No requested shader at event")
                payload["shader"] = {"rid": str(pipeline.GetShader(stage_enum)),
                    "sha256": hashlib.sha256(bytes(reflection.rawBytes)).hexdigest()}
                pipeline_object = pipeline.GetComputePipelineObject() if stage == "cs" else pipeline.GetGraphicsPipelineObject()
                payload["disassembly"] = controller.DisassembleShader(pipeline_object, reflection, "")
                if stage == "ps":
                    inputs = rd.DebugPixelInputs()
                    for field in ("sample", "primitive", "view"):
                        if field in params:
                            value = int(params[field])
                            if not 0 <= value <= 0xffffffff:
                                raise ValueError("Invalid pixel invocation selector")
                            setattr(inputs, field, value)
                    trace = controller.DebugPixel(x, y, inputs)
                elif stage == "vs":
                    values = [int(params[k]) for k in ("vertex", "instance", "index")]
                    if min(values) < 0:
                        raise ValueError("Vertex invocation indices cannot be negative")
                    trace = controller.DebugVertex(values[0], values[1], values[2], int(params.get("view", 0)))
                else:
                    trace = controller.DebugThread([int(v) for v in params["group"]], [int(v) for v in params["thread"]])
                if trace is None or trace.debugger is None:
                    raise RuntimeError("Requested shader debugger unavailable for this capture/API")
                for field in ("inputs", "constantBlocks", "readOnlyResources", "readWriteResources", "samplers"):
                    payload[field] = [_variable(value) for value in getattr(trace, field)]
                while True:
                    states = controller.ContinueDebug(trace.debugger)
                    if not states:
                        payload["complete"] = True
                        break
                    for state in states:
                        if len(payload["states"]) >= maximum:
                            raise RuntimeError("max_steps reached; trace incomplete")
                        payload["states"].append({"step": int(state.stepIndex), "next_instruction": int(state.nextInstruction),
                            "flags": str(state.flags), "callstack": list(state.callstack),
                            "changes": [{"before": _variable(change.before), "after": _variable(change.after)} for change in state.changes]})
            except Exception as exc:
                payload["errors"].append(str(exc))
            finally:
                if trace is not None:
                    controller.FreeTrace(trace)

        self.ctx.Replay().BlockInvoke(collect)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        temporary = path + ".tmp"
        with open(temporary, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, allow_nan=False, ensure_ascii=False, separators=(",", ":"))
            stream.write("\n")
        os.replace(temporary, path)
        return {"ok": payload["complete"], "mode": "summary",
                "data": {"path": path, "eid": eid, "x": x, "y": y, "steps": len(payload["states"]), "complete": payload["complete"]},
                "err": None if payload["complete"] else {"code": "incomplete_debug_trace", "msg": "; ".join(payload["errors"])},
                "meta": {"cap": "active", "truncated": False}}
