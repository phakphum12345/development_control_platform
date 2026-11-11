# DCP Command Library — Template Contract

## Categories
Git; Node.js/Web; Python; Flutter; PowerShell diagnostics; DCP operations; Browser testing; Security scanning.

## Template metadata
- id, name, description, version, category, tags
- supported OS and required tool versions
- task identifier and adapter identifier
- executable identifier from trusted registry
- validated argv schema (no arbitrary shell string)
- project/workspace working-directory policy
- environment variable allowlist (names only; secret values referenced through approved secret broker)
- network policy and permitted destinations
- mutation class: read-only, workspace-write, dependency-install, network, destructive, privileged
- timeout, output-byte cap, resource limits
- approval requirements and expected evidence

## Built-in starter templates
Read-only: Git status/diff/log, toolchain doctor, DCP health, framework detect.
Workspace-write: create virtual environment, generate build output, run test suite.
Dependency/network: npm/pip/pub install only after explicit policy and approval.
Destructive/privileged: excluded from initial library; require separate review.

## Import/export
JSON schema version is mandatory. Reject unknown executable identifiers, unknown fields, oversized packs, invalid paths and embedded secrets. Imported templates are disabled pending review. Export excludes secrets, runtime tokens and local absolute paths.
