"""Tests for the fixed-template Terminal executor; no project scripts are executed."""
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest
import uuid
from pathlib import Path
from unittest.mock import patch

from tools.cloud_gateway.terminal_catalog import preview_template
from tools.cloud_gateway.terminal_execution_contract import template_version_digest
from tools.local_runner_agent.terminal_isolation import IsolationAssessment
from tools.local_runner_agent.terminal_executor import (
    TerminalExecutionError,
    TerminalScriptExecutor,
    TerminalOutputRedactor,
    redact_terminal_output,
)
from tools.local_runner_agent.linux_sandbox import LinuxBubblewrapLauncher, LinuxSandboxError


class _TestOnlySandboxCommand:
    """Explicit unit-test launcher stub; never used by the production Runner."""

    def __init__(self, executable, argv):
        self.argv = (executable, *argv)
        self._fd = tempfile.TemporaryFile(mode="w+b")

    @property
    def seccomp_fd(self):
        return self._fd.fileno()

    def close(self):
        self._fd.close()


class _TestOnlyPassthroughLauncher:
    """Exercise executor process handling without claiming OS isolation."""

    def build(self, *, executable, argv, workspace, scratch, environment=None):
        return _TestOnlySandboxCommand(executable, argv)




class TerminalScriptExecutorTests(unittest.TestCase):
    def setUp(self):
        self.isolation_patch = patch(
            "tools.local_runner_agent.terminal_executor.assess_isolation_backend",
            return_value=IsolationAssessment(
                platform="linux",
                backend="test-only-verified-backend",
                state="VERIFIED",
                available=True,
                network_isolated=True,
                filesystem_isolated=True,
                process_tree_contained=True,
                reason="unit-test-only injected verifier",
            ),
        )
        self.isolation_patch.start()
        self.addCleanup(self.isolation_patch.stop)
        self.launcher_patch = patch(
            "tools.local_runner_agent.terminal_executor.LinuxBubblewrapLauncher",
            _TestOnlyPassthroughLauncher,
        )
        self.launcher_patch.start()
        self.addCleanup(self.launcher_patch.stop)
        # The test-only launcher accepts the host test interpreter as a stand-in
        # for /usr/bin; production LinuxBubblewrapLauncher rejects other runtime roots.
        original_which = shutil.which
        self.original_which = original_which
        def test_which(name, path=None):
            if path == "/usr/bin":
                return original_which(name) or (
                    original_which("python3") if name == "python" else None
                )
            return original_which(name, path=path)
        self.which_patch = patch(
            "tools.local_runner_agent.terminal_executor.shutil.which",
            side_effect=test_which,
        )
        self.which_patch.start()
        self.addCleanup(self.which_patch.stop)
        self.temp = tempfile.TemporaryDirectory()
        self.workspace = Path(self.temp.name) / "project"
        self.workspace.mkdir()
        (self.workspace / "README.md").write_text("DCP terminal workspace\n", encoding="utf-8")

    def tearDown(self):
        self.temp.cleanup()

    def test_git_environment_overrides_project_controlled_helpers(self):
        template = {
            "executable": "git",
            "environment_allowlist": ["PATH", "HOME", "USERPROFILE"],
        }
        job_home = Path(self.temp.name) / "git-home"
        job_home.mkdir()
        env = TerminalScriptExecutor._environment(template, job_home, "trusted-path")

        self.assertEqual(env["GIT_CONFIG_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_ATTR_NOSYSTEM"], "1")
        self.assertEqual(env["GIT_OPTIONAL_LOCKS"], "0")
        self.assertEqual(env["GIT_TERMINAL_PROMPT"], "0")
        self.assertEqual(env["GIT_CONFIG_COUNT"], "6")
        configured = {
            env[f"GIT_CONFIG_KEY_{index}"]: env[f"GIT_CONFIG_VALUE_{index}"]
            for index in range(6)
        }
        self.assertEqual(configured["core.fsmonitor"], "false")
        self.assertEqual(configured["diff.external"], "")
        self.assertEqual(configured["core.pager"], "cat")
        self.assertEqual(configured["pager.diff"], "false")
        self.assertEqual(configured["pager.log"], "false")
        self.assertEqual(configured["pager.show"], "false")
        self.assertEqual(env["GIT_PAGER"], "cat")
        self.assertEqual(env["PAGER"], "cat")
        self.assertEqual(env["HOME"], str(job_home))
        self.assertEqual(env["USERPROFILE"], str(job_home))

    def test_repository_fsmonitor_and_clean_filters_are_not_invoked_by_runner_git_commands(self):
        git = shutil.which("git")
        if not git:
            self.skipTest("Git is unavailable on this test host")
        version = subprocess.run(
            [git, "--version"], check=True, capture_output=True, text=True
        ).stdout
        match = re.search(r"([0-9]+)\.([0-9]+)\.([0-9]+)", version)
        if not match or tuple(map(int, match.groups())) < (2, 36, 0):
            self.skipTest("Git 2.36+ is required for boolean core.fsmonitor=false")

        def git_run(*args):
            return subprocess.run(
                [git, "-C", str(self.workspace), *args],
                check=True, capture_output=True, text=True,
            )

        git_run("init", "-q")
        git_run("config", "user.name", "DCP Test")
        git_run("config", "user.email", "dcp-test@example.invalid")
        attributes = self.workspace / ".gitattributes"
        attributes.write_text("README.md filter=hostile\n", encoding="utf-8")
        git_run("add", "README.md", ".gitattributes")
        git_run("commit", "-m", "test fixture")

        fsmonitor_marker = Path(self.temp.name) / "fsmonitor-hook-ran"
        fsmonitor_hook = Path(self.temp.name) / "fsmonitor_hook.py"
        fsmonitor_hook.write_text(
            "import pathlib\n"
            f"pathlib.Path({str(fsmonitor_marker)!r}).write_text('called', encoding='utf-8')\n"
            "print('token')\n",
            encoding="utf-8",
        )
        git_run("config", "core.fsmonitor", f'"{Path(sys.executable).as_posix()}" "{fsmonitor_hook.as_posix()}"')
        git_run("config", "core.fsmonitorHookVersion", "2")

        # Prove the repository-local fsmonitor hook is active before testing the Runner override.
        git_run("status", "--short")
        self.assertTrue(fsmonitor_marker.is_file())
        fsmonitor_marker.unlink()

        filter_marker = Path(self.temp.name) / "clean-filter-ran"
        filter_hook = Path(self.temp.name) / "clean_filter_hook.py"
        filter_hook.write_text(
            "import pathlib,sys\n"
            f"pathlib.Path({str(filter_marker)!r}).write_text('called', encoding='utf-8')\n"
            "sys.stdout.buffer.write(sys.stdin.buffer.read())\n",
            encoding="utf-8",
        )
        git_run("config", "filter.hostile.clean", f'"{Path(sys.executable).as_posix()}" "{filter_hook.as_posix()}"')
        git_run("config", "filter.hostile.required", "true")
        readme = self.workspace / "README.md"
        readme.write_text("DCP changed workspace!\n", encoding="utf-8")
        future_mtime = time.time() + 2
        os.utime(readme, (future_mtime, future_mtime))

        # Prove the repository-local clean filter is active on an explicit path conversion.
        git_run("hash-object", "--path=README.md", "README.md")
        self.assertTrue(filter_marker.is_file())
        filter_marker.unlink()

        template = {
            "id": "git_status",
            "executable": "git",
            "argv": ["status", "--short"],
            "parameters": [],
            "parameter_values": {},
            "execution_enabled": True,
            "mutation_class": "read-only",
            "network": "denied",
            "approval_required": False,
            "working_directory_policy": "assigned_workspace_required",
            "environment_allowlist": ["PATH", "HOME", "USERPROFILE", "SYSTEMROOT"],
            "timeout_seconds": 15,
            "max_output_bytes": 65536,
        }
        executor = TerminalScriptExecutor(enabled=True)
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.template_version_digest",
            return_value="f" * 64,
        ):
            result = executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "git_status", {}, "f" * 64,
            )

        self.assertEqual(result.outcome, "succeeded")
        self.assertFalse(fsmonitor_marker.exists(), "repository-controlled fsmonitor hook was invoked")

        # The same Runner boundary must also suppress a clean filter on Git path conversion.
        template["argv"] = ["hash-object", "--path=README.md", "README.md"]
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.template_version_digest",
            return_value="f" * 64,
        ):
            filter_result = executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "git_status", {}, "f" * 64,
            )
        self.assertEqual(filter_result.outcome, "succeeded")
        self.assertFalse(filter_marker.exists(), "repository-controlled clean filter was invoked")

    def test_repository_filter_driver_names_are_case_sensitive(self):
        env = {"GIT_CONFIG_COUNT": "0"}
        listed = subprocess.CompletedProcess(
            args=["git", "config"], returncode=0,
            stdout=b"filter.hostile.clean\0filter.Hostile.clean\0",
        )
        with tempfile.TemporaryDirectory() as scratch:
            with patch(
                "tools.local_runner_agent.terminal_executor.subprocess.run",
                return_value=listed,
            ):
                TerminalScriptExecutor._disable_repository_filters(
                    "git", self.workspace, env,
                    launcher=_TestOnlyPassthroughLauncher(),
                    scratch=Path(scratch),
                )

        self.assertEqual(env["GIT_CONFIG_COUNT"], "8")
        configured = {
            env[f"GIT_CONFIG_KEY_{index}"]: env[f"GIT_CONFIG_VALUE_{index}"]
            for index in range(8)
        }
        self.assertEqual(configured["filter.hostile.clean"], "")
        self.assertEqual(configured["filter.Hostile.clean"], "")
        self.assertEqual(configured["filter.hostile.required"], "false")
        self.assertEqual(configured["filter.Hostile.required"], "false")

    def test_git_diff_and_show_disable_external_diff_and_textconv(self):
        diff = TerminalScriptExecutor._build_command(
            "git", "git", ["diff", "--no-ext-diff", "--"]
        )
        show = TerminalScriptExecutor._build_command(
            "git", "git", ["show", "--no-ext-diff", "--stat", "--oneline", "a" * 40]
        )
        self.assertEqual(
            diff, ["git", "diff", "--no-ext-diff", "--no-textconv", "--"]
        )
        self.assertEqual(
            show,
            ["git", "show", "--no-ext-diff", "--no-textconv", "--stat", "--oneline", "a" * 40],
        )

    def test_non_git_command_builder_preserves_fixed_argv(self):
        self.assertEqual(
            TerminalScriptExecutor._build_command("python", "python", ["--version"]),
            ["python", "--version"],
        )


    def test_execution_is_blocked_without_verified_os_isolation(self):
        executor = TerminalScriptExecutor(enabled=True)
        blocked = IsolationAssessment(
            platform="linux",
            backend="bubblewrap-namespaces-seccomp",
            state="READY_FOR_ACCEPTANCE",
            available=True,
            network_isolated=False,
            filesystem_isolated=False,
            process_tree_contained=False,
            reason="backend not accepted",
        )
        with patch(
            "tools.local_runner_agent.terminal_executor.assess_isolation_backend",
            return_value=blocked,
        ):
            with self.assertRaisesRegex(TerminalExecutionError, "verified OS isolation"):
                executor.run(
                    str(uuid.uuid4()), "runner-local", self.workspace,
                    "python_version", {}, template_version_digest("python_version", {}),
                )

    def test_execution_remains_disabled_until_catalog_opt_in(self):
        executor = TerminalScriptExecutor(enabled=True)
        with self.assertRaisesRegex(TerminalExecutionError, "not enabled"):
            executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "python_version", {}, template_version_digest("python_version", {}),
            )

    @unittest.skipUnless(
        sys.platform.startswith("linux")
        and shutil.which("bwrap", path="/usr/bin")
        and (shutil.which("python", path="/usr/bin") or shutil.which("python3", path="/usr/bin")),
        "Linux bubblewrap runtime or /usr/bin Python is unavailable",
    )
    def test_real_bubblewrap_executor_launches_catalog_command_with_seccomp_fd(self):
        template = dict(preview_template("python_version", {}), execution_enabled=True)
        executor = TerminalScriptExecutor(enabled=True)
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.LinuxBubblewrapLauncher",
            LinuxBubblewrapLauncher,
        ), patch(
            "tools.local_runner_agent.terminal_executor.shutil.which",
            side_effect=self.original_which,
        ):
            result = executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "python_version", {}, template_version_digest("python_version", {}),
            )
        self.assertEqual(result.outcome, "succeeded", result)
        self.assertEqual(result.return_code, 0)
        self.assertGreater(result.output_bytes, 0)
        self.assertTrue(Path(result.command[0]).resolve().is_relative_to(Path("/usr/bin").resolve()))
        self.assertEqual(sorted(item.name for item in self.workspace.iterdir()), ["README.md"])

    def test_sandbox_construction_failure_never_falls_back_to_host_process(self):
        template = dict(preview_template("python_version", {}), execution_enabled=True)
        executor = TerminalScriptExecutor(enabled=True)
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.template_version_digest",
            return_value="b" * 64,
        ), patch(
            "tools.local_runner_agent.terminal_executor.LinuxBubblewrapLauncher",
            side_effect=LinuxSandboxError("bwrap unavailable"),
        ), patch(
            "tools.local_runner_agent.terminal_executor.subprocess.Popen"
        ) as popen:
            with self.assertRaisesRegex(TerminalExecutionError, "could not be constructed safely"):
                executor.run(
                    str(uuid.uuid4()), "runner-local", self.workspace,
                    "python_version", {}, "b" * 64,
                )
            popen.assert_not_called()

    def test_runs_catalog_python_version_in_selected_project_workspace(self):
        template = preview_template("python_version", {})
        enabled_template = dict(template, execution_enabled=True)
        logs = []
        executor = TerminalScriptExecutor(
            enabled=True, log=lambda stream, message: logs.append((stream, message)),
        )
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=enabled_template,
        ):
            result = executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "python_version", {}, template_version_digest("python_version", {}),
            )
        self.assertEqual(result.outcome, "succeeded")
        self.assertEqual(result.return_code, 0)
        self.assertGreater(result.output_bytes, 0)
        self.assertIn("Python", "".join(message for _, message in logs))
        self.assertFalse((self.workspace / ".dcp-terminal-home").exists())
        self.assertTrue((self.workspace / "README.md").is_file())

    def test_template_digest_mismatch_fails_before_process_start(self):
        template = preview_template("python_version", {})
        enabled_template = dict(template, execution_enabled=True)
        executor = TerminalScriptExecutor(enabled=True)
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=enabled_template,
        ):
            with self.assertRaisesRegex(TerminalExecutionError, "version changed"):
                executor.run(
                    str(uuid.uuid4()), "runner-local", self.workspace,
                    "python_version", {}, "0" * 64,
                )

    def _run_test_command(self, argv, *, timeout=5, output=4096, cancel_requested=None):
        template = dict(preview_template("python_version", {}))
        template.update({
            "execution_enabled": True,
            "executable": "python",
            "argv": argv,
            "timeout_seconds": timeout,
            "max_output_bytes": output,
        })
        executor = TerminalScriptExecutor(
            enabled=True, timeout_ceiling_seconds=timeout,
            output_ceiling_bytes=max(1024, output),
        )
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.template_version_digest",
            return_value="e" * 64,
        ):
            return executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "python_version", {}, "e" * 64,
                cancel_requested=cancel_requested,
            )

    def test_timeout_terminates_terminal_process(self):
        result = self._run_test_command(["-c", "import time; time.sleep(5)"], timeout=1)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.error_code, "TERMINAL_TIMEOUT")

    def test_output_limit_terminates_terminal_process(self):
        result = self._run_test_command(["-c", "print('x' * 10000)"], output=1024)
        self.assertEqual(result.outcome, "failed")
        self.assertEqual(result.error_code, "TERMINAL_OUTPUT_LIMIT")
        self.assertEqual(result.output_bytes, 1024)

    def test_cancellation_terminates_terminal_process(self):
        result = self._run_test_command(
            ["-c", "import time; time.sleep(5)"],
            cancel_requested=lambda: True,
        )
        self.assertEqual(result.outcome, "cancelled")
        self.assertEqual(result.error_code, "TERMINAL_CANCELLED")

    def test_project_workspace_symlink_is_rejected(self):
        link = Path(self.temp.name) / "project-link"
        try:
            link.symlink_to(self.workspace, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest("symlinks are unavailable on this platform")
        executor = TerminalScriptExecutor(enabled=True)
        with self.assertRaisesRegex(TerminalExecutionError, "contains a link"):
            executor.run(
                str(uuid.uuid4()), "runner-local", link,
                "python_version", {}, template_version_digest("python_version", {}),
            )

    def test_temporary_terminal_home_inside_project_workspace_is_rejected(self):
        template = dict(preview_template("python_version", {}), execution_enabled=True)
        unsafe_home = self.workspace / ".dcp-terminal-home-test"
        unsafe_home.mkdir()
        executor = TerminalScriptExecutor(enabled=True)
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.tempfile.mkdtemp",
            return_value=str(unsafe_home),
        ):
            with self.assertRaisesRegex(TerminalExecutionError, "outside the Project Workspace"):
                executor.run(
                    str(uuid.uuid4()), "runner-local", self.workspace,
                    "python_version", {}, template_version_digest("python_version", {}),
                )
        self.assertFalse(unsafe_home.exists())

    def test_streaming_redactor_holds_partial_lines_and_private_key_blocks(self):
        redactor = TerminalOutputRedactor()
        first = redactor.feed("diagnostic ghp_abcdefgh")
        self.assertEqual(first, "")
        second = redactor.feed("ijklmnopqrstuvwxyz1234\nnext line\n")
        self.assertNotIn("ghp_", second)
        self.assertIn("[REDACTED TOKEN]", second)
        self.assertIn("next line", second)

        key_redactor = TerminalOutputRedactor()
        opening = key_redactor.feed("-----BEGIN PRIVATE KEY-----\nprivate-part")
        self.assertIn("[REDACTED PRIVATE KEY]", opening)
        closing = key_redactor.feed("\nmore-private-part\n-----END PRIVATE KEY-----\npublic line\n")
        self.assertNotIn("private-part", closing)
        self.assertIn("public line", closing)

    def test_terminal_output_redacts_secrets_split_across_reader_chunks(self):
        template = {
            "id": "python_version",
            "executable": "python",
            "argv": ["-c", "import sys;sys.stdout.write('x'*4094+'ghp_'+'A'*40)"],
            "parameters": [],
            "parameter_values": {},
            "execution_enabled": True,
            "mutation_class": "read-only",
            "network": "denied",
            "approval_required": False,
            "working_directory_policy": "assigned_workspace_required",
            "environment_allowlist": ["PATH"],
            "timeout_seconds": 10,
            "max_output_bytes": 65536,
        }
        logs = []
        executor = TerminalScriptExecutor(
            enabled=True, log=lambda stream, message: logs.append((stream, message)),
        )
        with patch(
            "tools.local_runner_agent.terminal_executor.preview_template",
            return_value=template,
        ), patch(
            "tools.local_runner_agent.terminal_executor.template_version_digest",
            return_value="a" * 64,
        ):
            result = executor.run(
                str(uuid.uuid4()), "runner-local", self.workspace,
                "python_version", {}, "a" * 64,
            )
        combined = "".join(message for stream, message in logs if stream == "stdout")
        self.assertEqual(result.outcome, "succeeded")
        self.assertNotIn("ghp_", combined)
        self.assertNotIn("A" * 40, combined)
        self.assertIn("[REDACTED TOKEN]", combined)

    def test_log_chunks_respect_gateway_utf8_byte_limit(self):
        value = "ก" * 6000
        chunks = list(TerminalScriptExecutor._log_chunks(value, max_bytes=7000))
        self.assertEqual("".join(chunks), value)
        self.assertTrue(all(len(chunk.encode("utf-8")) <= 7000 for chunk in chunks))

    def test_streaming_redactor_handles_tokens_and_private_keys_split_across_chunks(self):
        redactor = TerminalOutputRedactor()
        first = redactor.feed("API_KEY=super-secret-value\nBearer abcdefghijkl")
        second = redactor.feed("mnopqrstuvwxyz\n-----BEGIN PRIVATE KEY-----\nprivate-")
        third = redactor.feed("key-material\n-----END PRIVATE KEY-----\n", final=True)
        combined = first + second + third
        self.assertNotIn("super-secret-value", combined)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", combined)
        self.assertNotIn("private-key-material", combined)
        self.assertIn("[REDACTED PRIVATE KEY]", combined)

    def test_terminal_output_redacts_truncated_secret_and_private_key_prefixes(self):
        redacted_token = redact_terminal_output("partial: ghp_abcd1234")
        redacted_key = redact_terminal_output(
            "-----BEGIN PRIVATE KEY-----\npartial-private-material"
        )
        self.assertNotIn("ghp_abcd1234", redacted_token)
        self.assertNotIn("partial-private-material", redacted_key)
        self.assertIn("[REDACTED TOKEN PREFIX]", redacted_token)
        self.assertIn("[REDACTED PRIVATE KEY]", redacted_key)

    def test_terminal_output_redacts_common_secrets_and_private_keys(self):
        token = "gh" + "p_" + "abcdefghijklmnopqrstuvwxyz123456"
        sample = (
            "API_KEY=abc123\n"
            "Authorization: Bearer abcdefghijklmnopqrstuvwxyz\n"
            + token + "\n"
            + "-----BEGIN PRIVATE KEY-----\nsecret-material\n-----END PRIVATE KEY-----"
        )
        redacted = redact_terminal_output(sample)
        self.assertNotIn("abc123", redacted)
        self.assertNotIn("abcdefghijklmnopqrstuvwxyz", redacted)
        self.assertNotIn("secret-material", redacted)
        self.assertIn("[REDACTED", redacted)


if __name__ == "__main__":
    unittest.main()
