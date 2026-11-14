import os
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
                launcher = LinuxBubblewrapLauncher(executable_lookup=lambda _name: str(fake_bwrap))
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
                self.assertEqual(args[-2:], ["/usr/bin/python3", "--version"])
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
                launcher = LinuxBubblewrapLauncher(executable_lookup=lambda _name: str(fake_bwrap))
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
                launcher = LinuxBubblewrapLauncher(executable_lookup=lambda _name: str(fake_bwrap))
            with self.assertRaisesRegex(LinuxSandboxError, "absolute trusted path"):
                launcher.build(executable="python3", argv=[], workspace=workspace, scratch=scratch)
            link = Path(root) / "workspace-link"
            link.symlink_to(workspace, target_is_directory=True)
            with self.assertRaisesRegex(LinuxSandboxError, "real directory"):
                launcher.build(executable="/usr/bin/python3", argv=[], workspace=link, scratch=scratch)


if __name__ == "__main__":
    unittest.main()
