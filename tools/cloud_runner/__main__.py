"""CLI used by the DCP manual multi-platform runner provisioning workflow."""
from __future__ import annotations
import argparse, json, os, sys
from .backend import ProvisionRequest, RunnerSettings, request_provisioning

def main() -> int:
    parser = argparse.ArgumentParser(description="Request an ephemeral cloud runner")
    parser.add_argument("--repository", default=os.getenv("DCP_TARGET_REPOSITORY", "phakphum12345/generated-A4-pdf"))
    parser.add_argument("--commit-sha", default=os.getenv("DCP_TARGET_COMMIT_SHA", ""))
    parser.add_argument("--run-id", type=int, default=int(os.getenv("GITHUB_RUN_ID", "0")))
    parser.add_argument("--target-os", choices=("linux", "windows", "macos"), default=os.getenv("DCP_TARGET_OS", "macos"))
    args = parser.parse_args()
    try:
        result = request_provisioning(RunnerSettings.from_env(),
            ProvisionRequest(args.repository, args.commit_sha, args.run_id, args.target_os))
    except (ValueError, RuntimeError) as exc:
        print(f"::error::{exc}", file=sys.stderr)
        return 1
    print(json.dumps({"id": result.runner_id, "state": result.state, "runner_name": result.runner_name,
        "labels": list(result.labels), "detail": result.detail}))
    print("Gateway acceptance is not runner-online or build-pass evidence.")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
