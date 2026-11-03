"""Read-only Azure Consumption budget guard; this adapter never creates budgets."""
from __future__ import annotations
import json,math,re
from dataclasses import dataclass
from urllib.parse import quote
from urllib.request import Request,urlopen
from .azure_identity import ManagedIdentityCredential

class BudgetReadError(RuntimeError): pass
@dataclass(frozen=True)
class BudgetSnapshot:
 amount:float
 current_spend:float
 forecast_spend:float|None
 currency:str
 def permits(self,projected_cost:float)->bool:
  if not math.isfinite(projected_cost) or projected_cost<0: return False
  if self.currency.upper()!="USD": return False
  if self.current_spend+projected_cost>self.amount: return False
  return self.forecast_spend is None or self.forecast_spend+projected_cost<=self.amount
class AzureBudgetReader:
 def __init__(self,subscription_id,budget_name,credential=None,timeout=10):
  if not re.fullmatch(r"[0-9a-fA-F-]{36}",subscription_id): raise ValueError("Invalid subscription ID")
  if not re.fullmatch(r"[A-Za-z0-9_.-]{1,63}",budget_name): raise ValueError("Invalid budget name")
  self.subscription_id=subscription_id; self.budget_name=budget_name
  self.credential=credential or ManagedIdentityCredential(); self.timeout=timeout
 def read(self):
  url=("https://management.azure.com/subscriptions/"+self.subscription_id+
       "/providers/Microsoft.Consumption/budgets/"+quote(self.budget_name,safe="")+
       "?api-version=2023-05-01")
  try:
   token=self.credential.get_token("https://management.azure.com/")
   req=Request(url,headers={"Authorization":"Bearer "+token,"Accept":"application/json"})
   with urlopen(req,timeout=self.timeout) as response: data=json.loads(response.read(65537).decode("utf-8"))
  except Exception as exc:
   raise BudgetReadError("Azure budget read failed: "+type(exc).__name__) from exc
  try:
   p=data["properties"]; amount=float(p["amount"]); current=float(p["currentSpend"]["amount"])
   currency=str(p["currentSpend"]["unit"])
   forecast=p.get("forecastSpend")
   forecast_amount=float(forecast["amount"]) if forecast and "amount" in forecast else None
   if not all(math.isfinite(x) and x>=0 for x in (amount,current)) or (forecast_amount is not None and (not math.isfinite(forecast_amount) or forecast_amount<0)): raise ValueError()
   if not currency: raise ValueError()
   return BudgetSnapshot(amount,current,forecast_amount,currency)
  except (KeyError,TypeError,ValueError) as exc:
   raise BudgetReadError("Azure budget response is incomplete or invalid") from exc
