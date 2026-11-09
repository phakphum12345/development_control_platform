# DCP Central Local Runner Manager

**Status:** initial Windows local-host implementation; cloud provisioning remains separately gated.

## What happens when started

Run the manager with an exact private repository. It checks Windows, GitHub CLI authentication, repository identity, and repository-admin permission. It then downloads the official latest Windows x64 GitHub Actions runner, creates a new isolated directory under %LOCALAPPDATA%\DCP\local-runners, obtains a short-lived registration token through the already-authenticated GitHub CLI, and registers a uniquely named **ephemeral** runner.

After a job completes, GitHub removes the ephemeral runner registration and the supervisor creates a fresh isolated instance. If GitHub reports the runner offline and not busy for three consecutive health checks, the supervisor restarts only its own child process. An API outage is treated as UNKNOWN and does not authorize a restart. Ctrl+C stops only the process tree created by this supervisor (scoped to its exact PID). Each completed or failed managed instance has its own temporary workspace removed; its runner log is retained under the managed root. Existing runner folders, Windows services, registrations, workspaces, and ports are not inspected for termination or modified.

## Prerequisites

- Windows 11 x64.
- GitHub CLI (gh) installed and already authenticated (gh auth login).
- The authenticated account has **Admin** permission on the target repository.
- The target repository is private. Public repositories are blocked because self-hosted runners must not execute untrusted public pull-request code.
- Network access to GitHub and the official Actions runner release.

No GitHub token, runner registration token, private key, or cloud credential belongs in a user-supplied command-line argument, configuration file, source code, or logs. The short-lived registration token is requested at runtime and held only in process memory while the runner is configured. The runner configuration command necessarily receives the temporary token as an argument, matching the official runner bootstrap interface; run this on a trusted, single-user machine.

## Commands

From the repository root:

    py -3 -m tools.local_runner_manager doctor --repository phakphum12345/phakphum-calendar
    py -3 -m tools.local_runner_manager start --repository phakphum12345/phakphum-calendar

The doctor command is read-only. Start creates a new runner; it never adopts or reconfigures an existing runner. Stop the supervisor with Ctrl+C. The default restart ceiling is five consecutive failures.

    py -3 -m tools.local_runner_manager start --repository OWNER/PRIVATE-REPOSITORY --max-restarts 5

## Isolation and safety

- Each run gets a fresh unique runner name and directory.
- Runner is registered with --ephemeral and --disableupdate; it deregisters after one job.
- Labels are dcp-managed, windows, and x64.
- Repository identity and privacy are checked through the authenticated GitHub API before provisioning.
- Only the exact process tree created by this supervisor is monitored or stopped, using its PID rather than a shared process name. No service modification, firewall rule, fixed port, or port reservation is used.
- Temporary workspaces belonging to this manager are removed after the runner exits; audit logs remain under the managed root. Cleanup refuses paths outside the managed root.
- Runner downloads are limited to 512 MiB and ZIP extraction rejects path traversal.
- Restart count is bounded; the manager stops rather than retrying forever.
- A successful gh auth status is not proof that a runner is online. Verify the new runner in Repository Settings > Actions > Runners and confirm a real workflow job is assigned to its labels.

## Important limitations

This first version is a local Windows runner supervisor, not a remote fleet scheduler. It does not automatically register every repository, change workflow runs-on labels, or activate Azure/Orka. Use it only for a private repository with trusted workflows. Cloud runners remain fail-closed until their separate provider, budget, bootstrap, online-job, and teardown acceptance gates pass.

The local runner has no service port. The DCP Gateway dynamic DCP_GATEWAY_PORT=0 behavior remains independent and unchanged.
