"""Zero-cost, read-only diagnostics for DCP Local-first mode.

This module inspects local executable availability and Python capabilities only.
It does not start services, open ports, invoke cloud APIs, read secret values,
install packages, or provision resources.
Run: python -m tools.cloud_gateway.local_mode
"""
from __future__ import annotations

import json
import os
import platform
import shutil
import sqlite3
import sys
from pathlib import Path


def inspect_local_environment(environ=None) -> dict:
    env = os.environ if environ is None else environ
    checks = []

    def add(name: str, status: str, detail: str) -> None:
        checks.append({"check": name, "status": status, "detail": detail})

    version = sys.version_info
    python_ok = version >= (3, 10)
    add(
        "python_runtime",
        "PASS" if python_ok else "FAIL",
        f"Python {version.major}.{version.minor}.{version.micro}; requires 3.10+",
    )

    try:
        connection = sqlite3.connect(":memory:")
        connection.execute("CREATE TABLE dcp_local_probe (id INTEGER PRIMARY KEY)")
        connection.execute("INSERT INTO dcp_local_probe DEFAULT VALUES")
        row = connection.execute("SELECT count(*) FROM dcp_local_probe").fetchone()
        connection.close()
        sqlite_ok = row == (1,)
    except Exception:
        sqlite_ok = False
    add(
        "sqlite",
        "PASS" if sqlite_ok else "FAIL",
        "SQLite in-memory lifecycle storage is available"
        if sqlite_ok else "Python SQLite support is unavailable",
    )

    git = shutil.which("git")
    add("git", "PASS" if git else "UNKNOWN",
        "Git executable is available" if git else "Git is optional and was not found")

    docker = shutil.which("docker") or shutil.which("podman")
    add("container_runtime", "PASS" if docker else "UNKNOWN",
        "Docker/Podman executable is available; daemon health is not checked"
        if docker else "Docker/Podman is optional; local isolation will need another approved backend")

    add("cloud_provisioning", "SKIPPED",
        "Local-first doctor never calls Azure, Orka, or any paid provider")
    add("network_listener", "SKIPPED",
        "No ports are opened and no service is started by this diagnostic")

    # Only report whether configuration is present; never include values.
    provisioning_enabled = str(env.get("DCP_GATEWAY_PROVISIONING_ENABLED", "false")).lower() == "true"
    add("cloud_provisioning_default", "FAIL" if provisioning_enabled else "PASS",
        "Cloud provisioning is enabled in the environment; keep it disabled for local-first mode"
        if provisioning_enabled else "Cloud provisioning is disabled")

    statuses = [item["status"] for item in checks]
    overall = "FAIL" if "FAIL" in statuses else (
        "UNKNOWN" if "UNKNOWN" in statuses else "PASS"
    )
    return {
        "mode": "local-first",
        "overall": overall,
        "platform": platform.system(),
        "architecture": platform.machine(),
        "python": f"{version.major}.{version.minor}.{version.micro}",
        "checks": checks,
    }


def main() -> int:
    result = inspect_local_environment()
    print(json.dumps(result, indent=2, sort_keys=True))
    return 1 if result["overall"] == "FAIL" else 0


if __name__ == "__main__":
    raise SystemExit(main())
