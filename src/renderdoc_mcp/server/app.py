"""Tool registry scaffold for the RenderDoc MCP server."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ToolSpec:
    name: str
    summary_first: bool
    description: str


V1_SUMMARY_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("open_capture", True, "Open a capture and return only high-level facts."),
    ToolSpec("get_capture_status", True, "Return current capture status."),
    ToolSpec("find_events", True, "Find candidate events using compact filters."),
    ToolSpec("list_passes", True, "List pass markers with compact counts."),
    ToolSpec(
        "inspect_pipeline_state",
        True,
        "Return a compact pipeline snapshot for an event.",
    ),
    ToolSpec(
        "inspect_texture_usage",
        True,
        "Return compact read/write usage for a texture.",
    ),
    ToolSpec("inspect_shader", True, "Return compact shader bindings and constants info."),
    ToolSpec(
        "inspect_cbuffer_values",
        True,
        "Return constant-buffer bindings, ranges, and decoded variable values.",
    ),
    ToolSpec(
        "read_buffer",
        True,
        "Read and decode bytes from a live buffer resource.",
    ),
    ToolSpec("get_shader_disasm", True, "Return shader disassembly text with pagination support."),
    ToolSpec("get_shader_source", True, "Return shader source/debug text when source symbols are available."),
    ToolSpec("get_shader_code", True, "Return shader source when available, otherwise fall back to disassembly."),
    ToolSpec("inspect_mesh", True, "Return compact mesh inspection data."),
)


OFFLINE_BOOTSTRAP_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("get_capture_status", True, "Return current capture status."),
    ToolSpec("get_capture_context", True, "Return UE-side context metadata attached to the active or selected capture."),
    ToolSpec("get_capture_hints", True, "Return compact UE semantic hints derived from capture context metadata."),
    ToolSpec("compare_capture_contexts", True, "Compare UE-side context metadata between two captures."),
    ToolSpec("compare_pass_lists", True, "Compare two saved pass-list or frame-packet artifacts."),
    ToolSpec("compare_packet_artifacts", True, "Compare two saved compact JSON packet artifacts."),
    ToolSpec("compare_draw_packets", True, "Compare two saved draw-packet artifacts with draw-focused summaries."),
    ToolSpec("compare_texture_usage_artifacts", True, "Compare two saved texture-usage artifacts with resource-flow summaries."),
    ToolSpec("list_captures", True, "List capture files recursively under a root directory."),
    ToolSpec("open_capture", True, "Open a capture and return only high-level facts."),
    ToolSpec("find_latest_capture", True, "Find the newest .rdc capture under a directory."),
    ToolSpec("load_latest_capture", True, "Open the newest .rdc capture under a directory."),
    ToolSpec("wait_for_new_capture", True, "Wait for a newer .rdc capture, then open it."),
)


LIVE_BRIDGE_TOOLS: tuple[ToolSpec, ...] = (
    ToolSpec("get_shared_buffer_state", True, "Read persistent Buffer overlays and the shared GUI/MCP undo revision without changing selection."),
    ToolSpec("set_shared_buffer_editing_enabled", True, "Explicitly opt in to persistent Buffer editing for this process; defaults off."),
    ToolSpec("apply_shared_buffer_edit", True, "Set or reset an exact shared Buffer byte range for all events; uses the B1 GUI/MCP undo stack. Unsupported GPU-write, indirect or aliased dependencies return errors."),
    ToolSpec("get_rt_history", True, "List a captured texture's event usage without changing selection."),
    ToolSpec("get_rt_snapshot", True, "Read native texture bytes plus a separate RGB8 preview at an event, restoring effective replay and GUI selection before returning. Optional raw_path atomically exports native bytes. Single-sample 2D mip/slice only."),
    ToolSpec("shader_parameters", True, "List, read, alias or write reflected Shader workspace parameters. Identity includes content, stage, binding and physical layout. Writes use exact string scalar values and explicit event/shared scope, with the existing capture revision and GUI/MCP undo. Aliases only change display; list/read never apply."),
    ToolSpec("shader_workspace", True, "Manage native shared Shader documents: state/create/update/compile/apply/save_draft/attach_file/decompile. Compile never applies. Apply requires document revision, capture session and edit_revision, and uses the existing GUI/MCP undo stack. Source paths are exact include identities; no disassembly is treated as source."),
    ToolSpec("get_event_edit_state", True, "Read capture session, revision, bindings, shared undo state and unscaled RGBA32_FLOAT pixel at x/y (default 0/0); optionally select an event and show the editor."),
    ToolSpec("set_event_editing_enabled", True, "Explicitly enable or disable event registration for the active native frontend process. Does not persist configuration."),
    ToolSpec("apply_event_shader_edit", True, "Compile and apply an event-scoped Shader with independent RGBA32_FLOAT preview. Uses shared GUI undo, never global replacement."),
    ToolSpec("apply_event_cbuffer_edit", True, "Edit a validated event CBuffer window using float32 components or a complete binary file. Untouched bytes are preserved."),
    ToolSpec("clear_event_edit", True, "Clear one event Shader or CBuffer layer through the shared GUI undo history."),
    ToolSpec("undo_event_edit", True, "Undo the last GUI or MCP event edit using the native shared history. Requires the current capture session and revision."),

    ToolSpec("get_replay_camera_state", True, "Read RenderDuck free-camera capability, pose, completion/error status and optionally the visible field configuration."),
    ToolSpec("configure_replay_camera", True, "Configure RenderDuck free camera through its public API and populate its visible panel. Matrices are 16 mathematical row-ordered values (column vectors). Fields specify semantic, shader ResourceId, stage VS/HS/DS/GS/PS/CS, slot, offset, first_event, last_event, row_major and row_vector. Poll get_replay_camera_state until busy/pending_update are false; last_error reports replay failures. Requires an updated local D3D11 RenderDuck frontend."),
    ToolSpec("reset_replay_camera", True, "Disable the free camera and restore original replay while retaining visible field configuration. Poll state for completion."),
    ToolSpec("configure_replay_camera_recipe", True, "Set a data-only JSON replay recipe and optionally run it. Version 2 declares camera matrix locators and explicit pass skip/colour_bypass rules with reasons and capture SHA256/size; the bundled frontend script expands actual shader/event bindings. Poll get_replay_camera_state while scanning/busy/pending_update. Inspect scan_report, scan_partial and scan_field_count; partial results require apply_replay_camera_recipe. No arbitrary Python execution."),
    ToolSpec("apply_replay_camera_recipe", True, "Explicitly accept and apply the last completed camera recipe result, including a confirmed partial result. Inspect scan_report first. Poll get_replay_camera_state for replay completion."),
    ToolSpec("export_shader_debug_trace", True, "Export complete pixel shader debugger states with exact value bits and disassembly."),
    ToolSpec("export_capture_inventory", True, "Export all capture actions/resources or a bounded page of full pipeline bindings to JSON."),
    ToolSpec("export_pixel_history", True, "Export original per-fragment pixel history and rejection reasons at a mip0 pixel."),
    ToolSpec("list_live_windows", True, "List active qrenderdoc bridge windows and their window_id values."),
    ToolSpec("attach_qrenderdoc", True, "Diagnose and attach to an active qrenderdoc bridge window."),
    ToolSpec("connect_live_bridge", True, "Alias for attach_qrenderdoc with explicit bridge diagnostics."),
    ToolSpec("get_capture_status", True, "Return current capture status from the live bridge."),
    ToolSpec("open_capture", True, "Load a capture by path into the live qrenderdoc session."),
    ToolSpec("close_capture", True, "Close the active capture in one qrenderdoc bridge window."),
    ToolSpec("find_latest_capture", True, "Find the newest .rdc capture under a directory."),
    ToolSpec("load_latest_capture", True, "Load the newest .rdc capture into the live qrenderdoc session."),
    ToolSpec("wait_for_new_capture", True, "Wait for a newer .rdc capture and load it into qrenderdoc."),
    ToolSpec(
        "get_capture_context",
        True,
        "Return UE-side context metadata attached to the active live capture.",
    ),
    ToolSpec(
        "get_capture_hints",
        True,
        "Return compact UE semantic hints derived from the active live capture context metadata.",
    ),
    ToolSpec(
        "compare_capture_contexts",
        True,
        "Compare UE-side context metadata between two captures.",
    ),
    ToolSpec("find_events", True, "Find compact event matches in the live capture."),
    ToolSpec("search_draw_events_by_ue_hint", True, "Search live draw events using UE actor, asset, material, or component hints."),
    ToolSpec("list_passes", True, "List pass markers in the live capture."),
    ToolSpec(
        "inspect_pipeline_state",
        True,
        "Return a compact pipeline snapshot for one event from the live capture.",
    ),
    ToolSpec(
        "inspect_shader",
        True,
        "Return a compact shader summary for one stage at one event from the live capture.",
    ),
    ToolSpec(
        "get_target_shader_encodings",
        True,
        "Return shader source encodings accepted for live replacement in the active capture API.",
    ),
    ToolSpec(
        "apply_shader_edit",
        True,
        "Compile source and apply a global Shader replacement located through one event/stage. Event overrides use apply_event_shader_edit.",
    ),
    ToolSpec(
        "revert_shader_edit",
        True,
        "Remove a shader replacement previously applied through apply_shader_edit.",
    ),
    ToolSpec(
        "export_shader_raw_bytes",
        True,
        "Export the raw shader bytecode bound at one event/stage to a local file.",
    ),
    ToolSpec(
        "save_event_output_texture",
        True,
        "Save one live event output render target or depth target to an export file for before/after validation.",
    ),
    ToolSpec(
        "inspect_cbuffer_values",
        True,
        "Return cbuffer binding ranges and actual variable values for one stage/event.",
    ),
    ToolSpec(
        "read_buffer",
        True,
        "Read a live buffer range and decode it as raw, float4, uint4, int4, matrix, or structured rows.",
    ),
    ToolSpec(
        "inspect_texture_usage",
        True,
        "Return a compact texture usage summary from the live capture.",
    ),
    ToolSpec(
        "get_shader_disasm",
        True,
        "Return shader disassembly text from the live capture with pagination support.",
    ),
    ToolSpec(
        "get_shader_source",
        True,
        "Return shader source text from the live capture when debug/source information is available.",
    ),
    ToolSpec(
        "get_shader_code",
        True,
        "Return shader source text when available, otherwise return disassembly from the live capture.",
    ),
    ToolSpec(
        "inspect_mesh",
        True,
        "Return a compact mesh summary for one event from the live capture.",
    ),
    ToolSpec(
        "export_mesh",
        True,
        "Export one live draw action's VS-input mesh to an OBJ file.",
    ),
    ToolSpec("export_postvs", True, "Export raw per-instance VS output buffers and exact mesh layouts into a fresh directory."),
    ToolSpec(
        "get_frame_packet",
        True,
        "Return a compact frame-level packet for the live capture.",
    ),
    ToolSpec(
        "get_pass_packet",
        True,
        "Return a compact pass-level packet for the live capture.",
    ),
    ToolSpec(
        "get_draw_packet",
        True,
        "Return a compact draw-level packet for the live capture.",
    ),
    ToolSpec(
        "debug_save_overlay",
        True,
        "Save a debug overlay texture such as Highlight Drawcall for one live event.",
    ),
    ToolSpec(
        "debug_save_texture",
        True,
        "Save one live texture resource to an export file. Use type_cast (e.g. UNorm, Float, Depth) to preserve the observed view interpretation of typeless textures; omitted keeps the legacy Typeless behavior.",
    ),
    ToolSpec(
        "export_buffer",
        True,
        "Export an exact live buffer range to a local binary file with SHA256. Length0 means the remaining resource; no bytes are truncated or embedded in the response.",
    ),
)
