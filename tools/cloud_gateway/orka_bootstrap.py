"""Build protected Orka 4.0 User Data for ephemeral macOS ARM64 runners.

The User Data script contains a short-lived repository-scoped GitHub runner
registration token. Orka stores the script in Kubernetes VM resources; callers
must explicitly attest that namespace RBAC prevents untrusted readers.
"""
from __future__ import annotations

import re
import shlex
from datetime import datetime, timedelta, timezone


class OrkaBootstrapError(RuntimeError):
    pass


class OrkaRunnerBootstrapFactory:
    def __init__(
        self,
        github_app,
        runner_version: str,
        runner_sha256: str,
        runner_user: str,
        runner_home: str,
    ):
        if not isinstance(runner_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", runner_version):
            raise ValueError("Runner version must be an explicit x.y.z release")
        if not isinstance(runner_sha256, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", runner_sha256):
            raise ValueError("macOS runner archive SHA-256 must be pinned")
        if not isinstance(runner_user, str) or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", runner_user):
            raise ValueError("Invalid pre-provisioned macOS runner account")
        if not isinstance(runner_home, str) or not re.fullmatch(r"/Users/[A-Za-z0-9._-]{1,64}", runner_home):
            raise ValueError("Invalid macOS runner home directory")
        self.github_app = github_app
        self.runner_version = runner_version
        self.runner_sha256 = runner_sha256.lower()
        self.runner_user = runner_user
        self.runner_home = runner_home

    @staticmethod
    def _validate_payload(vm_name, os_name, payload):
        if not isinstance(vm_name, str) or not re.fullmatch(r"dcp-[0-9]+-[a-f0-9]{8}", vm_name):
            raise OrkaBootstrapError("Invalid DCP macOS runner name")
        if os_name != "macos" or not isinstance(payload, dict) or payload.get("target_os") != "macos":
            raise OrkaBootstrapError("Orka bootstrap accepts only the approved macOS profile")
        if payload.get("image") != "macos-15-arm64":
            raise OrkaBootstrapError("Orka bootstrap requires the approved macOS 15 ARM64 image")
        if payload.get("ephemeral") is not True or payload.get("network_policy") != "restricted-egress":
            raise OrkaBootstrapError("Orka runner must be ephemeral with restricted egress")
        repository = payload.get("repository")
        if not isinstance(repository, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository
        ):
            raise OrkaBootstrapError("Invalid runner repository")
        labels = payload.get("labels")
        if not isinstance(labels, list) or not labels or any(
            not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", label)
            for label in labels
        ):
            raise OrkaBootstrapError("Invalid runner labels")
        return repository, labels

    def __call__(self, vm_name: str, os_name: str, payload: dict) -> dict:
        repository, labels = self._validate_payload(vm_name, os_name, payload)
        credential = self.github_app.create_registration_token(repository)
        token = getattr(credential, "token", None)
        expires_at = getattr(credential, "expires_at", None)
        now = datetime.now(timezone.utc)
        if (
            not isinstance(token, str) or not token or len(token) > 512
            or any(ord(char) < 33 or ord(char) > 126 for char in token)
        ):
            raise OrkaBootstrapError("GitHub runner registration credential is invalid")
        if (
            not isinstance(expires_at, datetime) or expires_at.tzinfo is None
            or expires_at <= now + timedelta(minutes=15)
        ):
            raise OrkaBootstrapError("GitHub runner registration credential expires too soon")

        version = self.runner_version
        archive = f"actions-runner-osx-arm64-{version}.tar.gz"
        url = f"https://github.com/actions/runner/releases/download/v{version}/{archive}"
        runner_dir = self.runner_home + "/actions-runner"
        config_command = " ".join([
            "cd", shlex.quote(runner_dir), "&&", "./config.sh",
            "--unattended",
            "--url", shlex.quote("https://github.com/" + repository),
            "--token", shlex.quote(token),
            "--name", shlex.quote(vm_name),
            "--labels", shlex.quote(",".join(labels)),
            "--ephemeral", "--disableupdate", "--work", "_work",
        ])
        script = "\n".join([
            "#!/bin/bash",
            "set -euo pipefail",
            "set +x",
            "umask 077",
            f"RUNNER_USER={shlex.quote(self.runner_user)}",
            f"RUNNER_HOME={shlex.quote(self.runner_home)}",
            f"RUNNER_DIR={shlex.quote(runner_dir)}",
            f"ARCHIVE={shlex.quote(archive)}",
            "if [ \"$(id -u)\" -ne 0 ]; then echo 'DCP bootstrap requires root'; exit 1; fi",
            "id \"$RUNNER_USER\" >/dev/null 2>&1 || { echo 'DCP runner account is missing'; exit 1; }",
            "if id -Gn \"$RUNNER_USER\" | tr ' ' '\\n' | grep -E '^(admin|wheel)$' >/dev/null; then echo 'DCP runner account must not be privileged'; exit 1; fi",
            "ACTUAL_HOME=\"$(dscl . -read \"/Users/$RUNNER_USER\" NFSHomeDirectory 2>/dev/null | awk '{print $2}')\"",
            "[ \"$ACTUAL_HOME\" = \"$RUNNER_HOME\" ] || { echo 'DCP runner home does not match image profile'; exit 1; }",
            "xcodebuild -version >/dev/null 2>&1 || { echo 'DCP macOS image does not contain Xcode'; exit 1; }",
            "install -d -m 0750 \"$RUNNER_DIR\"",
            "chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            "cd \"$RUNNER_DIR\"",
            "if [ ! -f .runner ]; then",
            f"  for attempt in 1 2 3 4 5 6; do if curl --fail --location --silent --show-error --connect-timeout 10 --max-time 120 {shlex.quote(url)} --output \"$ARCHIVE\"; then break; fi; rm -f -- \"$ARCHIVE\"; sleep 5; done",
            "  [ -s \"$ARCHIVE\" ] || { echo 'DCP runner archive download failed'; exit 1; }",
            f"  echo {shlex.quote(self.runner_sha256 + '  ' + archive)} | shasum -a 256 -c - >/dev/null 2>&1 || {{ echo 'DCP runner archive checksum mismatch'; exit 1; }}",
            "  tar -xzf \"$ARCHIVE\"",
            "  chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            f"  su - \"$RUNNER_USER\" -c {shlex.quote(config_command)} >/dev/null 2>&1 || {{ echo 'DCP runner configuration failed'; exit 1; }}",
            "fi",
            "if ! ./svc.sh status >/dev/null 2>&1; then",
            "  ./svc.sh install \"$RUNNER_USER\" >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service installation failed'; exit 1; }; }",
            "fi",
            "./svc.sh start >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service start failed'; exit 1; }; }",
            "rm -f -- \"$ARCHIVE\"",
            "echo 'DCP macOS runner bootstrap completed'",
            "",
        ])
        return {"script": script, "expires_at": expires_at}
 >/dev/null; then echo 'DCP runner account must not be privileged'; exit 1; fi",
            "ACTUAL_HOME=\"$(dscl . -read \"/Users/$RUNNER_USER\" NFSHomeDirectory 2>/dev/null | awk '{print $2}')\"",
            "[ \"$ACTUAL_HOME\" = \"$RUNNER_HOME\" ] || { echo 'DCP runner home does not match image profile'; exit 1; }",
            "install -d -m 0750 \"$RUNNER_DIR\"",
            "chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            "cd \"$RUNNER_DIR\"",
            "if [ ! -f .runner ]; then",
            f"  curl --fail --location --silent --show-error {shlex.quote(url)} --output \"$ARCHIVE\"",
            f"  echo {shlex.quote(self.runner_sha256 + '  ' + archive)} | shasum -a 256 --check --status",
            "  tar -xzf \"$ARCHIVE\"",
            "  chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            f"  su - \"$RUNNER_USER\" -c {shlex.quote(config_command)} >/dev/null 2>&1 || {{ echo 'DCP runner configuration failed'; exit 1; }}",
            "fi",
            "if ! ./svc.sh status >/dev/null 2>&1; then",
            "  ./svc.sh install \"$RUNNER_USER\" >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service installation failed'; exit 1; }; }",
            "fi",
            "./svc.sh start >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service start failed'; exit 1; }; }",
            "rm -f -- \"$ARCHIVE\"",
            "echo 'DCP macOS runner bootstrap completed'",
            "",
        ])
        return {"script": script, "expires_at": expires_at}
 >/dev/null; then echo 'DCP runner account must not be privileged'; exit 1; fi",
            "ACTUAL_HOME=\"$(dscl . -read \"/Users/$RUNNER_USER\" NFSHomeDirectory 2>/dev/null | awk '{print $2}')\"",
            "[ \"$ACTUAL_HOME\" = \"$RUNNER_HOME\" ] || { echo 'DCP runner home does not match image profile'; exit 1; }",
            "install -d -m 0750 \"$RUNNER_DIR\"",
            "chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            "cd \"$RUNNER_DIR\"",
            "if [ ! -f .runner ]; then",
            f"  curl --fail --location --silent --show-error {shlex.quote(url)} --output \"$ARCHIVE\"",
            f"  echo {shlex.quote(self.runner_sha256 + '  ' + archive)} | shasum -a 256 --check --status",
            "  tar -xzf \"$ARCHIVE\"",
            "  chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            f"  su - \"$RUNNER_USER\" -c {shlex.quote(config_command)} >/dev/null 2>&1 || {{ echo 'DCP runner configuration failed'; exit 1; }}",
            "fi",
            "if ! ./svc.sh status >/dev/null 2>&1; then",
            "  ./svc.sh install \"$RUNNER_USER\" >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service installation failed'; exit 1; }; }",
            "fi",
            "./svc.sh start >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service start failed'; exit 1; }; }",
            "rm -f -- \"$ARCHIVE\"",
            "echo 'DCP macOS runner bootstrap completed'",
            "",
        ])
        return {"script": script, "expires_at": expires_at}
 >/dev/null; then echo 'DCP runner account must not be privileged'; exit 1; fi",
            "ACTUAL_HOME=\"$(dscl . -read \"/Users/$RUNNER_USER\" NFSHomeDirectory 2>/dev/null | awk '{print $2}')\"",
            "[ \"$ACTUAL_HOME\" = \"$RUNNER_HOME\" ] || { echo 'DCP runner home does not match image profile'; exit 1; }",
            "install -d -m 0750 \"$RUNNER_DIR\"",
            "chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            "cd \"$RUNNER_DIR\"",
            "if [ ! -f .runner ]; then",
            f"  curl --fail --location --silent --show-error {shlex.quote(url)} --output \"$ARCHIVE\"",
            f"  echo {shlex.quote(self.runner_sha256 + '  ' + archive)} | shasum -a 256 --check --status",
            "  tar -xzf \"$ARCHIVE\"",
            "  chown -R \"$RUNNER_USER\":staff \"$RUNNER_DIR\"",
            f"  su - \"$RUNNER_USER\" -c {shlex.quote(config_command)} >/dev/null 2>&1 || {{ echo 'DCP runner configuration failed'; exit 1; }}",
            "fi",
            "if ! ./svc.sh status >/dev/null 2>&1; then",
            "  ./svc.sh install \"$RUNNER_USER\" >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service installation failed'; exit 1; }; }",
            "fi",
            "./svc.sh start >/dev/null 2>&1 || { ./svc.sh status >/dev/null 2>&1 || { echo 'DCP runner service start failed'; exit 1; }; }",
            "rm -f -- \"$ARCHIVE\"",
            "echo 'DCP macOS runner bootstrap completed'",
            "",
        ])
        return {"script": script, "expires_at": expires_at}
