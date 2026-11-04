# DCP Self-Learning Development & Universal Runner Platform

## Purpose

Turn DCP into a project-aware development control plane that can inspect a
repository, infer its technology stack and architecture signals, propose a
task plan, generate a runner profile, and later orchestrate approved isolated
build/test workflows. Inferred information must remain distinct from verified
evidence.

## Existing capabilities to reuse

- tools/cloud_runner and tools/runner_backend: cloud runner request and provider abstractions.
- tools/cloud_gateway: provider routing, budget guards, policy, bootstrap, lifecycle and cleanup.
- tools/mcp_engine: bounded read-only source inspection.
- tools/dev_environment.py: local toolchain and emulator inventory.
- schemas/project-state.schema.json, project registry and gate tests: SHA-bound project state and evidence contracts.

Do not create a parallel cloud provisioning API. Extend the existing gateway
only after its current contract and tests are understood.

## Target architecture

1. **Project Intelligence** — bounded repository inventory, manifest parsing,
   language/framework detection, architecture-area mapping, task context and
   explicit uncertainty.
2. **Architecture Planner** — derive a proposed dependency/module map, identify
   missing tests/toolchains/docs and produce a task-specific implementation
   plan. Inference must be labeled as inference.
3. **Universal Runner Factory** — produce deterministic OS-specific runner
   profiles from detected capabilities; reuse existing provider router and
   lifecycle APIs.
4. **Tool & Adapter Factory** — resolve required tools from approved catalogs,
   pin versions, verify checksums/signatures where available, and generate
   adapter contracts and tests. Never download or install automatically.
5. **Workflow Orchestrator** — stage work in an isolated workspace; run only
   owner-approved commands; capture exit codes, stdout/stderr, tool versions,
   environment facts and exact source SHA.
6. **Self-Development Pipeline** — generate patches and tests in a branch,
   validate them, open a PR, and wait for human review. Never edit main or
   self-approve/merge/deploy.
7. **Learning & Evidence** — retain structured outcomes, failure categories,
   remediation effectiveness and profile compatibility. Do not convert model
   suggestions or prior PASS results into current evidence.

## Current implementation slice

The first implementation slice provides:
- tools/project_intelligence.py: bounded read-only discovery and stack analysis.
- tools/dcp_project_intelligence.py: JSON command-line interface.
- tools/universal_runner_factory.py: deterministic runner profile preview.
- tests/test_project_intelligence.py: behavior and safety contract tests.

Example invocation (PowerShell):

    python -m tools.dcp_project_intelligence C:\path\to\repo --task "Add API tests"

The command emits a JSON assessment. A completed inventory is not proof that
the project builds or tests pass. The generated profile is a proposal only.

## Safety invariants

- Discovery is read-only, bounded, does not follow symlinks, and never imports
  or executes repository code.
- Runner profile generation is deterministic and dry-run only.
- No shell command string is generated; commands are argument arrays.
- No credentials are read or injected by discovery.
- Network is disabled by default in the proposed execution policy.
- Real provisioning requires the existing allowlist, owner approval,
  server-side policy, budget guard, ephemeral isolation and cleanup.
- No write to main, force push, self-approval, merge or deployment.
- Evidence records include exact full commit SHA, run ID, timestamps and
  inspectable logs/artifacts. Missing or stale evidence is UNKNOWN.

## Delivery phases and exit criteria

| Phase | Deliverable | Exit criteria |
|---|---|---|
| 1. Intelligence | Discovery, technology detector, architecture map | Fixture matrix passes; bounded scan; no execution |
| 2. Planning | Task-aware architecture and gap planner | Reproducible plans with assumptions and uncertainty |
| 3. Runner Factory | OS profiles and capability registry | Profile schema, policy tests, dynamic ports, isolation |
| 4. Tool Factory | Pinned tool catalog and adapters | Integrity verification, compatibility tests, no implicit installs |
| 5. Orchestration | Isolated build/test lifecycle | Real runner acceptance, logs, cleanup and SHA-bound evidence |
| 6. Self-development | Patch/test/PR pipeline | Branch-only writes, human review, all required gates |
| 7. Learning | Failure taxonomy and improvement records | Auditable outcomes; no automatic promotion of unverified claims |

## Known limits and pending work

The initial slice does not yet implement an LLM-based design engine, actual
runner provisioning, tool installation, command execution, automatic patch
generation, durable learning storage, or a live provider acceptance test.
These must be delivered in subsequent reviewed changes. Existing cloud
providers may be disabled or mock-backed; a passing unit test is not evidence
of live infrastructure readiness.
