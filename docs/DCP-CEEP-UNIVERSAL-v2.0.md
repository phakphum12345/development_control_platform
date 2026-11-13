# DCP-CEEP v2.0
## Universal Continuous Execution & Evidence Protocol

**Protocol ID:** DCP-CEEP  
**Version:** 2.0.0  
**Status:** Proposed; adoption requires review and approval  
**Scope:** Cross-project operating standard for research, engineering, software, hardware, data, documentation, operations, and other supported work  
**Supersedes:** DCP-CEEP v1.0 after an explicit migration/adoption decision  
**Operating principle:** One protocol, task-specific workflows, evidence-backed outcomes.

---

## 1. Purpose and governing principles

DCP-CEEP defines a repeatable lifecycle from request intake through discovery, research, planning, authorized execution, verification, recovery, and delivery.

The protocol MUST:
1. preserve the user's requested outcome and constraints;
2. inspect existing work before repeating it;
3. use the least risky method that can achieve the outcome;
4. distinguish plans, implementation, tests, CI, and real-world acceptance;
5. preserve evidence and continuity across sessions;
6. report blockers and waiting states instead of silently stalling;
7. continue independent work when another task is blocked;
8. stop at authorization, safety, or information boundaries;
9. never claim a result that has not been verified.

The protocol does not grant permissions. It governs how already-authorized work is performed.

## 2. Universal task classification

At intake, classify the task into one or more profiles. Profiles select relevant methods and acceptance criteria; they do not create separate governance systems.

Supported profiles include:
- software engineering and repository maintenance;
- system, platform, infrastructure, and operations engineering;
- web, API, application, and integration development;
- hardware, electronics, PCB, IC, sensor, and driver engineering;
- CAD, 2D/3D modeling, geometry, and simulation;
- physics, mathematics, numerical methods, and scientific computing;
- research, technical writing, documentation, and knowledge management;
- data engineering, analytics, reporting, and visualization;
- testing, quality assurance, security, and compliance;
- automation, workflow, and project/program management;
- education, training, and learning workflows.

A task may use multiple profiles. The selected profile MUST state the deliverable, constraints, and suitable verification method.

## 3. Master command and command registry

The default entry point is:

`DCP/INTELLIGENT-E2E`

It orchestrates only the stages required for the task and respects every approval gate.

### 3.1 Lifecycle commands

| Command | Purpose |
|---|---|
| `DCP/START` | Capture objective, scope, constraints, and authority |
| `DCP/STATUS` | Report current state, progress, blockers, and next action |
| `DCP/PLAN` | Create work packages, dependencies, and acceptance criteria |
| `DCP/SEARCH` | Search repository, files, project records, and supplied evidence |
| `DCP/WEB-SEARCH` | Research public web sources when useful or required |
| `DCP/AUDIT` | Inspect implementation, configuration, structure, and gaps |
| `DCP/TRACE` | Trace requirements, data flow, execution paths, and dependencies |
| `DCP/IMPLEMENT` | Perform authorized changes |
| `DCP/TEST` | Run task-appropriate tests |
| `DCP/VERIFY` | Independently verify results against acceptance criteria |
| `DCP/CHECKPOINT` | Persist current state and evidence |
| `DCP/CONTINUE` | Start the next unblocked authorized work package |
| `DCP/RECOVER` | Resume safely after interruption or failure |
| `DCP/ROLLBACK` | Restore a known-good state when authorized and appropriate |
| `DCP/REPORT` | Produce the evidence-backed delivery report |
| `DCP/STOP` | Stop work safely and record a resumable checkpoint |

### 3.2 Research and intelligence commands

| Command | Purpose |
|---|---|
| `DCP/OFFICIAL-DOCS` | Find and inspect authoritative product/framework documentation |
| `DCP/SOURCE-RESEARCH` | Inspect official source repositories, issues, discussions, and pull requests |
| `DCP/PACKAGE-SEARCH` | Discover packages, libraries, SDKs, and tools |
| `DCP/RELEASE-CHECK` | Check release notes, versions, deprecations, and breaking changes |
| `DCP/SECURITY-CHECK` | Check advisories, vulnerabilities, and security guidance |
| `DCP/RESEARCH-VERIFY` | Cross-check claims against primary sources |
| `DCP/KNOWLEDGE-CACHE` | Reuse prior research when scope and freshness remain valid |
| `DCP/ALTERNATIVES` | Compare implementation and tooling options |
| `DCP/COMPATIBILITY` | Check runtime, platform, API, and dependency compatibility |
| `DCP/SUPPLY-CHAIN` | Assess package provenance, integrity, licensing, and dependency risk |
| `DCP/INTEGRATION-PLAN` | Plan a safe integration and rollback path |

### 3.3 Quality and continuity commands

| Command | Purpose |
|---|---|
| `DCP/ROOT-CAUSE` | Determine the supported underlying cause of a failure |
| `DCP/PARALLELIZE` | Identify independent work that can safely run concurrently |
| `DCP/COMPLETION-AUDIT` | Check requirements and deliverables for omissions |
| `DCP/EVIDENCE-AUDIT` | Check that claims have current, relevant evidence |
| `DCP/DEPENDENCY-AUDIT` | Check internal and external dependency relationships |
| `DCP/PROGRESS-UPDATE` | Publish a meaningful progress checkpoint |
| `DCP/DECISION-RECORD` | Record important decisions, alternatives, and rationale |

Commands are protocol labels, not assertions that a particular automation tool exists. The operator MUST use only tools actually available and authorized in the current environment.

## 4. Intake and scope control

Every task MUST record:
- requested outcome and deliverable;
- project/repository/system identity;
- in-scope and out-of-scope work;
- user constraints and preferences;
- available permissions and approval boundaries;
- relevant deadlines or time expectations;
- acceptance criteria and evidence required.

If an essential fact is missing, ask one focused question. Do not block on optional preferences.

Scope changes MUST be recorded. Do not silently expand work into unrelated projects or destructive operations.

## 5. Internal discovery and audit

Use repository and project evidence before external research when the question concerns existing implementation.

Discovery MUST:
1. identify the authoritative repository, branch, version, and current revision;
2. inspect relevant files, entry points, configuration, tests, and documentation;
3. trace the actual execution or data path where behavior matters;
4. identify existing tools and dependencies before proposing replacements;
5. record files and areas inspected;
6. reuse earlier audit evidence only when its revision and scope still match.

A filename, README statement, type declaration, or UI label alone does not prove runtime behavior. For behavior claims, inspect implementation and tests, then execute an appropriate verification where possible.

## 6. External research and web intelligence

External research SHOULD be used when current or authoritative information materially improves correctness, including:
- undocumented or unclear errors;
- changing APIs, frameworks, runtimes, and platform behavior;
- compatibility and deprecation questions;
- missing capabilities or possible replacement tools;
- security advisories and known vulnerabilities;
- performance or reliability issues with evidence outside the repository.

### 6.1 Source priority

Prefer:
1. official documentation and vendor manuals;
2. official source repositories and maintainers' issue trackers;
3. official release notes and changelogs;
4. authoritative package registries and security databases;
5. standards bodies and recognized technical specifications;
6. reputable technical publications;
7. community discussions as supplementary evidence.

### 6.2 Research rules

For each material external claim, record URL, source owner, access/release date when available, applicable version, and the claim supported.

Inspect the source page rather than relying only on search snippets. Distinguish facts, maintainer guidance, community opinion, and inference. For high-risk decisions, corroborate with another authoritative source where feasible.

Do not transmit secrets, private source code, personal data, or credentials to public search services.

## 7. Package, tool, and supply-chain evaluation

Before adding a dependency or external tool, evaluate:
- whether it solves a demonstrated requirement;
- whether existing code or standard-library functionality is sufficient;
- supported language, runtime, operating system, and architecture;
- release cadence, maintenance status, and known end-of-life dates;
- direct and transitive dependencies;
- license obligations and compatibility;
- security advisories and malware reports;
- package provenance, publisher identity, integrity, and signatures where available;
- performance, size, operational burden, and upgrade path;
- removal and rollback strategy.

Prefer reuse of maintained existing dependencies or standard tools when they meet the need. Do not choose solely by stars, downloads, ranking, or search position.

Discovery does not authorize installation. Installation, script execution, binary execution, or lockfile changes require the applicable project permission and approval. Never run an unreviewed install script or downloaded executable.

## 8. Root-cause analysis and problem resolution

For each material failure:
1. capture the error, revision, environment, and reproducible context;
2. classify likely domain: code, design, configuration, dependency, permissions, data, platform, network, service, or external provider;
3. identify and test the causal hypothesis;
4. consult official documentation or external sources when internal evidence is insufficient;
5. compare low-risk alternatives;
6. implement the smallest justified correction;
7. run targeted tests and relevant regression tests;
8. record the root cause, correction, and residual risk.

Do not hide failures, weaken security controls, remove tests, or change acceptance criteria merely to obtain a passing status.

## 9. Planning, work packages, and dependency graph

Break substantial work into traceable Work Packages (WPs). Each WP MUST define:
- unique ID and objective;
- scope and expected outputs;
- prerequisites and dependencies;
- files/systems affected;
- risk and required approval;
- acceptance criteria;
- verification method;
- evidence location;
- owner/operator and next action;
- status.

Parallelize only independent work. Shared-file edits, migrations, ordered deployments, and other conflicting work MUST be serialized or coordinated. Re-check dependencies before starting a downstream WP.

When a WP passes, continue to the next unblocked WP that is within the authorized scope.

## 10. Execution and tool governance

Use the least-privileged available tool that can perform the task. Verify tool identity, scope, and permission before invoking it.

For application-to-runner workflows:
- the application/backend, not the browser, is the authority for authorization;
- browser input MUST be typed and allowlisted;
- never accept arbitrary browser-supplied shell commands, executable paths, argv, working directories, environment variables, identities, or approval flags;
- the trusted execution service MUST independently validate authorization, resource binding, expiry/revocation, and job ownership;
- derive paths and executable arguments from trusted server-side registries;
- record execution and results in an auditable way.

For other domains, apply equivalent controls: approved instruments, trusted data sources, scoped credentials, change windows, and human review for high-impact operations.

## 11. Security, privacy, and safety

Always:
- protect secrets and redact them from logs and reports;
- minimize data collection and external disclosure;
- use least privilege and explicit resource scope;
- validate untrusted input and external artifacts;
- preserve audit records without exposing sensitive content;
- use safe defaults and fail closed when authorization cannot be established;
- distinguish a process boundary from a true OS or hardware security boundary.

Do not claim sandboxing, isolation, compliance, or security certification without evidence of the actual enforcement mechanism and its limits.

## 12. Timebox, progress, and no-silent-waiting

Timeboxes are planning targets, not permission to skip verification.

- Begin with a bounded discovery pass and report what is known.
- If discovery or diagnosis exceeds its target, publish findings, unknowns, and the reason for further work.
- During CI, network, or external-service waits, perform independent authorized work where possible.
- Never report a wait as progress or leave a blocker unexplained.
- Provide a checkpoint after meaningful milestones, failures, recovery, or a long-running operation.
- Do not repeatedly rescan unchanged files or rerun unchanged tests without a reason.

A progress update MUST state completed work, current activity, blockers/waits, evidence revision, and next action.

## 13. Knowledge cache and evidence continuity

A cached result is reusable only if its source, scope, version, and freshness remain valid.

Record:
- project and task identity;
- repository, branch, commit/revision, or artifact version;
- audit scope and inspected paths;
- external research URLs and checked versions;
- package versions and relevant lockfile state;
- decisions and rationale;
- files changed and change identifiers;
- test commands, environment, and results;
- CI run/job identifiers and exact revision;
- outstanding risks, blockers, and next actions.

Invalidate or re-check evidence when relevant source files, configuration, dependencies, environment, or revision change.

## 14. Verification and acceptance

Choose verification methods appropriate to the task. They may include:
- static inspection and schema validation;
- unit, integration, contract, regression, and end-to-end tests;
- build, packaging, and reproducibility checks;
- security, dependency, and license checks;
- performance, load, and resource checks;
- simulation, calibration, physical measurement, or bench testing;
- data reconciliation and independent calculation;
- documentation review and user acceptance.

Define acceptance criteria before implementation when practical. Verify against the exact resulting revision or artifact. CI success is not equivalent to real-world acceptance. A document describing a feature is not proof that the feature exists.

## 15. Recovery and rollback

Before risky changes, identify a recoverable baseline and a rollback approach.

On interruption or failure:
1. stop unsafe or duplicate work;
2. identify the last confirmed checkpoint and exact revision;
3. inspect remote and local state before retrying;
4. determine whether an operation already completed;
5. resume idempotently where possible;
6. roll back only when authorized and technically safe;
7. verify the recovered state and record the incident.

Never delete user data or overwrite unreviewed work as a recovery shortcut.

## 16. Approval gates and protected actions

The following permissions are distinct and MUST NOT be inferred from one another:

| Action | Required control |
|---|---|
| Read, search, audit | Authorized read access |
| Local analysis or tests | Authorized environment and resource scope |
| Modify files | Explicit task scope and write access |
| Install dependencies or run downloaded tools | Dependency/security review and applicable approval |
| Push changes | Explicit push authorization |
| Merge a PR | Explicit merge authorization for the intended PR/revision |
| Deploy or publish | Explicit deployment/publishing authorization |
| Delete or irreversibly migrate data | Specific approval and recovery plan |
| Create paid resources or incur charges | Explicit cost approval |
| Access external accounts or sensitive data | Authorized connector/account scope and purpose |

Passing tests or CI does not grant permission to push, merge, deploy, publish, or delete.

## 17. Universal evidence statuses

Use these statuses consistently:

| Status | Meaning |
|---|---|
| PASS | Acceptance criterion met with relevant evidence |
| FAIL | Evidence shows the criterion is not met |
| SKIPPED | Check was intentionally or conditionally not run |
| UNKNOWN | Evidence is unavailable or insufficient |
| IN_PROGRESS | Work or verification is underway |
| BLOCKED | Progress requires a missing dependency, permission, decision, or external condition |

SKIPPED, UNKNOWN, IN_PROGRESS, and BLOCKED MUST NOT be counted as PASS. Report partial success at the criterion level rather than assigning a misleading overall PASS.

## 18. Delivery and completion audit

Before declaring completion, run `DCP/COMPLETION-AUDIT`:
- map every requirement to implementation/output and evidence;
- confirm all in-scope work packages have a final status;
- identify skipped and unknown checks;
- confirm the final revision/artifact identity;
- verify documentation matches actual behavior;
- record residual risks and unsupported claims;
- confirm protected actions were not performed without approval.

The final report MUST include:
1. requested outcome and scope;
2. work completed and files/artifacts changed;
3. research sources and dependency decisions, if applicable;
4. tests and verification results;
5. exact revision or artifact identifier;
6. PASS/FAIL/SKIPPED/UNKNOWN/IN_PROGRESS/BLOCKED summary;
7. remaining gaps, risks, and blockers;
8. next authorized action.

## 19. Universal lifecycle

The default lifecycle is:

`START → DISCOVER → RESEARCH (as needed) → AUDIT → PLAN → AUTHORIZE → IMPLEMENT → TEST → VERIFY → CHECKPOINT → REPORT → CONTINUE`

Not every task requires every stage. The operator MUST document omitted stages when they are material to acceptance. Approval gates cannot be skipped.

## 20. Adoption and versioning

This document is a proposed standard until reviewed and adopted by the project owner.

Adoption MUST include:
- review against the existing DCP-CEEP v1.0 document and continuity checkpoint;
- a migration note identifying retained, changed, and added requirements;
- a command reference and task-profile templates;
- README and roadmap links after the relevant base documentation is available;
- traceability from v2.0 requirements to repository documentation and, where implemented, automation;
- an explicit decision on whether v1.0 is superseded or retained for compatibility.

Version changes:
- PATCH: editorial corrections that do not change meaning;
- MINOR: backward-compatible additions;
- MAJOR: changes to lifecycle, governance, status semantics, or approval requirements.

**End of DCP-CEEP v2.0**
