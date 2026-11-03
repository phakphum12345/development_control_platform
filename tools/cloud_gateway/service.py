"""Fail-closed gateway orchestration over injected provider and durable store."""
import uuid
from datetime import datetime,timedelta,timezone
from tools.runner_backend.provider import RunnerInstance
from .policy import PolicyDenied,idempotency_fingerprint,validate_runner_request
from .store import LifecycleConflict

class GatewayService:
 def __init__(self,settings,store,provider): self.settings=settings; self.store=store; self.provider=provider
 @staticmethod
 def public(row):
  return {k:row.get(k) for k in ("id","state","target_os","created_at","updated_at","expires_at","runner_name","labels","detail")}
 def create(self,payload,key):
  if not isinstance(key,str) or not 8<=len(key)<=200: raise PolicyDenied("Idempotency-Key must be 8..200 characters",400)
  request=validate_runner_request(payload,self.settings); fingerprint=idempotency_fingerprint(request)
  old=self.store.get_by_key(key)
  if old:
   if old["fingerprint"]!=fingerprint: raise LifecycleConflict("Idempotency key conflicts with an existing request")
   return self.public(old),False
  self.settings.authorize_provisioning(self.store.active_count())
  rid=str(uuid.uuid4()); expiry=(datetime.now(timezone.utc)+timedelta(minutes=request["max_runtime_minutes"])).isoformat()
  row,created=self.store.create(rid,key,fingerprint,request,expiry)
  if not created:
   if row["fingerprint"]!=fingerprint: raise LifecycleConflict("Idempotency key conflicts with an existing request")
   return self.public(row),False
  try:
   instance=self.provider.provision(request)
   if not isinstance(instance,RunnerInstance): raise TypeError("Invalid provider result")
   row=self.store.transition(rid,"provisioning",instance.provider_id,instance.detail)
   row.update(runner_name=instance.runner_name,labels=list(instance.labels),detail=instance.detail)
  except Exception as exc:
   self.store.transition(rid,"failed",detail=type(exc).__name__); raise
  return self.public(row),True
 def get(self,rid):
  row=self.store.get(rid)
  if not row: return None
  if row["provider_id"] and row["state"] in ("provisioning","online","terminating"):
   instance=self.provider.status(row["provider_id"])
   if instance.state=="online" and row["state"]=="provisioning": row=self.store.transition(rid,"online",detail=instance.detail)
   elif instance.state in ("terminated","failed") and row["state"]!=instance.state: row=self.store.transition(rid,instance.state,detail=instance.detail)
   row.update(runner_name=instance.runner_name,labels=list(instance.labels),detail=instance.detail)
  return self.public(row)
 def terminate(self,rid):
  row=self.store.get(rid)
  if not row: return None
  if row["state"]=="terminated": return self.public(row)
  if row["state"]!="terminating": row=self.store.transition(rid,"terminating")
  if row["provider_id"]:
   instance=self.provider.terminate(row["provider_id"])
   if instance.state=="terminated": row=self.store.transition(rid,"terminated",detail=instance.detail)
  return self.public(row)
