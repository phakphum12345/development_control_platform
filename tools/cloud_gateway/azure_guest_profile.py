"""Build least-privilege Azure VM OS profiles for ephemeral DCP runners.

Linux uses a caller-supplied public Ed25519 key and password authentication is
disabled. Windows receives a fresh, high-entropy local administrator password
only in the one-time ARM create request; it is never returned or persisted by
this factory. Neither profile attaches a VM Managed Identity.
"""
from __future__ import annotations

import base64
import os
import re
import secrets
import string


class AzureGuestProfileError(ValueError):
    """Invalid or unsupported guest login profile configuration."""


class AzureGuestProfileFactory:
    """Create per-VM Linux/Windows profiles without sharing Gateway identity."""

    def __init__(self, admin_username: str, linux_ssh_public_key: str):
        if not isinstance(admin_username, str) or not re.fullmatch(
            r"[A-Za-z][A-Za-z0-9_-]{2,19}", admin_username
        ):
            raise AzureGuestProfileError("Invalid Azure guest administrator username")
        if admin_username.lower() in {
            "administrator", "admin", "root", "guest", "system",
            "defaultaccount", "wdagutilityaccount",
        }:
            raise AzureGuestProfileError("Reserved guest administrator username")
        self.admin_username = admin_username
        self.linux_ssh_public_key = self._validate_ed25519_key(linux_ssh_public_key)

    @classmethod
    def from_environment(cls, env=None):
        values = os.environ if env is None else env
        return cls(
            values.get("DCP_AZURE_GUEST_ADMIN_USERNAME", ""),
            values.get("DCP_AZURE_LINUX_SSH_PUBLIC_KEY", ""),
        )

    @staticmethod
    def _validate_ed25519_key(value: str) -> str:
        if not isinstance(value, str) or len(value) > 16384 or "\n" in value or "\r" in value:
            raise AzureGuestProfileError("A single-line SSH Ed25519 public key is required")
        parts = value.strip().split()
        if len(parts) < 2 or parts[0] != "ssh-ed25519":
            raise AzureGuestProfileError("Only OpenSSH Ed25519 public keys are accepted")
        try:
            decoded = base64.b64decode(parts[1], validate=True)
        except (ValueError, base64.binascii.Error) as exc:
            raise AzureGuestProfileError("SSH public key encoding is invalid") from exc
        prefix = len(b"ssh-ed25519").to_bytes(4, "big") + b"ssh-ed25519"
        if not decoded.startswith(prefix) or len(decoded) != len(prefix) + 4 + 32:
            raise AzureGuestProfileError("SSH key type or Ed25519 key length is invalid")
        if int.from_bytes(decoded[len(prefix):len(prefix) + 4], "big") != 32:
            raise AzureGuestProfileError("SSH Ed25519 key payload length is invalid")
        return " ".join(parts[:3])

    @staticmethod
    def _windows_password() -> str:
        # Azure Windows provisioning requires mixed character classes. Generate
        # at least one from each class, then cryptographically shuffle the result.
        chars = [
            secrets.choice(string.ascii_lowercase),
            secrets.choice(string.ascii_uppercase),
            secrets.choice(string.digits),
            secrets.choice("!@#$%^-_=+"),
        ]
        alphabet = string.ascii_letters + string.digits + "!@#$%^-_=+"
        chars.extend(secrets.choice(alphabet) for _ in range(44))
        secrets.SystemRandom().shuffle(chars)
        return "".join(chars)

    def __call__(self, vm_name: str, os_name: str, payload: dict) -> dict:
        if not isinstance(vm_name, str) or not re.fullmatch(
            r"dcp-[0-9]+-[a-f0-9]{8}", vm_name
        ):
            raise AzureGuestProfileError("Invalid DCP Azure VM name")
        if not isinstance(payload, dict) or payload.get("target_os") != os_name:
            raise AzureGuestProfileError("Guest OS does not match the runner request")
        if payload.get("ephemeral") is not True:
            raise AzureGuestProfileError("Cloud Runner guest must be ephemeral")

        profile = {
            "computerName": vm_name,
            "adminUsername": self.admin_username,
        }
        if os_name == "linux":
            profile["linuxConfiguration"] = {
                "disablePasswordAuthentication": True,
                "ssh": {
                    "publicKeys": [{
                        "path": f"/home/{self.admin_username}/.ssh/authorized_keys",
                        "keyData": self.linux_ssh_public_key,
                    }]
                },
            }
        elif os_name == "windows":
            profile["adminPassword"] = self._windows_password()
        else:
            raise AzureGuestProfileError("Azure guest profiles support Linux and Windows only")
        return profile
