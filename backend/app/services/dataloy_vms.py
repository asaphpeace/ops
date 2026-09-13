"""Machine-to-machine client for the real Dataloy VMS REST API.
Docs live at api.dataloy.com/dataloy-rest-api, but that host is the GitBook
docs site itself, not the API — confirmed live (a request there returns
GitBook's own HTML). The real API host is per-tenant: each customer's own
subdomain, at that subdomain's /ws/rest path (confirmed live against
https://demonew.dataloy.com/ws/rest/{Entity}/{key} — real, rich payloads
returned for Vessel/PortCall/Voyage/Cargo, chased end-to-end via their
{key,self} relationship pointers). Auth is an OAuth2 client-credentials
grant (client_id/client_secret/grant_type=client_credentials/audience -> a
JWT access_token with expires_in=86400, i.e. 24h — the docs explicitly say
to reuse the same token for its full lifetime rather than requesting a new
one per call). The API itself is a generic REST-over-entities shape:
GET /{Entity}/{key}, GET /{Entity}?filter=..., POST/PUT/DELETE /{Entity}/{key}
(filter syntax confirmed live, e.g. filter=currencyCode(EQ)USD). Unfiltered
list calls are capped at 2000 objects (confirmed live via a real 400 on an
unfiltered Voyage list).

Degrades gracefully like every other optional integration in this app
(ai_enabled, calendar_enabled): a missing token URL, missing credential, or
missing host raises VmsNotConfiguredError, which callers turn into a clear
"not configured" response, never a 500.
"""
import httpx

from app.config import settings
from app.models.vms_api_credential import VmsApiCredential


class VmsNotConfiguredError(Exception):
    pass


async def get_access_token(credential: VmsApiCredential, db) -> str:
    """Return a valid access token for this credential, reusing the cached
    one if it hasn't expired yet (per the docs' own "don't refetch per call"
    guidance) — otherwise requests a fresh one and persists it."""
    from datetime import datetime, timedelta, timezone

    if not settings.dataloy_vms_token_url:
        raise VmsNotConfiguredError("dataloy_vms_token_url is not configured")

    now = datetime.now(timezone.utc)
    if credential.cached_token and credential.token_expires_at and credential.token_expires_at > now:
        return credential.cached_token

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.post(
            settings.dataloy_vms_token_url,
            data={
                "client_id": credential.client_id,
                "client_secret": credential.client_secret,
                "grant_type": "client_credentials",
                "audience": credential.audience,
            },
        )
        resp.raise_for_status()
        data = resp.json()

    token = data["access_token"]
    expires_in = data.get("expires_in", 86400)
    credential.cached_token = token
    credential.token_expires_at = now + timedelta(seconds=expires_in)
    await db.commit()
    return token


async def get_entity(credential: VmsApiCredential, db, entity: str, key: str) -> dict:
    """GET /{entity}/{key} — raw entity fetch, no transformation."""
    if not settings.dataloy_vms_api_base_url:
        raise VmsNotConfiguredError("dataloy_vms_api_base_url is not configured")
    token = await get_access_token(credential, db)
    url = f"{settings.dataloy_vms_api_base_url.rstrip('/')}/{entity}/{key}"
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"})
        resp.raise_for_status()
        return resp.json()


async def list_entity(credential: VmsApiCredential, db, entity: str, filter: str | None = None) -> list[dict]:
    """GET /{entity}?filter=... — raw entity list, no transformation."""
    if not settings.dataloy_vms_api_base_url:
        raise VmsNotConfiguredError("dataloy_vms_api_base_url is not configured")
    token = await get_access_token(credential, db)
    url = f"{settings.dataloy_vms_api_base_url.rstrip('/')}/{entity}"
    params = {"filter": filter} if filter else {}
    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {token}"}, params=params)
        resp.raise_for_status()
        data = resp.json()
        return data if isinstance(data, list) else data.get("items", [data])


async def call_entity_direct(
    token: str, entity: str, host: str, method: str = "GET",
    key: str | None = None, filter: str | None = None, body: dict | None = None,
) -> tuple[int, object]:
    """Token-direct variant for the VMS Sandbox — the token is already in
    hand (pasted by the engineer), so this bypasses get_access_token()'s
    credential-row cache/lookup entirely. Not used by the per-customer
    explorer above (that goes through a stored VmsApiCredential); this is
    the sandbox's own path. Returns (status_code, parsed_body_or_text) —
    never raises on a non-2xx VMS response, only on a genuine network/config
    failure, so the sandbox can show the engineer a real error status
    instead of a generic failure.

    The API host is genuinely per-tenant (confirmed live — each customer's
    own subdomain, not a single global host), so unlike get_entity/
    list_entity above, this takes the host per-call rather than reading the
    single global settings.dataloy_vms_api_base_url — the whole point of the
    sandbox is testing against whichever tenant a pasted token belongs to.
    /ws/rest is hardcoded since it was confirmed identical across every hop
    of a real multi-entity chase this session."""
    if not host or not host.strip():
        raise VmsNotConfiguredError("host is required")

    clean_host = host.strip().removeprefix("https://").removeprefix("http://").rstrip("/")
    url = f"https://{clean_host}/ws/rest/{entity}"
    if key and method in ("GET", "PUT", "DELETE"):
        url = f"{url}/{key}"

    headers = {"Authorization": f"Bearer {token}"}
    params = {"filter": filter} if (filter and method == "GET") else {}
    json_body = body if method in ("POST", "PUT") else None

    async with httpx.AsyncClient(timeout=20) as client:
        resp = await client.request(method, url, headers=headers, params=params, json=json_body)

    try:
        data = resp.json()
    except Exception:
        data = resp.text
    return resp.status_code, data
