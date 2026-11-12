"""Sign Gateway assertions from an already-authenticated local OIDC proxy.

This component does not validate JWT signatures. It calls the loopback-only
oauth2-proxy auth endpoint, trusts only its verified subject/group response,
and creates a separate HttpOnly edge-session cookie for stable CSRF binding.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import secrets
import time
from http.cookies import CookieError, SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .oidc_assertion import OIDCAssertionError, sign_verified_oidc_assertion


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


class OIDCProxyIdentitySigner:
    """Bridge a loopback OIDC proxy session to DCP's per-request HMAC contract."""

    def __init__(
        self,
        *,
        auth_url: str,
        issuer: str,
        audience: str,
        owner_groups,
        operator_groups,
        secret: str | bytes,
        proxy_cookie_name: str = "_oauth2_proxy",
        session_cookie_name: str = "__Host-dcp_edge_session",
        session_max_age: int = 28800,
        timeout: float = 3.0,
        opener=None,
        clock=None,
    ):
        parsed = urlparse(auth_url)
        try:
            _ = parsed.port
        except ValueError as exc:
            raise ValueError("Invalid OIDC auth endpoint port") from exc
        if (
            parsed.scheme != "http"
            or parsed.hostname != "127.0.0.1"
            or parsed.username is not None
            or parsed.password is not None
            or parsed.path != "/oauth2/auth"
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("OIDC auth endpoint must be the loopback /oauth2/auth endpoint")
        if not isinstance(issuer, str) or not issuer.startswith("https://"):
            raise ValueError("A verified HTTPS OIDC issuer is required")
        if not isinstance(audience, str) or not audience:
            raise ValueError("OIDC audience is required")
        key = secret.encode("utf-8") if isinstance(secret, str) else secret
        if not isinstance(key, bytes) or len(key) < 32:
            raise ValueError("Trusted proxy HMAC secret must be at least 32 bytes")
        if not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", proxy_cookie_name):
            raise ValueError("Invalid OIDC proxy cookie name")
        if not re.fullmatch(r"__Host-[A-Za-z0-9_-]{1,64}", session_cookie_name):
            raise ValueError("DCP edge session cookie must use the __Host- prefix")
        if isinstance(session_max_age, bool) or not isinstance(session_max_age, int) or not 300 <= session_max_age <= 43200:
            raise ValueError("DCP edge session lifetime must be 300..43200 seconds")
        if isinstance(timeout, bool) or not isinstance(timeout, (int, float)) or not 0.5 <= timeout <= 10:
            raise ValueError("OIDC proxy timeout must be 0.5..10 seconds")
        # Reuse the assertion helper's strict, disjoint group validation.
        from .oidc_assertion import map_oidc_groups
        if not isinstance(owner_groups, (list, tuple, set)) or not isinstance(operator_groups, (list, tuple, set)):
            raise ValueError("OIDC group mappings must be collections")
        if (
            not owner_groups or not operator_groups
            or any(not isinstance(group, str) or not group for group in (*owner_groups, *operator_groups))
            or set(owner_groups) & set(operator_groups)
        ):
            raise ValueError("Owner and operator OIDC groups must be nonempty, valid and distinct")
        self.owner_groups = tuple(owner_groups)
        self.operator_groups = tuple(operator_groups)
        # Validate group collection element types at startup.
        map_oidc_groups(list(self.owner_groups), self.owner_groups, self.operator_groups)
        self.auth_url = auth_url
        self.issuer = issuer
        self.audience = audience
        self.secret = key
        self.proxy_cookie_name = proxy_cookie_name
        self.session_cookie_name = session_cookie_name
        self.session_max_age = session_max_age
        self.timeout = float(timeout)
        self.opener = opener or build_opener(_NoRedirect()).open
        self.clock = clock or time.time

    @staticmethod
    def _cookie_values(header: str) -> dict:
        if not isinstance(header, str) or len(header) > 16384:
            return {}
        parsed = SimpleCookie()
        try:
            parsed.load(header)
        except CookieError:
            return {}
        return {name: morsel.value for name, morsel in parsed.items()}

    def _session_signature(self, subject: str, session_id: str, expires: str) -> str:
        message = "\n".join(("dcp-edge-session", subject, session_id, expires)).encode("utf-8")
        return hmac.new(self.secret, message, hashlib.sha256).hexdigest()

    def _existing_session(self, cookie_value: str, subject: str, now: int):
        if not isinstance(cookie_value, str) or len(cookie_value) > 256:
            return None
        parts = cookie_value.split(".")
        if len(parts) != 3:
            return None
        session_id, expires, signature = parts
        if (
            not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", session_id)
            or not expires.isdigit()
            or not re.fullmatch(r"[a-f0-9]{64}", signature)
        ):
            return None
        expiry = int(expires)
        if expiry <= now or expiry > now + self.session_max_age + 60:
            return None
        expected = self._session_signature(subject, session_id, expires)
        if not hmac.compare_digest(expected, signature):
            return None
        return session_id

    def _new_session(self, subject: str, now: int):
        session_id = secrets.token_urlsafe(24)
        expires = str(now + self.session_max_age)
        signature = self._session_signature(subject, session_id, expires)
        value = ".".join((session_id, expires, signature))
        cookie = (
            self.session_cookie_name + "=" + value
            + "; Path=/; Max-Age=" + str(self.session_max_age)
            + "; Secure; HttpOnly; SameSite=Strict"
        )
        return session_id, cookie

    @staticmethod
    def _header_values(headers, name):
        get_all = getattr(headers, "get_all", None)
        if callable(get_all):
            values = get_all(name, [])
            if values:
                return [value for value in values if isinstance(value, str)]
        value = headers.get(name)
        return [value] if isinstance(value, str) else []

    def _verified_proxy_identity(self, cookie_header: str):
        cookies = self._cookie_values(cookie_header)
        if self.proxy_cookie_name not in cookies and not any(
            name.startswith(self.proxy_cookie_name + "_") for name in cookies
        ):
            return None
        request = Request(
            self.auth_url,
            headers={"Cookie": cookie_header, "Accept": "application/json"},
            method="GET",
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                status = getattr(response, "status", None)
                if status is None:
                    status = response.getcode()
                body = response.read(4097)
                if len(body) > 4096:
                    raise OIDCAssertionError("OIDC proxy auth response exceeded size limit")
                if status != 202:
                    return None
                headers = response.headers
                subjects = self._header_values(headers, "X-Auth-Request-User")
                group_headers = self._header_values(headers, "X-Auth-Request-Groups")
                if len(subjects) != 1:
                    return None
                subject = subjects[0]
                raw_groups = ",".join(group_headers)
        except HTTPError as exc:
            try:
                if exc.code in (401, 403):
                    return None
                raise OIDCAssertionError("OIDC proxy authentication failed") from exc
            finally:
                exc.close()
        except (URLError, TimeoutError, OSError) as exc:
            raise OIDCAssertionError("OIDC proxy authentication service unavailable") from exc
        if not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z0-9._:@/-]{1,256}", subject):
            return None
        if not isinstance(raw_groups, str) or len(raw_groups) > 8192:
            return None
        groups = [item.strip() for item in raw_groups.split(",") if item.strip()]
        if not groups or len(groups) > 100:
            return None
        from .oidc_assertion import map_oidc_groups
        try:
            map_oidc_groups(groups, self.owner_groups, self.operator_groups)
        except OIDCAssertionError:
            return None
        return subject, groups

    def authorize(self, method: str, path: str, cookie_header: str, now_epoch: int | None = None):
        """Return signed DCP headers, or None when the OIDC session is unauthorized."""
        now = int(self.clock()) if now_epoch is None else now_epoch
        if isinstance(now, bool) or not isinstance(now, int):
            raise OIDCAssertionError("Invalid assertion time")
        parsed = urlparse(path)
        if (
            not isinstance(method, str)
            or method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE")
            or not parsed.path.startswith("/")
            or parsed.path.startswith("//")
            or parsed.query
            or parsed.fragment
        ):
            raise OIDCAssertionError("Invalid original request method or path")
        if not isinstance(cookie_header, str) or not cookie_header or len(cookie_header) > 16384:
            return None
        identity = self._verified_proxy_identity(cookie_header)
        if identity is None:
            return None
        subject, groups = identity
        cookies = self._cookie_values(cookie_header)
        session_id = self._existing_session(
            cookies.get(self.session_cookie_name, ""), subject, now
        )
        set_cookie = None
        if session_id is None:
            session_id, set_cookie = self._new_session(subject, now)
        claims = {
            "iss": self.issuer,
            "aud": self.audience,
            "sub": subject,
            "groups": groups,
            "iat": now,
            "exp": now + 60,
        }
        headers = sign_verified_oidc_assertion(
            method, parsed.path, claims, session_id, self.secret,
            self.issuer, self.audience, self.owner_groups, self.operator_groups,
            now_epoch=now,
        )
        if set_cookie:
            headers["Set-Cookie"] = set_cookie
        return headers

    @classmethod
    def from_environment(cls, env=None, opener=None, clock=None):
        values = os.environ if env is None else env
        def groups(name):
            return tuple(item.strip() for item in values.get(name, "").split(",") if item.strip())
        return cls(
            auth_url=values.get("DCP_OIDC_PROXY_AUTH_URL", "http://127.0.0.1:4180/oauth2/auth"),
            issuer=values.get("DCP_OIDC_ISSUER", ""),
            audience=values.get("DCP_OIDC_AUDIENCE", ""),
            owner_groups=groups("DCP_OIDC_OWNER_GROUPS"),
            operator_groups=groups("DCP_OIDC_OPERATOR_GROUPS"),
            secret=values.get("DCP_TRUSTED_PROXY_HMAC_SECRET", ""),
            proxy_cookie_name=values.get("DCP_OIDC_PROXY_COOKIE_NAME", "_oauth2_proxy"),
            session_cookie_name=values.get("DCP_OIDC_EDGE_SESSION_COOKIE_NAME", "__Host-dcp_edge_session"),
            session_max_age=int(values.get("DCP_OIDC_EDGE_SESSION_SECONDS", "28800")),
            opener=opener,
            clock=clock,
        )


def make_handler(signer: OIDCProxyIdentitySigner):
    """Create the private auth-request handler used by a same-origin reverse proxy."""
    class Handler(BaseHTTPRequestHandler):
        server_version = "DCPIdentitySigner/1.0"

        def log_message(self, fmt, *args):
            # Never log cookies, subject identifiers, group claims or signatures.
            return

        def do_GET(self):
            if urlparse(self.path).path != "/authorize":
                self.send_response(404)
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            try:
                headers = signer.authorize(
                    self.headers.get("X-Original-Method", ""),
                    self.headers.get("X-Original-URI", ""),
                    self.headers.get("Cookie", ""),
                )
            except (OIDCAssertionError, ValueError):
                headers = None
                status = 503
            else:
                status = 202 if headers is not None else 401
            self.send_response(status)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            if headers:
                for name, value in headers.items():
                    self.send_header(name, value)
            self.end_headers()

    return Handler


def main():
    try:
        signer = OIDCProxyIdentitySigner.from_environment()
        host = os.getenv("DCP_OIDC_SIGNER_HOST", "127.0.0.1")
        if host != "127.0.0.1":
            raise ValueError("OIDC identity signer must bind to loopback")
        port = int(os.getenv("DCP_OIDC_SIGNER_PORT", "8790"))
        if not 1 <= port <= 65535:
            raise ValueError("Invalid OIDC identity signer port")
    except (TypeError, ValueError) as exc:
        raise SystemExit("OIDC identity signer configuration is invalid") from exc
    server = ThreadingHTTPServer((host, port), make_handler(signer))
    server.serve_forever()


if __name__ == "__main__":
    main()
