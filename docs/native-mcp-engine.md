# DCP Native MCP Integration Engine

**Status:** local stdio MCP adapter implemented; local-only prototype, not a remote service.

## Ownership and boundaries

The engine and protocol adapter are implemented in this repository. The adapter
uses the pinned MCP Python SDK in `requirements-mcp.txt`. It does not depend on
a third-party MCP server repository.

The adapter exposes exactly four tools:

- `read_text_file` — read UTF-8 text from the configured workspace, capped at 64 KiB;
- `inspect_file` — return bounded file metadata and SHA-256;
- `diff_files` — compare two files inside the same configured workspace;
- `copy_preview` — preview a copy to a new path without writing anything.

The MCP adapter deliberately does **not** expose `copy_apply`, shell execution,
Git operations, arbitrary network access, repository mutation, or a network
listener. It uses STDIO and one fixed workspace root configured at process
startup with `DCP_MCP_ROOT`. Relative paths are confined to that root. The
engine retains its 2 MiB file-inspection ceiling; text returned to a model is
limited to 64 KiB per call.

## Install the optional adapter dependency

From the repository root:

```powershell
python -m pip install -r requirements-mcp.txt
python -m unittest tests.test_native_mcp_engine tests.test_native_mcp_server -v
```

The SDK is pinned to `mcp==1.30.0` because this adapter uses the v1
`mcp.server.fastmcp.FastMCP` API. Do not silently upgrade to MCP SDK v2 without
migrating and testing the adapter.

## Codex configuration

Register this server in the local Codex configuration alongside the separately
configured `ollama_local` server. Use the Python interpreter where
`requirements-mcp.txt` was installed, and set both environment values to the
absolute local repository path:

```toml
[mcp_servers.dcp_local]
command = "C:/Path/To/Python/python.exe"
args = ["-m", "tools.mcp_engine.server"]
env = { DCP_MCP_ROOT = "C:/Path/To/development_control_platform", PYTHONPATH = "C:/Path/To/development_control_platform" }
```

Restart Codex after changing its MCP configuration. Verify that the tools
listed by `dcp_local` are exactly the four read-only tools above.

## Using DCP with Ollama Local

Codex is the MCP host/orchestrator. It can call `dcp_local.read_text_file` or
`dcp_local.diff_files`, then pass the bounded result to
`ollama_local.generate` for local analysis. The DCP server does not start
Ollama, call a cloud model, or proxy model traffic. The Ollama MCP server
remains a separate local process and retains its own model allowlist.

A recommended review sequence is:

1. Read a file through `dcp_local.read_text_file`.
2. Record its SHA-256 using `dcp_local.inspect_file`.
3. Ask `ollama_local.generate` to analyze the supplied text, explicitly
   requiring findings to distinguish evidence from inference.
4. Re-inspect the file and compare SHA-256 before/after to confirm the review
   did not change the source.
5. Treat model output as advisory; tests, CI, source review, and human approval
   remain authoritative.

## Dashboard boundary

The DCP Dashboard is a static browser application. It does not host MCP
servers, does not have a backend capable of invoking local STDIO processes, and
is not directly connected to Ollama by this adapter. The integration described
here is available to the local Codex Desktop/CLI MCP host. A future dashboard
integration would require a separately reviewed local service and browser
security design; this change does not add one.

## Existing CLI

From the repository root:

```powershell
python -m tools.mcp_engine.engine inspect --root . --path README.md
python -m tools.mcp_engine.engine diff --left-root . --left-path README.md --right-root ..\\Drive-letter --right-path README.md
python -m tools.mcp_engine.engine copy-preview --source-root . --source-path README.md --destination-root ..\\Drive-letter --destination-path README-copy-preview.md
```

The CLI also retains an explicit `copy-apply` operation for a new destination
only. That write operation is not exposed through the MCP server and must not be
invoked by the read-only integration.

## Evidence contract

Each engine command emits JSON with a status and operation label. SHA-256
identifies the exact inspected bytes, not whether the content is correct or
safe. A PASS means only that this operation completed under its stated checks;
it does not prove CI, repository policy, authentication, authorization, or
release readiness.

The MCP protocol tests exercise a real local STDIO handshake, the exposed tool
set, bounded text reading, path confinement, and copy-preview non-mutation.
They do not prove model correctness or production readiness.

## Current limitations

- The adapter is local STDIO only; no remote listener or web API is implemented.
- No dashboard integration, authentication service, authorization service,
  repository sync, Research OS API integration, or durable audit database is
  implemented here.
- MCP tools are read-only. A future write-capable tool requires a separately
  reviewed design, server-side authorization, explicit user approval, and
  additional tests.
- Model output is advisory and must never be treated as CI or release evidence.
