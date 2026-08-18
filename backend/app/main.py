import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import settings
from app.scheduler import init_scheduler
from app.routers import health
from app.routers import customers, cases, upgrades, releases, seed, migrations, education

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

app.include_router(health.router)
app.include_router(customers.router)
app.include_router(cases.router)
app.include_router(upgrades.router)
app.include_router(releases.router)
app.include_router(migrations.router)
app.include_router(education.router)
app.include_router(seed.router)


@app.get("/")
async def root():
    return {"service": "sedna-ops", "version": "0.1.0", "phase": 1}
