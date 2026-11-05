import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from renderdoc_mcp.integration.installation import discover_installation


class InstallationDiscoveryTests(unittest.TestCase):
    @staticmethod
    def _touch(root, *names):
        for name in names:
            (Path(root) / name).touch()

    def test_legacy_renderdoc_names_remain_supported(self):
        with tempfile.TemporaryDirectory() as root:
            self._touch(root, "renderdoccmd.exe", "qrenderdoc.exe", "renderdoc.dll")
            with patch.dict(os.environ, {"RENDERDOC_PATH": root}, clear=False):
                os.environ.pop("RENDERTEST_PATH", None)
                installation = discover_installation()

        self.assertEqual(installation.runtime_family, "renderdoc")
        self.assertEqual(installation.command.name, "renderdoccmd.exe")
        self.assertEqual(installation.gui.name, "qrenderdoc.exe")
        self.assertEqual(installation.runtime_dll.name, "renderdoc.dll")

    def test_explicit_rendertest_root_wins_and_selects_renamed_outputs(self):
        with tempfile.TemporaryDirectory() as legacy, tempfile.TemporaryDirectory() as test_root:
            self._touch(legacy, "renderdoccmd.exe", "qrenderdoc.exe", "renderdoc.dll")
            self._touch(test_root, "rendertestcmd.exe", "qrendertest.exe", "rendertest.dll")
            with patch.dict(
                os.environ,
                {"RENDERDOC_PATH": legacy, "RENDERTEST_PATH": test_root},
                clear=False,
            ):
                installation = discover_installation()

        self.assertEqual(installation.runtime_family, "rendertest")
        self.assertEqual(installation.root, Path(test_root))
        self.assertEqual(installation.command.name, "rendertestcmd.exe")
        self.assertEqual(installation.gui.name, "qrendertest.exe")
        self.assertEqual(installation.runtime_dll.name, "rendertest.dll")

    def test_broken_explicit_rendertest_root_does_not_fall_back_to_old_install(self):
        with tempfile.TemporaryDirectory() as legacy, tempfile.TemporaryDirectory() as test_root:
            self._touch(legacy, "renderdoccmd.exe")
            with patch.dict(
                os.environ,
                {"RENDERDOC_PATH": legacy, "RENDERTEST_PATH": test_root},
                clear=False,
            ):
                with self.assertRaisesRegex(FileNotFoundError, "rendertestcmd.exe"):
                    discover_installation()

    def test_single_new_name_install_can_use_legacy_path_variable(self):
        with tempfile.TemporaryDirectory() as root:
            self._touch(root, "rendertestcmd.exe", "qrendertest.exe", "rendertest.dll")
            with patch.dict(os.environ, {"RENDERDOC_PATH": root}, clear=False):
                os.environ.pop("RENDERTEST_PATH", None)
                installation = discover_installation()

        self.assertEqual(installation.runtime_family, "rendertest")
        self.assertEqual(installation.command.name, "rendertestcmd.exe")


if __name__ == "__main__":
    unittest.main()
