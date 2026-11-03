"""Durable SQLite lifecycle and credential-free audit ledger."""
import json, sqlite3, threading
from datetime import datetime,timezone
from pathlib import Path

ACTIVE=("provisioning","online","terminating")
TRANSITIONS={"provisioning":{"online","terminating","terminated","failed"},"online":{"terminating","terminated","failed"},"terminating":{"terminated","failed"},"failed":{"terminating","terminated"},"terminated":set()}
def now(): return datetime.now(timezone.utc).isoformat()
class LifecycleConflict(RuntimeError): pass
class RunnerStore:
 def __init__(self,path="dcp-gateway.sqlite3"):
  self.path=str(path); self.lock=threading.RLock()
  if self.path!=":memory:": Path(self.path).parent.mkdir(parents=True,exist_ok=True)
  with self.db() as c:
   c.executescript("""CREATE TABLE IF NOT EXISTS runners(id TEXT PRIMARY KEY,idempotency_key TEXT UNIQUE NOT NULL,fingerprint TEXT NOT NULL,repository TEXT NOT NULL,workflow_run_id INTEGER NOT NULL,commit_sha TEXT NOT NULL,target_os TEXT NOT NULL,provider_id TEXT,state TEXT NOT NULL,request_json TEXT NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,expires_at TEXT NOT NULL); CREATE INDEX IF NOT EXISTS idx_state ON runners(state); CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,runner_id TEXT,event TEXT,detail_json TEXT,created_at TEXT);""")
 def db(self):
  c=sqlite3.connect(self.path,timeout=10,isolation_level=None); c.row_factory=sqlite3.Row; return c
 def active_count(self):
  with self.lock,self.db() as c: return c.execute("SELECT count(*) FROM runners WHERE state IN (?,?,?)",ACTIVE).fetchone()[0]
 def get(self,rid):
  with self.lock,self.db() as c:
   r=c.execute("SELECT * FROM runners WHERE id=?",(rid,)).fetchone(); return dict(r) if r else None
 def get_by_key(self,key):
  with self.lock,self.db() as c:
   r=c.execute("SELECT * FROM runners WHERE idempotency_key=?",(key,)).fetchone(); return dict(r) if r else None
 def create(self,rid,key,fingerprint,payload,expires):
  with self.lock,self.db() as c:
   c.execute("BEGIN IMMEDIATE")
   old=c.execute("SELECT * FROM runners WHERE idempotency_key=?",(key,)).fetchone()
   if old:
    if old["fingerprint"]!=fingerprint: raise LifecycleConflict("Idempotency key conflicts with an existing request")
    c.execute("COMMIT"); return dict(old),False
   t=now()
   c.execute("INSERT INTO runners VALUES(?,?,?,?,?,?,?,NULL,'provisioning',?,?,?,?)",(rid,key,fingerprint,payload["repository"],payload["workflow_run_id"],payload["commit_sha"],payload["target_os"],json.dumps(payload,sort_keys=True),t,t,expires))
   c.execute("INSERT INTO audit(runner_id,event,detail_json,created_at) VALUES(?,?,?,?)",(rid,"provisioning_requested","{}",t))
   c.execute("COMMIT"); return self.get(rid),True
 def transition(self,rid,state,provider_id=None,detail=None):
  with self.lock,self.db() as c:
   c.execute("BEGIN IMMEDIATE"); r=c.execute("SELECT * FROM runners WHERE id=?",(rid,)).fetchone()
   if not r: raise KeyError(rid)
   if state not in TRANSITIONS.get(r["state"],set()): raise LifecycleConflict("Invalid transition "+r["state"]+" -> "+state)
   t=now(); c.execute("UPDATE runners SET state=?,provider_id=COALESCE(?,provider_id),updated_at=? WHERE id=?",(state,provider_id,t,rid))
   safe={"detail":detail[:300]} if isinstance(detail,str) else {}
   c.execute("INSERT INTO audit(runner_id,event,detail_json,created_at) VALUES(?,?,?,?)",(rid,state,json.dumps(safe),t)); c.execute("COMMIT")
   return self.get(rid)
 def audit_events(self,rid):
  with self.lock,self.db() as c:
   return [{"event":r["event"],"detail":json.loads(r["detail_json"]),"created_at":r["created_at"]} for r in c.execute("SELECT * FROM audit WHERE runner_id=? ORDER BY id",(rid,))]
