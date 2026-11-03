"""Authenticated HTTP API. The default provider is deliberately disabled."""
import hmac,json,os
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import unquote,urlparse
from .policy import GatewaySettings,PolicyDenied
from .service import GatewayService
from .store import LifecycleConflict,RunnerStore

class DisabledProvider:
 def provision(self,payload): raise RuntimeError("No provider adapter configured")
 def status(self,rid): raise RuntimeError("No provider adapter configured")
 def terminate(self,rid): raise RuntimeError("No provider adapter configured")

def make_handler(service,token):
 class Handler(BaseHTTPRequestHandler):
  server_version="DCPGateway/0.1"
  def log_message(self,fmt,*args): return
  def send_json(self,status,payload):
   body=json.dumps(payload,separators=(",",":")).encode()
   self.send_response(status); self.send_header("Content-Type","application/json"); self.send_header("Content-Length",str(len(body))); self.send_header("Cache-Control","no-store"); self.send_header("X-Content-Type-Options","nosniff"); self.end_headers(); self.wfile.write(body)
  def authorized(self):
   h=self.headers.get("Authorization",""); supplied=h[7:] if h.startswith("Bearer ") else ""
   return bool(token) and hmac.compare_digest(supplied,token)
  def body(self):
   try: n=int(self.headers.get("Content-Length","0"))
   except ValueError: raise PolicyDenied("Invalid Content-Length",400)
   if not 1<=n<=32768: raise PolicyDenied("Body size must be 1..32768 bytes",413)
   try: return json.loads(self.rfile.read(n).decode("utf-8"))
   except (UnicodeDecodeError,json.JSONDecodeError): raise PolicyDenied("Body must be UTF-8 JSON",400)
  def do_GET(self):
   path=urlparse(self.path).path
   if path=="/healthz": return self.send_json(200,{"status":"ok","provisioning_enabled":service.settings.provisioning_enabled})
   if not self.authorized(): return self.send_json(401,{"error":"unauthorized"})
   prefix="/v1/runners/"
   if not path.startswith(prefix): return self.send_json(404,{"error":"not found"})
   rid=unquote(path[len(prefix):])
   if not rid or "/" in rid: return self.send_json(400,{"error":"invalid runner id"})
   try: result=service.get(rid)
   except Exception: return self.send_json(503,{"error":"provider status unavailable"})
   return self.send_json(200,result) if result else self.send_json(404,{"error":"not found"})
  def do_POST(self):
   if urlparse(self.path).path!="/v1/runners": return self.send_json(404,{"error":"not found"})
   if not self.authorized(): return self.send_json(401,{"error":"unauthorized"})
   try:
    result,created=service.create(self.body(),self.headers.get("Idempotency-Key",""))
    return self.send_json(202 if created else 200,result)
   except PolicyDenied as e: return self.send_json(e.status_code,{"error":str(e)})
   except LifecycleConflict as e: return self.send_json(409,{"error":str(e)})
   except Exception: return self.send_json(503,{"error":"provisioning failed"})
  def do_DELETE(self):
   if not self.authorized(): return self.send_json(401,{"error":"unauthorized"})
   path=urlparse(self.path).path; prefix="/v1/runners/"
   if not path.startswith(prefix): return self.send_json(404,{"error":"not found"})
   rid=unquote(path[len(prefix):])
   if not rid or "/" in rid: return self.send_json(400,{"error":"invalid runner id"})
   try: result=service.terminate(rid)
   except Exception: return self.send_json(503,{"error":"termination incomplete"})
   return self.send_json(200,result) if result else self.send_json(404,{"error":"not found"})
 return Handler

def main():
 settings=GatewaySettings.from_env(); settings.validate_configuration()
 if not settings.api_token: raise SystemExit("DCP_GATEWAY_API_TOKEN required; refusing unauthenticated startup")
 host=os.getenv("DCP_GATEWAY_HOST","127.0.0.1"); port=int(os.getenv("DCP_GATEWAY_PORT","8789"))
 service=GatewayService(settings,RunnerStore(os.getenv("DCP_GATEWAY_DATABASE","dcp-gateway.sqlite3")),DisabledProvider())
 ThreadingHTTPServer((host,port),make_handler(service,settings.api_token)).serve_forever()
if __name__=="__main__": main()
