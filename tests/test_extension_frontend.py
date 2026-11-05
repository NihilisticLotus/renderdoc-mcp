import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


ROOT = Path(__file__).resolve().parents[1]


class ExtensionFrontendTests(unittest.TestCase):
    def test_rendertest_frontend_uses_its_own_appdata_namespace(self):
        with tempfile.TemporaryDirectory() as appdata:
            env = os.environ.copy()
            env["APPDATA"] = appdata
            subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts" / "install_ext.py"),
                    "--frontend",
                    "rendertest",
                    "--incremental",
                    "--skip-decompiler",
                ],
                cwd=str(ROOT),
                env=env,
                check=True,
                capture_output=True,
                text=True,
            )

            app_dir = Path(appdata) / "qrendertest"
            extension = app_dir / "extensions" / "renderdoc_mcp_bridge"
            config = json.loads((app_dir / "UI.config").read_text(encoding="utf-8"))

            self.assertTrue((extension / "__init__.py").is_file())
            self.assertIn("renderdoc_mcp_bridge", config["AlwaysLoad_Extensions"])
            self.assertFalse((Path(appdata) / "qrenderdoc").exists())


if __name__ == "__main__":
    unittest.main()
