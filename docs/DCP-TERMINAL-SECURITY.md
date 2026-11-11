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
