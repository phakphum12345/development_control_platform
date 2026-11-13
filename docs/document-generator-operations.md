# Document Generator and Local Write Workflow

**Status:** Local document writer implemented; dashboard generator is export-only until an authenticated local/server adapter is integrated.

## Dashboard one-click generator

Open `dashboard/index.html` and select **Document Generator**.

Supported outputs:
- Markdown: `.md`
- Roadmap: `-ROADMAP.md`
- Plain text: `.txt`

The generator assembles a complete structured artifact from the entered project, purpose, verified context, milestones, and risks/acceptance criteria. Missing information is explicitly marked `TBD` or `UNKNOWN`. It performs a basic credential-pattern check, produces a preview, computes SHA-256 where Web Crypto is available, and requests a browser download from the same click.

**Important:** Static browser downloads cannot confirm that the user saved the file, read it back from disk, or wrote it into a Git repository. Those states remain `UNKNOWN`. Do not treat the generated hash as proof of repository persistence.

## Local scoped writer

The Python library is `tools.document_workflow.writer.write_document`. It:
- accepts only `.md` and `.txt` paths;
- requires an explicit project ID and granted path prefixes;
- rejects absolute paths, traversal, symlinks, unsupported extensions, and paths outside scope;
- requires the expected current SHA-256 to replace an existing file;
- stores operation state in an SQLite journal outside the workspace;
- uses an idempotency key and SQLite write lock to serialize writers;
- stages content in the target directory, atomically replaces the target, then reads it back and compares SHA-256;
- reconciles a retry when the desired content reached disk but the process stopped before the journal commit.

Example:

```python
from tools.document_workflow import write_document

result = write_document(
    workspace_root="/approved/workspace",
    journal_path="/var/lib/dcp/document-operations.sqlite3",
    project_id="project-alpha",
    relative_path="docs/ROADMAP.md",
    content="# Roadmap\n\n- Status: UNKNOWN\n",
    operation_key="roadmap-run-20261113-0001",
    allowed_paths=["docs"],
    expected_sha256=None,  # New file only; updates require the current file SHA-256.
)
print(result)
```

For an existing file, fetch and verify its current SHA-256 and pass that exact digest as `expected_sha256`. A stale digest is rejected. Reusing an operation key with different content or target is rejected.

The operation journal must be outside the approved workspace so it cannot be accidentally committed with generated documents. Parent directories must already exist. The local writer does not create Git commits, push branches, open/close/merge PRs, run repository code, or expose a network listener.

## Timeout and connection behavior

Dashboard GitHub API calls are read-only GET requests. They use a 12-second per-attempt timeout and up to three attempts for network errors, timeouts, HTTP 429, and HTTP 5xx, with bounded backoff and Retry-After handling. Non-retryable permission/validation errors fail immediately. A lost response is never interpreted as success.

The local writer is synchronous and local. Its SQLite journal and idempotency key support safe retry/reconciliation around interrupted writes. A server-side queue, heartbeats, cancellation, cross-process worker lease, and authenticated reconnect/resume API are not yet implemented.

## Verification boundary

A local writer result of `PASS` means that the exact local target was read back and its SHA-256 matched the intended bytes. It does not prove GitHub persistence or PR/CI/merge status. The dashboard export path remains `UNKNOWN` for disk read-back. Remote PR lifecycle checkpoints must be implemented in a provider adapter before they can be automated.
