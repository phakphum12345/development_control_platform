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
