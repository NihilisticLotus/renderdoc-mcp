"""RenderDoc MCP bridge extension."""

# RenderTest and RenderDuck expose renamed replay modules while retaining the
# same API. Domain modules keep importing the legacy name, but it must refer to
# the very same SWIG module instance and type registry.
import importlib
import sys

from .runtime_identity import describe_runtime, install_legacy_replay_alias, runtime_display_name

try:
    renderdoc = importlib.import_module("rendertest")
    install_legacy_replay_alias(renderdoc)
except ImportError:
    try:
        renderdoc = importlib.import_module("renderdoc")
    except ImportError:
        renderdoc = importlib.import_module("riderduck")
        install_legacy_replay_alias(renderdoc)

try:
    import qrenderdoc
except ImportError:
    try:
        import qriderduck as qrenderdoc
        sys.modules["qrenderdoc"] = qrenderdoc
    except ImportError:
        pass  # Domain unit tests and replay-only Python do not provide a UI module.

from .request_handler import RequestHandler
from .server import BridgeServer

try:
    from .ruri_shader_processors import install_ruri_shader_processors
    _ruri_import_error = None
except Exception as exc:
    install_ruri_shader_processors = None
    _ruri_import_error = exc

_ctx = None
_server = None


def register(version, ctx):
    """Register the bridge with RenderDoc, RenderTest, or RenderDuck."""
    global _ctx, _server
    _ctx = ctx
    if install_ruri_shader_processors is not None:
        try:
            install_ruri_shader_processors(ctx)
        except Exception as exc:
            print("[renderdoc_mcp_bridge] failed to register Ruri shader processors: {}".format(exc))
    elif _ruri_import_error is not None:
        print("[renderdoc_mcp_bridge] failed to import Ruri shader processor installer: {}".format(_ruri_import_error))
    handler = RequestHandler(ctx, runtime_version=version)
    _server = BridgeServer(handler)
    _server.start()
    runtime_name = runtime_display_name(describe_runtime(version)["runtime_family"])
    print("[renderdoc_mcp_bridge] loaded for {} {}".format(runtime_name, version))


def unregister():
    """RenderDoc extension unload hook."""
    global _server
    if _server is not None:
        _server.stop()
        _server = None
    print("[renderdoc_mcp_bridge] unloaded")
