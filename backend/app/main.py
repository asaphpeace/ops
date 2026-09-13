import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from jose import JWTError, jwt

from app.config import settings
from app.scheduler import init_scheduler
from app.routers import health, auth
from app.routers import customers, cases, upgrades, releases, seed, migrations, education, sso, cancellations, campaigns
from app.routers import jira as jira_router, snapshot, desk, support_signals, bugs, command_center, vms_sandbox, incidents, tenant_discovery, ai_observations, ops_notes, ollama_chat, knowledge, migration_priority, audit_log, weekly_report, engineering, troubleshoot
import app.models.jira_unmatched  # noqa: F401 — ensures table is registered with Base
import app.models.aws_resource  # noqa: F401
import app.models.log_entry  # noqa: F401
import app.models.audit_log  # noqa: F401
import app.models.case_snapshot  # noqa: F401
import app.models.vms_bug  # noqa: F401
import app.models.customer_tenant_info  # noqa: F401
import app.models.unmatched_upgrade_customer  # noqa: F401
import app.models.customer_name_alias  # noqa: F401
import app.models.cancellation  # noqa: F401
import app.models.ollama_call_log  # noqa: F401
import app.models.ollama_conversation  # noqa: F401
import app.models.ollama_search_index  # noqa: F401
import app.models.knowledge_extract  # noqa: F401
import app.models.engineering_snapshot  # noqa: F401
import app.models.runbook  # noqa: F401

# Paths that never require a token (prefix-matched against the FastAPI path,
# i.e. after nginx has already stripped the /api prefix)
_AUTH_EXEMPT_PREFIXES = ("/health", "/auth/", "/seed")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Sedna Ops API starting")
    init_scheduler()
    yield
    logger.info("Sedna Ops API shutting down")


app = FastAPI(
    title="Sedna Ops API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def jwt_auth_middleware(request: Request, call_next):
    if not settings.auth_enabled:
        return await call_next(request)

    path = request.url.path
    if any(path.startswith(p) for p in _AUTH_EXEMPT_PREFIXES):
        return await call_next(request)

    auth_header = request.headers.get("Authorization", "")
    if not auth_header.startswith("Bearer "):
        return JSONResponse({"detail": "Not authenticated"}, status_code=401)

    try:
        jwt.decode(auth_header[7:], settings.secret_key, algorithms=[settings.algorithm])
    except JWTError:
        return JSONResponse({"detail": "Invalid or expired token"}, status_code=401)

    return await call_next(request)


app.include_router(health.router)
app.include_router(auth.router)
app.include_router(jira_router.router)
app.include_router(customers.router)
app.include_router(cases.router)
app.include_router(upgrades.router)
app.include_router(releases.router)
app.include_router(migrations.router)
app.include_router(cancellations.router)
app.include_router(campaigns.router)
app.include_router(education.router)
app.include_router(sso.router)
app.include_router(snapshot.router)
app.include_router(desk.router)
app.include_router(support_signals.router)
app.include_router(bugs.router)
app.include_router(command_center.router)
app.include_router(vms_sandbox.router)
app.include_router(incidents.router)
app.include_router(audit_log.router)
app.include_router(weekly_report.router)
app.include_router(tenant_discovery.router)
app.include_router(ai_observations.router)
app.include_router(ops_notes.router)
app.include_router(ollama_chat.router)
app.include_router(knowledge.router)
app.include_router(migration_priority.router)
app.include_router(engineering.router)
app.include_router(troubleshoot.router)
app.include_router(seed.router)


@app.get("/")
async def root():
    return {"service": "sedna-ops", "version": "0.1.0", "phase": 1}
