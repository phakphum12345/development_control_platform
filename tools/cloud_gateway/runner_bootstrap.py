"""Build protected Azure VM extension payloads for ephemeral GitHub runners.

The GitHub registration token is embedded only in Azure protectedSettings.
No live Azure request is made by this module; AzureVMProvider owns deployment.
"""
from __future__ import annotations

import base64
import re
import shlex
from datetime import datetime, timedelta, timezone
from typing import Callable


class RunnerBootstrapError(RuntimeError):
    pass


class AzureRunnerBootstrapFactory:
    """Create OS-specific protected bootstrap extensions with pinned artifacts."""

    def __init__(
        self,
        github_app,
        runner_version: str,
        linux_sha256: str,
        windows_sha256: str,
        os_profile_factory: Callable,
    ):
        if not isinstance(runner_version, str) or not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", runner_version):
            raise ValueError("Runner version must be an explicit x.y.z release")
        for checksum in (linux_sha256, windows_sha256):
            if not isinstance(checksum, str) or not re.fullmatch(r"[a-fA-F0-9]{64}", checksum):
                raise ValueError("Runner archive SHA-256 must be pinned")
        if not callable(os_profile_factory):
            raise ValueError("An OS profile factory is required")
        self.github_app = github_app
        self.runner_version = runner_version
        self.checksums = {"linux": linux_sha256.lower(), "windows": windows_sha256.lower()}
        self.os_profile_factory = os_profile_factory

    @staticmethod
    def _validate_payload(vm_name: str, os_name: str, payload: dict) -> tuple[str, list[str]]:
        if not isinstance(vm_name, str) or not re.fullmatch(r"dcp-[0-9]+-[a-f0-9]{8}", vm_name):
            raise RunnerBootstrapError("Invalid DCP runner name")
        if os_name not in ("linux", "windows"):
            raise RunnerBootstrapError("Azure bootstrap supports only approved Linux or Windows")
        if not isinstance(payload, dict) or payload.get("target_os") != os_name:
            raise RunnerBootstrapError("Runner target OS does not match the Azure profile")
        if payload.get("ephemeral") is not True or payload.get("network_policy") != "restricted-egress":
            raise RunnerBootstrapError("Runner must be ephemeral with restricted egress")
        repository = payload.get("repository")
        if not isinstance(repository, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repository
        ):
            raise RunnerBootstrapError("Invalid runner repository")
        labels = payload.get("labels")
        if not isinstance(labels, list) or not labels or any(
            not isinstance(label, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", label)
            for label in labels
        ):
            raise RunnerBootstrapError("Invalid runner labels")
        return repository, labels

    def _linux_script(self, vm_name: str, repository: str, labels: list[str], token: str, token_expiry_epoch: int) -> str:
        version = self.runner_version
        archive = f"actions-runner-linux-x64-{version}.tar.gz"
        url = f"https://github.com/actions/runner/releases/download/v{version}/{archive}"
        label_arg = ",".join(labels)
        return "\n".join([
            "#!/usr/bin/env bash",
            "set -euo pipefail",
            "umask 077",
            f"if [ \"$(date +%s)\" -ge {token_expiry_epoch} ]; then echo 'Runner registration credential expired'; exit 1; fi",
            "id dcp-runner >/dev/null 2>&1 || useradd --system --create-home --shell /bin/bash dcp-runner",
            "if id -nG dcp-runner | grep -Eq '(^| )(sudo|wheel|admin)( |$)'; then echo 'Runner account must not be privileged'; exit 1; fi",
            "if sudo -l -U dcp-runner 2>/dev/null | grep -Eq '^[[:space:]]*\\('; then echo 'Runner account must not have sudo privileges'; exit 1; fi",
            "install -d -o dcp-runner -g dcp-runner -m 0750 /opt/dcp-actions-runner",
            "cd /opt/dcp-actions-runner",
            f"for attempt in 1 2 3 4 5 6; do if curl --fail --location --silent --show-error --connect-timeout 10 --max-time 120 {shlex.quote(url)} --output {shlex.quote(archive)}; then break; fi; rm -f -- {shlex.quote(archive)}; sleep 5; done",
            f"test -s {shlex.quote(archive)} || {{ echo 'Runner archive download failed'; exit 1; }}",
            f"echo {shlex.quote(self.checksums['linux'] + '  ' + archive)} | sha256sum --check --status",
            f"if [ \"$(date +%s)\" -ge {token_expiry_epoch} ]; then echo 'Runner registration credential expired'; exit 1; fi",
            f"tar -xzf {shlex.quote(archive)}",
            "chown -R dcp-runner:dcp-runner /opt/dcp-actions-runner",
            "if ! runuser -u dcp-runner -- ./config.sh "
            f"--unattended --url {shlex.quote('https://github.com/' + repository)} "
            f"--token {shlex.quote(token)} --name {shlex.quote(vm_name)} "
            f"--labels {shlex.quote(label_arg)} --ephemeral --disableupdate >/dev/null 2>&1; "
            "then echo 'Runner configuration failed'; exit 1; fi",
            "./svc.sh install dcp-runner",
            "./svc.sh start",
            f"rm -f -- {shlex.quote(archive)}",
            "",
        ])

    def _windows_script(self, vm_name: str, repository: str, labels: list[str], token: str, token_expiry_epoch: int) -> str:
        version = self.runner_version
        archive = f"actions-runner-win-x64-{version}.zip"
        url = f"https://github.com/actions/runner/releases/download/v{version}/{archive}"
        def ps(value: str) -> str:
            return "'" + value.replace("'", "''") + "'"
        return "\r\n".join([
            "$ErrorActionPreference = 'Stop'",
            "$ProgressPreference = 'SilentlyContinue'",
            f"if ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge {token_expiry_epoch}) {{ throw 'Runner registration credential expired' }}",
            "$root = 'C:\\actions-runner'",
            "New-Item -ItemType Directory -Force -Path $root | Out-Null",
            f"$archive = Join-Path $root {ps(archive)}",
            f"for ($attempt = 1; $attempt -le 6; $attempt++) {{ try {{ Invoke-WebRequest -Uri {ps(url)} -OutFile $archive -TimeoutSec 120; break }} catch {{ Remove-Item -LiteralPath $archive -Force -ErrorAction SilentlyContinue; if ($attempt -eq 6) {{ throw 'Runner archive download failed' }}; Start-Sleep -Seconds 5 }} }}",
            "if (-not (Test-Path -LiteralPath $archive)) { throw 'Runner archive download failed' }",
            f"if ((Get-FileHash -Algorithm SHA256 $archive).Hash.ToLowerInvariant() -ne {ps(self.checksums['windows'])}) {{ throw 'Runner archive checksum mismatch' }}",
            f"if ([DateTimeOffset]::UtcNow.ToUnixTimeSeconds() -ge {token_expiry_epoch}) {{ throw 'Runner registration credential expired' }}",
            "Expand-Archive -LiteralPath $archive -DestinationPath $root -Force",
            "Set-Location $root",
            f"& .\\config.cmd --unattended --url {ps('https://github.com/' + repository)} "
            f"--token {ps(token)} --name {ps(vm_name)} --labels {ps(','.join(labels))} "
            "--ephemeral --disableupdate *> $null",
            "if ($LASTEXITCODE -ne 0) { throw 'Runner configuration failed' }",
            "$taskScript = Join-Path $root 'start-runner.ps1'",
            "@'\nSet-Location -LiteralPath $PSScriptRoot\n& .\\run.cmd\nexit $LASTEXITCODE\n'@ | Set-Content -LiteralPath $taskScript -Encoding UTF8",
            "& icacls.exe $root /inheritance:r /grant 'SYSTEM:(OI)(CI)F' 'BUILTIN\\Administrators:(OI)(CI)F' 'NT AUTHORITY\\NETWORK SERVICE:(OI)(CI)M' | Out-Null",
            "if ($LASTEXITCODE -ne 0) { throw 'Could not restrict runner directory ACL' }",
            "$taskCommand = 'powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -File \"' + $taskScript + '\"'",
            "& schtasks.exe /Create /SC ONSTART /TN 'DCP-Ephemeral-Runner' /TR $taskCommand /RU 'NT AUTHORITY\\NETWORK SERVICE' /RL LIMITED /F",
            "if ($LASTEXITCODE -ne 0) { throw 'Could not create least-privilege runner task' }",
            "& schtasks.exe /Run /TN 'DCP-Ephemeral-Runner'",
            "if ($LASTEXITCODE -ne 0) { throw 'Could not start least-privilege runner task' }",
            "Remove-Item -LiteralPath $archive -Force",
            "",
        ])

    def __call__(self, vm_name: str, os_name: str, payload: dict) -> dict:
        repository, labels = self._validate_payload(vm_name, os_name, payload)
        credential = self.github_app.create_registration_token(repository)
        token = getattr(credential, "token", None)
        expires_at = getattr(credential, "expires_at", None)
        if (
            not isinstance(token, str) or not token or len(token) > 512
            or any(ord(ch) < 33 or ord(ch) > 126 for ch in token)
            or not isinstance(expires_at, datetime) or expires_at.tzinfo is None
            or expires_at <= datetime.now(timezone.utc) + timedelta(minutes=50)
        ):
            raise RunnerBootstrapError("GitHub runner registration credential is invalid or expires before the VM extension budget")
        token_expiry_epoch = int(expires_at.timestamp())
        os_profile = self.os_profile_factory(vm_name, os_name, payload)
        if not isinstance(os_profile, dict) or not os_profile:
            raise RunnerBootstrapError("OS profile factory returned an invalid profile")
        if os_name == "linux":
            script = self._linux_script(vm_name, repository, labels, token, token_expiry_epoch)
            extension = {
                "name": "dcp-runner-bootstrap",
                "properties": {
                    "publisher": "Microsoft.Azure.Extensions",
                    "type": "CustomScript",
                    "typeHandlerVersion": "2.1",
                    "settings": {},
                    "protectedSettings": {
                        "script": base64.b64encode(script.encode("utf-8")).decode("ascii")
                    },
                },
            }
        else:
            script = self._windows_script(vm_name, repository, labels, token, token_expiry_epoch)
            encoded = base64.b64encode(script.encode("utf-16le")).decode("ascii")
            extension = {
                "name": "dcp-runner-bootstrap",
                "properties": {
                    "publisher": "Microsoft.Compute",
                    "type": "CustomScriptExtension",
                    "typeHandlerVersion": "1.10",
                    "settings": {},
                    "protectedSettings": {
                        "commandToExecute": "powershell.exe -NoProfile -NonInteractive -ExecutionPolicy Bypass -EncodedCommand " + encoded
                    },
                },
            }
        return {"os_profile": os_profile, "extension": extension}
