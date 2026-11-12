# DCP Local Folder Snapshot Build

## Supported workflow

1. Owner enrolls an approved local root and registers a project through the Local Project Registry CLI.
2. Dashboard lists opaque project IDs, relative paths, snapshot SHA-256, and static framework detection. Absolute host paths are never returned.
3. Owner selects the registered snapshot and queues a supported `build_static_web` or explicitly enabled `test_static_web` job.
4. Gateway refreshes the registry fingerprint and rejects a stale selection with HTTP 409.
5. Runner revalidates the exact SHA-256, materializes a read-only snapshot, then creates a separate writable build copy.
6. Runner executes only after `DCP_RUNNER_EXECUTION_ENABLED=1` and the project ID is in `DCP_RUNNER_TRUSTED_LOCAL_PROJECTS`.
7. Successful static builds retain the workspace for the bounded preview lifecycle; all other jobs clean up normally.

## Runner configuration

- `DCP_RUNNER_WORKSPACE_ROOT`: the same absolute path used by Gateway and Runner Agent.
- `DCP_LOCAL_PROJECT_REGISTRY`: registry file shared by Gateway and Runner Agent; default is `%LOCALAPPDATA%/DCP/local-projects.json` on Windows.
- `DCP_RUNNER_TRUSTED_LOCAL_PROJECTS`: JSON array of canonical project UUIDs explicitly trusted for execution, for example `["12345678-1234-4234-8234-123456789abc"]`.
- `DCP_RUNNER_EXECUTION_ENABLED=1`: existing global execution opt-in remains required.
- `DCP_RUNNER_MAX_LOCAL_PROJECT_BYTES`: maximum writable-copy size; defaults to 2 GiB, with workspace quota enforcement still applied.

Import/registration alone does not add a project to the Runner trust allowlist and does not execute source code.

## Current build scope

Local Folder jobs currently support dependency-free `Static HTML/CSS/JS` projects only, using `build_static_web` and the separately opt-in `test_static_web` target. The latter requires both `web` and `playwright` Runner capabilities plus `DCP_RUNNER_PLAYWRIGHT_ENABLED=1`. React/Vite and other dependency-managed projects may be detected, but are not queueable from Local Folder yet: `node_modules` is intentionally excluded and no dependency installation is performed automatically. A later dependency-management phase must add explicit, owner-approved dependency preparation before those targets can be enabled.

## Snapshot and secret handling

- Snapshot identity is SHA-256 over included relative paths, sizes, and file contents.
- The registry revalidates the source before and after materialization; changed or moved projects fail closed.
- Symlinks, junctions, special files, path traversal, oversized snapshots, and changed files are rejected.
- The snapshot is read-only. The build receives a separate writable copy; the two trees are integrity-checked before build.
- Credential and private-data exclusions include `.env` and `.env.*` (except `.env.example`, `.env.sample`, `.env.template`), `.npmrc`, `.pypirc`, `.netrc`, SSH keys/config, service-account JSON, private credential directories, private-key/certificate bundles, database files, logs, backups, Terraform state, and secret files.
- Environment values must be provided through an explicit future environment-profile feature; secret files are not copied into build output.

## Job API source metadata

Local jobs expose `source_type=local_folder`, `source_id=<project UUID>`, and `source_sha256=<64-hex snapshot digest>`. The legacy repository/commit database columns contain internal compatibility identifiers for these jobs; the dashboard displays the real snapshot SHA-256 and does not label the internal compatibility value as a Git commit.

## Limitations

- Local Folder source execution is still subject to the Runner host's OS isolation limits. Workspace separation is not an OS sandbox.
- No automatic npm/pip/pub dependency installation, arbitrary project scripts, dev server, cloud runner, VM, or deployment fallback is enabled.
- Local Folder currently builds static HTML/CSS/JS only; unknown or unsupported frameworks remain UNKNOWN/unsupported.


## Acceptance evidence still required

- Execute the supported workflow on a real Windows host using the documented launcher and a disposable, explicitly trusted static project.
- Verify the completed artifact's SHA-256 from both upload metadata and authenticated download; verify unauthorized download denial.
- Exercise preview through the authenticated Dashboard path and verify stop/expiry cleanup.
- Force Runner interruption and confirm workspace reconciliation removes only the interrupted job's owned workspace.
