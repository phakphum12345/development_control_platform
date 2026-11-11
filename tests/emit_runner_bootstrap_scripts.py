"""Emit mock runner bootstrap scripts for bash/PowerShell parser checks."""
import base64
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from tools.cloud_gateway.runner_bootstrap import AzureRunnerBootstrapFactory


class FakeGitHubApp:
    def create_registration_token(self, repository):
        return SimpleNamespace(
            token="mock-only-registration-token",
            expires_at=datetime.now(timezone.utc) + timedelta(minutes=30),
        )


def main():
    output = Path(sys.argv[1])
    output.mkdir(parents=True, exist_ok=True)
    factory = AzureRunnerBootstrapFactory(
        FakeGitHubApp(), "2.331.0", "a" * 64, "b" * 64,
        lambda vm, os_name, payload: {"computerName": vm},
    )
    profiles = {
        "linux": ["self-hosted", "Linux", "X64", "dcp-cloud-linux"],
        "windows": ["self-hosted", "Windows", "X64", "dcp-cloud-windows"],
    }
    for os_name, labels in profiles.items():
        payload = {
            "repository": "phakphum12345/generated-A4-pdf",
            "target_os": os_name,
            "labels": labels,
            "ephemeral": True,
            "network_policy": "restricted-egress",
        }
        result = factory("dcp-123-abcdef12", os_name, payload)
        protected = result["extension"]["properties"]["protectedSettings"]
        if os_name == "linux":
            script = base64.b64decode(protected["script"]).decode("utf-8")
            (output / "dcp-linux-bootstrap.sh").write_text(script, encoding="utf-8")
        else:
            command = protected["commandToExecute"]
            script = base64.b64decode(command.rsplit(" ", 1)[1]).decode("utf-16le")
            (output / "dcp-windows-bootstrap.ps1").write_text(script, encoding="utf-8")


if __name__ == "__main__":
    main()
