"""Fail-closed gateway orchestration over injected provider and durable store."""
import threading
import uuid
from datetime import datetime, timedelta, timezone

from .policy import PolicyDenied, idempotency_fingerprint, validate_runner_request
from .store import LifecycleConflict


class GatewayService:
    def __init__(
        self, settings, store, provider, budget_guard=None, runner_cleanup=None,
        provider_budget_guards=None, repository_catalog=None, repository_authorizer=None,
        repository_ref_catalog=None,
    ):
        self.settings = settings
        self.store = store
        self.provider = provider
        # Backwards-compatible budget_guard is Azure-only. Provider-specific
        # guards are keyed by the routed provider name (azure, orka, ...).
        self.provider_budget_guards = dict(provider_budget_guards or {})
        if budget_guard is not None:
            self.provider_budget_guards.setdefault("azure", budget_guard)
        self.budget_guard = self.provider_budget_guards.get("azure")
        self.runner_cleanup = runner_cleanup
        self.repository_catalog = repository_catalog
        self.repository_authorizer = repository_authorizer
        self.repository_ref_catalog = repository_ref_catalog
        self.create_lock = threading.Lock()

    def budget_provider_for_os(self, os_name):
        resolver = getattr(self.provider, "budget_provider_for_os", None)
        if callable(resolver):
            return resolver(os_name)
        return getattr(self.provider, "budget_provider", "azure")

    def budget_guard_for_os(self, os_name):
        return self.provider_budget_guards.get(self.budget_provider_for_os(os_name))

    @staticmethod
    def public(row):
        return {k: row.get(k) for k in (
            "id", "state", "target_os", "created_at", "updated_at",
            "expires_at", "runner_name", "labels"
        )}

    def create(self, payload, key):
        if not isinstance(key, str) or not 8 <= len(key) <= 200:
            raise PolicyDenied("Idempotency-Key must be 8..200 characters", 400)
        request = validate_runner_request(payload, self.settings, self.repository_authorizer)
        fingerprint = idempotency_fingerprint(request)
        # Reserve capacity before releasing the lock to provision. The durable
        # provisioning row is counted by the next request, preventing local races.
        with self.create_lock:
            old = self.store.get_by_key(key)
            if old:
                if old["fingerprint"] != fingerprint:
                    raise LifecycleConflict("Idempotency key conflicts with an existing request")
                return self.public(old), False
            budget_guard = self.budget_guard_for_os(request["target_os"])
            if getattr(self.provider, "requires_budget_guard", False) and budget_guard is None:
                raise PolicyDenied(
                    "Live provider-specific budget guard is not configured", 503
                )
            if getattr(self.provider, "requires_runner_cleanup", False) and self.runner_cleanup is None:
                raise PolicyDenied("GitHub runner deregistration is not configured", 503)
            readiness = getattr(self.provider, "readiness", None)
            if callable(readiness):
                try:
                    ready = readiness(request["target_os"])
                except Exception:
                    ready = None
                if not isinstance(ready, dict) or ready.get("ready") is not True:
                    raise PolicyDenied("Selected runner provider is not ready", 503)
            active_count = self.store.active_count()
            self.settings.authorize_provisioning(active_count, dynamic_repository_authorization=callable(self.repository_authorizer))
            if budget_guard is not None:
                budget_guard.authorize(active_count)
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
            provider_id = getattr(exc, "provider_id", None)
            self.store.transition(
                rid, "failed", provider_id=provider_id, detail=type(exc).__name__,
            )
            if provider_id:
                try:
                    self.terminate(rid)
                except Exception:
                    # The row remains terminating and is retried by reconciliation.
                    pass
            raise
        return self.public(row), True

    def list_repositories(self):
        if not callable(self.repository_catalog):
            raise RuntimeError("GitHub App repository catalog is not configured")
        repositories = self.repository_catalog()
        if not isinstance(repositories, list):
            raise RuntimeError("GitHub App repository catalog returned an invalid response")
        return repositories

    def list_repository_refs(self, repository, kind="branches"):
        if not callable(self.repository_ref_catalog):
            raise RuntimeError("GitHub App repository ref catalog is not configured")
        if not callable(self.repository_authorizer):
            raise RuntimeError("GitHub App repository authorization is not configured")
        if self.repository_authorizer(repository) is not True:
            raise PermissionError("Repository is not accessible to the DCP GitHub App installation")
        refs = self.repository_ref_catalog(repository, kind)
        if not isinstance(refs, list):
            raise RuntimeError("GitHub App repository ref catalog returned an invalid response")
        return refs

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
        if row.get("provider_id"):
            if self.runner_cleanup is not None:
                try:
                    result = self.runner_cleanup(row, instance)
                except Exception:
                    self.store.record_event(rid, "cleanup_retry", "pending")
                    self.store.mark_cleanup_due(rid)
                    raise
                self.store.record_event(rid, "runner_cleanup_confirmed", result)
            else:
                self.store.record_event(rid, "provider_cleanup_confirmed", "provider_only")
        return self.store.transition(rid, terminal)

    def get(self, rid):
        row = self.store.get(rid)
        if not row:
            return None
        if row["provider_id"] and row["state"] in ("provisioning", "online", "terminating"):
            instance = self.provider.status(row["provider_id"])
            if instance.state == "online" and row["state"] == "provisioning":
                row = self.store.transition(rid, "online")
            elif instance.state == "terminating":
                if row["state"] != "terminating":
                    row = self.store.transition(rid, "terminating")
                self.store.record_event(rid, "cleanup_retry", "pending")
                self.store.mark_cleanup_due(rid)
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
            self.store.mark_cleanup_due(rid)
            raise
        if instance.state in ("terminated", "failed"):
            row = self._finalize_provider_state(row, instance)
        else:
            self.store.record_event(rid, "cleanup_retry", "pending")
            self.store.mark_cleanup_due(rid)
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
