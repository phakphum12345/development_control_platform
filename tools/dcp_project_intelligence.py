"""Command-line interface for DCP project intelligence."""
from __future__ import annotations
import argparse
import json
import sys
from pathlib import Path

try:
    from tools.project_intelligence import DiscoveryError, discover_project
except ModuleNotFoundError:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.project_intelligence import DiscoveryError, discover_project


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workspace", help="Existing local project directory to inspect")
    parser.add_argument("--task", default="", help="Optional task description to classify")
    parser.add_argument("--max-files", type=int, default=20_000)
    args = parser.parse_args()
    try:
        result = discover_project(args.workspace, args.task, args.max_files)
    except (DiscoveryError, OSError, ValueError) as exc:
        print(json.dumps({"schema_version": 1, "status": "fail", "error": str(exc)}, ensure_ascii=False))
        return 1
    print(json.dumps(result, indent=2, ensure_ascii=False))
    return 0 if result["status"] == "pass" else 2


if __name__ == "__main__":
    raise SystemExit(main())
