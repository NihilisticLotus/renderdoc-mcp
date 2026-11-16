import importlib.util
import json
from pathlib import Path
import tempfile
import threading
import time
import types
import unittest
from unittest.mock import patch

_path = Path(__file__).resolve().parents[1] / "bridge_extension/renderdoc_mcp_bridge/server.py"
_spec = importlib.util.spec_from_file_location("bridge_server_liveness_tests", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class BridgeLivenessTests(unittest.TestCase):
    def test_heartbeat_does_not_wait_for_frontend_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            entered, release = threading.Event(), threading.Event()
            def describe():
                entered.set()
                release.wait(5.0)
                return {}
            with patch.object(_module, "IPC_DIR", directory), \
                 patch.object(_module, "INSTANCES_DIR", str(Path(directory) / "instances")), \
                 patch.object(_module, "QTimer", None):
                server = _module.BridgeServer(types.SimpleNamespace(describe_instance=describe), bridge_id="busy")
                server.start()
                try:
                    self.assertTrue(entered.wait(2.0))
                    with server._heartbeat_lock:
                        Path(server.heartbeat_file).write_text("0.0", encoding="utf-8")
                    deadline = time.monotonic() + 2.0
                    stamp = 0.0
                    while stamp == 0.0 and time.monotonic() < deadline:
                        time.sleep(0.05)
                        stamp = float(Path(server.heartbeat_file).read_text())
                    self.assertGreater(stamp, time.time() - 2.0)
                    self.assertFalse(release.is_set())
                finally:
                    release.set()
                    server.stop()
                self.assertFalse(Path(server.instance_dir).exists())

    def test_host_control_is_responsive_while_normal_handler_is_blocked(self):
        with tempfile.TemporaryDirectory() as directory:
            entered, release = threading.Event(), threading.Event()
            calls = []
            def handle(request):
                calls.append(request['id'])
                if request['method'] != 'host_tasks':
                    entered.set()
                    release.wait(3)
                return {'id': request['id'], 'result': {'ok': True}}
            handler = types.SimpleNamespace(handle=handle)
            with patch.object(_module, 'IPC_DIR', directory), \
                 patch.object(_module, 'INSTANCES_DIR', str(Path(directory) / 'instances')), \
                 patch.object(_module, 'QTimer', None):
                server = _module.BridgeServer(handler, bridge_id='control')
                server.start()
                try:
                    for identity, method in [('slow', 'native_edit'), ('query', 'host_tasks')]:
                        server._write_json_atomic(str(Path(server.requests_dir) / (identity + '.json')),
                                                  {'id': identity, 'method': method})
                        if identity == 'slow':
                            self.assertTrue(entered.wait(1))
                    end = time.monotonic() + 1
                    path = Path(server.responses_dir) / 'query.json'
                    while not path.exists() and time.monotonic() < end:
                        time.sleep(.01)
                    self.assertTrue(path.exists())
                    self.assertFalse((Path(server.responses_dir) / 'slow.json').exists())
                    self.assertEqual(calls.count('query'), 1)
                    self.assertFalse(release.is_set())
                finally:
                    release.set()
                    server.stop()

    def test_long_request_refreshes_heartbeat_before_response(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(_module, "IPC_DIR", directory), patch.object(_module, "INSTANCES_DIR", str(Path(directory) / "instances")):
                handler = types.SimpleNamespace()
                server = _module.BridgeServer(handler, bridge_id="test")
                server._running = True
                def handle(request):
                    # Reproduces a handler that consumed more than the 2-second
                    # client freshness interval, without sleeping in the test.
                    Path(server.heartbeat_file).write_text("0.0", encoding="utf-8")
                    return {"id": request["id"], "result": {"ok": True}}
                handler.handle = handle
                request = Path(server.requests_dir) / "request.json"
                request.write_text(json.dumps({"id": "request", "method": "long_export"}), encoding="utf-8")
                server._poll()
                response = Path(server.responses_dir) / "request.json"
                self.assertTrue(response.exists())
                self.assertGreater(float(Path(server.heartbeat_file).read_text()), time.time() - 2.0)


if __name__ == "__main__":
    unittest.main()
