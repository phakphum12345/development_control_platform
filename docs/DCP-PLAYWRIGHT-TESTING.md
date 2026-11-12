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

For a manually prepared Runner environment, install the Python package and its
matching Chromium browser explicitly:

```powershell
python -m pip install "playwright>=1.48"
python -m playwright install chromium
```

On Linux, required OS libraries must also be present. An administrator may
install them explicitly with `python -m playwright install-deps chromium`
when the host's package repositories are reachable and approved. Do not run
package-manager installation automatically from a DCP job. CI deliberately
separates browser download from OS package installation; a browser download
succeeding does not prove that the host can launch a sandboxed Chromium.
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


## CI failure classification and troubleshooting

Keep these outcomes distinct:

1. **Prerequisite failure** — Python Playwright package, matching Chromium
   executable, or WebSocket routing support is missing. Runner preflight must
   report the missing capability and must not install it.
2. **Sandbox launch failure** — Chromium exits before a page is opened. This is
   a Runner/host isolation prerequisite failure, not an application assertion
   failure. Keep `chromium_sandbox=True`; do not add `--no-sandbox` or silently
   retry without the sandbox.
3. **Application test failure** — Chromium launched and one or more fixed DCP
   checks failed. Preserve the JSON failure report and screenshots where
   available.
4. **Evidence failure** — report packaging, quota validation, or required
   Artifact Store upload failed. The job must not be marked PASS.

The launch exception is surfaced as a bounded diagnostic so CI can report the
browser error class and a short error summary without swallowing the underlying
reason. The repository CI also records read-only Linux identity, namespace,
seccomp, AppArmor restriction and capability information and enables Playwright
browser debug output for the failing smoke step.

On Ubuntu CI images that set
`kernel.apparmor_restrict_unprivileged_userns=1`, the workflow installs a
temporary, path-scoped AppArmor profile granting `userns` only to the exact
Playwright `chrome-headless-shell` executable found under the Playwright cache.
It does not disable the system-wide AppArmor user-namespace restriction. The
subsequent real-browser smoke test is the required proof that the profile is
effective; if the profile cannot be loaded or Chromium still cannot create its
sandbox, CI fails closed. This CI-only profile does not configure a user's
local Runner. Local administrators must provide an equivalent narrowly scoped
host policy or use a host that already supports Chromium sandboxing.

Do not add `--no-sandbox`, globally disable AppArmor's user-namespace
restriction, or infer sandbox support from a successful browser download.

### Latest observed CI evidence (2026-11-12)

On PR #71 commit
`52a99f2403c7ffc5c8d82fe44cbb477f8189b325`, the Python contract suite passed
(508 tests), Python/Node Playwright installation and Chromium download passed,
but the real static-app smoke test failed during sandboxed Chromium launch.
Dashboard browser smoke and registry validation were skipped because the
workflow stops after the failed step. Windows dynamic-port integration and
Windows Auth Proxy/Gateway checks passed; self-hosted Windows Runner acceptance
was skipped. A follow-up commit adds bounded launch diagnostics; do not treat
the preceding run as validation of that follow-up commit.

Official references:
- Playwright `chromiumSandbox` launch option:
  https://playwright.dev/docs/api/class-browsertype
- Playwright CI prerequisites and browser-launch debugging:
  https://playwright.dev/docs/ci
- Chromium Linux sandbox architecture:
  https://chromium.googlesource.com/chromium/src/+/HEAD/sandbox/linux/README.md


## Authenticated Preview Proxy browser E2E — 2026-11-12

A real Chromium test now exercises the owner-authenticated browser-facing preview URL, not the RuntimeManager upstream port. It requires Chromium sandboxing, checks HTML/CSS and browser request/error behavior, captures a screenshot, and verifies access is unavailable after preview stop. A short-lived HttpOnly/Secure cookie is scoped to the job runtime content path and revoked on stop, logout or expiry. Runtime capability tokens and upstream ports stay server-side. CI runs the test in the control-plane validation workflow. This does not claim cross-browser, visual-regression or WCAG conformance.
