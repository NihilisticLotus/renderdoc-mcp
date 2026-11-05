# AGENTS.md

## 默认工作方式

- 回答尽量简洁，先给结论，再补充必要说明。
- 不要主动扩展任务范围，除非用户明确要求。
- 除非确有必要，不要额外做检查、修改或延伸操作。
- 优先直接回答问题，再提供可选建议。
- 默认尽量使用中文回答。

## RenderDoc runtime / MCP compatibility gate

For every change touching RenderDoc runtime identity, exported/imported names,
runtime files, GUI discovery, Python/SWIG bindings, extension loading, paths,
logs, IPC, or tool inputs/results, compatibility analysis and any required MCP
adaptation are part of the same change. Do not merge or report the runtime change
as MCP-compatible based only on a successful RenderDoc build.

Required workflow:

1. Read the complete runtime diff and its retained-identity/diagnostic notes.
   Build a producer/consumer matrix for the GUI, CLI, DLL, Python module and
   compatibility aliases, extension/config directories, temp/log paths, MCP
   discovery, bridge protocol, and packaged launchers.
2. Preserve the old runtime layout where the API/file contract is intentionally
   retained. If a runtime is renamed, add explicit family-aware path discovery
   and a deliberate old-name fallback. An explicitly requested new runtime
   that is incomplete must fail; it must never silently validate against an old
   installation.
3. For Python/SWIG aliases, verify that old and new import names resolve to the
   same module object/type registry. Do not load two DLLs or bindings under
   different module names and treat them as compatible.
4. Keep MCP tool names and input schemas stable unless the runtime change
   requires an intentional contract change. Compare the actual `tools/list`
   result before and after; document every changed tool and its compatibility
   behavior.
5. Run automated path/alias/schema checks, then use a fresh MCP stdio session
   against the new runtime. Record the new GUI executable path, loaded replay
   DLL path and SHA256, MCP tool count/schema, bridge window identity, capture
   operations, and errors. An old GUI, old installed DLL, or stale bridge does
   not count as new-runtime validation.
6. Preserve active user windows and captures. Use a side-by-side GUI/config
   directory for validation when possible; never close unrelated windows.
7. List untested APIs/platforms and any remaining limits. Never claim full
   compatibility from static search alone.

Run the focused regression suite with:

```powershell
# Run from the MCP repository root.
.\venv\Scripts\python.exe -m unittest discover -s tests -t . -v
```

Run the live MCP input-schema contract check with:

```powershell
.\venv\Scripts\python.exe scripts\verify_mcp_tool_schema.py
```

For an intentional tool or input-schema change, review the full baseline diff,
document compatibility behavior, then refresh it explicitly with
`scripts\verify_mcp_tool_schema.py --update`.

The current RenderTest name-migration checklist and verified compatibility
matrix are in `docs/renderdoc-compatibility.md`.

## Skills

- 仓库内技能以 `.claude/skills/` 为准。
- RenderDoc 分析技能位于 `.claude/skills/renderdoc-analysis/SKILL.md`。
- 不再使用根目录 `skills/` 下的技能副本。
