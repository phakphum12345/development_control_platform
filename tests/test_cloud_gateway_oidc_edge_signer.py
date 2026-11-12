"""Tests for the loopback OIDC proxy assertion signer."""
import hashlib
import hmac
import unittest
from http.cookies import SimpleCookie
from urllib.error import HTTPError, URLError

from tools.cloud_gateway.oidc_edge_signer import OIDCProxyIdentitySigner
from tools.cloud_gateway.oidc_assertion import OIDCAssertionError


ISSUER = "https://identity.example.test/"
AUDIENCE = "dcp-dashboard"
SECRET = "edge-signing-secret-material-at-least-32-bytes-long"
OWNER = "dcp-owner-group-id"
OPERATOR = "dcp-operator-group-id"
COOKIE = "_oauth2_proxy=opaque-authenticated-session"
NOW = 1_800_000_000


class FakeResponse:
    def __init__(self, status=202, headers=None, body=b""):
        self.status = status
        self.headers = headers or {}
        self.body = body
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def read(self, limit):
        return self.body[:limit]


class FakeOpener:
    def __init__(self, response=None, error=None):
        self.response = response or FakeResponse(headers={
            "X-Auth-Request-User": "immutable-oidc-subject-123",
            "X-Auth-Request-Groups": OPERATOR + "," + OWNER,
        })
        self.error = error
        self.request = None
        self.timeout = None

    def __call__(self, request, timeout):
        self.request = request
        self.timeout = timeout
        if self.error:
            raise self.error
        return self.response


def signer(opener=None, **overrides):
    values = {
        "auth_url": "http://127.0.0.1:4180/oauth2/auth",
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "owner_groups": (OWNER,),
        "operator_groups": (OPERATOR,),
        "secret": SECRET,
        "opener": opener or FakeOpener(),
        "clock": lambda: NOW,
    }
    values.update(overrides)
    return OIDCProxyIdentitySigner(**values)


class OIDCProxyIdentitySignerTests(unittest.TestCase):
    def test_signs_verified_owner_and_sets_secure_stable_edge_session_cookie(self):
        upstream = FakeOpener()
        bridge = signer(upstream)
        headers = bridge.authorize("GET", "/api/auth/session", COOKIE, now_epoch=NOW)
        self.assertEqual(headers["X-DCP-Role"], "owner")
        self.assertEqual(headers["X-DCP-User"], "immutable-oidc-subject-123")
        self.assertEqual(len(headers["X-DCP-Auth-Signature"]), 64)
        self.assertEqual(upstream.request.full_url, "http://127.0.0.1:4180/oauth2/auth")
        self.assertEqual(upstream.request.get_header("Cookie"), COOKIE)
        self.assertEqual(upstream.timeout, 3.0)

        canonical = "\n".join((
            "GET", "/api/auth/session", headers["X-DCP-User"],
            "owner", headers["X-DCP-Session"],
            headers["X-DCP-Auth-Timestamp"], headers["X-DCP-Auth-Nonce"],
        )).encode("utf-8")
        expected = hmac.new(SECRET.encode(), canonical, hashlib.sha256).hexdigest()
        self.assertTrue(hmac.compare_digest(expected, headers["X-DCP-Auth-Signature"]))

        parsed = SimpleCookie()
        parsed.load(headers["Set-Cookie"])
        morsel = parsed["__Host-dcp_edge_session"]
        self.assertTrue(morsel["secure"])
        self.assertTrue(morsel["httponly"])
        self.assertEqual(morsel["samesite"], "Strict")
        self.assertEqual(morsel["path"], "/")


    def test_collects_repeated_group_headers_from_oidc_proxy(self):
        class MultiHeaders(dict):
            def get_all(self, name, default=None):
                if name.lower() == "x-auth-request-groups":
                    return [OPERATOR, OWNER]
                value = self.get(name)
                return [value] if value is not None else (default or [])
        upstream = FakeOpener(FakeResponse(headers=MultiHeaders({
            "X-Auth-Request-User": "immutable-oidc-subject-123",
        })))
        headers = signer(upstream).authorize(
            "GET", "/api/auth/session", COOKIE, now_epoch=NOW
        )
        self.assertEqual(headers["X-DCP-Role"], "owner")

    def test_reuses_edge_session_cookie_without_reissuing_it(self):
        bridge = signer()
        first = bridge.authorize("GET", "/api/auth/session", COOKIE, now_epoch=NOW)
        cookie = SimpleCookie()
        cookie.load(first["Set-Cookie"])
        value = cookie["__Host-dcp_edge_session"].value
        next_headers = bridge.authorize(
            "POST", "/api/cloud-runners",
            COOKIE + "; __Host-dcp_edge_session=" + value,
            now_epoch=NOW + 1,
        )
        self.assertEqual(next_headers["X-DCP-Session"], first["X-DCP-Session"])
        self.assertNotIn("Set-Cookie", next_headers)
        self.assertEqual(next_headers["X-DCP-Role"], "owner")

    def test_edge_session_is_bound_to_oidc_subject(self):
        bridge = signer()
        first = bridge.authorize("GET", "/api/auth/session", COOKIE, now_epoch=NOW)
        cookie = SimpleCookie()
        cookie.load(first["Set-Cookie"])
        value = cookie["__Host-dcp_edge_session"].value
        other = FakeOpener(FakeResponse(headers={
            "X-Auth-Request-User": "different-subject",
            "X-Auth-Request-Groups": OWNER,
        }))
        second = signer(other).authorize(
            "GET", "/api/auth/session",
            COOKIE + "; __Host-dcp_edge_session=" + value,
            now_epoch=NOW + 1,
        )
        self.assertNotEqual(second["X-DCP-Session"], first["X-DCP-Session"])
        self.assertIn("Set-Cookie", second)

    def test_unknown_group_and_missing_proxy_session_are_denied(self):
        denied = FakeOpener(FakeResponse(headers={
            "X-Auth-Request-User": "subject-1",
            "X-Auth-Request-Groups": "unapproved-group",
        }))
        self.assertIsNone(signer(denied).authorize("GET", "/api/auth/session", COOKIE, now_epoch=NOW))
        no_cookie = FakeOpener()
        self.assertIsNone(signer(no_cookie).authorize("GET", "/api/auth/session", "", now_epoch=NOW))
        self.assertIsNone(no_cookie.request)

    def test_proxy_401_and_403_are_denied(self):
        for code in (401, 403):
            with self.subTest(code=code):
                error = HTTPError("http://127.0.0.1:4180/oauth2/auth", code, "denied", {}, None)
                self.assertIsNone(signer(FakeOpener(error=error)).authorize(
                    "GET", "/api/auth/session", COOKIE, now_epoch=NOW
                ))

    def test_proxy_transport_failure_fails_closed(self):
        with self.assertRaises(OIDCAssertionError):
            signer(FakeOpener(error=URLError("offline"))).authorize(
                "GET", "/api/auth/session", COOKIE, now_epoch=NOW
            )

    def test_rejects_non_loopback_auth_endpoint_and_overlapping_groups(self):
        with self.assertRaises(ValueError):
            signer(auth_url="http://example.test/oauth2/auth")
        with self.assertRaises(ValueError):
            signer(owner_groups=(OWNER,), operator_groups=(OWNER,))

    def test_rejects_query_string_and_unsupported_method(self):
        bridge = signer()
        for method, path in (("TRACE", "/api/auth/session"), ("GET", "/api/auth/session?x=1")):
            with self.subTest(method=method, path=path), self.assertRaises(OIDCAssertionError):
                bridge.authorize(method, path, COOKIE, now_epoch=NOW)

    def test_environment_factory_requires_issuer_audience_and_role_groups(self):
        env = {
            "DCP_OIDC_ISSUER": ISSUER,
            "DCP_OIDC_AUDIENCE": AUDIENCE,
            "DCP_OIDC_OWNER_GROUPS": OWNER,
            "DCP_OIDC_OPERATOR_GROUPS": OPERATOR,
            "DCP_TRUSTED_PROXY_HMAC_SECRET": SECRET,
        }
        configured = OIDCProxyIdentitySigner.from_environment(env, opener=FakeOpener())
        self.assertEqual(configured.issuer, ISSUER)
        with self.assertRaises(ValueError):
            OIDCProxyIdentitySigner.from_environment({})


if __name__ == "__main__":
    unittest.main()
