# DCP Native MCP Integration Engine

**Status:** prototype core; not yet a production MCP server.

## Ownership and boundaries

The engine core is implemented in this repository. It does not import or require
`remote-mcp-functions-python` at runtime. That repository and Research OS /
Drive-letter are integration targets and architecture references, not trusted
execution authorities.

The initial core provides:

- bounded local file inspection with SHA-256 evidence;
- unified text diff, with binary files represented as metadata only;
- copy preview that performs no writes;
- explicit copy apply to a new destination only, with post-copy SHA-256 verification;
- path-root confinement, a 2 MiB per-file limit, and refusal to overwrite existing files.

## CLI

From the repository root:

```powershell
python -m tools.mcp_engine.engine inspect --root . --path README.md
python -m tools.mcp_engine.engine diff --left-root . --left-path README.md --right-root ..\Drive-letter --right-path README.md
python -m tools.mcp_engine.engine copy-preview --source-root . --source-path README.md --destination-root ..\Drive-letter --destination-path README-copy-preview.md
```

The copy preview command is read-only. `copy-apply` is an explicit local write and
must only be used after reviewing the preview and selecting a new destination.
Existing destinations are refused; automatic overwrite and automatic merge are
not supported.

## Evidence contract

Each command emits JSON with a status and operation label. SHA-256 identifies the
exact inspected bytes, not whether the content is correct or safe. A PASS means
only that this operation completed under its stated checks; it does not prove
CI, repository policy, authentication, authorization, or release readiness.

## Planned adapter boundary

A future MCP protocol adapter may expose narrowly scoped tools such as
`inspect_file`, `diff_files`, and `copy_preview`. The adapter must validate
input schemas, apply server-side authorization, constrain configured roots,
enforce request/time/output limits, redact secrets from logs, and default to
read-only. A write-capable tool must be separately enabled and require explicit
approval; client-side controls are not authorization.

## Current limitations

- This is a Python library/CLI core, **not yet an MCP wire-protocol server**.
- No remote listener, authentication, authorization service, repository sync,
  Research OS API integration, or durable audit database is implemented here.
- No tests have been executed by this GitHub file-creation workflow. Run
  `python -m unittest tests.test_native_mcp_engine -v` locally and inspect CI
  for the exact commit SHA before describing the tests as passing.
- No branch has been merged and no deployment has been performed.
