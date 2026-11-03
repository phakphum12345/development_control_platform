"""Create per-request HMAC assertions from claims verified by an upstream OIDC proxy.

This module does not validate JWT signatures. It must only receive claims after
the trusted OIDC middleware has validated signature, issuer, audience, nonce,
state, expiry, and redirect URI.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from urllib.parse import urlparse


class OIDCAssertionError(ValueError):
    pass


def _audiences(value):
    if isinstance(value, str):
        return {value}
    if isinstance(value, list) and all(isinstance(item, str) for item in value):
        return set(value)
    return set()


def map_oidc_groups(groups, owner_groups, operator_groups):
    if not isinstance(groups, list) or any(not isinstance(group, str) for group in groups):
        raise OIDCAssertionError("Verified OIDC groups must be a string list")
    owner = set(owner_groups)
    operator = set(operator_groups)
    if not owner or not operator or owner & operator:
        raise OIDCAssertionError("Owner and operator group mappings must be nonempty and distinct")
    observed = set(groups)
    if observed & owner:
        return "owner"
    if observed & operator:
        return "operator"
    raise OIDCAssertionError("OIDC identity has no authorized DCP group")


def sign_verified_oidc_assertion(
    method: str,
    path: str,
    claims: dict,
    session_id: str,
    secret: str | bytes,
    issuer: str,
    audience: str,
    owner_groups,
    operator_groups,
    now_epoch: int | None = None,
) -> dict[str, str]:
    """Sign a single request using already-verified OIDC claims and a server secret."""
    if not isinstance(claims, dict):
        raise OIDCAssertionError("Verified OIDC claims are required")
    if not isinstance(issuer, str) or not issuer or claims.get("iss") != issuer:
        raise OIDCAssertionError("OIDC issuer mismatch")
    if not isinstance(audience, str) or not audience or audience not in _audiences(claims.get("aud")):
        raise OIDCAssertionError("OIDC audience mismatch")
    current = int(time.time()) if now_epoch is None else now_epoch
    if isinstance(current, bool) or not isinstance(current, int):
        raise OIDCAssertionError("Invalid assertion time")
    expires = claims.get("exp")
    issued_at = claims.get("iat")
    if (isinstance(expires, bool) or not isinstance(expires, int) or expires <= current
            or isinstance(issued_at, bool) or not isinstance(issued_at, int)
            or issued_at > current + 60 or current - issued_at > 600):
        raise OIDCAssertionError("OIDC token is expired or outside the accepted issue-time window")
    subject = claims.get("sub")
    if not isinstance(subject, str) or not re.fullmatch(r"[A-Za-z0-9._:@/-]{1,256}", subject):
        raise OIDCAssertionError("OIDC subject is invalid")
    role = map_oidc_groups(claims.get("groups"), owner_groups, operator_groups)
    if not isinstance(session_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", session_id):
        raise OIDCAssertionError("OIDC session identifier is invalid")
    key = secret.encode("utf-8") if isinstance(secret, str) else secret
    if not isinstance(key, bytes) or len(key) < 32:
        raise OIDCAssertionError("Trusted proxy HMAC secret must be at least 32 bytes")
    if not isinstance(method, str) or method.upper() not in ("GET", "POST", "PUT", "PATCH", "DELETE"):
        raise OIDCAssertionError("Unsupported HTTP method")
    request_path = urlparse(path).path
    if not request_path.startswith("/") or request_path.startswith("//"):
        raise OIDCAssertionError("Invalid request path")
    timestamp = str(current)
    nonce = secrets.token_urlsafe(24)
    canonical = "\n".join((
        method.upper(), request_path, subject, role, session_id, timestamp, nonce
    )).encode("utf-8")
    signature = hmac.new(key, canonical, hashlib.sha256).hexdigest()
    return {
        "X-DCP-User": subject,
        "X-DCP-Role": role,
        "X-DCP-Session": session_id,
        "X-DCP-Auth-Timestamp": timestamp,
        "X-DCP-Auth-Nonce": nonce,
        "X-DCP-Auth-Signature": signature,
    }
