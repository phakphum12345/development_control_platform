# DCP Terminal Studio — Local Runner Setup

## Purpose

The Dashboard never launches a shell. It submits a typed request for a fixed built-in template. The Gateway issues a short-lived one-time authorization grant, and the local DCP Runner independently checks its credential, active Job lease, grant, Project ID, Workspace ID and snapshot before executing.

The Runner is the app-owned execution component. It is not a third-party shell service.

## Preconditions

1. The Project is enrolled in the Local Project Registry and has a stable Project ID and Workspace ID.
2. The Gateway and Runner resolve the same Local Project Registry and the same Project Workspace snapshot.
3. The local Runner runs under a dedicated, least-privileged operating-system account. Do not run it as Administrator/root for normal Terminal jobs.
4. The Runner has a valid Gateway URL and Runner credential through the existing DCP Runner configuration. Do not put credentials in this document, Dashboard fields, project scripts or command parameters.

Use the existing registry commands when a project still needs to be enrolled:

```powershell
python -m tools.local_runner_agent --enroll-root "<APPROVED_PROJECTS_ROOT>"
python -m tools.local_runner_agent --register-project "<ROOT_ID>" "<PROJECT_PATH>"
python -m tools.local_runner_agent --list-projects
```

Copy the exact Project UUID from the local registry output into the trusted-project setting below. Do not invent or reuse an ID from another machine.

## Explicit Terminal opt-in (PowerShell)

Set these variables in the Runner service's protected environment. Replace the placeholders with the actual registered Project UUID and a local absolute workspace scratch directory.

```powershell
$env:DCP_RUNNER_EXECUTION_ENABLED = "1"
$env:DCP_RUNNER_TERMINAL_ENABLED = "1"
$env:DCP_RUNNER_TRUSTED_LOCAL_PROJECTS = '["<PROJECT_UUID>"]'
$env:DCP_RUNNER_TRUSTED_REPOSITORIES = '[]'
$env:DCP_RUNNER_WORKSPACE_ROOT = "C:\ProgramData\DCP\workspaces"
python -m tools.local_runner_agent --serve
```

The Runner also requires its normal DCP Gateway URL and credential configuration. Preserve the existing secure credential setup; do not put tokens directly in shell history or commit them to the repository.

For a one-time foreground diagnostic, use `--check` to validate connectivity only. `--enroll-only` registers the Runner offline and cannot claim or execute Jobs. `--serve` is required for continuous job polling.

## Fail-closed behavior

- Terminal capability is advertised only when both DCP_RUNNER_EXECUTION_ENABLED=1 and DCP_RUNNER_TERMINAL_ENABLED=1 are set and at least one trusted Local Project ID is configured.
- The Runner refuses Terminal opt-in when no trusted Local Project ID is configured.
- A Runner without the terminal capability cannot claim terminal_script Jobs.
- A Project ID absent from DCP_RUNNER_TRUSTED_LOCAL_PROJECTS is rejected locally, even if a Dashboard grant exists.
- A Workspace ID or snapshot mismatch is rejected before execution and checked again after execution.
- Terminal Jobs have one attempt because their authorization grant is one-time. A failed or lease-expired Job requires a new app authorization and a new Job.
- The Runner executes only fixed catalog templates using a trusted executable registry, server-derived argv and shell=false. It does not accept a browser-supplied command, executable, argv, cwd or environment.
- Imported templates remain inert after Owner review.
- The Runner opt-in does not override the catalog's execution_enabled flag. If the selected template is disabled, the Gateway rejects authorization and no Job is queued.

## Security boundary

The fixed MVP templates are read-only and have no network command. This is an application-level command policy, not kernel-enforced network isolation. The process runs with the operating-system permissions of the Runner account; Workspace Manager is not an OS sandbox. Use a dedicated least-privileged account and keep the trusted Project allowlist narrow.

The Dashboard shows whether an online Runner advertises the terminal capability. If none is online, a queued Job may wait until a suitable Runner is started. A terminal-capable Runner must still trust the selected Project ID locally.

## Current rollout

The Dashboard Run panel, app authorization, explicit confirmation, durable Job submission, status/log polling and cancellation are implemented on the feature branch. The built-in catalog remains fail-closed until its exact-head acceptance gates pass and the reviewed MVP templates are explicitly enabled. A green Runner status alone does not enable a disabled template.
