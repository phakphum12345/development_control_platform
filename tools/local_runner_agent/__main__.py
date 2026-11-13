"""DCP Runner Agent CLI: health check or one explicitly enabled job."""
from __future__ import annotations

import argparse
import json
import os
import platform
import re
import signal
import sys
import threading
from pathlib import Path

from .client import GatewayClient, RunnerAgentConfig, RunnerGatewayError
from .checkout import GitHubCommitCheckout, LocalProjectCheckout
from .execution import FlutterBuildExecutor
from .service import RunnerAgentService
from .web_build import WebBuildExecutor
from .browser_test import StaticWebPlaywrightTester
from .pipeline import RunnerPipeline
from .terminal_executor import TerminalScriptExecutor
from .workspace import WorkspaceManager
from .local_project import LocalProjectError, LocalProjectRegistry, default_registry_path
from tools.runner_agent.preflight import collect_preflight, resolve_capabilities


def _positive_int(name: str, default: int) -> int:
    raw = os.environ.get(name, str(default))
    try:
        value = int(raw)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be an integer") from exc
    if value < 1:
        raise ValueError(f"{name} must be positive")
    return value


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="DCP local Runner Agent")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument(
        "--check", action="store_true",
        help="validate Gateway connectivity only; does not claim or execute a job",
    )
    modes.add_argument(
        "--once", action="store_true",
        help="claim and process at most one job; requires explicit execution opt-in",
    )
    modes.add_argument(
        "--serve", action="store_true",
        help="run the local Runner service until Ctrl+C/SIGTERM; requires explicit execution opt-in",
    )
    modes.add_argument(
        "--enroll-only", action="store_true",
        help="register this host offline; never claim or execute jobs",
    )
    modes.add_argument(
        "--enroll-root", metavar="PATH",
        help="explicitly enroll one local directory as an allowed project root",
    )
    modes.add_argument(
        "--register-project", nargs=2, metavar=("ROOT_ID", "PATH"),
        help="register a project directory beneath an already enrolled root",
    )
    modes.add_argument(
        "--list-projects", action="store_true",
        help="list locally enrolled roots and project IDs",
    )
    args = parser.parse_args(argv)
    try:
        if args.enroll_root or args.register_project or args.list_projects:
            registry = LocalProjectRegistry(
                os.environ.get("DCP_LOCAL_PROJECT_REGISTRY", str(default_registry_path()))
            )
            if args.enroll_root:
                print(json.dumps(registry.enroll_root(args.enroll_root), indent=2, sort_keys=True))
                return 0
            if args.register_project:
                root_id, project_path = args.register_project
                print(json.dumps(
                    registry.register_project(root_id, project_path),
                    indent=2, sort_keys=True,
                ))
                return 0
            print(json.dumps({
                "roots": registry.list_roots(),
                "projects": registry.list_projects(),
            }, indent=2, sort_keys=True))
            return 0

        config = RunnerAgentConfig.from_env()
        client = GatewayClient(config)
        health = client.health()
        if health.get("status") != "ok":
            raise RunnerGatewayError("Gateway health check did not report ready")
        if args.check:
            print(json.dumps({
                "agent": "ready", "worker_id": config.worker_id,
                "gateway_status": health.get("status"),
                "mode": "control-plane-only", "job_execution_enabled": False,
            }, indent=2, sort_keys=True))
            return 0

        host_os = platform.system().lower()
        if host_os == "darwin":
            host_os = "macos"
        if host_os not in ("linux", "windows", "macos"):
            raise ValueError("unsupported Runner host operating system")
        preflight = collect_preflight()
        if preflight.get("host_os") != host_os:
            raise ValueError("Runner host preflight OS does not match this machine")
        raw_capabilities = os.environ.get("DCP_RUNNER_CAPABILITIES")
        configured_capabilities = (
            json.loads(raw_capabilities) if raw_capabilities is not None else None
        )
        capabilities = resolve_capabilities(preflight, configured_capabilities)
        playwright_enabled = os.environ.get("DCP_RUNNER_PLAYWRIGHT_ENABLED") == "1"
        if not playwright_enabled:
            if configured_capabilities is not None and "playwright" in configured_capabilities:
                raise ValueError("DCP_RUNNER_PLAYWRIGHT_ENABLED=1 is required to advertise Playwright capability")
            capabilities = [item for item in capabilities if item != "playwright"]
        elif "playwright" not in capabilities:
            raise ValueError("Playwright package and Chromium browser must pass host preflight before opt-in")

        if args.enroll_only:
            runner = client.enroll(host_os, capabilities)
            print(json.dumps({
                "agent": "enrolled",
                "worker_id": runner.get("worker_id", config.worker_id),
                "host_os": runner.get("host_os", host_os),
                "capabilities": runner.get("capabilities", capabilities),
                "state": runner.get("state", "offline"),
                "execution_enabled": False,
            }, indent=2, sort_keys=True))
            return 0

        if os.environ.get("DCP_RUNNER_EXECUTION_ENABLED") != "1":
            raise ValueError("DCP_RUNNER_EXECUTION_ENABLED=1 is required for --once or --serve")
        root = os.environ.get("DCP_RUNNER_WORKSPACE_ROOT", "").strip()
        if not root:
            root = str(default_registry_path().parent / "workspaces")
            os.environ["DCP_RUNNER_WORKSPACE_ROOT"] = root
        if not Path(root).is_absolute():
            raise ValueError("DCP_RUNNER_WORKSPACE_ROOT must be an absolute path")
        raw_repositories = json.loads(os.environ.get("DCP_RUNNER_TRUSTED_REPOSITORIES", "[]"))
        raw_local_projects = json.loads(os.environ.get("DCP_RUNNER_TRUSTED_LOCAL_PROJECTS", "[]"))
        if (not isinstance(raw_repositories, list)
                or any(not isinstance(item, str) or not item for item in raw_repositories)):
            raise ValueError("DCP_RUNNER_TRUSTED_REPOSITORIES must be a JSON string array")
        if (not isinstance(raw_local_projects, list)
                or any(not isinstance(item, str) or not re.fullmatch(
                    r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", item
                ) for item in raw_local_projects)):
            raise ValueError("DCP_RUNNER_TRUSTED_LOCAL_PROJECTS must be a JSON array of canonical project UUIDs")
        if not raw_repositories and not raw_local_projects:
            raise ValueError("configure at least one trusted GitHub repository or Local Project ID")
        terminal_enabled = os.environ.get("DCP_RUNNER_TERMINAL_ENABLED") == "1"
        if terminal_enabled:
            if not raw_local_projects:
                raise ValueError("Terminal capability requires at least one trusted Local Project ID")
            capabilities = sorted(set(capabilities) | {"terminal"})
        manager = WorkspaceManager(
            root,
            max_active=_positive_int("DCP_RUNNER_MAX_ACTIVE_WORKSPACES", 8),
            max_workspace_bytes=_positive_int(
                "DCP_RUNNER_MAX_WORKSPACE_BYTES", 2 * 1024 * 1024 * 1024
            ),
        )
        checkout = GitHubCommitCheckout(
            manager, token=os.environ.get("DCP_GITHUB_TOKEN") or None,
            max_archive_bytes=_positive_int("DCP_RUNNER_MAX_ARCHIVE_BYTES", 100 * 1024 * 1024),
            max_expanded_bytes=_positive_int(
                "DCP_RUNNER_MAX_EXPANDED_BYTES", 1024 * 1024 * 1024
            ),
        )
        local_project_checkout = None
        if raw_local_projects:
            local_registry = LocalProjectRegistry(
                os.environ.get("DCP_LOCAL_PROJECT_REGISTRY", str(default_registry_path()))
            )
            local_project_checkout = LocalProjectCheckout(
                manager, local_registry,
                max_bytes=_positive_int("DCP_RUNNER_MAX_LOCAL_PROJECT_BYTES", 2 * 1024 * 1024 * 1024),
            )
        executor = FlutterBuildExecutor(
            manager, enabled=True,
            timeout_seconds=_positive_int("DCP_RUNNER_BUILD_TIMEOUT_SECONDS", 1800),
            max_output_bytes=_positive_int(
                "DCP_RUNNER_MAX_OUTPUT_BYTES", 5 * 1024 * 1024
            ),
        )
        pipeline = RunnerPipeline(
            client, manager, checkout, executor,
            trusted_repositories=frozenset(raw_repositories),
            worker_os=host_os,
            capabilities=frozenset(capabilities),
            web_executor=WebBuildExecutor(
                manager, enabled=True,
                timeout_seconds=_positive_int("DCP_RUNNER_BUILD_TIMEOUT_SECONDS", 1800),
                max_output_bytes=_positive_int("DCP_RUNNER_MAX_OUTPUT_BYTES", 5 * 1024 * 1024),
            ),
            local_project_checkout=local_project_checkout,
            trusted_local_projects=frozenset(raw_local_projects),
            browser_test_executor=(
                StaticWebPlaywrightTester(
                    manager, enabled=True,
                    timeout_ms=_positive_int("DCP_RUNNER_PLAYWRIGHT_TIMEOUT_MS", 15000),
                ) if playwright_enabled else None
            ),
            terminal_executor=TerminalScriptExecutor(
                enabled=terminal_enabled,
                timeout_ceiling_seconds=_positive_int("DCP_RUNNER_TERMINAL_TIMEOUT_SECONDS", 60),
                output_ceiling_bytes=_positive_int("DCP_RUNNER_TERMINAL_OUTPUT_BYTES", 1024 * 1024),
            ),
        )
        if args.serve:
            poll_interval = _positive_int("DCP_RUNNER_POLL_INTERVAL_SECONDS", 5)
            max_backoff = _positive_int("DCP_RUNNER_MAX_BACKOFF_SECONDS", 60)
            if poll_interval > 60:
                raise ValueError("DCP_RUNNER_POLL_INTERVAL_SECONDS must not exceed 60")
            if max_backoff > 300:
                raise ValueError("DCP_RUNNER_MAX_BACKOFF_SECONDS must not exceed 300")
            stop_event = threading.Event()
            previous_handlers = {}

            def request_stop(_signum, _frame):
                stop_event.set()

            for signum in (signal.SIGINT, signal.SIGTERM):
                previous_handlers[signum] = signal.getsignal(signum)
                signal.signal(signum, request_stop)
            try:
                summary = RunnerAgentService(
                    pipeline,
                    poll_interval_seconds=poll_interval,
                    max_backoff_seconds=max_backoff,
                ).run(stop_event)
            finally:
                for signum, previous in previous_handlers.items():
                    signal.signal(signum, previous)
            print(json.dumps({
                "agent": "stopped" if summary["stopped"] else "not_ready",
                "worker_id": config.worker_id,
                **summary,
            }, indent=2, sort_keys=True))
            return 0 if summary["stopped"] else 1

        result = pipeline.run_once()
        if result is None:
            print(json.dumps({"agent": "idle", "worker_id": config.worker_id}))
            return 0
        job = result.get("job", {})
        summary = {
            "agent": "completed" if result.get("outcome") == "succeeded" else result.get("outcome"),
            "job_id": job.get("id", result.get("job_id")),
            "job_state": job.get("state"),
            "error": result.get("error"),
        }
        print(json.dumps(summary, indent=2, sort_keys=True))
        return 0 if result.get("outcome") == "succeeded" else 1
    except (ValueError, RunnerGatewayError, LocalProjectError) as exc:
        print(json.dumps({"agent": "not_ready", "error": str(exc)}), file=sys.stderr)
        return 1
    except Exception as exc:
        # Never print arbitrary exception text; it may contain request or credential data.
        print(json.dumps({"agent": "failed", "error": type(exc).__name__}), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
