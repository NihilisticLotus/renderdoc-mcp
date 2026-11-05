"""Runtime family and Python module identity checks for embedded frontends."""

import os
import sys


def runtime_display_name(family):
    return {
        "renderdoc": "RenderDoc",
        "rendertest": "RenderTest",
        "renderduck": "RenderDuck",
    }.get(family, "unknown runtime")


def install_legacy_replay_alias(replay_module):
    """Expose the legacy import name without creating a second SWIG module."""
    current = sys.modules.get("renderdoc")
    if current is not None and current is not replay_module:
        raise RuntimeError(
            "RenderDoc replay module aliases refer to different module instances; "
            "refusing to mix SWIG type registries"
        )
    sys.modules["renderdoc"] = replay_module
    return replay_module


def _frontend_executable():
    if os.name == "nt":
        try:
            import ctypes

            buffer = ctypes.create_unicode_buffer(32768)
            length = ctypes.windll.kernel32.GetModuleFileNameW(None, buffer, len(buffer))
            if length:
                return os.path.abspath(buffer.value)
        except Exception:
            pass
    return os.path.abspath(sys.executable)


def describe_runtime(version=None):
    """Return bridge metadata that lets the MCP reject stale frontend windows."""
    rendertest = sys.modules.get("rendertest")
    renderdoc = sys.modules.get("renderdoc")
    riderduck = sys.modules.get("riderduck")

    if rendertest is not None:
        family = "rendertest"
        replay_module = rendertest
        replay_module_name = "rendertest"
        alias_consistent = renderdoc is None or renderdoc is rendertest
    elif riderduck is not None and renderdoc is riderduck:
        family = "renderduck"
        replay_module = riderduck
        replay_module_name = "riderduck"
        alias_consistent = True
    elif renderdoc is not None:
        family = "renderdoc"
        replay_module = renderdoc
        replay_module_name = "renderdoc"
        alias_consistent = True
    else:
        family = "unknown"
        replay_module = None
        replay_module_name = None
        alias_consistent = False

    executable = _frontend_executable()
    return {
        "runtime_family": family,
        "runtime_version": str(version) if version is not None else None,
        "frontend_executable": executable,
        "frontend_name": os.path.basename(executable),
        "python_version": sys.version.split()[0],
        "replay_module": replay_module_name,
        "replay_module_file": getattr(replay_module, "__file__", None),
        "module_alias_consistent": alias_consistent,
    }
