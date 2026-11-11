"""Fixed, sandboxed Playwright smoke tests for built local web applications.

This module never imports or executes project-provided test scripts. It starts only
an already-built static directory on loopback and runs a fixed DCP-owned browser
check with Chromium sandboxing and an explicit same-loopback network allowlist.
"""
from __future__ import annotations

import json
import os
import stat
import time
import zipfile
from pathlib import Path
from urllib.parse import urlsplit

from .runtime import RuntimeErrorDCP, RuntimeManager
from .workspace import WorkspaceError, WorkspaceManager


class BrowserTestError(RuntimeError):
    """Browser-test preconditions or report packaging failed."""


class StaticWebPlaywrightTester:
    VIEWPORTS = (
        {"name": "mobile", "width": 360, "height": 800},
        {"name": "tablet", "width": 768, "height": 1024},
        {"name": "desktop", "width": 1366, "height": 768},
    )
    MAX_SCREENSHOT_BYTES = 8 * 1024 * 1024
    MAX_RESULTS_BYTES = 32 * 1024 * 1024

    def __init__(self, workspaces: WorkspaceManager, *, enabled: bool = False,
                 timeout_ms: int = 15000, runtime_manager: RuntimeManager | None = None):
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be boolean")
        if isinstance(timeout_ms, bool) or not isinstance(timeout_ms, int) or not 1000 <= timeout_ms <= 60000:
            raise ValueError("timeout_ms must be between 1000 and 60000")
        self.workspaces = workspaces
        self.enabled = enabled
        self.timeout_ms = timeout_ms
        self.runtime_manager = runtime_manager or RuntimeManager(
            workspaces, max_active=1, session_ttl_seconds=300,
            startup_timeout_seconds=10,
        )

    @staticmethod
    def _results_directory(workspace: Path) -> Path:
        source = workspace / "source"
        if source.is_symlink() or not source.is_dir():
            raise BrowserTestError("built source directory is unavailable")
        results = source / ".dcp-test-results"
        if results.is_symlink() or results.exists():
            raise BrowserTestError("test results directory already exists or is unsafe")
        results.mkdir(mode=0o700)
        return results

    @staticmethod
    def _accessibility_snapshot(page) -> dict:
        return page.evaluate("""() => {
          const named = (element) => Boolean(
            (element.getAttribute('aria-label') || '').trim() ||
            (element.getAttribute('aria-labelledby') || '').trim() ||
            (element.innerText || element.textContent || '').trim()
          );
          return {
            title: (document.title || '').trim(),
            language: (document.documentElement.getAttribute('lang') || '').trim(),
            horizontal_overflow: document.documentElement.scrollWidth > window.innerWidth + 1,
            images_without_alt: document.querySelectorAll('img:not([alt])').length,
            buttons_without_name: [...document.querySelectorAll('button')].filter(e => !named(e)).length,
            links_without_name: [...document.querySelectorAll('a[href]')].filter(e => !named(e)).length
          };
        }""")

    def run(self, job_id: str, worker_id: str, *,
            output_relative: str = "source/dist") -> dict:
        if not self.enabled:
            raise BrowserTestError("Playwright execution is disabled by Runner policy")
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            raise BrowserTestError("Python Playwright is not installed; no dependency was installed automatically") from None

        workspace = self.workspaces.get(job_id, worker_id)
        results_dir = self._results_directory(workspace)
        runtime = None
        browser = None
        started = time.monotonic()
        report = {
            "schema_version": 1,
            "engine": "Playwright Chromium",
            "status": "FAIL",
            "checks": {
                "viewports": [],
                "console_errors": 0,
                "page_errors": 0,
                "failed_requests": 0,
                "blocked_external_requests": [],
                "accessibility_issues": [],
            },
            "screenshots": [],
            "duration_seconds": None,
        }
        try:
            runtime = self.runtime_manager.start_static(
                job_id, worker_id, output_relative=output_relative
            )
            parsed = urlsplit(runtime["url"])
            expected_port = parsed.port
            if parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or not expected_port:
                raise BrowserTestError("static runtime did not provide a loopback-only URL")

            with sync_playwright() as playwright:
                try:
                    browser = playwright.chromium.launch(
                        headless=True,
                        chromium_sandbox=True,
                        args=[
                            "--disable-background-networking",
                            "--disable-component-update",
                            "--disable-sync",
                            "--metrics-recording-only",
                        ],
                    )
                except Exception:
                    raise BrowserTestError("Chromium could not start with its browser sandbox enabled") from None

                context = browser.new_context(
                    viewport={"width": 360, "height": 800},
                    service_workers="block",
                    accept_downloads=False,
                )
                page = context.new_page()
                page.set_default_timeout(self.timeout_ms)
                console_errors = []
                page_errors = []
                failed_requests = []
                blocked_external = []

                page.on("console", lambda message: console_errors.append("console_error")
                        if message.type == "error" else None)
                page.on("pageerror", lambda error: page_errors.append(type(error).__name__))
                page.on("requestfailed", lambda request: failed_requests.append(request.resource_type))

                def local_only(route):
                    target = urlsplit(route.request.url)
                    if (target.scheme == "http" and target.hostname == "127.0.0.1"
                            and target.port == expected_port):
                        route.continue_()
                        return
                    blocked_external.append({
                        "host": target.hostname or "unknown",
                        "resource_type": route.request.resource_type,
                    })
                    route.abort()

                context.route("**/*", local_only)
                page.goto(runtime["url"], wait_until="load", timeout=self.timeout_ms)

                for viewport in self.VIEWPORTS:
                    page.set_viewport_size({
                        "width": viewport["width"], "height": viewport["height"]
                    })
                    snapshot = self._accessibility_snapshot(page)
                    report["checks"]["viewports"].append({
                        "name": viewport["name"],
                        "width": viewport["width"],
                        "height": viewport["height"],
                        "horizontal_overflow": snapshot["horizontal_overflow"],
                    })
                    if not snapshot["title"]:
                        report["checks"]["accessibility_issues"].append(
                            viewport["name"] + ": document title is missing"
                        )
                    if not snapshot["language"]:
                        report["checks"]["accessibility_issues"].append(
                            viewport["name"] + ": document language is missing"
                        )
                    for field, label in (
                        ("images_without_alt", "images without alt text"),
                        ("buttons_without_name", "buttons without accessible names"),
                        ("links_without_name", "links without accessible names"),
                    ):
                        if snapshot[field]:
                            report["checks"]["accessibility_issues"].append(
                                f"{viewport['name']}: {snapshot[field]} {label}"
                            )
                    if snapshot["horizontal_overflow"]:
                        report["checks"]["accessibility_issues"].append(
                            viewport["name"] + ": horizontal page overflow"
                        )
                    filename = f"viewport-{viewport['name']}.png"
                    screenshot = results_dir / filename
                    page.screenshot(
                        path=str(screenshot), full_page=True, animations="disabled",
                        timeout=self.timeout_ms,
                    )
                    if screenshot.stat().st_size > self.MAX_SCREENSHOT_BYTES:
                        raise BrowserTestError("a viewport screenshot exceeds the configured size limit")
                    report["screenshots"].append(filename)

                report["checks"]["console_errors"] = len(console_errors)
                report["checks"]["page_errors"] = len(page_errors)
                report["checks"]["failed_requests"] = len(failed_requests)
                report["checks"]["blocked_external_requests"] = blocked_external
                if console_errors or page_errors or failed_requests or blocked_external:
                    report["checks"]["runtime_issues"] = {
                        "console_errors": len(console_errors),
                        "page_errors": len(page_errors),
                        "failed_requests": len(failed_requests),
                    }
                report["status"] = (
                    "PASS" if not (
                        console_errors or page_errors or failed_requests or blocked_external
                        or report["checks"]["accessibility_issues"]
                    ) else "FAIL"
                )
                context.close()
        except BrowserTestError:
            raise
        except Exception as exc:
            report["status"] = "FAIL"
            report["failure"] = {
                "type": type(exc).__name__,
                "code": "BROWSER_TEST_EXECUTION_FAILED",
            }
        finally:
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if runtime is not None:
                try:
                    self.runtime_manager.stop(runtime["runtime_id"], runtime["session_token"])
                except RuntimeErrorDCP:
                    pass

        report["duration_seconds"] = round(time.monotonic() - started, 3)
        report_path = results_dir / "report.json"
        report_path.write_text(
            json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8"
        )
        artifact_dir = workspace / ".dcp-artifacts"
        if artifact_dir.is_symlink() or (artifact_dir.exists() and not artifact_dir.is_dir()):
            raise BrowserTestError("test artifact staging directory is unsafe")
        artifact_dir.mkdir(mode=0o700, exist_ok=True)
        artifact_path = artifact_dir / "web-test-results.zip"
        if artifact_path.exists() or artifact_path.is_symlink():
            raise BrowserTestError("test results artifact already exists")
        total = 0
        files = sorted(results_dir.iterdir(), key=lambda item: item.name)
        if not files or any(not item.is_file() or item.is_symlink() for item in files):
            raise BrowserTestError("test results contain an unsafe or missing file")
        for item in files:
            info = item.lstat()
            if not stat.S_ISREG(info.st_mode):
                raise BrowserTestError("test results contain a non-regular file")
            total += info.st_size
            if total > self.MAX_RESULTS_BYTES:
                raise BrowserTestError("test results exceed the configured size limit")
        with zipfile.ZipFile(artifact_path, "x", zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            for item in files:
                archive.write(item, item.name)
        if artifact_path.stat().st_size > self.MAX_RESULTS_BYTES:
            artifact_path.unlink(missing_ok=True)
            raise BrowserTestError("compressed test results exceed the configured size limit")
        artifact_path.chmod(0o600)
        self.workspaces.check_quota(job_id, worker_id)
        return {
            "status": report["status"],
            "duration_seconds": report["duration_seconds"],
            "screenshots": list(report["screenshots"]),
            "accessibility_issue_count": len(report["checks"]["accessibility_issues"]),
            "blocked_external_request_count": len(report["checks"]["blocked_external_requests"]),
            "console_error_count": report["checks"]["console_errors"],
            "page_error_count": report["checks"]["page_errors"],
            "report_path": "source/.dcp-test-results/report.json",
            "artifact_path": artifact_path,
            "artifact_name": artifact_path.name,
        }
