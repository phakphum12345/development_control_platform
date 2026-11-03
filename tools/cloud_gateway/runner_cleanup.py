"""Idempotent GitHub runner cleanup after provider deletion is confirmed."""
from .github_app import GitHubAppError


class GitHubRunnerCleanup:
    def __init__(self, github_app):
        self.github_app = github_app

    def __call__(self, row: dict, provider_state) -> str:
        if getattr(provider_state, "state", None) not in ("terminated", "failed"):
            raise GitHubAppError("Provider deletion is not confirmed")
        repository = row.get("repository")
        runner_name = row.get("provider_id")
        if not isinstance(repository, str) or not isinstance(runner_name, str):
            raise GitHubAppError("Runner cleanup record is missing repository identity")
        runner = self.github_app.find_runner(repository, runner_name)
        if runner is None:
            return "already_absent"
        if runner["status"] != "offline":
            raise GitHubAppError("Refusing cleanup until the GitHub runner is offline")
        self.github_app.remove_runner(repository, runner["id"])
        remaining = self.github_app.find_runner(repository, runner_name)
        if remaining is not None:
            raise GitHubAppError("GitHub runner deregistration is not yet confirmed")
        return "removed"
