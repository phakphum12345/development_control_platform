"""Native, local-first source inspection and copy-preview engine.

This module is deliberately independent of third-party MCP servers. It exposes
small functions that a future MCP adapter can call after applying authorization.
"""
from __future__ import annotations

import argparse
import difflib
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any

MAX_FILE_BYTES = 2 * 1024 * 1024


class EngineError(ValueError):
    """A safe, user-correctable engine error."""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _rooted_file(root: str | Path, relative_path: str) -> tuple[Path, Path]:
    base = Path(root).expanduser().resolve(strict=True)
    if not base.is_dir():
        raise EngineError("Root must be an existing directory.")
    candidate_input = Path(relative_path)
    if candidate_input.is_absolute():
        raise EngineError("Use a relative path inside the configured root.")
    candidate = (base / candidate_input).resolve(strict=True)
    try:
        candidate.relative_to(base)
    except ValueError as exc:
        raise EngineError("Path escapes the configured root.") from exc
    if not candidate.is_file():
        raise EngineError("Path must identify an existing regular file.")
    if candidate.stat().st_size > MAX_FILE_BYTES:
        raise EngineError(f"File exceeds the {MAX_FILE_BYTES}-byte inspection limit.")
    return base, candidate


def inspect_file(root: str | Path, relative_path: str) -> dict[str, Any]:
    base, path = _rooted_file(root, relative_path)
    return {
        "status": "PASS",
        "root": str(base),
        "path": path.relative_to(base).as_posix(),
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
        "encoding": "utf-8" if _is_utf8(path) else "binary-or-non-utf8",
        "operation": "READ_ONLY",
    }


def _is_utf8(path: Path) -> bool:
    try:
        path.read_text(encoding="utf-8")
        return True
    except UnicodeDecodeError:
        return False


def diff_files(
    left_root: str | Path, left_path: str,
    right_root: str | Path, right_path: str,
) -> dict[str, Any]:
    left_base, left = _rooted_file(left_root, left_path)
    right_base, right = _rooted_file(right_root, right_path)
    left_hash, right_hash = sha256_file(left), sha256_file(right)
    result: dict[str, Any] = {
        "status": "PASS",
        "left": {"root": str(left_base), "path": left.relative_to(left_base).as_posix(), "sha256": left_hash},
        "right": {"root": str(right_base), "path": right.relative_to(right_base).as_posix(), "sha256": right_hash},
        "equal": left_hash == right_hash,
        "operation": "READ_ONLY",
    }
    try:
        left_lines = left.read_text(encoding="utf-8").splitlines(keepends=True)
        right_lines = right.read_text(encoding="utf-8").splitlines(keepends=True)
    except UnicodeDecodeError:
        result["diff_type"] = "binary"
        result["diff"] = None
        return result
    result["diff_type"] = "unified"
    result["diff"] = "".join(difflib.unified_diff(
        left_lines, right_lines,
        fromfile=f"a/{left.relative_to(left_base).as_posix()}",
        tofile=f"b/{right.relative_to(right_base).as_posix()}",
    ))
    return result


def copy_preview(source_root: str | Path, source_path: str,
                 destination_root: str | Path, destination_path: str) -> dict[str, Any]:
    source_base, source = _rooted_file(source_root, source_path)
    destination_base = Path(destination_root).expanduser().resolve(strict=True)
    if not destination_base.is_dir():
        raise EngineError("Destination root must be an existing directory.")
    rel = Path(destination_path)
    if rel.is_absolute() or not rel.parts or any(part in ("..", ".") for part in rel.parts):
        raise EngineError("Destination must be a clean relative path inside destination root.")
    target = (destination_base / rel).resolve(strict=False)
    try:
        target.relative_to(destination_base)
    except ValueError as exc:
        raise EngineError("Destination escapes the configured root.") from exc
    if target.exists():
        raise EngineError("Destination already exists; overwrite is not supported.")
    return {
        "status": "PASS",
        "operation": "COPY_PREVIEW_ONLY",
        "source": str(source),
        "source_sha256": sha256_file(source),
        "destination": str(target),
        "destination_exists": False,
        "writes_performed": False,
        "approval_required_for_apply": True,
    }


def copy_apply(source_root: str | Path, source_path: str,
               destination_root: str | Path, destination_path: str) -> dict[str, Any]:
    """Copy to a new destination only; never overwrite existing data."""
    preview = copy_preview(source_root, source_path, destination_root, destination_path)
    target = Path(preview["destination"])
    # Re-check destination immediately before writing. No overwrite path exists.
    if target.exists():
        raise EngineError("Destination appeared after preview; refusing to overwrite.")
    target.parent.mkdir(parents=True, exist_ok=True)
    # Exclusive creation protects against accidental replacement of an existing file.
    source = Path(preview["source"])
    try:
        with source.open("rb") as src, target.open("xb") as dst:
            shutil.copyfileobj(src, dst, length=64 * 1024)
    except Exception:
        try:
            target.unlink(missing_ok=True)
        except OSError:
            pass
        raise
    copied_hash = sha256_file(target)
    if copied_hash != preview["source_sha256"]:
        target.unlink(missing_ok=True)
        raise EngineError("Post-copy SHA-256 mismatch; destination was removed.")
    return {
        **preview,
        "operation": "COPY_APPLIED",
        "writes_performed": True,
        "destination_sha256": copied_hash,
        "status": "PASS",
    }


def _emit(value: dict[str, Any]) -> None:
    print(json.dumps(value, ensure_ascii=False, indent=2))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="DCP native source inspection engine")
    sub = parser.add_subparsers(dest="command", required=True)
    inspect_cmd = sub.add_parser("inspect")
    inspect_cmd.add_argument("--root", required=True)
    inspect_cmd.add_argument("--path", required=True)
    diff_cmd = sub.add_parser("diff")
    diff_cmd.add_argument("--left-root", required=True)
    diff_cmd.add_argument("--left-path", required=True)
    diff_cmd.add_argument("--right-root", required=True)
    diff_cmd.add_argument("--right-path", required=True)
    preview_cmd = sub.add_parser("copy-preview")
    for command in (preview_cmd,):
        command.add_argument("--source-root", required=True)
        command.add_argument("--source-path", required=True)
        command.add_argument("--destination-root", required=True)
        command.add_argument("--destination-path", required=True)
    apply_cmd = sub.add_parser("copy-apply", help="Copy to a new path; existing files are never overwritten")
    apply_cmd.add_argument("--source-root", required=True)
    apply_cmd.add_argument("--source-path", required=True)
    apply_cmd.add_argument("--destination-root", required=True)
    apply_cmd.add_argument("--destination-path", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "inspect":
            result = inspect_file(args.root, args.path)
        elif args.command == "diff":
            result = diff_files(args.left_root, args.left_path, args.right_root, args.right_path)
        elif args.command == "copy-preview":
            result = copy_preview(args.source_root, args.source_path, args.destination_root, args.destination_path)
        else:
            result = copy_apply(args.source_root, args.source_path, args.destination_root, args.destination_path)
        _emit(result)
        return 0
    except (EngineError, OSError) as exc:
        _emit({"status": "FAIL", "error": str(exc), "writes_performed": False})
        return 2


if __name__ == "__main__":
    sys.exit(main())
