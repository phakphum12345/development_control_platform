from datetime import datetime, timedelta, timezone
import uuid

import pytest

from tools.cloud_gateway.terminal_grants import TerminalGrantError, TerminalGrantStore


NOW = datetime(2026, 11, 13, 12, 0, tzinfo=timezone.utc)
PROJECT = str(uuid.uuid4())
WORKSPACE = str(uuid.uuid4())
JOB = str(uuid.uuid4())
SUBJECT = "owner@example.test"
SESSION = "session_token_1234567890"
SNAPSHOT = "a" * 64
TEMPLATE_DIGEST = "b" * 64
PARAMETERS_DIGEST = "c" * 64


def issue(store, *, now=NOW, ttl=120, action="terminal.read_only"):
    return store.issue(
        subject=SUBJECT, session_id=SESSION, project_id=PROJECT,
        workspace_id=WORKSPACE, snapshot_sha256=SNAPSHOT,
        template_id="git_status", template_digest=TEMPLATE_DIGEST,
        parameters_sha256=PARAMETERS_DIGEST, action=action,
        ttl_seconds=ttl, now=now,
    )


def bind(store, grant, *, job_id=JOB, worker_id="runner-local", now=NOW):
    return store.bind_job(grant["authorization_id"], job_id=job_id,
                          worker_id=worker_id, now=now)


def consume(store, grant, **overrides):
    claims = {
        "job_id": JOB, "worker_id": "runner-local", "subject": SUBJECT,
        "session_id": SESSION, "project_id": PROJECT, "workspace_id": WORKSPACE,
        "snapshot_sha256": SNAPSHOT, "template_id": "git_status",
        "template_digest": TEMPLATE_DIGEST, "parameters_sha256": PARAMETERS_DIGEST,
        "action": "terminal.read_only", "now": NOW,
    }
    claims.update(overrides)
    return store.consume(grant["authorization_id"], **claims)


def test_grant_is_durable_and_consumable_only_once(tmp_path):
    path = tmp_path / "grants.sqlite3"
    store = TerminalGrantStore(path)
    grant = issue(store)
    bind(store, grant)

    # Reopening the store proves the grant is durable, not process-local state.
    reopened = TerminalGrantStore(path)
    result = consume(reopened, grant)
    assert result["authorized"] is True
    with pytest.raises(TerminalGrantError, match="not active"):
        consume(reopened, grant)


def test_grant_cannot_be_bound_to_a_second_job_or_runner(tmp_path):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    grant = issue(store)
    bind(store, grant)
    with pytest.raises(TerminalGrantError, match="already bound"):
        bind(store, grant, job_id=str(uuid.uuid4()), worker_id="runner-other")


@pytest.mark.parametrize("field,value", [
    ("subject", "different-user"),
    ("session_id", "different_session_123456"),
    ("project_id", str(uuid.uuid4())),
    ("workspace_id", str(uuid.uuid4())),
    ("snapshot_sha256", "d" * 64),
    ("template_id", "git_diff"),
    ("template_digest", "e" * 64),
    ("parameters_sha256", "f" * 64),
    ("action", "terminal.modify"),
])
def test_scope_mismatch_is_rejected(tmp_path, field, value):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    grant = issue(store)
    bind(store, grant)
    with pytest.raises(TerminalGrantError, match="scope"):
        consume(store, grant, **{field: value})


def test_wrong_job_or_runner_cannot_consume_grant(tmp_path):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    grant = issue(store)
    bind(store, grant)
    with pytest.raises(TerminalGrantError, match="not bound"):
        consume(store, grant, worker_id="runner-attacker")


def test_expired_grant_fails_closed(tmp_path):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    grant = issue(store, ttl=15)
    bind(store, grant)
    with pytest.raises(TerminalGrantError, match="not active"):
        consume(store, grant, now=NOW + timedelta(seconds=16))


def test_revoked_grant_cannot_be_consumed_or_reactivated(tmp_path):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    grant = issue(store)
    bind(store, grant)
    assert store.revoke(grant["authorization_id"], now=NOW) is True
    assert store.revoke(grant["authorization_id"], now=NOW) is False
    with pytest.raises(TerminalGrantError, match="not active"):
        consume(store, grant)


def test_only_read_only_action_can_be_issued(tmp_path):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    with pytest.raises(ValueError, match="unsupported"):
        issue(store, action="terminal.modify")


def test_parameters_digest_is_canonical(tmp_path):
    first = TerminalGrantStore.parameters_digest({"limit": 10, "path": "."})
    second = TerminalGrantStore.parameters_digest({"path": ".", "limit": 10})
    assert first == second
    assert first != TerminalGrantStore.parameters_digest({"limit": 11, "path": "."})


def test_invalid_ttl_and_digest_are_rejected(tmp_path):
    store = TerminalGrantStore(tmp_path / "grants.sqlite3")
    with pytest.raises(ValueError, match="TTL"):
        issue(store, ttl=301)
    with pytest.raises(ValueError, match="SHA-256"):
        store.issue(
            subject=SUBJECT, session_id=SESSION, project_id=PROJECT,
            workspace_id=WORKSPACE, snapshot_sha256="not-a-digest",
            template_id="git_status", template_digest=TEMPLATE_DIGEST,
            parameters_sha256=PARAMETERS_DIGEST,
        )
