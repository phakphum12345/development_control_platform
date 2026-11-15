import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INSTALLER = ROOT / "packaging" / "windows" / "DCP.iss"


class ReleasePackagingTests(unittest.TestCase):
    def test_installer_source_paths_exist(self):
        source_paths = re.findall(r'^Source:\s*"([^"]+)"', INSTALLER.read_text(encoding="utf-8"), re.MULTILINE)
        self.assertTrue(source_paths)
        for source in source_paths:
            relative = source.replace("\\", "/")
            if relative.endswith("/*"):
                relative = relative[:-2]
            with self.subTest(source=source):
                self.assertTrue((INSTALLER.parent / relative).resolve().exists())

    def test_release_builder_verifies_all_three_package_outputs(self):
        builder = (ROOT / "packaging" / "package-release.ps1").read_text(encoding="utf-8")
        workflow = (ROOT / ".github" / "workflows" / "package-release.yml").read_text(encoding="utf-8")
        self.assertIn("pull_request:", workflow)
        for output in ("DCP-PWA-$Version.zip", "DCP-Portable-Windows-$Version.zip", "Development-Control-Platform-Setup-$Version.exe"):
            with self.subTest(output=output):
                self.assertIn(output, builder)
        for artifact in ("dist/DCP-PWA-*.zip", "dist/DCP-Portable-Windows-*.zip", "dist/Development-Control-Platform-Setup-*.exe"):
            with self.subTest(artifact=artifact):
                self.assertIn(artifact, workflow)


if __name__ == "__main__":
    unittest.main(verbosity=2)
