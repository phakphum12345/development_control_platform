
import http.cookiejar
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import (
    HTTPCookieProcessor,
    Request,
    build_opener,
    urlopen,
)

from tools import local_auth_proxy as auth


def _chromium_ready():
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as playwright:
            return Path(playwright.chromium.executable_path).is_file()
    except Exception:
        return False


def free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class OwnerCredentialSetupTests(unittest.TestCase):
    def test_first_time_setup_requires_fourteen_character_password(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "owner-auth.json"
            with patch("builtins.input", return_value="owner-kept"), patch(
                "tools.local_auth_proxy.getpass.getpass",
                side_effect=["x" * 13, "new-owner-passphrase", "new-owner-passphrase"],
            ):
                record = auth.load_or_create_credentials(path)
            self.assertTrue(
                auth.verify_password(record, "owner-kept", "new-owner-passphrase")
            )
            self.assertFalse(auth.verify_password(record, "owner-kept", "x" * 13))
            if os.name != "nt":
                self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class LocalAuthProxyEndToEndTests(unittest.TestCase):

    @classmethod
    def _cleanup_resources(cls):
        """Stop test servers and release all temporary resources."""
        try:
            if hasattr(cls, "httpd"):
                try:
                    if (
                        hasattr(cls, "thread")
                        and cls.thread.is_alive()
                    ):
                        cls.httpd.shutdown()
                finally:
                    cls.httpd.server_close()
        finally:
            try:
                if hasattr(cls, "thread"):
                    cls.thread.join(timeout=5)
            finally:
                try:
                    if hasattr(cls, "gateway"):
                        if cls.gateway.poll() is None:
                            cls.gateway.terminate()

                        try:
                            cls.gateway.wait(timeout=10)
                        except subprocess.TimeoutExpired:
                            cls.gateway.kill()
                            cls.gateway.wait(timeout=5)
                        finally:
                            if cls.gateway.stderr is not None:
                                cls.gateway.stderr.close()
                finally:
                    if hasattr(cls, "temp"):
                        cls.temp.cleanup()

    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.local_port = free_port()
        cls.gateway_port = free_port()

        while cls.gateway_port == cls.local_port:
            cls.gateway_port = free_port()

        auth.PORT = cls.local_port

        cls.token = "test-gateway-token-never-sent-to-browser"
        cls.secret = "test-proxy-hmac-secret-" + ("x" * 48)
        cls.gateway_db = str(
            Path(cls.temp.name) / "gateway.sqlite3"
        )
        cls.workspace_root = Path(cls.temp.name) / "workspaces"
        cls.jobs_db = cls.gateway_db + ".jobs"

        env = os.environ.copy()
        env.update({
            "DCP_GATEWAY_HOST": "127.0.0.1",
            "DCP_GATEWAY_PORT": str(cls.gateway_port),
            "DCP_GATEWAY_API_TOKEN": cls.token,
            "DCP_TRUSTED_PROXY_HMAC_SECRET": cls.secret,
            "DCP_PUBLIC_ORIGIN": (
                f"http://127.0.0.1:{cls.local_port}"
            ),
            "DCP_GATEWAY_DATABASE": cls.gateway_db,
            "DCP_GATEWAY_JOBS_DATABASE": cls.jobs_db,
            "DCP_RUNNER_WORKSPACE_ROOT": str(cls.workspace_root),
            "DCP_GATEWAY_PROVISIONING_ENABLED": "false",
            "DCP_GATEWAY_OWNER_APPROVED": "false",
        })

        cls.gateway = subprocess.Popen(
            [sys.executable, "-m", "tools.cloud_gateway.server"],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )

        try:
            for _ in range(60):
                if cls.gateway.poll() is not None:
                    stderr = cls.gateway.stderr.read().decode(
                        errors="replace"
                    )
                    raise RuntimeError(
                        "Gateway failed to start: " + stderr
                    )

                try:
                    with urlopen(
                        f"http://127.0.0.1:{cls.gateway_port}/healthz",
                        timeout=1,
                    ):
                        break
                except Exception:
                    time.sleep(0.2)
            else:
                raise RuntimeError("Gateway health timeout")

            record = auth.password_record(
                "owner-test",
                "correct horse battery staple 2026!",
            )

            cls.app = auth.LocalAuthProxy(
                record,
                cls.token,
                cls.secret,
                cls.gateway_port,
            )

            cls.httpd = auth.ThreadingHTTPServer(
                ("127.0.0.1", cls.local_port),
                auth.make_handler(
                    cls.app,
                    Path(__file__).resolve().parents[1] / "dashboard",
                ),
            )

            cls.thread = threading.Thread(
                target=cls.httpd.serve_forever,
                daemon=True,
            )
            cls.thread.start()

            cls.base = f"http://127.0.0.1:{cls.local_port}"
            cls.cookie_jar = http.cookiejar.CookieJar()
            cls.opener = build_opener(
                HTTPCookieProcessor(cls.cookie_jar)
            )

        except Exception:
            try:
                cls._cleanup_resources()
            except Exception:
                # Preserve the original setup exception.
                pass
            raise

    @classmethod
    def tearDownClass(cls):
        cls._cleanup_resources()

    def request(
        self,
        path,
        method="GET",
        data=None,
        csrf=None,
        origin=True,
        idempotency_key=None,
    ):
        headers = {
            "Accept": "application/json",
        }

        if origin:
            headers["Origin"] = self.base

        if data is not None:
            headers["Content-Type"] = "application/json"

        if csrf:
            headers["X-CSRF-Token"] = csrf
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key

        req = Request(
            self.base + path,
            data=(
                json.dumps(data).encode()
                if data is not None
                else None
            ),
            headers=headers,
            method=method,
        )

        try:
            with self.opener.open(req, timeout=5) as response:
                return (
                    response.status,
                    response.headers,
                    response.read(),
                )
        except HTTPError as exc:
            try:
                return (
                    exc.code,
                    exc.headers,
                    exc.read(),
                )
            finally:
                exc.close()

    def test_full_login_gateway_session_logout_flow(self):
        status, headers, body = self.request(
            "/api/auth/session"
        )

        self.assertEqual(status, 200)
        self.assertIn(
            "HttpOnly",
            headers.get("Set-Cookie", ""),
        )
        self.assertIn(
            "SameSite=Strict",
            headers.get("Set-Cookie", ""),
        )

        preauth = json.loads(body)

        self.assertFalse(preauth["authenticated"])
        self.assertGreaterEqual(
            len(preauth["csrfToken"]),
            32,
        )

        denied, _, _ = self.request(
            "/api/cloud-runners/status"
        )
        self.assertEqual(denied, 401)

        denied, _, _ = self.request(
            "/api/auth/login",
            "POST",
            {
                "username": "owner-test",
                "password": "wrong-password",
            },
            preauth["csrfToken"],
        )
        self.assertEqual(denied, 401)

        logged_in, _, _ = self.request(
            "/api/auth/login",
            "POST",
            {
                "username": "owner-test",
                "password": "correct horse battery staple 2026!",
            },
            preauth["csrfToken"],
        )
        self.assertEqual(logged_in, 200)
        self.assertNotIn("127.0.0.1", self.app.failures)

        session_status, _, session_body = self.request(
            "/api/auth/session"
        )

        self.assertEqual(session_status, 200)

        session = json.loads(session_body)

        self.assertTrue(session["authenticated"])
        self.assertEqual(
            session["user"]["role"],
            "owner",
        )

        # Verify that the browser session becomes a valid signed
        # proxy identity accepted by the Gateway.
        api_status, _, api_body = self.request(
            "/api/cloud-runners/status"
        )

        self.assertEqual(
            api_status,
            200,
            api_body.decode(errors="replace"),
        )

        api = json.loads(api_body)

        self.assertEqual(api["gateway"], "READY")
        self.assertFalse(api["provisioning_enabled"])

        gates_status, _, gates_body = self.request("/api/infrastructure/gates")
        self.assertEqual(gates_status, 200, gates_body.decode(errors="replace"))
        gates = json.loads(gates_body)["gates"]
        self.assertFalse(gates["cloud_provisioning"]["enabled"])
        self.assertFalse(gates["vm_creation"]["enabled"])

        gate_off, _, gate_off_body = self.request(
            "/api/infrastructure/gates/vm_creation", "POST",
            {"enabled": False}, session["csrfToken"],
        )
        self.assertEqual(gate_off, 200, gate_off_body.decode(errors="replace"))
        self.assertFalse(json.loads(gate_off_body)["gate"]["enabled"])

        gate_on, _, gate_on_body = self.request(
            "/api/infrastructure/gates/vm_creation", "POST",
            {"enabled": True, "confirmation": "ENABLE VM CREATION"},
            session["csrfToken"],
        )
        self.assertEqual(gate_on, 503, gate_on_body.decode(errors="replace"))
        self.assertIn("not ready", json.loads(gate_on_body)["error"])

        no_csrf, _, _ = self.request(
            "/api/auth/logout",
            "POST",
        )
        self.assertEqual(no_csrf, 403)

        logged_out, _, _ = self.request(
            "/api/auth/logout",
            "POST",
            csrf=session["csrfToken"],
        )
        self.assertEqual(logged_out, 200)

        denied_after_logout, _, _ = self.request(
            "/api/cloud-runners/status"
        )
        self.assertEqual(denied_after_logout, 401)

    def test_preview_proxy_requires_session_and_sandboxes_preview_documents(self):
        import base64
        import uuid

        job_id = str(uuid.uuid4())
        runtime_id = str(uuid.uuid4())
        path = f"/api/jobs/{job_id}/previews/{runtime_id}/content/index.html"
        denied, _, _ = self.request(path)
        self.assertEqual(denied, 401)

        _, _, preauth_body = self.request("/api/auth/session")
        csrf = json.loads(preauth_body)["csrfToken"]
        logged_in, _, _ = self.request(
            "/api/auth/login",
            "POST",
            {"username": "owner-test", "password": "correct horse battery staple 2026!"},
            csrf,
        )
        self.assertEqual(logged_in, 200)

        payload = json.dumps({
            "content_type": "text/html; charset=utf-8",
            "body_base64": base64.b64encode(b"<h1>Preview</h1>").decode("ascii"),
        }).encode("utf-8")
        with patch.object(self.app, "gateway_request", return_value=(200, payload)) as gateway:
            status, headers, body = self.request(path)
        self.assertEqual(status, 200)
        self.assertEqual(body, b"<h1>Preview</h1>")
        self.assertIn("sandbox allow-scripts", headers.get("Content-Security-Policy", ""))
        self.assertEqual(headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertNotIn("session_token", body.decode("utf-8", "ignore"))
        gateway.assert_called_once()
        _, _, session_body = self.request("/api/auth/session")
        logout_csrf = json.loads(session_body)["csrfToken"]
        logged_out, _, _ = self.request(
            "/api/auth/logout", "POST", csrf=logout_csrf
        )
        self.assertEqual(logged_out, 200)

    @unittest.skipUnless(_chromium_ready(), "Python Playwright and Chromium are optional test prerequisites")
    def test_real_chromium_loads_app_through_authenticated_preview_proxy(self):
        import uuid
        from playwright.sync_api import sync_playwright

        from tools.cloud_gateway.job_control import JobStore
        from tools.local_runner_agent.workspace import WorkspaceManager

        worker_id = "preview-chromium-worker"
        jobs = JobStore(self.jobs_db)
        job, created = jobs.create(
            {
                "repository": "example/preview-chromium-fixture",
                "commit_sha": "b" * 40,
                "target": "build_static_web",
            },
            "authenticated-preview-chromium-0001",
        )
        self.assertTrue(created)
        claimed = jobs.claim(worker_id, allowed_targets=["build_static_web"])
        self.assertEqual(claimed["id"], job["id"])

        workspace = WorkspaceManager(self.workspace_root).create(job["id"], worker_id)
        dist = workspace / "source" / "dist"
        (dist / "assets").mkdir(parents=True)
        (dist / "index.html").write_text(
            "<!doctype html><html lang='en'><head><meta name='viewport' "
            "content='width=device-width,initial-scale=1'><title>Preview Proxy Browser E2E</title>"
            "<link rel='icon' href='data:,'><link rel='stylesheet' href='assets/site.css'></head>"
            "<body><main><h1 id='preview-ready'>Browser reached authenticated preview</h1>"
            "<button type='button'>Continue</button></main></body></html>",
            encoding="utf-8",
        )
        (dist / "assets" / "site.css").write_text(
            "body { color: rgb(1, 2, 3); }", encoding="utf-8"
        )
        jobs.finish(job["id"], worker_id, "succeeded", {"exit_code": 0})

        browser = None
        preview = None
        csrf = None
        try:
            _, _, preauth_body = self.request("/api/auth/session")
            preauth = json.loads(preauth_body)
            login, _, login_body = self.request(
                "/api/auth/login", "POST",
                {"username": "owner-test", "password": "correct horse battery staple 2026!"},
                preauth["csrfToken"],
            )
            self.assertEqual(login, 200, login_body.decode(errors="replace"))
            _, _, session_body = self.request("/api/auth/session")
            csrf = json.loads(session_body)["csrfToken"]

            started, start_headers, start_body = self.request(
                f"/api/jobs/{job['id']}/previews", "POST", {}, csrf
            )
            self.assertEqual(started, 201, start_body.decode(errors="replace"))
            preview = json.loads(start_body)
            self.assertTrue(preview["preview_path"].endswith("/content/"))
            self.assertNotIn("port", preview)
            self.assertNotIn("session_token", start_body.decode("utf-8", "ignore"))
            css_status, css_headers, css_body = self.request(
                preview["preview_path"] + "assets/site.css"
            )
            self.assertEqual(css_status, 200, css_body.decode("utf-8", "replace"))
            self.assertIn("text/css", css_headers.get("Content-Type", ""))
            self.assertIn(b"rgb(1, 2, 3)", css_body)

            from http.cookies import SimpleCookie
            preview_set_cookie = start_headers.get("Set-Cookie", "")
            parsed_preview_cookie = SimpleCookie()
            parsed_preview_cookie.load(preview_set_cookie)
            preview_cookie_name = next(
                (name for name in parsed_preview_cookie if name.startswith("DCP_PREVIEW_")),
                None,
            )
            self.assertIsNotNone(preview_cookie_name, preview_set_cookie)
            preview_cookie = parsed_preview_cookie[preview_cookie_name]
            self.assertTrue(preview_cookie["httponly"])
            self.assertTrue(preview_cookie["secure"])
            self.assertEqual(preview_cookie["samesite"], "None")
            self.assertEqual(preview_cookie["path"], preview["preview_path"])
            self.assertGreater(int(preview_cookie["max-age"]), 0)
            cookies = [{
                "name": preview_cookie_name,
                "value": preview_cookie.value,
                "domain": "127.0.0.1",
                "path": preview_cookie["path"],
                "httpOnly": True,
                "secure": True,
                "sameSite": "None",
            }]

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True, chromium_sandbox=True)
                try:
                    context = browser.new_context(viewport={"width": 1366, "height": 768})
                    context.add_cookies(cookies)
                    page = context.new_page()
                    console_errors = []
                    page_errors = []
                    failed_requests = []
                    request_urls = []
                    css_requests = []
                    asset_responses = []
                    page.on("console", lambda message: console_errors.append(message.text) if message.type == "error" else None)
                    page.on("pageerror", lambda error: page_errors.append(str(error)))

                    def capture_request(request):
                        request_urls.append(request.url)
                        if "site.css" in request.url:
                            css_requests.append({
                                "url": request.url,
                                "headers": request.all_headers(),
                            })

                    def capture_failed_request(request):
                        if "site.css" in request.url:
                            failed_requests.append({
                                "url": request.url,
                                "failure": request.failure,
                            })

                    page.on("requestfailed", capture_failed_request)
                    page.on("request", capture_request)

                    def capture_asset_response(response):
                        if "site.css" in response.url:
                            asset_responses.append({
                                "url": response.url,
                                "status": response.status,
                                "content_type": response.headers.get("content-type"),
                            })

                    page.on("response", capture_asset_response)
                    response = page.goto(
                        self.base + preview["preview_path"],
                        wait_until="networkidle",
                        timeout=15000,
                    )
                    self.assertIsNotNone(response)
                    self.assertEqual(response.status, 200)
                    self.assertEqual(page.title(), "Preview Proxy Browser E2E")
                    self.assertEqual(
                        page.locator("#preview-ready").inner_text(),
                        "Browser reached authenticated preview",
                    )
                    css_color = page.locator("body").evaluate(
                        "(element) => getComputedStyle(element).color"
                    )
                    self.assertEqual(
                        css_color, "rgb(1, 2, 3)",
                        "CSS diagnostics: responses=%r console=%r requests=%r css_requests=%r failed=%r cookies=%r" % (
                            asset_responses, console_errors, request_urls, css_requests,
                            failed_requests, context.cookies(self.base)
                        ),
                    )
                    self.assertEqual(len(asset_responses), 1)
                    self.assertEqual(asset_responses[0]["status"], 200)
                    self.assertTrue(any("/content/assets/site.css" in url for url in request_urls))
                    http_requests = [
                    url for url in request_urls
                    if url.startswith(("http://", "https://"))
                ]
                self.assertTrue(http_requests)
                self.assertTrue(all(url.startswith(self.base + "/") for url in http_requests))
                    self.assertEqual(console_errors, [])
                    self.assertEqual(page_errors, [])
                    self.assertEqual(failed_requests, [])
    
                    screenshot = Path(self.temp.name) / "authenticated-preview.png"
                    page.screenshot(path=str(screenshot), full_page=True)
                    self.assertTrue(screenshot.is_file())
    
                    stopped, stop_headers, stop_body = self.request(
                        f"/api/jobs/{job['id']}/previews/{preview['runtime_id']}",
                        "DELETE", csrf=csrf,
                    )
                    self.assertEqual(stopped, 200, stop_body.decode(errors="replace"))
                    self.assertIn("Max-Age=0", stop_headers.get("Set-Cookie", ""))
                    after_stop = page.goto(
                        self.base + preview["preview_path"],
                        wait_until="domcontentloaded",
                        timeout=10000,
                    )
                    self.assertIsNotNone(after_stop)
                    self.assertEqual(after_stop.status, 404)
                    context.close()
                finally:
                    browser.close()
                    browser = None
        finally:
            if browser is not None:
                browser.close()
            if preview and csrf:
                self.request(
                    f"/api/jobs/{job['id']}/previews/{preview['runtime_id']}",
                    "DELETE", csrf=csrf,
                )
            if csrf:
                self.request("/api/auth/logout", "POST", csrf=csrf)

    def test_real_authenticated_preview_proxy_serves_and_stops_completed_job(self):
        import uuid

        from tools.cloud_gateway.job_control import JobStore
        from tools.local_runner_agent.workspace import WorkspaceManager

        worker_id = "preview-e2e-worker"
        jobs = JobStore(self.jobs_db)
        job, created = jobs.create(
            {
                "repository": "example/preview-fixture",
                "commit_sha": "a" * 40,
                "target": "build_static_web",
            },
            "authenticated-preview-e2e-0001",
        )
        self.assertTrue(created)
        claimed = jobs.claim(worker_id, allowed_targets=["build_static_web"])
        self.assertEqual(claimed["id"], job["id"])

        workspaces = WorkspaceManager(self.workspace_root)
        workspace = workspaces.create(job["id"], worker_id)
        dist = workspace / "source" / "dist"
        (dist / "assets").mkdir(parents=True)
        html = (
            "<!doctype html><html lang='en'><head><title>DCP Preview E2E</title>"
            "<link rel='stylesheet' href='/assets/site.css'></head>"
            "<body><h1 id='preview-ready'>Authenticated preview works</h1></body></html>"
        )
        (dist / "index.html").write_text(html, encoding="utf-8")
        (dist / "assets" / "site.css").write_text(
            "body { color: rgb(1, 2, 3); }", encoding="utf-8"
        )
        completed = jobs.finish(
            job["id"], worker_id, "succeeded", {"exit_code": 0}
        )
        self.assertEqual(completed["state"], "succeeded")
        self.assertIsNone(completed["worker"])
        self.assertEqual(completed["last_worker"], worker_id)

        _, _, preauth_body = self.request("/api/auth/session")
        preauth = json.loads(preauth_body)
        denied, _, _ = self.request(
            f"/api/jobs/{job['id']}/previews"
        )
        self.assertEqual(denied, 401)

        logged_in, _, _ = self.request(
            "/api/auth/login",
            "POST",
            {
                "username": "owner-test",
                "password": "correct horse battery staple 2026!",
            },
            preauth["csrfToken"],
        )
        self.assertEqual(logged_in, 200)
        _, _, session_body = self.request("/api/auth/session")
        csrf = json.loads(session_body)["csrfToken"]

        preview_list_path = f"/api/jobs/{job['id']}/previews"
        self.assertRegex(job["id"], r"^[0-9a-f-]{36}$")
        cookie_header = "; ".join(
            f"{cookie.name}={cookie.value}" for cookie in self.cookie_jar
        )
        owner_session = self.app.get_session(cookie_header)
        self.assertTrue(owner_session and owner_session["authenticated"])
        direct_status, direct_body = self.app.gateway_request(
            "GET", preview_list_path, owner_session
        )
        self.assertEqual(
            direct_status, 200,
            "Gateway preview-list route failed: " + direct_body.decode(errors="replace"),
        )

        listed, _, list_body = self.request(preview_list_path)
        self.assertEqual(listed, 200, list_body.decode(errors="replace"))
        self.assertEqual(json.loads(list_body)["previews"], [])

        started, _, start_body = self.request(
            f"/api/jobs/{job['id']}/previews",
            "POST",
            {},
            csrf,
        )
        self.assertEqual(started, 201, start_body.decode(errors="replace"))
        preview = json.loads(start_body)
        self.assertEqual(preview["job_id"], job["id"])
        self.assertEqual(preview["state"], "running")
        self.assertTrue(preview["preview_path"].endswith("/content/"))
        self.assertNotIn("session_token", start_body.decode("utf-8"))
        self.assertNotIn("port", preview)
        self.assertNotIn("url", preview)

        listed, _, list_body = self.request(
            f"/api/jobs/{job['id']}/previews"
        )
        self.assertEqual(listed, 200)
        self.assertEqual(len(json.loads(list_body)["previews"]), 1)
        self.assertEqual(
            json.loads(list_body)["previews"][0]["runtime_id"],
            preview["runtime_id"],
        )

        status, _, status_body = self.request(
            f"/api/jobs/{job['id']}/previews/{preview['runtime_id']}"
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(status_body)["state"], "running")

        content_status, content_headers, content_body = self.request(
            preview["preview_path"] + "index.html"
        )
        self.assertEqual(content_status, 200)
        self.assertIn(b"Authenticated preview works", content_body)
        self.assertIn("sandbox allow-scripts", content_headers.get("Content-Security-Policy", ""))
        self.assertEqual(content_headers.get("X-Frame-Options"), "SAMEORIGIN")
        self.assertEqual(content_headers.get("X-Content-Type-Options"), "nosniff")
        self.assertNotIn("session_token", content_body.decode("utf-8", "ignore"))

        asset_status, asset_headers, asset_body = self.request(
            preview["preview_path"] + "assets/site.css"
        )
        self.assertEqual(asset_status, 200)
        self.assertIn("text/css", asset_headers.get("Content-Type", ""))
        self.assertIn(b"rgb(1, 2, 3)", asset_body)

        other_job_id = str(uuid.uuid4())
        cross_job, _, _ = self.request(
            f"/api/jobs/{other_job_id}/previews/{preview['runtime_id']}/content/index.html"
        )
        self.assertEqual(cross_job, 404)
        query_status, _, _ = self.request(
            preview["preview_path"] + "index.html?external=1"
        )
        self.assertEqual(query_status, 400)

        stopped, _, stop_body = self.request(
            f"/api/jobs/{job['id']}/previews/{preview['runtime_id']}",
            "DELETE",
            csrf=csrf,
        )
        self.assertEqual(stopped, 200, stop_body.decode(errors="replace"))
        stopped_status, _, _ = self.request(
            f"/api/jobs/{job['id']}/previews/{preview['runtime_id']}"
        )
        self.assertEqual(stopped_status, 404)

        logged_out, _, _ = self.request(
            "/api/auth/logout", "POST", csrf=csrf
        )
        self.assertEqual(logged_out, 200)
        denied_after_logout, _, _ = self.request(
            preview["preview_path"] + "index.html"
        )
        self.assertEqual(denied_after_logout, 401)

    def test_job_creation_proxy_forwards_idempotency_key_and_owner_csrf(self):
        _, _, preauth_body = self.request("/api/auth/session")
        csrf = json.loads(preauth_body)["csrfToken"]
        status, _, _ = self.request(
            "/api/auth/login", "POST",
            {"username": "owner-test", "password": "correct horse battery staple 2026!"},
            csrf,
        )
        self.assertEqual(status, 200)
        _, _, session_body = self.request("/api/auth/session")
        csrf = json.loads(session_body)["csrfToken"]
        payload = {
            "source_type": "local_folder",
            "project_id": "12345678-1234-4234-8234-123456789abc",
            "snapshot_sha256": "a" * 64,
            "target": "build_static_web",
        }
        with patch.object(self.app, "gateway_request", return_value=(202, b'{"id":"job"}')) as gateway:
            status, _, body = self.request(
                "/api/jobs", "POST", payload, csrf,
                idempotency_key="local-proxy-job-0001",
            )
        self.assertEqual(status, 202)
        self.assertEqual(json.loads(body)["id"], "job")
        args, kwargs = gateway.call_args
        self.assertEqual(args[:2], ("POST", "/api/jobs"))
        self.assertTrue(args[2]["authenticated"])
        self.assertEqual(kwargs["idempotency_key"], "local-proxy-job-0001")
        self.assertEqual(json.loads(args[3]), payload)
        _, _, session_body = self.request("/api/auth/session")
        logout_csrf = json.loads(session_body)["csrfToken"]
        self.assertEqual(self.request("/api/auth/logout", "POST", csrf=logout_csrf)[0], 200)

    def test_origin_and_csrf_protections_fail_closed(self):
        _, _, body = self.request(
            "/api/auth/session"
        )

        csrf = json.loads(body)["csrfToken"]

        bad_origin, _, _ = self.request(
            "/api/auth/login",
            "POST",
            {
                "username": "owner-test",
                "password": "wrong",
            },
            csrf,
            origin=False,
        )

        self.assertEqual(bad_origin, 403)

    def test_dashboard_served_by_same_origin_proxy_without_gateway_secret(
        self,
    ):
        with urlopen(
            self.base + "/",
            timeout=3,
        ) as response:
            html = response.read().decode("utf-8")
            self.assertEqual(response.status, 200)

        self.assertIn("auth-login-form", html)
        self.assertIn('id="auth-forgot-password"', html)
        self.assertIn('id="auth-recovery-help"', html)
        self.assertIn("Reset-DCP-Owner-Password.cmd", html)
        self.assertIn("Start-DCP-Local.cmd", html)
        self.assertIn("ยังไม่มีการกู้คืนผ่านอีเมล", html)
        self.assertNotIn(self.token, html)
        self.assertNotIn(self.secret, html)



class LocalRunnerCredentialFileTests(unittest.TestCase):
    def test_missing_runner_credential_file_returns_empty_map(self):
        with tempfile.TemporaryDirectory() as temp:
            self.assertEqual(auth.load_runner_tokens(Path(temp) / "missing.json"), {})

    def test_gateway_environment_defaults_shared_workspace_root_to_local_data_dir(self):
        with tempfile.TemporaryDirectory() as temp:
            credentials_file = Path(temp) / "owner-auth.json"
            with patch.object(auth, "CREDENTIALS", credentials_file):
                env = auth.gateway_child_environment({"PATH": "safe-path"})
            self.assertEqual(env["DCP_RUNNER_WORKSPACE_ROOT"], str(Path(temp) / "workspaces"))

    def test_gateway_environment_preserves_explicit_shared_workspace_root(self):
        with tempfile.TemporaryDirectory() as temp:
            explicit = str(Path(temp) / "runner-workspaces")
            with patch.object(auth, "CREDENTIALS", Path(temp) / "owner-auth.json"):
                env = auth.gateway_child_environment({"DCP_RUNNER_WORKSPACE_ROOT": explicit})
            self.assertEqual(env["DCP_RUNNER_WORKSPACE_ROOT"], explicit)

    def test_gateway_environment_uses_protected_file_runner_map(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner-tokens.json"
            credentials = {"windows-local-01": "r" * 48}
            path.write_text(json.dumps(credentials), encoding="utf-8")
            with patch.object(auth, "RUNNER_TOKENS_FILE", path):
                env = auth.gateway_child_environment({
                    "PATH": "safe-path",
                    "DCP_RUNNER_TOKENS": "inherited-value-must-be-overridden",
                })
            self.assertEqual(
                json.loads(env["DCP_RUNNER_TOKENS"]),
                credentials,
            )
            self.assertEqual(env["PATH"], "safe-path")

    def test_gateway_environment_keeps_explicit_environment_when_no_file_exists(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch.object(auth, "RUNNER_TOKENS_FILE", Path(temp) / "missing.json"):
                env = auth.gateway_child_environment({"DCP_RUNNER_TOKENS": '{"worker":"' + "x" * 40 + '"}'})
            self.assertIn("DCP_RUNNER_TOKENS", env)

    def test_loads_valid_local_runner_credential_map(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner-tokens.json"
            credentials = {
                "windows-local-01": "a" * 48,
                "linux-build-01": "b" * 48,
            }
            path.write_text(json.dumps(credentials), encoding="utf-8")
            self.assertEqual(auth.load_runner_tokens(path), credentials)

    def test_rejects_invalid_or_duplicate_runner_credentials(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner-tokens.json"
            for credentials in (
                [],
                {"bad/worker": "a" * 48},
                {"worker": "short"},
                {"worker-a": "a" * 48, "worker-b": "a" * 48},
            ):
                with self.subTest(credentials=list(credentials) if isinstance(credentials, dict) else credentials):
                    path.write_text(json.dumps(credentials), encoding="utf-8")
                    with self.assertRaises(SystemExit):
                        auth.load_runner_tokens(path)

    def test_rejects_duplicate_json_worker_keys(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner-tokens.json"
            path.write_text(
                '{"worker":"' + "a" * 48 + '","worker":"' + "b" * 48 + '"}',
                encoding="utf-8",
            )
            with self.assertRaisesRegex(SystemExit, "invalid JSON"):
                auth.load_runner_tokens(path)

    def test_rejects_broken_symlink_runner_credential_file(self):
        with tempfile.TemporaryDirectory() as temp:
            link = Path(temp) / "runner-tokens.json"
            try:
                link.symlink_to(Path(temp) / "missing-target.json")
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation is not available on this host")
            with self.assertRaisesRegex(SystemExit, "symlink"):
                auth.load_runner_tokens(link)

    def test_rejects_symlink_runner_credential_file(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            actual = root / "actual.json"
            actual.write_text(json.dumps({"worker": "a" * 48}), encoding="utf-8")
            link = root / "runner-tokens.json"
            try:
                link.symlink_to(actual)
            except (OSError, NotImplementedError):
                self.skipTest("Symlink creation is not available on this host")
            with self.assertRaisesRegex(SystemExit, "symlink"):
                auth.load_runner_tokens(link)

    def test_rejects_oversized_runner_credential_file(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "runner-tokens.json"
            path.write_text(" " * (auth.MAX_RUNNER_TOKEN_FILE_BYTES + 1), encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "size limit"):
                auth.load_runner_tokens(path)

if __name__ == "__main__":
    unittest.main()
