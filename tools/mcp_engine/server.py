"""Local STDIO MCP adapter for DCP's read-only source inspection tools.

The workspace root is fixed at process startup via DCP_MCP_ROOT. This server
does not expose copy_apply, shell execution, network listeners, or Git writes.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from mcp.server.fastmcp import FastMCP

from .engine import (
    copy_preview as engine_copy_preview,
    diff_files as engine_diff_files,
    inspect_file as engine_inspect_file,
    read_text_file as engine_read_text_file,
)

_ROOT_VALUE = os.environ.get("DCP_MCP_ROOT", "").strip()
if not _ROOT_VALUE:
    raise RuntimeError("DCP_MCP_ROOT must point to one explicitly approved local workspace.")

WORKSPACE_ROOT = Path(_ROOT_VALUE).expanduser().resolve(strict=True)
if not WORKSPACE_ROOT.is_dir():
    raise RuntimeError("DCP_MCP_ROOT must point to an existing directory.")

mcp = FastMCP("dcp-local-readonly")


@mcp.tool()
def read_text_file(path: str) -> dict[str, Any]:
    """Read a UTF-8 text file under the configured workspace (maximum 64 KiB)."""
    return engine_read_text_file(WORKSPACE_ROOT, path)


@mcp.tool()
def inspect_file(path: str) -> dict[str, Any]:
    """Return file size, encoding and SHA-256 evidence without changing the file."""
    return engine_inspect_file(WORKSPACE_ROOT, path)


@mcp.tool()
def diff_files(left_path: str, right_path: str) -> dict[str, Any]:
    """Compare two files inside the same configured workspace; never writes."""
    return engine_diff_files(WORKSPACE_ROOT, left_path, WORKSPACE_ROOT, right_path)


@mcp.tool()
def copy_preview(source_path: str, destination_path: str) -> dict[str, Any]:
    """Preview copying to a new path inside the workspace; performs no write."""
    return engine_copy_preview(
        WORKSPACE_ROOT, source_path, WORKSPACE_ROOT, destination_path
    )


if __name__ == "__main__":
    mcp.run(transport="stdio")
