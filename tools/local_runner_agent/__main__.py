"""Safe Runner Agent CLI: validates Gateway connectivity only; no job execution."""
from __future__ import annotations

import argparse
import json
import sys

from .client import GatewayClient, RunnerAgentConfig, RunnerGatewayError


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the DCP Runner Agent control-plane connection (no job execution)"
    )
    parser.add_argument(
        "--check", action="store_true", required=True,
        help="validate configuration and read Gateway health; does not claim or execute jobs",
    )
    args = parser.parse_args(argv)
    if not args.check:
        parser.error("--check is required")
    try:
        config = RunnerAgentConfig.from_env()
        health = GatewayClient(config).health()
    except (ValueError, RunnerGatewayError) as exc:
        print(json.dumps({"agent": "not_ready", "error": str(exc)}), file=sys.stderr)
        return 1
    result = {
        "agent": "ready",
        "worker_id": config.worker_id,
        "gateway_status": health.get("status", "unknown"),
        "provisioning_enabled": health.get("provisioning_enabled"),
        "mode": "control-plane-only",
        "job_execution_enabled": False,
    }
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0 if health.get("status") == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
