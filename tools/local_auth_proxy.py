"""Loopback-only local auth/session broker and signed Gateway reverse proxy.

The browser never receives Gateway credentials or the HMAC signing secret.
"""
from __future__ import annotations

import getpass
import hashlib
import hmac
import json
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import unquote, urlparse
from urllib.request import Request, urlopen

HOST = "127.0.0.1"
PORT = int(os.getenv("DCP_LOCAL_PORT", "8789"))
GATEWAY_PORT = int(os.getenv("DCP_GATEWAY_PORT", "18790"))
SESSION_TTL = 12 * 60 * 60
PBKDF2_ROUNDS = 600_000
MIN_PASSWORD_LENGTH = 14
COOKIE = "DCP_LOCAL_SESSION"
MAX_BODY = 32_768
MAX_PREVIEW_RESPONSE_BYTES = 12 * 1024 * 1024
MAX_ARTIFACT_DOWNLOAD_BYTES = 1024 * 1024 * 1024
MAX_DASHBOARD_READ_RESPONSE_BYTES = 1024 * 1024
ALLOWED_GET = ("/api/cloud-runners/status", "/api/cloud-runners", "/api/local-projects", "/api/local-projects/roots", "/api/github/repositories", "/api/infrastructure/gates", "/api/runners", "/api/terminal/templates", "/api/infrastructure")
CREDENTIALS = Path(os.getenv("DCP_LOCAL_AUTH_CREDENTIAL_FILE", str(Path(os.getenv("LOCALAPPDATA", str(Path.home()))) / "DCP" / "owner-auth.json")))


RUNNER_TOKENS_FILE = CREDENTIALS.parent / "runner-tokens.json"
MAX_RUNNER_TOKEN_FILE_BYTES = 64 * 1024


def _unique_runner_token_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate worker ID")
        result[key] = value
    return result


def load_runner_tokens(path: Path | None = None) -> dict[str, str]:
    """Load the protected local Runner token map without logging or exposing secrets."""
    target = Path(path) if path is not None else RUNNER_TOKENS_FILE
    if target.is_symlink():
        raise SystemExit("Local Runner credential file must not be a symlink")
    if not target.exists():
        return {}
    if not target.is_file():
        raise SystemExit("Local Runner credential file must be a regular non-symlink file")
    if target.stat().st_size > MAX_RUNNER_TOKEN_FILE_BYTES:
        raise SystemExit("Local Runner credential file exceeds its size limit")
    try:
        value = json.loads(
            target.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_runner_token_object,
        )
    except (OSError, UnicodeDecodeError, json.JSONDecodeError, ValueError):
        raise SystemExit("Local Runner credential file is unreadable or invalid JSON") from None
    if not isinstance(value, dict) or not 1 <= len(value) <= 16:
        raise SystemExit("Local Runner credential file must contain 1..16 worker credentials")
    for worker, token in value.items():
        if (
            not isinstance(worker, str)
            or not re.fullmatch(r"[A-Za-z0-9_.:-]{1,100}", worker)
            or not isinstance(token, str)
            or len(token) < 32
            or len(token) > 256
        ):
            raise SystemExit("Local Runner credential file contains an invalid worker credential")
    if len(set(value.values())) != len(value):
        raise SystemExit("Local Runner credentials must be unique per worker")
    return value


def gateway_child_environment(base_environment=None) -> dict[str, str]:
    """Prepare the Gateway environment, overriding any inherited Runner map with the protected file."""
    env = dict(os.environ if base_environment is None else base_environment)
    if not str(env.get("DCP_RUNNER_WORKSPACE_ROOT", "")).strip():
        env["DCP_RUNNER_WORKSPACE_ROOT"] = str(CREDENTIALS.parent / "workspaces")
    runner_tokens = load_runner_tokens()
    if runner_tokens:
        env["DCP_RUNNER_TOKENS"] = json.dumps(runner_tokens, separators=(",", ":"))
    return env


def password_record(username: str, password: str, salt: bytes | None = None) -> dict:
    salt = salt or secrets.token_bytes(32)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PBKDF2_ROUNDS)
    return {"username": username, "salt": salt.hex(), "password_hash": digest.hex(),
            "rounds": PBKDF2_ROUNDS, "algorithm": "pbkdf2_sha256"}


def verify_password(record: dict, username: str, password: str) -> bool:
    try:
        if record.get("algorithm") != "pbkdf2_sha256" or int(record["rounds"]) < 300_000:
            return False
        candidate = hashlib.pbkdf2_hmac(
            "sha256", password.encode("utf-8"), bytes.fromhex(record["salt"]), int(record["rounds"])
        ).hex()
        return hmac.compare_digest(str(record["username"]).encode("utf-8"), username.encode("utf-8")) and hmac.compare_digest(
            candidate, str(record["password_hash"])
        )
    except (KeyError, TypeError, ValueError):
        return False


def load_or_create_credentials(path: Path = CREDENTIALS) -> dict:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            if (not isinstance(record, dict) or not isinstance(record.get("username"), str)
                    or not record["username"] or record.get("algorithm") != "pbkdf2_sha256"
                    or len(bytes.fromhex(record["salt"])) != 32
                    or len(bytes.fromhex(record["password_hash"])) != 32
                    or int(record["rounds"]) < 300_000):
                raise ValueError("invalid credential record")
            return record
        except Exception as exc:
            raise RuntimeError(f"Owner credential file is invalid; preserve it and inspect {path}") from exc

    print("DCP first-time owner setup (credentials are stored as a salted PBKDF2 hash).", flush=True)
    username = input("Choose owner username: ").strip()
    if (not username or len(username) > 64 or not all(
            c.isascii() and (c.isalnum() or c in "._@-") for c in username
    )):
        raise SystemExit("Username must be 1..64 ASCII letters, digits, dot, underscore, @, or hyphen.")
    while True:
        password = getpass.getpass("Choose owner password (minimum 14 characters): ")
        if len(password) < MIN_PASSWORD_LENGTH:
            print(f"Password must contain at least {MIN_PASSWORD_LENGTH} characters.", flush=True)
            continue
        confirmation = getpass.getpass("Confirm owner password: ")
        if not hmac.compare_digest(password, confirmation):
            print("Passwords do not match.", flush=True)
            continue
        break
    record = password_record(username, password)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(record), encoding="utf-8")
    try:
        if os.name == "nt":
            # Restrict the file to the current Windows account; inherited profile ACLs remain.
            import subprocess as _sp
            _sp.run(["icacls", str(temporary), "/inheritance:r", "/grant:r",
                     f"{os.getenv('USERDOMAIN', '')}\\{os.getenv('USERNAME', '')}:(F)"],
                    check=True, capture_output=True)
        else:
            temporary.chmod(0o600)
        os.replace(temporary, path)
    finally:
        if temporary.exists():
            temporary.unlink()
    return record


class LocalAuthProxy:
    def __init__(self, credentials: dict, gateway_token: str, proxy_secret: str,
                 gateway_port: int = GATEWAY_PORT):
        self.credentials = credentials
        self.gateway_token = gateway_token
        self.proxy_secret = proxy_secret.encode("utf-8")
        self.gateway_port = gateway_port
        self.sessions: dict[str, dict] = {}
        self.preview_sessions: dict[tuple[str, str], dict] = {}
        self.lock = threading.RLock()
        self.failures: dict[str, list[float]] = {}

    def csrf(self, session: dict) -> str:
        msg = "csrf\n" + session["username"] + "\n" + session["id"]
        return hmac.new(self.proxy_secret, msg.encode(), hashlib.sha256).hexdigest()

    def new_session(self, authenticated: bool) -> tuple[str, dict]:
        sid = secrets.token_urlsafe(32)
        session = {"id": sid, "username": self.credentials["username"] if authenticated else "",
                   "authenticated": authenticated, "created": time.time(),
                   "csrf": secrets.token_urlsafe(32)}
        with self.lock:
            self.sessions[sid] = session
        return sid, session

    def get_session(self, cookie_header: str) -> dict | None:
        token = ""
        for part in cookie_header.split(";"):
            key, sep, value = part.strip().partition("=")
            if sep and key == COOKIE:
                token = value
        if not token:
            return None
        with self.lock:
            session = self.sessions.get(token)
            if not session:
                return None
            if time.time() - session["created"] > SESSION_TTL:
                self.sessions.pop(token, None)
                for key, record in list(self.preview_sessions.items()):
                    if record["session_id"] == token:
                        self.preview_sessions.pop(key, None)
                return None
            return session

    @staticmethod
    def _preview_cookie_name(job_id: str, runtime_id: str) -> str:
        uuid_pattern = r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}"
        if not re.fullmatch(uuid_pattern, job_id or "") or not re.fullmatch(uuid_pattern, runtime_id or ""):
            raise ValueError("invalid preview identity")
        return "DCP_PREVIEW_" + runtime_id.replace("-", "").upper()

    @staticmethod
    def _preview_cookie_path(job_id: str, runtime_id: str) -> str:
        return f"/api/jobs/{job_id}/previews/{runtime_id}/content/"

    def create_preview_cookie(
        self, job_id: str, runtime_id: str, session: dict, expires_in_seconds: int
    ) -> str:
        if (
            isinstance(expires_in_seconds, bool)
            or not isinstance(expires_in_seconds, int)
            or not 1 <= expires_in_seconds <= 86400
            or not session.get("authenticated")
        ):
            raise ValueError("invalid preview cookie lifetime or session")
        name = self._preview_cookie_name(job_id, runtime_id)
        path = self._preview_cookie_path(job_id, runtime_id)
        token = secrets.token_urlsafe(32)
        now = time.time()
        session_remaining = max(1, int(SESSION_TTL - (now - session["created"])))
        ttl = min(expires_in_seconds, session_remaining)
        with self.lock:
            for key, record in list(self.preview_sessions.items()):
                if record["expires_at"] <= now:
                    self.preview_sessions.pop(key, None)
            self.preview_sessions[(job_id, runtime_id)] = {
                "token": token,
                "session_id": session["id"],
                "expires_at": now + ttl,
            }
        return f"{name}={token}; HttpOnly; Secure; SameSite=None; Path={path}; Max-Age={ttl}"

    def get_preview_session(self, job_id: str, runtime_id: str, cookie_header: str) -> dict | None:
        try:
            name = self._preview_cookie_name(job_id, runtime_id)
        except ValueError:
            return None
        token = ""
        for part in cookie_header.split(";"):
            key, sep, value = part.strip().partition("=")
            if sep and key == name:
                token = value
        if not token:
            return None
        now = time.time()
        with self.lock:
            record = self.preview_sessions.get((job_id, runtime_id))
            if not record:
                return None
            if record["expires_at"] <= now:
                self.preview_sessions.pop((job_id, runtime_id), None)
                return None
            if not hmac.compare_digest(token, record["token"]):
                return None
            session = self.sessions.get(record["session_id"])
            if (
                not session
                or not session.get("authenticated")
                or now - session["created"] > SESSION_TTL
            ):
                self.preview_sessions.pop((job_id, runtime_id), None)
                return None
            return session

    def revoke_preview_session(self, job_id: str, runtime_id: str) -> str:
        name = self._preview_cookie_name(job_id, runtime_id)
        path = self._preview_cookie_path(job_id, runtime_id)
        with self.lock:
            self.preview_sessions.pop((job_id, runtime_id), None)
        return f"{name}=; HttpOnly; Secure; SameSite=None; Path={path}; Max-Age=0"

    def revoke_session_previews(self, session_id: str) -> list[str]:
        cookies = []
        with self.lock:
            keys = [
                key for key, record in self.preview_sessions.items()
                if record["session_id"] == session_id
            ]
            for job_id, runtime_id in keys:
                self.preview_sessions.pop((job_id, runtime_id), None)
                name = self._preview_cookie_name(job_id, runtime_id)
                path = self._preview_cookie_path(job_id, runtime_id)
                cookies.append(
                    f"{name}=; HttpOnly; Secure; SameSite=None; Path={path}; Max-Age=0"
                )
        return cookies

    def sign_gateway(self, method: str, path: str, session: dict) -> dict:
        timestamp = str(int(time.time()))
        nonce = secrets.token_urlsafe(24)
        canonical = "\n".join((method, path, session["username"], "owner",
                                session["id"], timestamp, nonce)).encode("utf-8")
        signature = hmac.new(self.proxy_secret, canonical, hashlib.sha256).hexdigest()
        return {
            "Authorization": "Bearer " + self.gateway_token,
            "X-DCP-User": session["username"], "X-DCP-Role": "owner",
            "X-DCP-Session": session["id"], "X-DCP-Auth-Timestamp": timestamp,
            "X-DCP-Auth-Nonce": nonce, "X-DCP-Auth-Signature": signature,
            "Origin": f"http://{HOST}:{PORT}", "Accept": "application/json",
        }

    def gateway_request(self, method: str, path: str, session: dict, body: bytes = b"",
                        csrf_token: str = "", max_response_bytes: int = MAX_BODY,
                        idempotency_key: str = "") -> tuple[int, bytes]:
        headers = self.sign_gateway(method, urlparse(path).path, session)
        if csrf_token:
            expected = hmac.new(
                self.proxy_secret,
                ("csrf\n" + session["username"] + "\n" + session["id"]).encode(),
                hashlib.sha256,
            ).hexdigest()
            if not hmac.compare_digest(csrf_token, expected):
                return 403, b'{"error":"CSRF validation failed"}'
            headers["X-CSRF-Token"] = expected
        if idempotency_key:
            if not re.fullmatch(r"[A-Za-z0-9._:-]{8,200}", idempotency_key):
                return 400, b'{"error":"Invalid Idempotency-Key"}'
            headers["Idempotency-Key"] = idempotency_key
        if body:
            headers["Content-Type"] = "application/json"
            headers["Content-Length"] = str(len(body))
        request = Request(f"http://{HOST}:{self.gateway_port}{path}", data=body or None,
                          headers=headers, method=method)
        try:
            with urlopen(request, timeout=5) as response:
                return response.status, response.read(max_response_bytes + 1)
        except HTTPError as exc:
            return exc.code, exc.read(max_response_bytes + 1)
        except (URLError, TimeoutError, OSError):
            return 503, b'{"error":"Gateway unavailable"}'


def make_handler(app: LocalAuthProxy, dashboard_dir: Path):
    root = dashboard_dir.resolve()

    class Handler(BaseHTTPRequestHandler):
        server_version = "DCP-Local-Auth/1.0"

        def log_message(self, fmt, *args):
            return

        def send_bytes(self, status: int, data: bytes, content_type: str = "application/json",
                       cookie: str | None = None, allow_same_origin_frame: bool = False,
                       cookies: list[str] | None = None):
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("X-Frame-Options", "SAMEORIGIN" if allow_same_origin_frame else "DENY")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy",
                             ("sandbox allow-scripts; default-src * data: blob:; "
                              "script-src * 'unsafe-inline' 'unsafe-eval'; "
                              "style-src * 'unsafe-inline'; img-src * data: blob:; "
                              "connect-src *; font-src * data:; media-src *; "
                              "form-action 'none'; base-uri 'none'; frame-ancestors 'self'")
                             if allow_same_origin_frame
                             else "frame-ancestors 'none'; base-uri 'self'")
            if cookie:
                self.send_header("Set-Cookie", cookie)
            for extra_cookie in cookies or []:
                self.send_header("Set-Cookie", extra_cookie)
            self.end_headers()
            self.wfile.write(data)

        def send_json(self, status, payload, cookie=None, cookies=None):
            self.send_bytes(
                status, json.dumps(payload, separators=(",", ":")).encode(),
                cookie=cookie, cookies=cookies,
            )

        def body(self):
            try:
                size = int(self.headers.get("Content-Length", "0"))
            except ValueError:
                raise ValueError("Invalid Content-Length")
            if not 1 <= size <= MAX_BODY:
                raise ValueError("Request body size must be 1..32768 bytes")
            raw = self.rfile.read(size)
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict):
                raise ValueError("JSON object required")
            return value, raw

        def same_origin(self):
            return self.headers.get("Origin") == f"http://{HOST}:{PORT}" and (
                self.headers.get("Host") == f"{HOST}:{PORT}"
            )

        def require_session(self):
            session = app.get_session(self.headers.get("Cookie", ""))
            if not session or not session["authenticated"]:
                return None
            return session

        def csrf_ok(self, session):
            supplied = self.headers.get("X-CSRF-Token", "")
            expected = app.csrf(session)
            return bool(supplied) and hmac.compare_digest(supplied, expected)

        def send_artifact_download(self, path, session):
            """Stream a bounded artifact while preserving its verified SHA-256 ETag."""
            gateway_headers = app.sign_gateway("GET", urlparse(path).path, session)
            request = Request(
                f"http://{HOST}:{app.gateway_port}{path}",
                headers=gateway_headers,
                method="GET",
            )
            try:
                response = urlopen(request, timeout=30)
            except HTTPError as exc:
                try:
                    body = exc.read(MAX_BODY + 1)
                    if len(body) > MAX_BODY:
                        return self.send_json(502, {"error": "artifact gateway error response exceeds proxy limit"})
                    return self.send_bytes(exc.code, body)
                finally:
                    exc.close()
            except (URLError, TimeoutError, OSError):
                return self.send_json(503, {"error": "Gateway unavailable"})

            try:
                try:
                    size = int(response.headers.get("Content-Length", ""))
                except (TypeError, ValueError):
                    return self.send_json(502, {"error": "artifact download size is invalid"})
                etag = response.headers.get("ETag", "")
                content_type = response.headers.get("Content-Type", "").split(";", 1)[0].strip().lower()
                if (
                    response.status != 200
                    or not 1 <= size <= MAX_ARTIFACT_DOWNLOAD_BYTES
                    or content_type != "application/octet-stream"
                    or not re.fullmatch(r'"[0-9a-f]{64}"', etag)
                ):
                    return self.send_json(502, {"error": "artifact download response failed proxy validation"})
                disposition = response.headers.get("Content-Disposition", "")
                if not re.fullmatch(r"attachment; filename=[A-Za-z0-9._-]{1,120}", disposition):
                    disposition = "attachment; filename=artifact.bin"
                self.send_response(200)
                self.send_header("Content-Type", "application/octet-stream")
                self.send_header("Content-Length", str(size))
                self.send_header("Content-Disposition", disposition)
                self.send_header("ETag", etag)
                self.send_header("Cache-Control", "private, no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                remaining = size
                while remaining:
                    chunk = response.read(min(1024 * 1024, remaining))
                    if not chunk:
                        break
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                pass
            finally:
                response.close()

        def do_GET(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if path == "/healthz":
                return self.send_json(200, {"status": "ok", "auth_proxy": "ready",
                                            "gateway": "local", "provisioning_enabled": False})
            if path == "/api/auth/session":
                session = app.get_session(self.headers.get("Cookie", ""))
                if not session:
                    sid, session = app.new_session(False)
                    cookie = f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"
                else:
                    cookie = None
                return self.send_json(200, {
                    "authenticated": bool(session["authenticated"]),
                    "csrfToken": app.csrf(session),
                    "user": {"displayName": session["username"], "role": "owner"} if session["authenticated"] else None,
                }, cookie)
            preview_list = re.fullmatch(r"/api/jobs/([0-9a-f-]{36})/previews", path)
            if preview_list:
                session = self.require_session()
                if not session:
                    return self.send_json(401, {"error": "authenticated session required"})
                if parsed.query:
                    return self.send_json(400, {"error": "preview query parameters are not supported"})
                status, data = app.gateway_request("GET", path, session)
                return self.send_bytes(status, data)
            preview_match = re.fullmatch(
                r"/api/jobs/([0-9a-f-]{36})/previews/([0-9a-f-]{36})(?:/content/(.*))?",
                path,
            )
            if preview_match:
                if parsed.query:
                    return self.send_json(400, {"error": "preview query parameters are not supported"})
                job_id, runtime_id, relative_path = preview_match.groups()
                session = app.get_session(self.headers.get("Cookie", ""))
                if relative_path is not None and (
                    not session or not session.get("authenticated")
                ):
                    session = app.get_preview_session(
                        job_id, runtime_id, self.headers.get("Cookie", "")
                    )
                if not session or not session.get("authenticated"):
                    return self.send_json(401, {"error": "authenticated preview session required"})
                if relative_path is not None:
                    gateway_path = f"/api/jobs/{job_id}/previews/{runtime_id}/content/{relative_path}"
                    status, data = app.gateway_request(
                        "GET", gateway_path, session,
                        max_response_bytes=MAX_PREVIEW_RESPONSE_BYTES,
                    )
                    if len(data) > MAX_PREVIEW_RESPONSE_BYTES:
                        return self.send_json(502, {"error": "preview response exceeds proxy limit"})
                    try:
                        envelope = json.loads(data.decode("utf-8"))
                        import base64
                        payload = base64.b64decode(envelope["body_base64"], validate=True)
                        content_type = envelope["content_type"]
                    except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                        return self.send_json(status if status >= 400 else 502,
                                               {"error": "invalid preview proxy response"})
                    if len(payload) > 8 * 1024 * 1024:
                        return self.send_json(502, {"error": "preview response exceeds proxy limit"})
                    return self.send_bytes(status, payload, content_type,
                                           allow_same_origin_frame=True)
                gateway_path = f"/api/jobs/{job_id}/previews/{runtime_id}"
                status, data = app.gateway_request("GET", gateway_path, session)
                return self.send_bytes(status, data)
            artifact_download = re.fullmatch(
                r"/api/artifacts/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/download",
                path,
            )
            if artifact_download:
                session = self.require_session()
                if not session:
                    return self.send_json(401, {"error": "authenticated session required"})
                if parsed.query:
                    return self.send_json(404, {"error": "not found"})
                return self.send_artifact_download(path, session)
            if path.startswith("/api/"):
                session = self.require_session()
                if not session:
                    return self.send_json(401, {"error": "authenticated session required"})
                github_read_path = re.fullmatch(
                    r"/api/github/repositories/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}/(?:refs|commits/[0-9a-fA-F]{40}|projects/[0-9a-fA-F]{40})",
                    path,
                )
                github_refs_path = re.fullmatch(
                    r"/api/github/repositories/[A-Za-z0-9_.-]{1,100}/[A-Za-z0-9_.-]{1,100}/refs",
                    path,
                )
                job_list_path = path == "/api/jobs"
                job_logs_path = re.fullmatch(
                    r"/api/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/logs",
                    path,
                )
                job_read_path = re.fullmatch(
                    r"/api/jobs/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:/(?:artifacts|events))?",
                    path,
                )
                artifact_download_path = re.fullmatch(
                    r"/api/artifacts/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/download",
                    path,
                )
                terminal_events_path = re.fullmatch(
                    r"/api/terminal/templates/custom-[a-z0-9][a-z0-9-]{1,62}/events",
                    path,
                )
                infrastructure_resource_path = re.fullmatch(
                    r"/api/infrastructure/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}(?:/events)?",
                    path,
                )
                query_allowed = not parsed.query or (
                    bool(github_refs_path) and parsed.query in ("kind=branches", "kind=tags")
                )
                if path == "/api/infrastructure" and parsed.query:
                    query_allowed = parsed.query == "view=catalog"
                if job_list_path and parsed.query:
                    list_query = re.fullmatch(r"limit=([1-9][0-9]{0,2})", parsed.query)
                    query_allowed = bool(list_query) and int(list_query.group(1)) <= 200
                if job_logs_path and parsed.query:
                    logs_query = re.fullmatch(
                        r"after_id=([0-9]{1,18})&limit=([1-9][0-9]{0,2})|"
                        r"limit=([1-9][0-9]{0,2})&after_id=([0-9]{1,18})",
                        parsed.query,
                    )
                    if logs_query:
                        after_id = int(logs_query.group(1) or logs_query.group(4))
                        limit = int(logs_query.group(2) or logs_query.group(3))
                        query_allowed = after_id <= 9223372036854775807 and limit <= 500
                    else:
                        query_allowed = False
                if (not query_allowed or (
                    path not in ALLOWED_GET and not job_list_path and not (
                        path.startswith("/api/cloud-runners/") and path.count("/") == 3
                    ) and not re.fullmatch(r"/api/local-projects/[0-9a-f-]{36}", path)
                    and not github_read_path and not job_read_path
                    and not job_logs_path and not artifact_download_path
                    and not terminal_events_path and not infrastructure_resource_path
                )):
                    return self.send_json(404, {"error": "not found"})
                gateway_path = path + (("?" + parsed.query) if parsed.query else "")
                status, data = app.gateway_request(
                    "GET", gateway_path, session,
                    max_response_bytes=MAX_DASHBOARD_READ_RESPONSE_BYTES,
                )
                if len(data) > MAX_DASHBOARD_READ_RESPONSE_BYTES:
                    return self.send_json(502, {"error": "Dashboard read response exceeds proxy limit"})
                return self.send_bytes(status, data)
            relative = "index.html" if path == "/" else unquote(path.lstrip("/"))
            target = (root / relative).resolve()
            if root not in target.parents and target != root:
                return self.send_json(404, {"error": "not found"})
            if not target.is_file():
                return self.send_json(404, {"error": "not found"})
            types = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                     ".css": "text/css; charset=utf-8", ".svg": "image/svg+xml",
                     ".webmanifest": "application/manifest+json"}
            return self.send_bytes(200, target.read_bytes(), types.get(target.suffix, "application/octet-stream"))

        def do_POST(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if not self.same_origin():
                return self.send_json(403, {"error": "same-origin request required"})
            if parsed.query:
                return self.send_json(404, {"error": "not found"})
            session = app.get_session(self.headers.get("Cookie", ""))
            if path == "/api/auth/login":
                if not session or session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "valid pre-authentication CSRF session required"})
                try:
                    payload, _ = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                username, password = payload.get("username"), payload.get("password")
                if not isinstance(username, str) or not isinstance(password, str):
                    return self.send_json(400, {"error": "username and password required"})
                now = time.time()
                ip = self.client_address[0]
                attempts = [t for t in app.failures.get(ip, []) if now - t < 900]
                if len(attempts) >= 5:
                    app.failures[ip] = attempts
                    return self.send_json(429, {"error": "too many login attempts; wait 15 minutes"})
                if not verify_password(app.credentials, username, password):
                    attempts.append(now)
                    app.failures[ip] = attempts
                    return self.send_json(401, {"error": "invalid username or password"})
                with app.lock:
                    app.failures.pop(ip, None)
                    app.sessions.pop(session["id"], None)
                sid, new_session = app.new_session(True)
                cookie = f"{COOKIE}={sid}; HttpOnly; SameSite=Strict; Path=/; Max-Age={SESSION_TTL}"
                return self.send_json(200, {"authenticated": True}, cookie)
            if path == "/api/auth/logout":
                if not session or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                preview_cookies = app.revoke_session_previews(session["id"])
                with app.lock:
                    app.sessions.pop(session["id"], None)
                return self.send_json(
                    200, {"authenticated": False},
                    f"{COOKIE}=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0",
                    cookies=preview_cookies,
                )
            if path == "/api/jobs":
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    _, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", ""),
                    idempotency_key=self.headers.get("Idempotency-Key", ""),
                )
                return self.send_bytes(status, data)
            job_resume = re.fullmatch(r"/api/jobs/([0-9a-f-]{36})/resume", path)
            if job_resume:
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    _, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", "")
                )
                return self.send_bytes(status, data)
            preview_start = re.fullmatch(r"/api/jobs/([0-9a-f-]{36})/previews", path)
            if preview_start:
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    _, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", "")
                )
                if status not in (200, 201):
                    return self.send_bytes(status, data)
                try:
                    payload = json.loads(data.decode("utf-8"))
                    job_id = preview_start.group(1)
                    runtime_id = payload["runtime_id"]
                    expected_path = (
                        f"/api/jobs/{job_id}/previews/{runtime_id}/content/"
                    )
                    if payload.get("job_id") != job_id or payload.get("preview_path") != expected_path:
                        raise ValueError("preview response identity mismatch")
                    cookie = app.create_preview_cookie(
                        job_id, runtime_id, session, payload["expires_in_seconds"]
                    )
                except (ValueError, KeyError, TypeError, UnicodeDecodeError):
                    return self.send_json(502, {"error": "invalid preview start response"})
                return self.send_bytes(status, data, cookie=cookie)
            gate_match = re.fullmatch(
                r"/api/infrastructure/gates/(cloud_provisioning|vm_creation)", path
            )
            if gate_match:
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    _, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", "")
                )
                return self.send_bytes(status, data)
            if path.startswith("/api/cloud-runners"):
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                if path != "/api/cloud-runners":
                    return self.send_json(404, {"error": "not found"})
                try:
                    _, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", ""),
                    idempotency_key=self.headers.get("Idempotency-Key", ""),
                )
                return self.send_bytes(status, data)
            terminal_template_import = path == "/api/terminal/templates/import"
            terminal_command_preview = path == "/api/terminal/commands/preview"
            terminal_template_review = re.fullmatch(
                r"/api/terminal/templates/custom-[a-z0-9][a-z0-9-]{1,62}/review",
                path,
            )
            if terminal_template_import or terminal_command_preview or terminal_template_review:
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    _, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", "")
                )
                return self.send_bytes(status, data)
            infrastructure_action = re.fullmatch(
                r"/api/infrastructure/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/(start|stop|restart)",
                path,
            )
            if path == "/api/infrastructure" or infrastructure_action:
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    payload, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                if infrastructure_action and payload:
                    return self.send_json(400, {"error": "infrastructure lifecycle payload must be an empty object"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", ""),
                    idempotency_key=self.headers.get("Idempotency-Key", "") if path == "/api/infrastructure" else "",
                )
                return self.send_bytes(status, data)
            runner_control = re.fullmatch(
                r"/api/runners/((?!\.{1,2}/)(?:[A-Za-z0-9_.:-]|%3[Aa]){1,300})/(drain|enable)", path
            )
            if runner_control:
                if not session or not session["authenticated"] or not self.csrf_ok(session):
                    return self.send_json(403, {"error": "authenticated session and CSRF token required"})
                try:
                    payload, raw = self.body()
                except Exception:
                    return self.send_json(400, {"error": "invalid JSON body"})
                if payload:
                    return self.send_json(400, {"error": "runner control payload must be an empty object"})
                status, data = app.gateway_request(
                    "POST", path, session, raw, self.headers.get("X-CSRF-Token", "")
                )
                return self.send_bytes(status, data)
            return self.send_json(404, {"error": "not found"})

        def do_DELETE(self):
            parsed = urlparse(self.path)
            path = parsed.path
            if not self.same_origin():
                return self.send_json(403, {"error": "same-origin request required"})
            if parsed.query:
                return self.send_json(404, {"error": "not found"})
            session = self.require_session()
            if not session or not self.csrf_ok(session):
                return self.send_json(403, {"error": "authenticated session and CSRF token required"})
            preview_stop = re.fullmatch(
                r"/api/jobs/([0-9a-f-]{36})/previews/([0-9a-f-]{36})", path
            )
            if preview_stop:
                status, data = app.gateway_request(
                    "DELETE", path, session,
                    csrf_token=self.headers.get("X-CSRF-Token", ""),
                )
                clear_cookie = app.revoke_preview_session(
                    preview_stop.group(1), preview_stop.group(2)
                )
                return self.send_bytes(status, data, cookie=clear_cookie)
            infrastructure_delete = re.fullmatch(
                r"/api/infrastructure/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
                path,
            )
            if infrastructure_delete:
                status, data = app.gateway_request(
                    "DELETE", path, session,
                    csrf_token=self.headers.get("X-CSRF-Token", ""),
                )
                return self.send_bytes(status, data)
            if not (path.startswith("/api/cloud-runners/") and path.count("/") == 3):
                return self.send_json(404, {"error": "not found"})
            status, data = app.gateway_request("DELETE", path, session, csrf_token=self.headers.get("X-CSRF-Token", ""))
            return self.send_bytes(status, data)

        def do_OPTIONS(self):
            return self.send_json(405, {"error": "method not allowed"})

    return Handler


def main():
    if PORT < 1 or PORT > 65535 or GATEWAY_PORT < 1 or GATEWAY_PORT > 65535 or PORT == GATEWAY_PORT:
        raise SystemExit("Local and Gateway ports must be distinct valid TCP ports")
    credentials = load_or_create_credentials()
    gateway_token = secrets.token_urlsafe(48)
    proxy_secret = secrets.token_urlsafe(48)
    env = gateway_child_environment()
    env.update({
        "DCP_GATEWAY_HOST": HOST, "DCP_GATEWAY_PORT": str(GATEWAY_PORT),
        "DCP_GATEWAY_API_TOKEN": gateway_token, "DCP_TRUSTED_PROXY_HMAC_SECRET": proxy_secret,
        "DCP_PUBLIC_ORIGIN": f"http://{HOST}:{PORT}",
        "DCP_GATEWAY_PROVISIONING_ENABLED": "false", "DCP_GATEWAY_OWNER_APPROVED": "false",
        "DCP_GATEWAY_DATABASE": str(CREDENTIALS.parent / "gateway.sqlite3"),
        "DCP_LOCAL_PROJECT_REGISTRY": str(CREDENTIALS.parent / "local-projects.json"),
    })
    gateway = subprocess.Popen([sys.executable, "-m", "tools.cloud_gateway.server"], env=env)
    server = None
    print(f"Dashboard + Local Auth Proxy: http://{HOST}:{PORT}/", flush=True)
    print(f"Gateway: http://{HOST}:{GATEWAY_PORT}/ (loopback only; provisioning disabled)", flush=True)
    try:
        for _ in range(40):
            if gateway.poll() is not None:
                raise SystemExit(f"Gateway exited during startup with code {gateway.returncode}")
            try:
                with urlopen(f"http://{HOST}:{GATEWAY_PORT}/healthz", timeout=1) as response:
                    health = json.loads(response.read().decode("utf-8"))
                if health.get("status") != "ok" or health.get("provisioning_enabled") is not False:
                    raise SystemExit("Gateway health or safe-default contract failed")
                break
            except SystemExit:
                raise
            except Exception:
                time.sleep(0.25)
        else:
            raise SystemExit("Gateway health check timed out")
        app = LocalAuthProxy(credentials, gateway_token, proxy_secret, GATEWAY_PORT)
        server = ThreadingHTTPServer(
            (HOST, PORT), make_handler(app, Path(__file__).resolve().parents[1] / "dashboard")
        )
        server.daemon_threads = True
        server.serve_forever()
    finally:
        if server is not None:
            server.server_close()
        gateway.terminate()
        try:
            gateway.wait(timeout=10)
        except subprocess.TimeoutExpired:
            gateway.kill()
            gateway.wait(timeout=5)


if __name__ == "__main__":
    main()
