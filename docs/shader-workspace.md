# Shader workspace (B3.1)

`shader_workspace` routes to the native CaptureContext on the UI thread. It adds no Python workspace,
replacement map or undo history. A frontend without `ShaderWorkspaceCommand` returns an explicit error.
Select an event using the existing event tools first. Do not use global `apply_shader_edit` for this workflow.

| operation | Required inputs / meaning |
| --- | --- |
| state | Documents, source/last successful snapshots, capture session and current edit revision; works after capture close |
| create | session_id, stage (vs/hs/ds/gs/ps/cs); binds selected event and captured Shader content |
| update | id, document revision, complete files map; optional main_file/entry. Invalidates candidate, never edits replay |
| compile | id, revision, session_id; immutable include snapshot through native compiler and ABI checks; no apply |
| apply | id, revision, session_id, edit_revision; uses B1 transaction. independent_float and output_target are explicit |
| save_draft | id, revision, path; atomic portable draft JSON. Not the later B3 project-restore format |
| attach_file | id, revision, name, path; UTF-8 file snapshot + hash. External changes are rejected at compile/apply |
| decompile | id, revision, session_id, tool index; configured matching encoder-to-HLSL tool only. Output is an unvalidated candidate |

`show=true` opens the same dock used by native GUI. Resource names, compiler diagnostics, source and
machine keys remain unchanged by UI language. Existing `set_event_editing_enabled` remains opt-in.
Use `undo_event_edit` with the latest session/revision to undo either GUI or MCP applies.

Never reuse a document's old capture session after reopening an RDC. Drafts survive capture changes,
but runtime bindings and candidates are invalidated. The next B3 phase will provide reviewed project
matching and explicit batch application; current drafts do not silently replay saved edits.

Source limits: 4 MiB per file, 16 MiB per unit, 64 files, nesting depth 16. Includes use exact relative
paths; missing/dynamic includes fail explicitly. Leading pragma-once and conventional ifndef/define
guards are preserved, including inactive conditional occurrences. Every referenced include must exist
in the snapshot, including inactive branches. Last-successful source snapshots are separate from the
current candidate and from active GPU edits. Native compilation failure leaves active edits intact.

Validation: 118 local MCP tests; reviewed tools/list grows 72 to 73 with no old schema changes;
actual fresh bridge sessions against new x64/x86 GUI and D3D11/D3D12 RDCs. Full evidence and limits:
main repository `docs/diagnostics/fork-sync-b3-stage1-20261116.md/json`. No deployment this phase.

Compiler flags are returned as an ordered array of name/value entries so repeated names are not lost.
The workspace accepts only options that the current native compiler preserves, and requires a captured
profile. Unsupported extra options fail explicitly; the compiled profile and encoding must match the
capture. Generated reflection metadata is not misclassified as user-supplied compiler options.


## B3.2 参数与别名

`shader_parameters` 的 `list/read/alias/write` 全部进入原生工作区同一队列。
别名身份由 Shader 字节内容、阶段、bind/space、完整物理布局构成；只改变显示。
`list` 返回 blocks、fields、identity、人工 reuse_candidates 和 alias_revision。
`alias` 需要 alias_revision；清空字符串删除别名。布局相同但内容不同不自动复用。
`read/write` 显式选择 `scope=event|shared`，传捕获 session_id、文档 revision 和
edit_revision。`value` 是字符串，64位整数不经过 JSON double；拒绝溢出/不可靠布局。
事件写与持续共享写分别走 B1/B2，继续使用现有 GUI/MCP 撤销。
前端不支持时明确报错。普通开关仍默认关闭；list/read 不自动启用编辑。
原子草稿含完整别名字典，完整项目读取和组合应用仍属 B3.3。
本批本地74工具，旧73 schema保持不变；实际122个MCP测试通过。
