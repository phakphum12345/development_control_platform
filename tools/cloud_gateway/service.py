"""Fail-closed gateway orchestration over injected provider and durable store."""
import uuid
from datetime import datetime, timedelta, timezone

from .policy import PolicyDenied, idempotency_fingerprint, validate_runner_request
from .store import LifecycleConflict


class GatewayService:
    def __init__(self, settings, store, provider, budget_guard=None, runner_cleanup=None):
        self.settings = settings
        self.store = store
        self.provider = provider
        self.budget_guard = budget_guard
        self.runner_cleanup = runner_cleanup

    @staticmethod
    def public(row):
        return {k: row.get(k) for k in (
            "id", "state", "target_os", "created_at", "updated_at",
            "expires_at", "runner_name", "labels"
        )}

    def create(self, payload, key):
        if not isinstance(key, str) or not 8 <= len(key) <= 200:
            raise PolicyDenied("Idempotency-Key must be 8..200 characters", 400)
        if getattr(self.provider, "requires_runner_cleanup", False) and self.runner_cleanup is None:
            raise PolicyDenied("GitHub runner deregistration is not configured", 503)
        request = validate_runner_request(payload, self.settings)
        readiness = getattr(self.provider, "readiness", None)
        if callable(readiness):
            try:
                ready = readiness(request["target_os"])
            except Exception:
                ready = None
            if not isinstance(ready, dict) or ready.get("ready") is not True:
                raise PolicyDenied("Selected runner provider is not ready", 503)
        fingerprint = idempotency_fingerprint(request)
        old = self.store.get_by_key(key)
        if old:
            if old["fingerprint"] != fingerprint:
                raise LifecycleConflict("Idempotency key conflicts with an existing request")
            return self.public(old), False
        active_count = self.store.active_count()
        self.settings.authorize_provisioning(active_count)
        if self.budget_guard is not None:
            self.budget_guard.authorize(active_count)
        rid = str(uuid.uuid4())
        expiry = (datetime.now(timezone.utc) + timedelta(
            minutes=request["max_runtime_minutes"]
        )).isoformat()
        row, created = self.store.create(rid, key, fingerprint, request, expiry)
        if not created:
            if row["fingerprint"] != fingerprint:
                raise LifecycleConflict("Idempotency key conflicts with an existing request")
            return self.public(row), False
        try:
            instance = self.provider.provision(request)
            from tools.runner_backend.provider import RunnerInstance
            if not isinstance(instance, RunnerInstance):
                raise TypeError("Invalid provider result")
            row = self.store.transition(rid, "provisioning", instance.provider_id)
            row.update(runner_name=instance.runner_name, labels=list(instance.labels))
        except Exception as exc:
            self.store.transition(\n                rid, "failed", provider_id=getattr(exc, "provider_id", None),\n                detail=type(exc).__name__,\n            )
            raise
        return self.public(row), True

    def list_recent(self, limit=50):
        return [self.public(row) for row in self.store.list_recent(limit)]

    def _finalize_provider_state(self, row, instance):
        terminal = instance.state
        if terminal not in ("terminated", "failed"):
            return row
        rid = row["id"]
        if row["state"] != "terminating":
            row = self.store.transition(rid, "terminating")
        if getattr(self.provider, "requires_runner_cleanup", False) and self.runner_cleanup is None:
            raise RuntimeError("GitHub runner deregistration is not configured")
        if self.runner_cleanup is not None and row.get("provider_id"):
            try:
                result = self.runner_cleanup(row, instance)
            except Exception:
                self.store.record_event(rid, "cleanup_retry", "pending")
                raise
            self.store.record_event(rid, "runner_cleanup_confirmed", result)
        return self.store.transition(rid, terminal)

    def get(self, rid):
        row = self.store.get(rid)
        if not row:
            return None
        if row["provider_id"] and row["state"] in ("provisioning", "online", "terminating"):
            instance = self.provider.status(row["provider_id"])
            if instance.state == "online" and row["state"] == "provisioning":
                row = self.store.transition(rid, "online")
            elif instance.state == "terminating" and row["state"] != "terminating":
                row = self.store.transition(rid, "terminating")
            elif instance.state in ("terminated", "failed"):
                row = self._finalize_provider_state(row, instance)
            row.update(runner_name=instance.runner_name, labels=list(instance.labels))
        return self.public(row)

    def terminate(self, rid):
        row = self.store.get(rid)
        if not row:
            return None
        if row["state"] == "terminated":
            return self.public(row)
        if getattr(self.provider, "requires_runner_cleanup", False) and self.runner_cleanup is None:
            raise RuntimeError("GitHub runner deregistration is not configured")
        if row["state"] != "terminating":
            row = self.store.transition(rid, "terminating")
        if not row.get("provider_id"):
            row = self.store.transition(rid, "terminated")
            return self.public(row)
        try:
            instance = self.provider.terminate(row["provider_id"])
            if instance.state not in ("terminated", "failed"):
                instance = self.provider.status(row["provider_id"])
        except Exception:
            self.store.record_event(rid, "cleanup_retry", "pending")
            raise
        if instance.state in ("terminated", "failed"):
            row = self._finalize_provider_state(row, instance)
        return self.public(row)

    def reconcile_expired(self, now_utc=None):
        """Retry provider and GitHub cleanup for expired active/failed records."""
        current = now_utc or datetime.now(timezone.utc)
        if current.tzinfo is None:
            raise ValueError("Reconciliation time must be timezone-aware")
        expired = self.store.expired_active(current.isoformat())
        results = []
        for row in expired:
            try:
                result = self.terminate(row["id"])
                results.append({"id": row["id"], "state": result["state"] if result else "missing"})
            except Exception:
                # Keep the record active/terminating so the next sweep retries.
                results.append({"id": row["id"], "state": "cleanup_pending"})
        return results
