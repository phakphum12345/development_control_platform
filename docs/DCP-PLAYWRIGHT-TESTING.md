# DCP Local Static Web Playwright Testing

## Scope

The `test_static_web` job is a local Runner capability for dependency-free,
already-detected Static HTML/CSS/JS projects. It first runs the normal static
build and then launches only the generated `source/dist` output through DCP's
loopback-only static runtime. It does not install packages or execute a
project-provided test command, Playwright config, test file, or package script.

The current checks cover:
- Page load and document title/language presence
- Mobile (360px), tablet (768px), and desktop (1366px) viewports
- Horizontal overflow and a bounded 12,000px full-page screenshot height
- Images missing alt attributes, and buttons/links without accessible names
- Browser console errors, uncaught page errors, failed requests, and blocked
  external network requests
- Three viewport screenshots and a JSON report, packaged as a bounded ZIP
  evidence artifact and uploaded through the existing Artifact Store

A report is PASS only when all implemented checks pass. Missing browser
prerequisites, launch failures, or report-generation failures never produce a
PASS. The current accessibility checks are a small deterministic smoke subset,
not a claim of WCAG conformance or a full axe-core audit.

## Runner setup and opt-in

The Runner preflight detects the Python Playwright package and its Chromium
binary without installing anything. A runner advertises the `playwright`
capability only when both are present and the owner explicitly sets:

```powershell
$env:DCP_RUNNER_PLAYWRIGHT_ENABLED = "1"
```

If that switch is absent, Playwright capability is not advertised. Setting
`DCP_RUNNER_CAPABILITIES` to include `playwright` without the explicit switch
fails closed. The `test_static_web` target is schedulable only on a Runner
advertising both `web` and `playwright`.

Install and browser maintenance remain an explicit administrator action on
the local machine; DCP does not download browsers or install Python packages.
The browser is launched with Chromium sandboxing enabled. HTTP requests are restricted to the exact loopback origin/port of the DCP static runtime; WebSocket connections are closed, WebRTC peer/media APIs are disabled in the page context, and service workers are blocked. These browser-level controls are defense-in-depth, not an OS firewall or network namespace. Project HTML/JavaScript is still untrusted executable
content: use only explicitly trusted projects and a suitably isolated local
Runner. Workspace separation alone is not an OS sandbox.

## Safety and evidence

- Runtime binds only to `127.0.0.1` and is stopped after the test.
- No project server, package script, custom test script, or dependency install
  is executed by this target.
- Browser session and network access are not exposed to the dashboard.
- Browser request routing is not a substitute for host-level egress isolation; use only trusted projects on a suitably isolated Runner.
- Screenshot and ZIP sizes are bounded; oversized full-page screenshots are
  reduced to viewport captures and reported as a failure.
- The result ZIP and static build artifact are uploaded to the Gateway Artifact
  Store; the job fails if a required test evidence upload fails.
- `PASS` means only the checks listed in this document passed. It is not a
  production-readiness, security, or cross-browser certification.

## Deferred coverage

Cross-browser engines, automated visual baselines, keyboard interaction flows,
full WCAG/axe audits, API/backend integration tests, authenticated preview
proxy tests, and arbitrary framework builds remain separate backlog items.
