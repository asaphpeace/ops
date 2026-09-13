"""VMS Sandbox — standalone request workbench for the Dataloy VMS API.

Token-direct: the caller pastes an access token they already have (not a
stored per-customer credential from vms_api_credentials), so this bypasses
that table entirely. Session-only on the frontend — nothing here is
persisted server-side; every request is a stateless proxy call.

Write-safety (GET-only unless the caller explicitly marked their token as
the demo/sandbox one) is a frontend UI decision, not re-enforced here — this
is a single-engineer sandbox tool, not a multi-user system needing
server-side permission checks.
"""
import httpx
from fastapi import APIRouter
from pydantic import BaseModel

from app.services.dataloy_vms import VmsNotConfiguredError, call_entity_direct

router = APIRouter(prefix="/vms-sandbox", tags=["vms-sandbox"])


class VmsSandboxRequestBody(BaseModel):
    token: str
    entity: str
    host: str
    method: str = "GET"
    key: str | None = None
    filter: str | None = None
    body: dict | None = None


@router.post("/request")
async def vms_sandbox_request(data: VmsSandboxRequestBody):
    method = data.method.upper()
    if method not in ("GET", "POST", "PUT", "DELETE"):
        return {"status": None, "data": None, "message": f"Unsupported method {method}"}

    try:
        status, body = await call_entity_direct(
            data.token, data.entity, host=data.host, method=method,
            key=data.key, filter=data.filter, body=data.body,
        )
    except VmsNotConfiguredError as exc:
        return {"status": None, "data": None, "message": str(exc)}
    except httpx.RequestError as exc:
        return {"status": None, "data": None, "message": f"Request failed: {exc}"}

    return {"status": status, "data": body, "message": None}
