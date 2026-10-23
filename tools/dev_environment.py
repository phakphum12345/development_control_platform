#!/usr/bin/env python3
"""Read-only local development and emulator discovery for Development Control Platform."""
from __future__ import annotations
import argparse
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def _sdk_candidates() -> list[Path]:
    values = [os.environ.get("ANDROID_SDK_ROOT"), os.environ.get("ANDROID_HOME")]
    home = Path.home()
    if sys.platform == "win32":
        values.append(str(home / "AppData" / "Local" / "Android" / "Sdk"))
    elif sys.platform == "darwin":
        values.append(str(home / "Library" / "Android" / "sdk"))
    else:
        values.append(str(home / "Android" / "Sdk"))
    result: list[Path] = []
    for value in values:
        if value:
            path = Path(value).expanduser()
            if path not in result:
                result.append(path)
    return result


def _find_tool(name: str, sdk_suffix: str | None = None) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    if sdk_suffix:
        for sdk in _sdk_candidates():
            suffix = sdk_suffix + (".exe" if sys.platform == "win32" else "")
            candidate = sdk / suffix
            if candidate.is_file():
                return str(candidate)
    return None


def _run(args: list[str], timeout: int = 20) -> dict[str, Any]:
    try:
        completed = subprocess.run(args, capture_output=True, text=True, timeout=timeout, check=False)
        return {"command": args, "exit_code": completed.returncode, "stdout": completed.stdout.strip(),
                "stderr": completed.stderr.strip(), "status": "pass" if completed.returncode == 0 else "fail"}
    except subprocess.TimeoutExpired:
        return {"command": args, "status": "unknown", "error": f"Timed out after {timeout}s"}
    except OSError as exc:
        return {"command": args, "status": "unknown", "error": str(exc)}


def _tool_inventory() -> dict[str, str | None]:
    return {
        "python": sys.executable, "node": shutil.which("node"), "npm": shutil.which("npm"),
        "vscode": shutil.which("code"), "flutter": shutil.which("flutter"),
        "adb": _find_tool("adb", "platform-tools/adb"),
        "android_emulator": _find_tool("emulator", "emulator/emulator"),
        "xcrun": shutil.which("xcrun") if sys.platform == "darwin" else None,
    }


def status() -> dict[str, Any]:
    tools = _tool_inventory()
    missing = [name for name, path in tools.items() if not path and name != "xcrun"]
    return {"schema_version": 1, "command": "status", "platform": platform.platform(),
            "python_version": platform.python_version(), "tools": tools,
            "available_count": sum(bool(path) for path in tools.values()), "missing_tools": missing,
            "status": "pass" if not missing else "unknown",
            "notes": ["UNKNOWN means a tool is not discoverable; it is not proof the tool is unnecessary.",
                      "No SDK installation, PATH mutation, credential access, or project modification is performed."]}


def devices() -> dict[str, Any]:
    checks: dict[str, Any] = {}
    flutter = shutil.which("flutter")
    adb = _find_tool("adb", "platform-tools/adb")
    checks["flutter_devices"] = _run([flutter, "devices", "--machine"], timeout=45) if flutter else {
        "status": "unknown", "error": "Flutter CLI not found"}
    checks["adb_devices"] = _run([adb, "devices", "-l"]) if adb else {
        "status": "unknown", "error": "Android Debug Bridge not found"}
    overall = "pass" if any(item.get("status") == "pass" for item in checks.values()) else "unknown"
    return {"schema_version": 1, "command": "devices", "status": overall, "checks": checks}


def avds() -> dict[str, Any]:
    emulator = _find_tool("emulator", "emulator/emulator")
    if not emulator:
        return {"schema_version": 1, "command": "avds", "status": "unknown", "avds": [],
                "error": "Android emulator executable not found"}
    probe = _run([emulator, "-list-avds"])
    names = [line.strip() for line in probe.get("stdout", "").splitlines() if line.strip()]
    return {"schema_version": 1, "command": "avds", "status": probe["status"], "avds": names, "probe": probe}


def launch_avd(name: str) -> dict[str, Any]:
    if not name or name.strip() != name or name.startswith("-") or any(c in name for c in "\\/") or chr(0) in name:
        return {"schema_version": 1, "command": "launch-avd", "status": "fail", "error": "Invalid AVD name"}
    available = avds()
    if available["status"] != "pass":
        return {"schema_version": 1, "command": "launch-avd", "status": "unknown",
                "error": "Could not verify installed AVDs", "avd_probe": available}
    if name not in available["avds"]:
        return {"schema_version": 1, "command": "launch-avd", "status": "fail",
                "error": "AVD name is not in the installed AVD list", "available_avds": available["avds"]}
    emulator = _find_tool("emulator", "emulator/emulator")
    assert emulator is not None
    try:
        process = subprocess.Popen([emulator, "-avd", name], stdin=subprocess.DEVNULL,
                                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, shell=False)
    except OSError as exc:
        return {"schema_version": 1, "command": "launch-avd", "status": "fail", "error": str(exc)}
    return {"schema_version": 1, "command": "launch-avd", "status": "pass", "avd": name, "pid": process.pid,
            "note": "Emulator process started locally. App installation, boot completion, and app tests are not implied."}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("status", "devices", "avds", "launch-avd"))
    parser.add_argument("--name", help="Exact installed Android Virtual Device name for launch-avd")
    args = parser.parse_args()
    if args.command == "launch-avd" and not args.name:
        parser.error("launch-avd requires --name")
    result: dict[str, Any]
    if args.command == "status":
        result = status()
    elif args.command == "devices":
        result = devices()
    elif args.command == "avds":
        result = avds()
    else:
        result = launch_avd(args.name)
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result.get("status") == "pass" else (1 if result.get("status") == "fail" else 2)


if __name__ == "__main__":
    raise SystemExit(main())
