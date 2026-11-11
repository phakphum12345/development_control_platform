# DCP Authenticated Local Preview

## Scope

The first authenticated preview release serves an already-built static output directory from an existing local Runner workspace. It does not start a project development server, run package scripts, install dependencies, or execute imported source. Cloud Provisioning, VM Creation, and Cloud Deployment are not involved.

## Trust boundary

- The Gateway and Local Auth Proxy are the only browser-facing route.
- The browser receives an opaque runtime ID and a same-origin preview path. It never receives the Runtime Manager session capability, upstream port, or upstream URL.
- Every start, status, content, and stop request requires the authenticated owner session. Mutations additionally require same-origin and CSRF validation.
- Gateway verifies that the requested job exists, belongs to a local worker, and completed successfully before starting a preview.
- The Runtime Manager binds only to 127.0.0.1. The Gateway proxy uses a fixed loopback host and a port read from the server-side runtime record; clients cannot choose either.
- Content paths reject absolute paths, dot segments, backslashes, control characters, and oversized values. Responses are bounded to 8 MiB.
- Preview content is restricted to static web MIME types; cookies and arbitrary upstream request headers are not forwarded.

## Configuration

The supported Local Auth Proxy launcher defaults DCP_RUNNER_WORKSPACE_ROOT to CREDENTIALS.parent/workspaces (normally %LOCALAPPDATA%/DCP/workspaces) when the variable is not already set. Run-DCP-Gateway.ps1 uses the same default. Configure the Local Runner Agent with the exact same absolute path. The Gateway creates no project workspaces; it only opens a workspace whose job/worker marker already exists. If the variable is not configured when launching the Gateway outside the supported local startup script, preview endpoints fail closed as unavailable.

The Gateway also reads DCP_RUNNER_MAX_ACTIVE_WORKSPACES and DCP_RUNNER_MAX_WORKSPACE_BYTES to validate the shared workspace root using the same bounds as the agent.

Successful Static Web and Vite jobs retain their workspace for up to one hour so the built output remains available after the Runner pipeline finishes. Starting a preview renews the retention marker to the runtime session TTL plus a short cleanup margin. The Gateway's periodic reaper stops expired preview processes and removes only workspaces with a valid, expired DCP retention marker. The Runner also prunes expired retained workspaces before allocating a new job workspace. Non-web jobs continue to clean their workspaces immediately.

## API

All routes are exposed through the Local Auth Proxy:

- POST /api/jobs/{job_id}/previews with JSON {} or {"output_relative":"source/dist"} starts a preview.
- GET /api/jobs/{job_id}/previews lists sanitized active preview sessions for that job.
- GET /api/jobs/{job_id}/previews/{runtime_id} returns sanitized runtime status.
- GET /api/jobs/{job_id}/previews/{runtime_id}/content/{path} serves a bounded static asset through the authenticated proxy.
- DELETE /api/jobs/{job_id}/previews/{runtime_id} stops the runtime.

Supported output roots are source/dist, source/build/web, dist, and build/web. A job must be in succeeded state. Only one active preview per job is allowed.

## Current limitations

This is a static-output preview, not a general-purpose application server. It does not yet provide WebSocket/HMR, arbitrary framework runtime profiles, range requests, or browser automation. The runtime capability is held in Gateway memory; Gateway restart invalidates preview sessions and leaves runtime cleanup to process lifecycle/TTL handling. Do not expose Runtime Manager or its loopback port directly to a LAN.
