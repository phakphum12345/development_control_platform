import tempfile, unittest, zipfile
from pathlib import Path
from unittest.mock import patch
from tools import local_runner_manager as manager

class LocalRunnerManagerTests(unittest.TestCase):
    def test_repository_requires_exact_owner_and_name(self):
        self.assertEqual(manager.validate_repository("owner/project"), ("owner", "project"))
        for value in ("owner", "owner/project/extra", "../project", "owner/../project", "owner/name with spaces"):
            with self.subTest(value=value), self.assertRaises(manager.RunnerError):
                manager.validate_repository(value)
    def test_runner_archive_rejects_path_traversal(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"runner.zip"; target=root/"instance"; target.mkdir()
            with zipfile.ZipFile(archive,"w") as bundle: bundle.writestr("../escape.txt","no")
            with self.assertRaises(manager.RunnerError): manager.safe_extract(archive,target)
            self.assertFalse((root/"escape.txt").exists())
    def test_public_repository_is_blocked(self):
        with patch.object(manager.platform,"system",return_value="Windows"), patch.object(manager.shutil,"which",return_value="gh"), patch.object(manager,"run_command",return_value="authenticated"), patch.object(manager,"gh_json",return_value={"full_name":"owner/project","private":False}):
            with self.assertRaisesRegex(manager.RunnerError,"public"): manager.check_prerequisites("owner/project")
    def test_missing_admin_permission_is_blocked(self):
        with patch.object(manager.platform,"system",return_value="Windows"), patch.object(manager.shutil,"which",return_value="gh"), patch.object(manager,"run_command",return_value="authenticated"), patch.object(manager,"gh_json",return_value={"full_name":"owner/project","private":True,"permissions":{"admin":False}}):
            with self.assertRaisesRegex(manager.RunnerError,"admin"): manager.check_prerequisites("owner/project")
    def test_archive_extraction_accepts_normal_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); archive=root/"runner.zip"; target=root/"instance"; target.mkdir()
            with zipfile.ZipFile(archive,"w") as bundle: bundle.writestr("config.cmd","echo safe")
            manager.safe_extract(archive,target)
            self.assertTrue((target/"config.cmd").is_file())
    def test_runner_status_matches_exact_runner_name(self):
        with patch.object(manager,"gh_json",return_value={"runners":[{"name":"old","status":"online","busy":True},{"name":"new","status":"offline","busy":False}]}):
            self.assertEqual(manager.runner_status("owner/project","new"),("offline",False))
            self.assertIsNone(manager.runner_status("owner/project","missing"))

if __name__ == "__main__": unittest.main()
