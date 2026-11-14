import os
import shutil
import subprocess
import tempfile
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.local_runner_agent.linux_sandbox import (
    LinuxBubblewrapLauncher,
    LinuxSandboxError,
    _seccomp_program,
)


@unittest.skipUnless(sys.platform.startswith('linux'), 'Linux-only')
class LinuxBubblewrapLauncherTests(unittest.TestCase):
    def test_seccomp_program_is_aligned_and_rejects_unknown_architecture(self):
        program = _seccomp_program("x86_64")
        self.assertGreater(len(program), 8)
        self.assertEqual(len(program) % 8, 0)
        with self.assertRaisesRegex(LinuxSandboxError, "unsupported CPU architecture"):
            _seccomp_program("unknown-cpu")

    def test_builder_creates_network_and_filesystem_isolation_arguments(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            scratch = Path(root) / "scratch"
            workspace.mkdir()
            scratch.mkdir()
            fake_bwrap = Path(root) / "bwrap"
            fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_bwrap.chmod(0o700)
            with patch("tools.local_runner_agent.linux_sandbox.sys_platform_linux", return_value=True):
                launcher = LinuxBubblewrapLauncher(
                    executable_lookup=lambda _name, path=None: str(fake_bwrap),
                    runtime_bin_dir=root,
                )
            result = launcher.build(
                executable="/usr/bin/python3",
                argv=["--version"],
                workspace=workspace,
                scratch=scratch,
            )
            try:
                args = list(result.argv)
                self.assertIn("--unshare-net", args)
                self.assertIn("--unshare-pid", args)
                self.assertIn("--unshare-ipc", args)
                self.assertIn("--unshare-uts", args)
                self.assertIn("--ro-bind", args)
                self.assertIn("--bind", args)
                self.assertIn("--seccomp", args)
                self.assertIn("--disable-userns", args)
                self.assertIn("--cap-drop", args)
                self.assertEqual(Path(args[-2]).resolve(), Path("/usr/bin/python3").resolve())
                self.assertEqual(args[-1], "--version")
                self.assertTrue(os.fstat(result.seccomp_fd))
            finally:
                result.close()

    def test_builder_rejects_scratch_nested_under_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            scratch = workspace / "scratch"
            scratch.mkdir(parents=True)
            fake_bwrap = Path(root) / "bwrap"
            fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_bwrap.chmod(0o700)
            with patch("tools.local_runner_agent.linux_sandbox.sys_platform_linux", return_value=True):
                launcher = LinuxBubblewrapLauncher(
                    executable_lookup=lambda _name, path=None: str(fake_bwrap),
                    runtime_bin_dir=root,
                )
            with self.assertRaisesRegex(LinuxSandboxError, "separate directory trees"):
                launcher.build(
                    executable="/usr/bin/python3",
                    argv=["--version"],
                    workspace=workspace,
                    scratch=scratch,
                )

    def test_builder_rejects_relative_executable_and_symlink_workspace(self):
        with tempfile.TemporaryDirectory() as root:
            workspace = Path(root) / "workspace"
            scratch = Path(root) / "scratch"
            workspace.mkdir()
            scratch.mkdir()
            fake_bwrap = Path(root) / "bwrap"
            fake_bwrap.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
            fake_bwrap.chmod(0o700)
            with patch("tools.local_runner_agent.linux_sandbox.sys_platform_linux", return_value=True):
                launcher = LinuxBubblewrapLauncher(
                    executable_lookup=lambda _name, path=None: str(fake_bwrap),
                    runtime_bin_dir=root,
                )
            with self.assertRaisesRegex(LinuxSandboxError, "absolute trusted path"):
                launcher.build(executable="python3", argv=[], workspace=workspace, scratch=scratch)
            link = Path(root) / "workspace-link"
            link.symlink_to(workspace, target_is_directory=True)
            with self.assertRaisesRegex(LinuxSandboxError, "symlink"):
                launcher.build(executable="/usr/bin/python3", argv=[], workspace=link, scratch=scratch)


    @unittest.skipUnless(sys.platform.startswith("linux") and shutil.which("bwrap"), "bubblewrap runtime unavailable")
    def test_actual_bubblewrap_enforces_filesystem_network_and_scratch_boundaries(self):
        with tempfile.TemporaryDirectory() as root:
            root_path = Path(root)
            workspace = root_path / "workspace"
            scratch = root_path / "scratch"
            workspace.mkdir()
            scratch.mkdir()
            (workspace / "visible.txt").write_text("workspace-ok", encoding="utf-8")
            secret = root_path / "host-secret.txt"
            secret.write_text("host-secret", encoding="utf-8")
            script = (
                "import pathlib,socket,sys; "
                "w=pathlib.Path('/workspace'); "
                "assert (w/'visible.txt').read_text() == 'workspace-ok'; "
                "p=pathlib.Path(sys.argv[1]); "
                "exec(\"try: p.read_text(); raise AssertionError('host file visible')\\nexcept FileNotFoundError: pass\"); "
                "exec(\"try: (w/'forbidden.txt').write_text('bad'); raise AssertionError('workspace writable')\\nexcept OSError: pass\"); "
                "exec(\"try: socket.socket(); raise AssertionError('socket allowed')\\nexcept PermissionError: pass\"); "
                "pathlib.Path('/tmp/scratch-proof.txt').write_text('scratch-ok')"
            )
            launcher = LinuxBubblewrapLauncher()
            sandbox = launcher.build(
                executable="/usr/bin/python3",
                argv=["-c", script, str(secret)],
                workspace=workspace,
                scratch=scratch,
            )
            try:
                result = subprocess.run(
                    sandbox.argv,
                    stdin=subprocess.DEVNULL,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=15,
                    check=False,
                    pass_fds=(sandbox.seccomp_fd,),
                )
            finally:
                sandbox.close()
            self.assertEqual(result.returncode, 0, msg=result.stderr or result.stdout)
            self.assertFalse((workspace / "forbidden.txt").exists())
            self.assertEqual((scratch / "scratch-proof.txt").read_text(encoding="utf-8"), "scratch-ok")


if __name__ == "__main__":
    unittest.main()
