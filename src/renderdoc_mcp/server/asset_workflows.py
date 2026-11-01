"""Capture evidence and portable scene exports. Replay stays in the existing bridge."""
from __future__ import annotations

import base64
import hashlib
import json
import math
from pathlib import Path
import struct
import subprocess
from typing import Any

from .shader_conversion import ruri_backend

IDENTITY = [1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1., 0., 0., 0., 0., 1.]


def matrix(value):
    if len(value) != 16 or not all(isinstance(x, (int, float)) and math.isfinite(x) for x in value):
        raise ValueError("Matrix must contain 16 finite row-ordered numbers, using column vectors")
    return list(map(float, value))


def inverse(value):
    m = matrix(value)
    rows = [m[i*4:i*4+4] + IDENTITY[i*4:i*4+4] for i in range(4)]
    for col in range(4):
        pivot = max(range(col, 4), key=lambda r: abs(rows[r][col]))
        if abs(rows[pivot][col]) < 1e-12:
            raise ValueError("Singular camera/view matrix")
        rows[col], rows[pivot] = rows[pivot], rows[col]
        divisor = rows[col][col]
        rows[col] = [x / divisor for x in rows[col]]
        for row in range(4):
            if row != col:
                factor = rows[row][col]
                rows[row] = [x-factor*y for x, y in zip(rows[row], rows[col])]
    return [x for row in rows for x in row[4:]]


def resolve_camera(view, projection, evidence, coordinate_system):
    """Never infer camera semantics from a matrix-shaped constant alone."""
    if not evidence or not coordinate_system:
        raise ValueError("Camera requires matrix provenance and source coordinate convention")
    view, projection = matrix(view), matrix(projection)
    if any(abs(a-b) > 1e-6 for a, b in zip(view[12:], [0, 0, 0, 1])):
        raise ValueError("View must be affine world-to-camera; a combined view-projection is invalid")
    world = inverse(view)
    return {"view": view, "projection": projection, "camera_to_world": world,
            "position": [world[3], world[7], world[11]], "coordinate_system": coordinate_system,
            "matrix_convention": "row-ordered, column-vector multiplication",
            "evidence": evidence, "status": "derived_from_supplied_view",
            "limitations": "Caller must establish view semantics, world origin, jitter and camera identity from capture evidence."}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")


def new_directory(dest):
    path = Path(dest).resolve()
    path.mkdir(parents=True, exist_ok=False)
    return path


class Bundle:
    def __init__(self, live, dest, window_id, expected_capture):
        if not window_id or not expected_capture:
            raise ValueError("An explicit window_id and expected_capture path are required")
        self.live, self.window_id, self.expected = live, window_id, expected_capture
        self.check_capture()
        self.path = new_directory(dest)
        self.errors = []
        self.records = []

    def check_capture(self):
        status = self.live.require("get_capture_status", {"window_id": self.window_id})
        data = status.get("data") or {}
        if not status.get("ok") or not data.get("loaded") or Path(data.get("path", "")).resolve() != Path(self.expected).resolve():
            raise RuntimeError("Capture changed or not loaded in requested window")
        return status

    def call(self, name, **params):
        # Check each operation so a switched window cannot silently mix captures.
        self.check_capture()
        try:
            result = self.live.require(name, dict(params, window_id=self.window_id))
        except Exception as exc:
            result = {"ok": False, "err": {"message": str(exc)}}
        self.records.append({"tool": name, "params": params, "result": result})
        if not result.get("ok"):
            self.errors.append({"tool": name, "params": params, "error": result.get("err")})
        return result

    def finish(self, payload):
        self.check_capture()
        files = []
        for path in sorted(self.path.rglob("*")):
            if path.is_file():
                with path.open("rb") as stream:
                    digest = hashlib.file_digest(stream, "sha256").hexdigest()
                files.append({"path": path.relative_to(self.path).as_posix(), "bytes": path.stat().st_size, "sha256": digest})
        payload.update(schema_version=1, capture=self.expected, window_id=self.window_id,
                       errors=self.errors, complete=not self.errors, files=files)
        write_json(self.path / "evidence.json", self.records)
        write_json(self.path / "manifest.json", payload)
        return {"ok": not self.errors, "path": str(self.path / "manifest.json"),
                "complete": not self.errors, "errors": self.errors, "files": len(files),
                "reconstruction_complete": payload.get("reconstruction_complete"), "unresolved": payload.get("unresolved", [])}


def export_textures(bundle, items):
    if len(items) > 256:
        raise ValueError("At most 256 textures per bundle")
    out = []
    for index, item in enumerate(items):
        fmt = str(item.get("format", "dds")).lower()
        if fmt not in {"dds", "png", "exr", "hdr", "tga", "jpg", "bmp"}:
            raise ValueError("Unsupported texture format")
        if not item.get("rid") or "eid" not in item:
            raise ValueError("Each texture requires rid and eid (resource contents vary per event)")
        name = "texture_{:04d}.{}".format(index, fmt)
        result = bundle.call("debug_save_texture", rid=str(item["rid"]), eid=int(item["eid"]),
                             dest=str(bundle.path / name), format=fmt, type_cast=item.get("type_cast"), overwrite=False)
        out.append({"file": name if result.get("ok") else None, "request": item,
                    "result": result, "semantic_status": "caller_supplied" if item.get("role") else "unassigned"})
    return out


class Gltf:
    """Small standard glTF writer for exported OBJ geometry; preserves split UV/normal indices."""
    def __init__(self):
        self.blob = bytearray()
        self.doc = {"asset": {"version": "2.0", "generator": "renderdoc-mcp"},
                    "scene": 0, "scenes": [{"nodes": []}], "nodes": [], "meshes": [],
                    "buffers": [], "bufferViews": [], "accessors": []}

    def accessor(self, values, width, indices=False):
        while len(self.blob) % 4:
            self.blob.append(0)
        offset = len(self.blob)
        flat = values if indices else [v for row in values for v in row]
        self.blob.extend(struct.pack("<" + ("I" if indices else "f") * len(flat), *flat))
        views = self.doc["bufferViews"]
        views.append({"buffer": 0, "byteOffset": offset, "byteLength": len(self.blob)-offset})
        a = {"bufferView": len(views)-1, "componentType": 5125 if indices else 5126,
             "count": len(values), "type": "SCALAR" if indices else "VEC"+str(width)}
        if not indices:
            a.update(min=[min(v[i] for v in values) for i in range(width)], max=[max(v[i] for v in values) for i in range(width)])
        self.doc["accessors"].append(a)
        return len(self.doc["accessors"])-1

    def obj(self, path):
        source = {"v": [], "vt": [], "vn": []}
        vertices, lookup, indices = [], {}, []
        for line in path.read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue
            if parts[0] in source:
                source[parts[0]].append(list(map(float, parts[1:])))
            elif parts[0] == "f":
                if len(parts) != 4:
                    raise ValueError("Expected triangulated OBJ")
                for token in parts[1:]:
                    if token not in lookup:
                        fields = (token + "//").split("/")[:3]
                        row = [source[key][int(i)-1] if i else None for key, i in zip(("v", "vt", "vn"), fields)]
                        lookup[token] = len(vertices)
                        vertices.append(row)
                    indices.append(lookup[token])
        if not vertices or not indices:
            raise ValueError("OBJ contains no triangles")
        attrs = {"POSITION": self.accessor([v[0][:3] for v in vertices], 3)}
        if all(v[1] is not None for v in vertices):
            attrs["TEXCOORD_0"] = self.accessor([v[1][:2] for v in vertices], 2)
        if all(v[2] is not None for v in vertices):
            attrs["NORMAL"] = self.accessor([v[2][:3] for v in vertices], 3)
        self.doc["meshes"].append({"primitives": [{"attributes": attrs, "indices": self.accessor(indices, 1, True), "mode": 4}]})
        return len(self.doc["meshes"])-1

    def node(self, name, mesh, transform, extras):
        # glTF serializes matrices column-major.
        m = matrix(transform)
        node = {"name": name, "matrix": [m[r*4+c] for c in range(4) for r in range(4)], "extras": extras}
        if mesh is not None:
            node["mesh"] = mesh
        self.doc["nodes"].append(node)
        self.doc["scenes"][0]["nodes"].append(len(self.doc["nodes"])-1)

    def save(self, path):
        self.doc["buffers"] = [{"byteLength": len(self.blob), "uri": "data:application/octet-stream;base64,"+base64.b64encode(self.blob).decode("ascii")}]
        write_json(path, self.doc)


def scene_bundle(live, dest, draws, texture_items, camera, source_to_gltf, window_id, expected_capture, delivery="data"):
    if not 1 <= len(draws) <= 512:
        raise ValueError("Provide 1..512 selected draw events")
    if delivery not in {"data", "obj", "gltf", "fbx"}:
        raise ValueError("delivery must be data, obj, gltf or fbx (DCC export job)")
    basis = matrix(source_to_gltf) if source_to_gltf is not None else None
    b = Bundle(live, dest, window_id, expected_capture)
    gltf, objects, unresolved = Gltf(), [], []
    for index, draw in enumerate(draws):
        eid = int(draw["eid"])
        filename = "mesh_{:04d}_eid_{}.obj".format(index, eid)
        result = b.call("export_mesh", eid=eid, dest=str(b.path / filename), overwrite=False)
        entry = {"eid": eid, "file": filename if result.get("ok") else None, "result": result,
                 "instances": draw.get("instances", []), "material_bindings": draw.get("material_bindings", [])}
        objects.append(entry)
        entry["pipeline"] = b.call("inspect_pipeline_state", eid=eid)
        if draw.get("export_postvs"):
            entry["postvs"] = b.call("export_postvs", eid=eid, dest=str(b.path / ("postvs_"+str(index))),
                                    first_instance=int(draw.get("first_instance", 0)), instance_count=int(draw.get("instance_count", 1)))
        if not result.get("ok"):
            continue
        # DCCs can build geometry directly without invoking an OBJ/glTF importer.
        geometry = {"positions": [], "normals": [], "uv0": [], "faces": [],
                    "index_base": 0, "space": "VS input; deformation/object transform not baked"}
        for line in (b.path / filename).read_text(encoding="utf-8").splitlines():
            parts = line.split()
            if not parts:
                continue
            key = {"v": "positions", "vn": "normals", "vt": "uv0"}.get(parts[0])
            if key:
                geometry[key].append(list(map(float, parts[1:])))
            elif parts[0] == "f":
                geometry["faces"].append([[int(i)-1 if i else None for i in (token+"//").split("/")[:3]] for token in parts[1:]])
        geometry_name = filename.replace(".obj", ".geometry.json")
        write_json(b.path / geometry_name, geometry)
        entry["geometry_data"] = geometry_name
        placed = draw.get("instances") or []
        if not placed:
            unresolved.append({"eid": eid, "reason": "Object/instance transforms unresolved; base geometry only"})
        if basis is None:
            continue
        try:
            mesh_index = gltf.obj(b.path / filename)
            for n, instance in enumerate(placed):
                if not instance.get("evidence"):
                    raise ValueError("Each instance transform requires evidence")
                m = matrix(instance["matrix"])
                world = [sum(basis[r*4+k]*m[k*4+c] for k in range(4)) for r in range(4) for c in range(4)]
                gltf.node("eid_{}_instance_{}".format(eid, n), mesh_index, world, instance)
        except Exception as exc:
            b.errors.append({"eid": eid, "error": str(exc)})
    cam = None
    if camera:
        cam = resolve_camera(camera["view"], camera["projection"], camera["evidence"], camera["coordinate_system"])
        write_json(b.path / "camera.json", cam)
    else:
        unresolved.append({"reason": "Camera view/projection not supplied; inspect cbuffer evidence before reconstruction"})
    if basis is not None and gltf.doc["nodes"]:
        gltf.save(b.path / "scene.gltf")
    elif basis is None:
        unresolved.append({"reason": "source_to_gltf axis/unit mapping unspecified; OBJ and manifest retain source coordinates"})
    exported = export_textures(b, texture_items)
    write_json(b.path / "DCC_HANDOFF.json", {"schema_version": 1, "objects": objects, "camera": cam, "textures": exported,
        "requested_delivery": delivery, "fbx_status": "requires_downstream_DCC_export" if delivery == "fbx" else "not_requested",
        "source_to_gltf": basis, "unresolved": unresolved,
        "instructions": ["Read *.geometry.json to create DCC meshes directly; face corners are [position,uv,normal] indices, zero-based, nullable.",
          "Apply only evidenced instance transforms; unresolved base meshes belong in an unplaced collection.",
          "Optionally import scene.gltf for placed geometry, or OBJ files using manifest instance matrices.",
          "Create a camera from camera_to_world and projection using the declared source convention; preserve off-axis/jitter/reverse-Z metadata.",
          "Bind textures only using explicit material_bindings; shader slots alone do not establish PBR semantics.",
          "No original skeleton, animation, engine materials, invisible geometry or pre-skinning asset recovery is implied.",
          "For requested FBX, reconstruct in the target DCC, then export FBX there; do not report FBX success until that file exists."]})
    return b.finish({"kind": "scene", "objects": objects, "camera": cam, "textures": exported,
                     "unresolved": unresolved, "reconstruction_complete": not unresolved and not b.errors})


def shader_bundle(live, dest, eid, stages, pixels, window_id, expected_capture):
    if not stages or any(s not in {"vs", "ps", "cs", "hs", "ds", "gs"} for s in stages):
        raise ValueError("Stages must be vs/ps/cs/hs/ds/gs")
    if len(pixels) > 16:
        raise ValueError("At most 16 explicitly selected pixels")
    b = Bundle(live, dest, window_id, expected_capture)
    summary = {"kind": "shader_analysis", "eid": eid, "stages": {}, "interpretation":
               "Source requires capture debug info. Disassembly is authoritative over decompilation. Debug traces are RenderDoc simulation, not hardware measurements."}
    summary["draw"] = b.call("get_draw_packet", eid=eid)
    for stage in dict.fromkeys(stages):
        stage_data = {"reflection": b.call("inspect_shader", eid=eid, stage=stage),
                      "constants": b.call("inspect_cbuffer_values", eid=eid, stage=stage),
                      "bytecode": b.call("export_shader_raw_bytes", eid=eid, stage=stage, dest=str(b.path / (stage+".bin")))}
        for method, suffix in [("get_shader_code", "code"), ("get_shader_disasm", "disasm")]:
            pages, offset = [], 0
            complete = False
            for _ in range(2500):
                page = b.call(method, eid=eid, stage=stage, offset=offset, max_lines=400)
                if not page.get("ok"):
                    break
                outer = page.get("data") or {}
                data = outer.get("code", outer)
                text = data.get("text", "")
                pages.append(text)
                if not data.get("truncated", page.get("meta", {}).get("truncated", False)):
                    complete = True
                    break
                count = int(data.get("returned", len(text.splitlines())))
                if count <= 0:
                    break
                offset += count
            (b.path / (stage+"."+suffix+".txt")).write_text("\n".join(pages), encoding="utf-8")
            stage_data[suffix] = {"complete": complete, "file": stage+"."+suffix+".txt"}
            if not complete:
                b.errors.append({"stage": stage, "tool": method, "error": "Code retrieval incomplete"})
        # Use the already installed bundled decompiler, never an arbitrary command from a tool argument.
        ruri, dotnet = ruri_backend()
        encoding = str((stage_data["bytecode"].get("data") or {}).get("encoding", ""))
        decompiled = {"status": "unavailable", "reason": "Bundled decompiler/runtime or supported shader encoding unavailable"}
        if stage_data["bytecode"].get("ok") and ruri.is_file() and dotnet is not None and encoding in {"DXBC", "DXIL", "SPIRV"}:
            output = b.path / (stage+".decompiled.hlsl")
            try:
                run = subprocess.run([str(dotnet), str(ruri), str(b.path / (stage+".bin")), str(output),
                    "--shader-model", "50" if encoding == "DXBC" else "60"], capture_output=True, text=True,
                    encoding="utf-8", errors="replace", timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
                decompiled = {"status": "success" if run.returncode == 0 and output.is_file() else "failed",
                              "returncode": run.returncode, "file": output.name if output.is_file() else None,
                              "diagnostics": (run.stdout+run.stderr)[-12000:], "interpretation": "Reconstructed HLSL, not original source; verify against bytecode"}
            except Exception as exc:
                decompiled = {"status": "failed", "reason": str(exc)}
        stage_data["decompilation"] = decompiled
        if decompiled['status'] != 'success':
            b.errors.append({'stage': stage, 'tool': 'ruri_decompile', 'error': decompiled})
        summary["stages"][stage] = stage_data
    for index, pixel in enumerate(pixels):
        b.call("export_shader_debug_trace", eid=eid, x=int(pixel["x"]), y=int(pixel["y"]),
               dest=str(b.path / ("pixel_{}.json".format(index))), max_steps=100000)
        if pixel.get("rid"):
            b.call("export_pixel_history", rid=pixel["rid"], x=int(pixel["x"]), y=int(pixel["y"]),
                   eid_max=eid, dest=str(b.path / ("history_{}.json".format(index))))
    (b.path / "ANALYSIS_GUIDE.md").write_text("# Shader evidence workflow\n\n"
        "1. Cross-check bindings, actual constant values and shader bytecode.\n"
        "2. Split source/disassembly into input decode, sampling, evaluation and output packing; cite line ranges.\n"
        "3. Trace important input RIDs with inspect_texture_usage, then inspect their producer shaders.\n"
        "4. Preserve exact bit operations and decompiler identifiers until semantics have evidence.\n"
        "5. Compare pixel debug simulation with exported hardware replay output. Treat differences as unresolved.\n"
        "6. Report confirmed facts, hypotheses, missing source, incomplete traces and API limitations separately.\n", encoding="utf-8")
    return b.finish(summary)


def register_asset_tools(app, live):
    @app.tool()
    def resolve_capture_camera(view: list[float], projection: list[float], evidence: dict[str, Any], coordinate_system: str) -> Any:
        """Derive position and camera-to-world from an evidenced world-to-view matrix. Row-ordered matrices, column vectors. Does not guess camera constants."""
        return resolve_camera(view, projection, evidence, coordinate_system)

    @app.tool()
    def extract_capture_camera(eid: int, view_locator: dict[str, Any], projection_locator: dict[str, Any],
                               coordinate_system: str, evidence: dict[str, Any], dest: str,
                               window_id: str, expected_capture: str) -> Any:
        """Read exact float32 4x4 view/projection matrices from capture buffers and derive camera pose. Locators require rid,offset (absolute buffer byte offset),row_major(bool),row_vector(bool). Declare source axes/units/world origin and evidence establishing matrix meanings; no blind matrix guessing. Fresh output directory."""
        if not evidence or not coordinate_system:
            raise ValueError("Camera matrix semantics and coordinate convention need evidence")
        for locator in (view_locator, projection_locator):
            if not all(k in locator for k in ("rid", "offset", "row_major", "row_vector")):
                raise ValueError("Each locator requires rid, offset, row_major and row_vector")
            if int(locator["offset"]) < 0 or not isinstance(locator['row_major'], bool) or not isinstance(locator['row_vector'], bool):
                raise ValueError("Invalid locator convention or offset")
        b = Bundle(live, dest, window_id, expected_capture)
        matrices = {}
        for name, locator in (("view", view_locator), ("projection", projection_locator)):
            path = b.path / (name+".bin")
            result = b.call("export_buffer", eid=eid, rid=locator['rid'], offset=int(locator['offset']), length=64, dest=str(path))
            if not result.get('ok'):
                return b.finish({'kind': 'camera', 'camera': None})
            values = list(struct.unpack('<16f', path.read_bytes()))
            # Column-major storage and row-vector math are separate transpose operations.
            for transpose in (not locator['row_major'], locator['row_vector']):
                if transpose:
                    values = [values[c*4+r] for r in range(4) for c in range(4)]
            matrices[name] = values
        camera = resolve_camera(matrices['view'], matrices['projection'],
            dict(evidence, eid=eid, view_locator=view_locator, projection_locator=projection_locator), coordinate_system)
        write_json(b.path/'camera.json', camera)
        return b.finish({'kind': 'camera', 'camera': camera})

    @app.tool()
    def collect_reconstruction_evidence(eids: list[int], window_id: str, expected_capture: str, dest: str) -> Any:
        """Export mesh/pipeline and VS/PS constants for locating object/view/projection matrices. Constant names are candidates, not proof of semantics."""
        if not 1 <= len(eids) <= 128:
            raise ValueError("Provide 1..128 selected events")
        b = Bundle(live, dest, window_id, expected_capture)
        for eid in eids:
            b.call("inspect_mesh", eid=eid)
            b.call("inspect_pipeline_state", eid=eid)
            for stage in ("vs", "ps"):
                b.call("inspect_shader", eid=eid, stage=stage)
                b.call("inspect_cbuffer_values", eid=eid, stage=stage)
        return b.finish({"kind": "reconstruction_evidence", "eids": eids})

    @app.tool()
    def export_scene_bundle(dest: str, draws: list[dict[str, Any]], window_id: str, expected_capture: str,
                            textures: list[dict[str, Any]] | None = None, camera: dict[str, Any] | None = None,
                            source_to_gltf: list[float] | None = None, delivery: str = "data") -> Any:
        """Export portable geometry JSON, OBJ, optional placed glTF, textures and DCC_HANDOFF.json for direct reconstruction via DCC MCP. delivery=data/obj/gltf/fbx; FBX is an explicit downstream DCC export job, not a fabricated local file. Each draw: eid, optional instances [{matrix:16 row-ordered values,evidence:{...}}], material_bindings, export_postvs. Camera: view,projection,evidence,coordinate_system. source_to_gltf maps source-world axes/units to RH Y-up meters. Missing transforms/camera stay unresolved. Fresh destination required."""
        return scene_bundle(live, dest, draws, textures or [], camera, source_to_gltf, window_id, expected_capture, delivery)

    @app.tool()
    def export_texture_bundle(dest: str, textures: list[dict[str, Any]], window_id: str, expected_capture: str) -> Any:
        """Batch-export textures with hashes and per-item errors. Each entry: rid,eid,format (default dds), optional type_cast and role. DDS preserves data better than display PNG; supply observed typeless view cast. Fresh destination required."""
        b = Bundle(live, dest, window_id, expected_capture)
        return b.finish({"kind": "textures", "textures": export_textures(b, textures)})

    @app.tool()
    def export_shader_analysis_bundle(dest: str, eid: int, stages: list[str], window_id: str, expected_capture: str,
                                       pixels: list[dict[str, Any]] | None = None) -> Any:
        """Export paginated shader code/disassembly, raw bytecode, bindings, actual constants, and optional full pixel traces/history. pixels: [{x,y,rid?}]. Explicit stages vs/ps/cs/hs/ds/gs; no fabricated source or semantics. Fresh destination required."""
        return shader_bundle(live, dest, eid, stages, pixels or [], window_id, expected_capture)
