"""CLI used by the DCP manual provisioning workflow."""
from __future__ import annotations

import argparse
import json
import os
import sys

from .backend import ProvisionRequest, RunnerSettings, request_provisioning


def main() -> int:
    parser = argparse.ArgumentParser(description="Request an ephemeral macOS cloud runner")
    parser.add_argument("--repository", default=os.getenv("DCP_TARGET_REPOSITORY", "phakphum12345/generated-A4-pdf"))
    parser.add_argument("--commit-sha", default=os.getenv("DCP_TARGET_COMMIT_SHA", ""))
    parser.add_argument("--ref", default=os.getenv("DCP_TARGET_REF", "refs/heads/main"))
    parser.add_argument("--run-id", type=int, default=int(os.getenv("GITHUB_RUN_ID", "0")))
    parser.add_argument("--run-attempt", type=int, default=int(os.getenv("GITHUB_RUN_ATTEMPT", "1")))
    args = parser.parse_args()
    try:
        settings = RunnerSettings.from_env()
        request = ProvisionRequest(args.repository, args.commit_sha, args.ref, args.run_id, args.run_attempt)
        result = request_provisioning(settings, request)
    except (ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps({"accepted": result.accepted, "request_id": result.request_id, "state": result.state}))
    print("Dispatch acceptance is not runner-online or build-pass evidence.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
