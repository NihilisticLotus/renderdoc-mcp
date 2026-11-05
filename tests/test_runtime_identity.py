import importlib.util
from pathlib import Path
import sys
import types
import unittest
from unittest.mock import patch


_path = Path(__file__).resolve().parents[1] / "bridge_extension/renderdoc_mcp_bridge/runtime_identity.py"
_spec = importlib.util.spec_from_file_location("runtime_identity_tests", _path)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)


class RuntimeIdentityTests(unittest.TestCase):
    def test_new_module_alias_is_the_same_swig_instance(self):
        replay = types.ModuleType("rendertest")
        modules = {"rendertest": replay}
        with patch.dict(sys.modules, modules, clear=False):
            sys.modules.pop("renderdoc", None)
            self.assertIs(_module.install_legacy_replay_alias(replay), replay)
            self.assertIs(sys.modules["renderdoc"], replay)
            with patch.object(_module, "_frontend_executable", return_value=r"E:\\qrendertest.exe"):
                info = _module.describe_runtime("1.48")

        self.assertEqual(info["runtime_family"], "rendertest")
        self.assertEqual(info["frontend_name"], "qrendertest.exe")
        self.assertTrue(info["module_alias_consistent"])
        self.assertEqual(_module.runtime_display_name(info["runtime_family"]), "RenderTest")

    def test_conflicting_old_and_new_module_instances_are_rejected(self):
        replay = types.ModuleType("rendertest")
        old = types.ModuleType("renderdoc")
        with patch.dict(sys.modules, {"rendertest": replay, "renderdoc": old}, clear=False):
            with self.assertRaisesRegex(RuntimeError, "different module instances"):
                _module.install_legacy_replay_alias(replay)

    def test_legacy_module_is_reported_without_changing_its_name(self):
        old = types.ModuleType("renderdoc")
        with patch.dict(sys.modules, {"renderdoc": old}, clear=False):
            sys.modules.pop("rendertest", None)
            with patch.object(_module, "_frontend_executable", return_value=r"C:\\qrenderdoc.exe"):
                info = _module.describe_runtime("1.43")

        self.assertEqual(info["runtime_family"], "renderdoc")
        self.assertEqual(info["replay_module"], "renderdoc")
        self.assertTrue(info["module_alias_consistent"])
        self.assertEqual(_module.runtime_display_name(info["runtime_family"]), "RenderDoc")


if __name__ == "__main__":
    unittest.main()
