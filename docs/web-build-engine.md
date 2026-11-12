# DCP Local Web Build Engine

## Supported targets

| Target | CLI | Required local dependencies | Output |
|---|---|---|---|
| `build_static_web` | DCP bounded file copy | Root `index.html` | `dist/` |
| `build_vite` | Local `node_modules/vite/bin/vite.js build` | Vite plus React or Vue; Node.js | `dist/` |
| `build_next` | Local `node_modules/next/dist/bin/next build` | Next.js and React; Node.js | `.next/` |
| `build_angular` | Local `node_modules/@angular/cli/bin/ng.js build` | Angular Core and CLI; Node.js | `dist/` |

The Local Runner must already have the project's dependencies available. DCP does not run npm, pnpm, yarn, bun, pip or other dependency installation commands, and it does not invoke package.json lifecycle scripts.

## Execution and trust boundary

- The web build executor is disabled by default and requires the existing Runner execution opt-in.
- GitHub projects must match the Runner's trusted-repository allowlist. Local projects must match the explicitly trusted local-project allowlist.
- Build commands use a fixed executable and argv array with `shell=False`; the browser cannot provide a command line.
- Project build/configuration code is executed by Vite, Next.js or Angular. These targets are therefore not suitable for untrusted source.
- Timeouts, bounded output, workspace quotas and process-tree cancellation are enforced by the existing executor.
- Dependency directories and CLI paths are checked for symlinks. Angular project selection fails closed if it is ambiguous.
- Artifact packaging rejects symlinks and non-regular files and enforces file-count and byte limits.

## Output and runtime limitations

- Vite and Angular artifacts are packaged from `dist/`.
- Next.js build artifacts are packaged from `.next/`. This does not provide a Next.js server runtime, SSR preview, HMR or WebSocket proxy.
- Angular static output may be served by the existing static Runtime Manager when its build output contains a suitable `index.html`; this is not a general Angular SSR runtime.
- A successful build means the selected CLI exited successfully and its expected output directory exists. It does not mean the application has passed browser tests or is production-ready.

## Verification

Unit tests cover CLI discovery, required manifests, Angular project selection, fixed argv, artifact output directories and failure behavior. Gateway tests cover accepted job targets; Runner Registry tests cover advertised capabilities; Dashboard exposes the new targets in its Build Jobs selector.


## Dashboard target gating

- GitHub App inspection supplies immutable commit identity and bounded project-type evidence.
- The Dashboard enables Flutter targets only for a detected Flutter project, and Vite/Next.js/Angular candidates only for a detected Node project.
- This is an eligibility hint, not toolchain readiness. The Runner rechecks the exact manifest and local CLI and fails closed if dependencies are absent.
- A truncated or UNKNOWN inspection never enables a build action.
- No dependencies are installed automatically.
