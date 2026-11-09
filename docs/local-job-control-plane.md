# Local Job Control Plane — milestone 1

This milestone adds a durable SQLite job queue contract. It does not execute repository code, launch a runner process, create VMs, or enable cloud provisioning.

## Contract
- Idempotent job creation from repository, immutable 40-character commit SHA, and allowlisted target (test/build/package).
- Atomic claim with a bounded worker lease.
- Expired running leases are requeued; expired cancellation requests become cancelled.
- Expired workers are fenced from heartbeat, logs, and completion updates.
- Worker-owned heartbeat, logs, and terminal status.
- Queued cancellation is immediate; running cancellation becomes cancel_requested and must be acknowledged by the worker.
- Append-only lifecycle events and paginated logs.

## Safety boundary
The queue accepts no shell command, arbitrary environment, filesystem path, or provider selection. It does not clone repositories or execute build scripts. A later local agent must add workspace isolation, command policy, process-tree termination, and resource limits before executing code.

## Next
Add authenticated API routes, then a dry-run local agent. Only after isolation tests pass should checkout and build execution be enabled.
