"""GitHub App-backed, repository-scoped ephemeral runner registration.

This module is server-side only. It never writes credentials to disk or returns
them through the dashboard API. Callers must deliver the registration token
only through a provider's protected bootstrap channel.
"""
from __future__ import annotations

import base64
import json
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


class GitHubAppError(RuntimeError):
    """Sanitized GitHub App integration error."""


@dataclass(frozen=True)
class RunnerRegistrationCredential:
    token: str = field(repr=False)
    expires_at: datetime

    def __repr__(self) -> str:
        return "RunnerRegistrationCredential(token=<redacted>, expires_at={!r})".format(
            self.expires_at.isoformat()
        )


def _b64url(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def _claims_json(value: dict) -> bytes:
    return json.dumps(value, separators=(",", ":"), sort_keys=True).encode("utf-8")


class GitHubAppRunnerBootstrap:
    """Mint narrowly scoped registration tokens using a GitHub App installation.

    The App private key should be read from a server-side secret store (for
    example Key Vault) and passed in memory. The installation token is scoped
    to the one allowlisted repository and is never returned to callers.
    """

    API_ORIGIN = "https://api.github.com"

    def __init__(
        self,
        app_id: str,
        installation_id: int,
        private_key_pem: str,
        allowed_repositories: tuple[str, ...] | list[str],
        *,
        clock=time.time,
        timeout: int = 10,
        opener=None,
    ):
        if not isinstance(app_id, str) or not re.fullmatch(r"[0-9]{1,20}", app_id):
            raise ValueError("GitHub App ID must be numeric")
        if isinstance(installation_id, bool) or not isinstance(installation_id, int) or installation_id < 1:
            raise ValueError("GitHub App installation ID must be positive")
        if not isinstance(private_key_pem, str) or "BEGIN" not in private_key_pem:
            raise ValueError("GitHub App private key is required")
        repos = tuple(allowed_repositories)
        if not repos or len(set(repos)) != len(repos):
            raise ValueError("A non-empty unique repository allowlist is required")
        if any(not isinstance(repo, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}", repo
        ) for repo in repos):
            raise ValueError("Invalid repository allowlist entry")
        if isinstance(timeout, bool) or not isinstance(timeout, int) or not 1 <= timeout <= 30:
            raise ValueError("GitHub API timeout must be 1..30 seconds")
        self.app_id = app_id
        self.installation_id = installation_id
        self.private_key_pem = private_key_pem
        self.allowed_repositories = frozenset(repos)
        self.clock = clock
        self.timeout = timeout
        self.opener = opener or urlopen

    def _app_jwt(self) -> str:
        try:
            from cryptography.hazmat.primitives import hashes, serialization
            from cryptography.hazmat.primitives.asymmetric import padding, rsa

            key = serialization.load_pem_private_key(
                self.private_key_pem.encode("utf-8"), password=None
            )
            if not isinstance(key, rsa.RSAPrivateKey):
                raise ValueError("GitHub App key must be RSA")
            now = int(self.clock())
            header = _b64url(_claims_json({"alg": "RS256", "typ": "JWT"}))
            claims = _b64url(_claims_json({
                "iat": now - 30,
                "exp": now + 540,
                "iss": self.app_id,
            }))
            signing_input = (header + "." + claims).encode("ascii")
            signature = key.sign(signing_input, padding.PKCS1v15(), hashes.SHA256())
            return header + "." + claims + "." + _b64url(signature)
        except GitHubAppError:
            raise
        except Exception as exc:
            raise GitHubAppError("GitHub App JWT signing failed: " + type(exc).__name__) from exc

    def _request(self, method: str, path: str, token: str, payload: dict | None = None) -> dict:
        if not path.startswith("/") or ".." in path.split("/"):
            raise GitHubAppError("Invalid GitHub API path")
        body = None if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = {
            "Accept": "application/vnd.github+json",
            "Authorization": "Bearer " + token,
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "DCP-GitHub-App-Runner-Bootstrap/1.0",
        }
        if body is not None:
            headers["Content-Type"] = "application/json"
        request = Request(self.API_ORIGIN + path, data=body, method=method, headers=headers)
        try:
            with self.opener(request, timeout=self.timeout) as response:
                raw = response.read(65537)
            if len(raw) > 65536:
                raise GitHubAppError("GitHub API response exceeded size limit")
            data = json.loads(raw.decode("utf-8")) if raw else {}
        except HTTPError as exc:
            raise GitHubAppError("GitHub API returned HTTP " + str(exc.code)) from exc
        except (URLError, TimeoutError) as exc:
            raise GitHubAppError("GitHub API request failed: " + type(exc).__name__) from exc
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise GitHubAppError("GitHub API returned malformed JSON") from exc
        if not isinstance(data, dict):
            raise GitHubAppError("GitHub API returned an invalid response shape")
        return data

    @staticmethod
    def _expiry(value: object) -> datetime:
        if not isinstance(value, str):
            raise GitHubAppError("GitHub token response omitted expiry")
        try:
            expiry = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError as exc:
            raise GitHubAppError("GitHub token expiry is invalid") from exc
        if expiry.tzinfo is None or expiry <= datetime.now(timezone.utc):
            raise GitHubAppError("GitHub token is expired or has no timezone")
        return expiry.astimezone(timezone.utc)

    def _installation_token(self, repository: str, administration: str) -> str:
        if not isinstance(repository, str) or repository not in self.allowed_repositories:
            raise GitHubAppError("Repository is not allowlisted for runner administration")
        if administration not in ("read", "write"):
            raise ValueError("Unsupported GitHub repository administration scope")
        app_jwt = self._app_jwt()
        installation = self._request(
            "POST",
            "/app/installations/{}/access_tokens".format(self.installation_id),
            app_jwt,
            {
                "repositories": [repository],
                "permissions": {"administration": administration},
            },
        )
        token = installation.get("token")
        if not isinstance(token, str) or not token:
            raise GitHubAppError("GitHub installation token was not issued")
        permissions = installation.get("permissions")
        granted = permissions.get("administration") if isinstance(permissions, dict) else None
        acceptable = ("read", "write", "admin") if administration == "read" else ("write", "admin")
        if granted not in acceptable:
            raise GitHubAppError("GitHub App installation lacks required Administration permission")
        self._expiry(installation.get("expires_at"))
        return token

    def create_registration_token(self, repository: str) -> RunnerRegistrationCredential:
        installation_token = self._installation_token(repository, "write")
        owner, name = repository.split("/", 1)
        registration = self._request(
            "POST",
            "/repos/{}/{}/actions/runners/registration-token".format(owner, name),
            installation_token,
            {},
        )
        token = registration.get("token")
        if not isinstance(token, str) or not token:
            raise GitHubAppError("GitHub runner registration token was not issued")
        expiry = self._expiry(registration.get("expires_at"))
        return RunnerRegistrationCredential(token=token, expires_at=expiry)

    def _list_runners(self, repository: str) -> list[dict]:
        token = self._installation_token(repository, "read")
        owner, name = repository.split("/", 1)
        runners = []
        for page in range(1, 11):
            data = self._request(
                "GET",
                "/repos/{}/{}/actions/runners?per_page=100&page={}".format(owner, name, page),
                token,
            )
            batch = data.get("runners")
            if not isinstance(batch, list):
                raise GitHubAppError("GitHub runner inventory response is invalid")
            runners.extend(item for item in batch if isinstance(item, dict))
            if len(batch) < 100:
                return runners
        raise GitHubAppError("GitHub runner inventory exceeded the safe pagination limit")

    def find_runner(self, repository: str, runner_name: str) -> dict | None:
        if not isinstance(runner_name, str) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,128}", runner_name):
            raise GitHubAppError("Invalid GitHub runner name")
        runners = self._list_runners(repository)
        matches = [runner for runner in runners if isinstance(runner, dict) and runner.get("name") == runner_name]
        if len(matches) > 1:
            raise GitHubAppError("GitHub returned duplicate runner names")
        if not matches:
            return None
        runner = matches[0]
        runner_id = runner.get("id")
        status = runner.get("status")
        if isinstance(runner_id, bool) or not isinstance(runner_id, int) or runner_id < 1:
            raise GitHubAppError("GitHub runner inventory omitted a valid runner ID")
        if status not in ("online", "offline"):
            raise GitHubAppError("GitHub runner inventory returned an unknown status")
        observed = runner.get("labels")
        labels = tuple(
            item["name"] for item in observed
            if isinstance(item, dict) and isinstance(item.get("name"), str)
        ) if isinstance(observed, list) else ()
        return {"id": runner_id, "name": runner_name, "status": status, "labels": labels}

    def is_runner_online(
        self, repository: str, runner_name: str, expected_labels: list[str] | tuple[str, ...]
    ) -> bool:
        if not isinstance(expected_labels, (list, tuple)):
            raise GitHubAppError("Expected runner labels must be a list or tuple")
        labels = tuple(expected_labels)
        if not labels or any(not isinstance(label, str) or not re.fullmatch(
            r"[A-Za-z0-9_.-]{1,64}", label
        ) for label in labels):
            raise GitHubAppError("Invalid expected GitHub runner labels")
        runner = self.find_runner(repository, runner_name)
        return bool(runner and runner["status"] == "online" and set(labels).issubset(set(runner["labels"])))

    def remove_runner(self, repository: str, runner_id: int) -> bool:
        if isinstance(runner_id, bool) or not isinstance(runner_id, int) or runner_id < 1:
            raise GitHubAppError("Invalid GitHub runner ID")
        owner, name = repository.split("/", 1) if repository in self.allowed_repositories else ("", "")
        if not owner:
            raise GitHubAppError("Repository is not allowlisted for runner administration")
        runners = self._list_runners(repository)
        matches = [runner for runner in runners if isinstance(runner, dict) and runner.get("id") == runner_id]
        if not matches:
            return True
        if len(matches) != 1 or matches[0].get("status") != "offline":
            raise GitHubAppError("Refusing to deregister a runner that is not confirmed offline")
        write_token = self._installation_token(repository, "write")
        self._request(
            "DELETE",
            "/repos/{}/{}/actions/runners/{}".format(owner, name, runner_id),
            write_token,
        )
        return True


class GitHubRunnerOnlineChecker:
    """Adapt provider metadata to an exact GitHub runner-online check."""

    LABELS = {
        "linux": ("self-hosted", "Linux", "X64", "dcp-cloud-linux"),
        "windows": ("self-hosted", "Windows", "X64", "dcp-cloud-windows"),
        "macos": ("self-hosted", "macOS", "ARM64", "dcp-cloud-macos"),
    }

    def __init__(self, github_app: GitHubAppRunnerBootstrap):
        self.github_app = github_app

    def __call__(self, runner_name: str, repository: str, target_os: str) -> bool:
        labels = self.LABELS.get(target_os)
        if labels is None:
            return False
        return self.github_app.is_runner_online(repository, runner_name, labels)
