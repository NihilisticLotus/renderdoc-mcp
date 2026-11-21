import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from renderdoc_mcp.server.shader_conversion import register_shader_tools
from tests.test_shader_debug_export import module as exporter


def page_tool():
    class App:
        def tool(self):
            def register(function):
                setattr(self, function.__name__, function)
                return function
            return register
    app = App()
    register_shader_tools(app, None)
    return app.read_shader_debug_trace


class TracePagingTests(unittest.TestCase):
    def test_pages_equal_old_reader_including_partial_and_filtered(self):
        read = page_tool()
        change = {"before": {"name": "变数", "raw_hex": "0100c07f"}, "after": {"name": "r0"}}
        trace = dict(stage="PS", complete=False, errors=["step limit"], disassembly="x\ny",
                     states=[dict(step=i, changes=[change] if i % 2 else []) for i in range(219)])
        with tempfile.TemporaryDirectory() as tmp:
            old, new = Path(tmp)/"old", Path(tmp)/"new"
            old.write_text(json.dumps(trace), encoding="utf8")
            exporter.publish_trace(str(new), trace, False)
            for variable in (None, "变数", "r0", "absent"):
                for offset in (0, 61, 200, 218, 219, 220):
                    expected = read(str(old), offset, 50, variable)
                    with patch("renderdoc_mcp.server.trace_page.json.load", side_effect=AssertionError("full read")):
                        self.assertEqual(read(str(new), offset, 50, variable), expected)
            # Deliberately damage only the index, leaving the states intact.
            raw = new.read_bytes()
            at = raw.index(b'],"_rd_seek":"') + len(b'],"_rd_seek":"')
            new.write_bytes(raw[:at] + b'f'*16 + raw[at+16:])
            self.assertEqual(read(str(new), 0, 3), read(str(old), 0, 3))

    def test_interrupted_publication_and_new_generation(self):
        read = page_tool()
        with tempfile.TemporaryDirectory() as tmp:
            path = str(Path(tmp)/"trace.json")
            first = dict(stage="VS", complete=True, errors=[], states=[{"step": 3}])
            exporter.publish_trace(path, first, False)
            with self.assertRaises(ValueError):
                exporter.publish_trace(path, dict(first, states=[{}, {"value": float("nan")}]), True)
            self.assertEqual(read(path)["states"], [{"step": 3}])
            with self.assertRaises(FileExistsError):
                exporter.publish_trace(path, first, False)
            exporter.publish_trace(path, dict(first, stage="CS", states=[]), True)
            result = read(path)
            self.assertEqual((result["stage"], result["states"], result["total_steps"]), ("CS", [], 0))
            self.assertEqual(list(Path(tmp).iterdir()), [Path(path)])
