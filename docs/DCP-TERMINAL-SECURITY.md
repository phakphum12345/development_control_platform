# DCP Terminal Studio — Security Contract

- Imported .ps1, .bat, .cmd, .sh, JSON or clipboard commands are inert data on import.
- Never execute a script or command pack automatically.
- Use a typed template registry; browser cannot submit arbitrary shell strings.
- Execute through Local Agent only, after server-side authorization and policy evaluation.
- Prefer executable + argv arrays; shell invocation is prohibited except for narrowly reviewed platform shims whose command and arguments are fixed by trusted adapter code.
- Restrict cwd to an enrolled project/workspace and re-check path/symlink containment.
- Use a minimal environment allowlist. Never inherit Gateway, GitHub App, owner or unrelated user secrets.
- Network access is denied by default and granted only per reviewed task.
- Install, write, delete, privileged, system configuration and external network operations require explicit approval or remain blocked.
- Apply time, output, CPU/RAM/disk and concurrent-process limits.
- Stop must terminate the process tree and verify cleanup.
- Redact secrets from logs and artifacts.
- Audit actor, project, template/version, command hash, approval, policy decision, start/end, exit code and cleanup result.
- Terminal must not bypass Cloud Provisioning OFF, VM Creation OFF or Cloud Deployment OFF.


## Imported command-pack controls

- JSON command packs are treated as untrusted data and never executed during import.
- The API accepts a strict versioned schema, a bounded request, allowlisted executable identifiers and argv arrays only.
- Shell metacharacters and common code-evaluation flags are rejected; network policy must be denied.
- Imported templates are stored disabled and pending review. Import approval is not execution approval.
- Imported templates cannot be enabled or executed through the current API. No arbitrary script upload or shell endpoint is exposed.
- The private SQLite import store records actor, template ID, source hash and import timestamp without storing credentials.


## Owner review is not execution approval

- Only the Owner can approve or reject an imported template.
- The review request must include the exact source SHA-256 currently stored and a typed confirmation phrase containing the template ID.
- A stale hash, invalid confirmation, repeated review or non-owner request is rejected.
- Every decision is audited with actor and source hash.
- Approval only changes review status. It never sets enabled=true and never authorizes a process launch.


## Read-only Git invocation hardening

Git commands can consult repository-local configuration. A read-only command must not be allowed to invoke a repository-controlled helper:

- Start Git with a clean, per-job environment and temporary HOME; disable system configuration and use command-scope `GIT_CONFIG_COUNT` overrides for `core.fsmonitor=false`, empty `diff.external`, and non-interactive pager settings. Git documents that these environment entries override configuration-file values and are in the protected command scope: https://git-scm.com/docs/git-config#ENVIRONMENT.
- Before running a read-only Git command, enumerate repository config keys using `git config --name-only --null --list`; fail closed if config cannot be read. For every configured filter driver, override `filter.<driver>.clean`, `smudge` and `process` with empty values and `required=false` in command-scope config. This prevents repository-local filter programs from running during worktree inspection. Git documents filter drivers and their external commands: https://git-scm.com/docs/gitattributes#_filter.
- `git diff` and `git show` must include `--no-ext-diff` and `--no-textconv`. Git documents that external diff helpers and textconv filters can run external commands unless disabled: https://git-scm.com/docs/git-diff#_options.
- Keep `GIT_PAGER` and `PAGER` fixed to a non-interactive pager and keep `shell=false` for the Runner process.
- Git versions 2.35.1 and earlier do not understand boolean `core.fsmonitor=false` and may interpret it as a hook pathname. Before any Git template is enabled, require a verified Git version 2.36.0 or later; unknown or older versions must remain blocked. See the `core.fsmonitor` compatibility note: https://git-scm.com/docs/git-config#Documentation/git-config.txt-corefsmonitor.

These controls reduce helper execution paths for the fixed read-only templates. They do not provide an OS sandbox, network isolation, or protection against every behavior of a compromised Git binary. All built-in templates remain disabled until the full isolation and host-acceptance gates pass.
