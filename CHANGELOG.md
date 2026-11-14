# Changelog

## 2026-11-14 — Bread workflow capability negotiation

- Add read-only `get_workflow_capabilities(window_id)` for actual frontend/capture discovery; planned B2–B6 adapters are explicitly not integrated. There are now 67 tools; all previous 66 input schemas are unchanged.
- Capture status exposes native session, edit revision and event-edit activity. Export bundles pin session/revision, reject same-path reopen/edit changes, and label legacy path-only guards.
- Document the current B1 boundary, deployment gap and full subsequent workflow scope. No native B2–B6 implementation or deployment is implied.
- Validation: 107 unit tests; unchanged previous 66 input contracts plus the new query; Windows x64 D3D11/D3D12 owned GUI fixtures each passed 205 checks using the latest Development runtime and source bridge. No x86/remote/Metal or fresh C++ build claim.

## 2026-11-13：B1 事件编辑

- 新增 6 个事件 Shader/CBuffer 工具，复用 CaptureContext 会话、回放队列与 GUI 撤销历史。
- 全局 Shader 工具保持原 schema，补充新前端的互斥与会话清理。
- 见 [使用说明](docs/event-editing.md)；旧前端显式不支持，暂未部署。

## 2026-11-02 — Scene/DCC and shader workflow extensions

Based on upstream `JinxiangW/renderdoc-mcp` commit `bb7d577421f740c5ae8f54bec0edb33e18a16742`.

### Added

- Six asset/evidence tools: reconstruction evidence, camera resolution and buffer extraction, scene/DCC bundles, batch textures, and shader analysis bundles.
- Four shader tools: backend discovery, language conversion, PS/VS/CS invocation debugging, and paginated trace reading.
- DCC-neutral geometry JSON and handoff metadata; optional glTF geometry/instances; explicit downstream FBX export requests.
- Per-event resource provenance, file hashes, partial-failure reporting and explicit unresolved reconstruction information.
- Regression coverage for camera math, geometry serialization, capture switching, shader pagination, compiler routes and debugger dispatch/cleanup.
- Portable Windows setup, compiler configuration and workflow documentation.

### Changed

- Live bridge default timeout increased from 20 to 120 seconds to accommodate loading large captures. This is a client wait budget, not a guaranteed operation time or cancellation mechanism.
- Ruri discovery works with arbitrarily named source checkouts, a configured DLL, and .NET from `DOTNET_ROOT`, the existing isolated installation, or PATH.
- Buffer export regression compares file identity so Windows 8.3 temporary-path aliases do not cause false failures.

### Validation and limitations

- 2026-11-02: all 87 unittest cases passed on Windows/Python 3.12 with the optional local compiler backends installed. Stdio MCP startup exposed 60 tools, including all 10 additions; backend capability lookup succeeded.
- Local D3D11 capture checks exported base geometry, DDS textures and VS/PS evidence. One PS Ruri decompilation failed with an upstream overflow; raw bytecode/disassembly and diagnostics remain available and the bundle reports incomplete.
- Real local compiler checks cover HLSL to DXBC/DXIL/SPIR-V/GLSL/MSL, SPIR-V to HLSL/MSL, GLSL to SPIR-V and a synthetic DXBC-to-HLSL decompilation.
- New VS/CS debugger routes have simulated-backend coverage; live-capture acceptance remains pending. Full scene/camera reconstruction and DCC/FBX delivery have not been validated end to end.
- No automatic matrix/material semantic inference, native FBX writer, original-source recovery, or target-runtime visual-equivalence guarantee is provided. See [workflow limitations](docs/asset-shader-workflows.md).
