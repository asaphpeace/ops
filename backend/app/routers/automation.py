"""Upgrade Runner — drives aws-util's upgrade_environment.sh through the host
runner (runner/sedna_runner.py) with a gated flow:

  pre-checks (runner up, SSO valid, ECR tag exists, live /info)
  → dry-run (required) → typed confirmation → real run with live log
  → post-check (/info reports the new release).

The runner holds jobs in memory only; every run is mirrored into
AutomationRun (log included) each time the UI polls it, so history survives
runner restarts. Every start/cancel/post-check is audit-logged.
"""
import re
from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.automation_run import AutomationRun
from app.models.customer import Customer
from app.models.customer_tenant_info import CustomerTenantInfo
from app.models.release import Release
from app.models.verified_version import VerifiedVersion
from app.models.runner_env_host import RunnerEnvHost
from app.services.cert_scan import _resolve_hostname
from app.services.release_catalog import published_versions, release_url, version_key

router = APIRouter(prefix="/automation", tags=["automation"])

_VERSION_RE = re.compile(r"^\d+\.\d+\.\d+$")
_DRY_RUN_VALID_FOR = timedelta(minutes=60)
_KINDS = {"upgrade_environment", "ecr_tag_check", "ecs_force_deploy"}


# ── Runner client ────────────────────────────────────────────────────────

async def _runner(method: str, path: str, json: dict | None = None, timeout: float = 30) -> dict | list:
    if not settings.runner_enabled:
        raise HTTPException(status_code=503, detail="Runner not configured (RUNNER_URL / RUNNER_TOKEN in .env)")
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.request(
                method, f"{settings.runner_url.rstrip('/')}{path}",
                headers={"X-Runner-Token": settings.runner_token}, json=json,
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=503, detail="Runner is not reachable — start runner/sedna_runner.py on this Mac")
    if resp.status_code == 401:
        raise HTTPException(status_code=503, detail="Runner rejected the token — RUNNER_TOKEN in .env and runner/runner.env differ")
    body = resp.json()
    if resp.status_code >= 400:
        raise HTTPException(status_code=resp.status_code, detail=body.get("error", "Runner error"))
    return body


# ── Environment ↔ customer tenant matching ────────────────────────────────

def _info_url(target: str) -> str:
    """Same bare-code vs custom-domain rule as cert_scan._resolve_hostname,
    so "vms.klaveness.com" isn't wrapped onto *.dataloy.com."""
    if "://" in target:
        return target if "/ws/rest/" in target else target.rstrip("/") + "/ws/rest/dataloy/info"
    return f"https://{_resolve_hostname(target)}/ws/rest/dataloy/info"


async def _tenant_index(db: AsyncSession) -> dict[str, CustomerTenantInfo]:
    rows = (await db.execute(
        select(CustomerTenantInfo).options(joinedload(CustomerTenantInfo.customer))
    )).scalars().all()
    return {_resolve_hostname(r.subdomain).lower(): r for r in rows if r.subdomain}


def _match_tenant(env_name: str, index: dict[str, CustomerTenantInfo]) -> CustomerTenantInfo | None:
    """aws-util env names are usually the tenant subdomain itself
    ("sedna-dev", "breadbox-test"); PROD tenants are often the bare base
    ("breadbox" for "breadbox-prod")."""
    candidates = [env_name]
    if env_name.endswith("-prod"):
        candidates.append(env_name[: -len("-prod")])
    for c in candidates:
        row = index.get(f"{c}.dataloy.com".lower())
        if row:
            return row
    return None


async def _probe_target(db: AsyncSession, env_name: str) -> str:
    """What to probe for an aws-util environment's /info: a saved public
    host override first (unlinked envs like demo-test → demo.dataloy.com),
    then the linked customer instance's subdomain, then the env name."""
    override = (await db.execute(select(RunnerEnvHost).where(RunnerEnvHost.environment == env_name))).scalar_one_or_none()
    if override:
        return override.host
    t = _match_tenant(env_name, await _tenant_index(db))
    return t.subdomain if t else env_name


def _same_version(release: str | None, target: str | None) -> bool:
    if not release or not target:
        return False
    return re.split(r"[-_]", release.strip())[0] == target


async def _probe_info(target: str) -> dict:
    url = _info_url(target)
    started = datetime.now(timezone.utc)
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as client:
            resp = await client.get(url)
        ms = int((datetime.now(timezone.utc) - started).total_seconds() * 1000)
        if resp.status_code != 200:
            return {"ok": False, "url": url, "latency_ms": ms, "error": f"HTTP {resp.status_code}"}
        data = resp.json()
        return {"ok": True, "url": url, "latency_ms": ms, "release": data.get("release"), "environment": data.get("environment")}
    except httpx.TimeoutException:
        return {"ok": False, "url": url, "error": "Timed out — tenant may be VPN/firewall-restricted"}
    except Exception as exc:
        return {"ok": False, "url": url, "error": str(exc)[:300]}


# ── Serialisation / sync ─────────────────────────────────────────────────

def _run_out(r: AutomationRun, since: int | None = None) -> dict:
    out = {
        "id": r.id, "kind": r.kind, "environment": r.environment, "from_version": r.from_version,
        "target_version": r.target_version, "dry_run": r.dry_run, "dry_run_of_id": r.dry_run_of_id,
        "customer_id": r.customer_id, "customer_name": r.customer.name if r.customer else None,
        "status": r.status, "exit_code": r.exit_code, "log_line_count": r.log_line_count,
        "post_check_release": r.post_check_release, "post_check_ok": r.post_check_ok,
        "post_checked_at": r.post_checked_at, "actor": r.actor,
        "started_at": r.started_at, "finished_at": r.finished_at,
    }
    if since is not None:
        lines = r.log.split("\n") if r.log else []
        out["lines"] = lines[since:]
    return out


async def _get_run(db: AsyncSession, run_id: int) -> AutomationRun:
    run = (await db.execute(
        select(AutomationRun).options(joinedload(AutomationRun.customer)).where(AutomationRun.id == run_id)
    )).scalar_one_or_none()
    if not run:
        raise HTTPException(status_code=404, detail="Run not found")
    return run


async def _sync(db: AsyncSession, run: AutomationRun) -> None:
    """Pull new log lines + status from the runner into the DB row."""
    if run.status != "running" or not run.runner_job_id:
        return
    try:
        job = await _runner("GET", f"/jobs/{run.runner_job_id}?since={run.log_line_count}")
    except HTTPException as exc:
        if exc.status_code == 404:  # runner restarted — the job is gone
            run.status, run.finished_at = "lost", datetime.now(timezone.utc)
            await db.commit()
        return  # runner unreachable: keep "running", try again on next poll
    new = [line["text"] for line in job.get("lines", [])]
    if new:
        run.log = (run.log + "\n" if run.log else "") + "\n".join(new)
        run.log_line_count += len(new)
    if job["status"] != "running":
        run.status, run.exit_code = job["status"], job.get("exit_code")
        run.finished_at = datetime.now(timezone.utc)
    await db.commit()


# ── Endpoints ────────────────────────────────────────────────────────────

@router.get("/status")
async def runner_status():
    if not settings.runner_enabled:
        return {"enabled": False, "reachable": False, "error": "Runner not configured"}
    try:
        health = await _runner("GET", "/health", timeout=20)
        sso = await _runner("GET", "/sso")
        return {"enabled": True, "reachable": True, "gitlab_token_set": health.get("gitlab_token_set"),
                "gitlab": health.get("gitlab"), "sso": sso}
    except HTTPException as exc:
        return {"enabled": True, "reachable": False, "error": exc.detail}


async def _version_catalog(db: AsyncSession) -> tuple[dict[str, str], str]:
    """Every acceptable upgrade target → how we know it's real, plus where
    the published list came from. Basis values, strongest first:
      releasenotes — on releasenotes.dataloy.com right now
      jira         — released in Jira's VMS project (Release table, synced
                     daily). Jira is the most current record — releasenotes
                     runs a couple of patches behind (8.31.7/8.31.8 were
                     released in Jira before releasenotes had them).
      remembered   — confirmed on releasenotes earlier (kept in VerifiedVersion)
      manual       — verified by a person when neither source has it yet
    The real run's ECR image check stays the hard gate either way.
    """
    catalog: dict[str, str] = {}
    published, _ = await published_versions()
    if published:
        catalog.update({v: "releasenotes" for v in published})
    for v in (await db.execute(select(Release.version))).scalars().all():
        base = v.split("-")[0]
        if _VERSION_RE.match(base) and base not in catalog:
            catalog[base] = "jira"
    for row in (await db.execute(select(VerifiedVersion))).scalars().all():
        if row.version not in catalog:
            catalog[row.version] = "manual" if row.source == "manual" else "remembered"
    source = "releasenotes.dataloy.com + Jira releases" if published else "Jira releases (releasenotes.dataloy.com unreachable)"
    return catalog, source


async def _remember(db: AsyncSession, version: str, source: str, note: str | None = None) -> VerifiedVersion:
    """Record a verification decision once; a later releasenotes
    confirmation upgrades a manual entry (the delay has caught up)."""
    row = (await db.execute(select(VerifiedVersion).where(VerifiedVersion.version == version))).scalar_one_or_none()
    if row is None:
        row = VerifiedVersion(version=version, source=source, note=note, verified_at=datetime.now(timezone.utc))
        db.add(row)
    elif row.source == "manual" and source == "releasenotes":
        row.source = "releasenotes"
    return row


def _strip_auth0(v: str | None) -> str | None:
    return re.split(r"-auth0$", v)[0] if v else None


_last_envs: dict = {"envs": None}  # last successful runner /environments


@router.get("/targets")
async def list_targets(db: AsyncSession = Depends(get_db)):
    """What can be upgraded, organised the way support thinks about it:
    VMS customers → their PROD/TEST instances, each linked to its aws-util
    environment when one exists. Runner environments that match no
    customer instance (sedna-dev, staging, demo…) are listed separately."""
    # Still useful with the runner down: customers and instances load, and
    # the last known aws-util environment list is reused so the picker can
    # still find e.g. demo-test while the runner restarts (nothing can run
    # until it's back anyway — the UI says so).
    try:
        envs = await _runner("GET", "/environments")
        runner_online = True
        _last_envs["envs"] = envs
    except HTTPException:
        envs, runner_online = _last_envs["envs"] or [], False
    index = await _tenant_index(db)
    hosts = {h.environment: h.host for h in (await db.execute(select(RunnerEnvHost))).scalars()}
    env_by_tenant: dict[int, dict] = {}
    other = []
    for e in envs:
        t = _match_tenant(e["name"], index)
        if t and t.customer and t.customer.product and "VMS" in t.customer.product.upper():
            env_by_tenant[t.id] = e
        else:
            other.append({"runner_env": e["name"], "region": e["region"],
                          "current_version": _strip_auth0(e.get("repo_version") or e.get("listed_version")),
                          "host": hosts.get(e["name"])})

    customers = (await db.execute(
        select(Customer).options(joinedload(Customer.tenant_info)).where(Customer.product.ilike("%vms%")).order_by(Customer.name)
    )).unique().scalars().all()
    env_order = {"PROD": 0, "TEST": 1, "DEV": 2}
    out = []
    for c in customers:
        instances = []
        for t in sorted(c.tenant_info, key=lambda t: env_order.get(t.environment, 9)):
            e = env_by_tenant.get(t.id)
            instances.append({
                "environment": t.environment, "subdomain": t.subdomain,
                "runner_env": e["name"] if e else None, "region": e["region"] if e else None,
                "current_version": _strip_auth0(e.get("repo_version")) if e else (t.release or "").split("-")[0] or None,
            })
        out.append({"customer_id": c.id, "name": c.name, "tier": c.tier, "instances": instances})
    return {"customers": out, "other_environments": sorted(other, key=lambda o: o["runner_env"]),
            "runner_online": runner_online, "environments_cached": not runner_online and bool(envs)}


@router.get("/versions")
async def list_versions(db: AsyncSession = Depends(get_db)):
    catalog, source = await _version_catalog(db)
    ordered = sorted(catalog, key=version_key, reverse=True)
    return {
        "versions": [{"version": v, "basis": catalog[v]} for v in ordered],
        "latest": ordered[0] if ordered else None, "source": source,
    }


@router.get("/versions/{version}/check")
async def check_version(version: str, db: AsyncSession = Depends(get_db)):
    version = version.strip().lstrip("v")
    if not _VERSION_RE.match(version):
        return {"version": version, "accepted": False, "basis": None, "reason": "Not a version — expected X.Y.Z"}
    catalog, source = await _version_catalog(db)
    basis = catalog.get(version)
    if basis == "releasenotes":
        await _remember(db, version, "releasenotes")
        await db.commit()
    return {
        "version": version, "accepted": basis is not None, "basis": basis, "source": source,
        "url": release_url(version) if basis in ("releasenotes", "remembered") else None,
        "reason": None if basis else f"{version} isn't released in Jira or published on releasenotes yet — verify it manually if you've confirmed the build exists",
    }


@router.post("/versions/{version}/verify")
async def verify_version(version: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Manual verification for a release that's real but not on releasenotes
    yet. Remembered; audit-logged; the real run's ECR check is still the
    hard stop if no image was ever built."""
    version = version.strip().lstrip("v")
    if not _VERSION_RE.match(version):
        raise HTTPException(status_code=400, detail="version must look like X.Y.Z")
    catalog, _ = await _version_catalog(db)
    source = "releasenotes" if catalog.get(version) == "releasenotes" else "manual"
    note = (data.get("note") or "").strip() or None
    await _remember(db, version, source, note)
    db.add(AuditLog(actor="you", action="automation.version_verified", target_type="version", target_id=version,
                    detail=f"{source}{': ' + note if note else ''}"))
    await db.commit()
    return await check_version(version, db)


@router.get("/environments/{name}/live")
async def live_info(name: str, db: AsyncSession = Depends(get_db)):
    return await _probe_info(await _probe_target(db, name))


@router.get("/environments/{name}/deployment")
async def deployment_status(name: str):
    """aws-util's ECS deployment monitor for one environment, one refresh."""
    return await _runner("GET", f"/monitor/{name}", timeout=70)


@router.put("/environments/{name}/host")
async def set_env_host(name: str, data: dict, db: AsyncSession = Depends(get_db)):
    """Remember the public host for an aws-util environment (empty clears it)."""
    host = (data.get("host") or "").strip().removeprefix("https://").removeprefix("http://").split("/")[0]
    row = (await db.execute(select(RunnerEnvHost).where(RunnerEnvHost.environment == name))).scalar_one_or_none()
    if not host:
        if row:
            await db.delete(row)
    elif row:
        row.host = host
    else:
        db.add(RunnerEnvHost(environment=name, host=host))
    db.add(AuditLog(actor="you", action="automation.env_host_set", target_type="runner_env", target_id=name, detail=host or "cleared"))
    await db.commit()
    return await _probe_info(host or await _probe_target(db, name))


@router.post("/sso-login")
async def sso_login():
    job = await _runner("POST", "/jobs", json={"kind": "sso_login", "args": {}})
    return {"runner_job_id": job["id"], "message": "A browser window should open on this Mac — approve the AWS sign-in there."}


_DEVICE_URL = re.compile(r"https://\S+/device\S*")
_DEVICE_CODE = re.compile(r"^\s*([A-Z0-9]{4}-[A-Z0-9]{4})\s*$")


@router.get("/sso-login/{job_id}")
async def sso_login_progress(job_id: str):
    """The device sign-in link + one-time code that `aws sso login` prints.
    AWS asks you to confirm that code in the browser — it used to be
    visible only in the runner's log, so the in-app sign-in couldn't be
    completed (confirmed 2026-10-09)."""
    job = await _runner("GET", f"/jobs/{job_id}")
    lines = [line["text"] for line in job.get("lines", [])]
    url = next((m.group(0) for line in lines if (m := _DEVICE_URL.search(line))), None)
    code = next((m.group(1) for line in lines if (m := _DEVICE_CODE.match(line))), None)
    failed = job["status"] == "failed"
    return {
        "status": job["status"], "url": url, "code": code,
        "error": lines[-2] if failed and len(lines) > 1 else None,
    }


@router.get("/runs")
async def list_runs(limit: int = 30, db: AsyncSession = Depends(get_db)):
    rows = (await db.execute(
        select(AutomationRun).options(joinedload(AutomationRun.customer))
        .order_by(AutomationRun.started_at.desc()).limit(min(limit, 200))
    )).scalars().all()
    return [_run_out(r) for r in rows]


@router.post("/runs", status_code=201)
async def start_run(data: dict, db: AsyncSession = Depends(get_db)):
    kind = data.get("kind")
    if kind not in _KINDS:
        raise HTTPException(status_code=400, detail=f"kind must be one of {sorted(_KINDS)}")
    environment = (data.get("environment") or "").strip() or None
    follows = None
    if kind == "ecs_force_deploy":
        # awsforcedeploy redeploys whatever image is already built — no
        # version of its own. When it follows an upgrade run, carry that
        # run's target over so Post-check knows what to expect.
        if not environment:
            raise HTTPException(status_code=400, detail="environment is required")
        if data.get("confirm_environment") != environment:
            raise HTTPException(status_code=400, detail="Confirm the environment name to force a deployment")
        if data.get("follows_run_id"):
            follows = await db.get(AutomationRun, int(data["follows_run_id"]))
        version = follows.target_version if follows and follows.environment == environment else None
    else:
        version = (data.get("version") or "").strip().lstrip("v")
        if not _VERSION_RE.match(version):
            raise HTTPException(status_code=400, detail="version must look like X.Y.Z")
        catalog, source = await _version_catalog(db)
        if version not in catalog:
            raise HTTPException(status_code=400, detail=f"{version} isn't released in Jira or on releasenotes, and hasn't been verified manually")
        if catalog[version] == "releasenotes":
            await _remember(db, version, "releasenotes")
    dry_run = bool(data.get("dry_run", True)) if kind == "upgrade_environment" else kind != "ecs_force_deploy"
    dry_run_of = None

    if kind == "upgrade_environment":
        if not environment:
            raise HTTPException(status_code=400, detail="environment is required")
        if not dry_run:
            # The gate that replaces the script's interactive confirm.
            if data.get("confirm_environment") != environment:
                raise HTTPException(status_code=400, detail="Type the environment name exactly to confirm a real upgrade")
            dry_run_of = await db.get(AutomationRun, int(data.get("dry_run_of_id") or 0)) if data.get("dry_run_of_id") else None
            fresh_after = datetime.now(timezone.utc) - _DRY_RUN_VALID_FOR
            if (not dry_run_of or not dry_run_of.dry_run or dry_run_of.status != "succeeded"
                    or dry_run_of.environment != environment or dry_run_of.target_version != version
                    or dry_run_of.started_at < fresh_after):
                raise HTTPException(status_code=400, detail="A successful dry-run of this environment and version from the last 60 minutes is required first")

    envs = await _runner("GET", "/environments") if environment else []
    env_row = next((e for e in envs if e["name"] == environment), None)
    if environment and not env_row:
        raise HTTPException(status_code=400, detail=f"Unknown environment: {environment}")
    t = _match_tenant(environment, await _tenant_index(db)) if environment else None

    if kind == "ecs_force_deploy":
        args = {"environment": environment}
    else:
        args = {"version": version}
    if kind == "upgrade_environment":
        args.update({"environment": environment, "dry_run": dry_run})
    job = await _runner("POST", "/jobs", json={"kind": kind, "args": args})

    run = AutomationRun(
        kind=kind, environment=environment, target_version=version, dry_run=dry_run,
        from_version=re.split(r"-auth0$", (env_row or {}).get("repo_version") or "")[0] or None,
        dry_run_of_id=dry_run_of.id if dry_run_of else (follows.id if follows else None), customer_id=t.customer_id if t else None,
        runner_job_id=job["id"], status="running", started_at=datetime.now(timezone.utc),
    )
    db.add(run)
    await db.flush()
    label = "awsforcedeploy" if kind == "ecs_force_deploy" else "dry-run" if dry_run else "REAL"
    db.add(AuditLog(actor="you", action=f"automation.{kind}.started", target_type="automation_run",
                    target_id=str(run.id), detail=f"{environment or '-'} → {version} ({label})"))
    await db.commit()
    return _run_out(await _get_run(db, run.id), since=0)


@router.get("/runs/{run_id}")
async def get_run(run_id: int, since: int = 0, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, run_id)
    await _sync(db, run)
    return _run_out(await _get_run(db, run_id), since=since)


_PIPELINE_RE = re.compile(r"Found pipeline #(\d+)")


@router.get("/runs/{run_id}/progress")
async def run_progress(run_id: int, db: AsyncSession = Depends(get_db)):
    """Stage-by-stage progress of an upgrade, for the progress donut:
    ECR image → push → build → force deploy → (ECS rollout: the UI's
    deployment monitor) → post-check. Works from the upgrade run itself or
    any force-deploy run that follows it. Build status is read-only from
    GitLab, following the same chain as the script's pipeline watch."""
    run = await _get_run(db, run_id)
    root = run
    if run.kind == "ecs_force_deploy" and run.dry_run_of_id:
        root = await _get_run(db, run.dry_run_of_id)
    if root.kind != "upgrade_environment" or root.dry_run:
        raise HTTPException(status_code=400, detail="Progress is tracked for real upgrade runs")

    log = root.log or ""
    follow_ups = (await db.execute(
        select(AutomationRun).where(AutomationRun.kind == "ecs_force_deploy", AutomationRun.dry_run_of_id == root.id)
        .order_by(AutomationRun.started_at)
    )).scalars().all()

    def stage(state: str, detail: str = "") -> dict:
        return {"state": state, "detail": detail}

    ecr = (stage("done", "image found in ECR") if "SUCCESS: Tag" in log
           else stage("failed", "image not found") if "ECR tag check failed" in log
           else stage("active" if root.status == "running" else "pending"))
    pushed = "main -> main" in log
    push = stage("done", "version pushed to GitLab") if pushed else stage("active" if root.status == "running" and ecr["state"] == "done" else "pending")

    build = stage("pending")
    pipeline = None
    m = _PIPELINE_RE.search(log)
    if m and root.environment:
        try:
            pipeline = await _runner("GET", f"/pipeline/{root.environment}/{m.group(1)}", timeout=40)
        except HTTPException as exc:
            pipeline = {"ok": False, "error": exc.detail}
        b = (pipeline or {}).get("build") or {}
        st = b.get("status")
        if not pipeline.get("ok"):
            err = pipeline.get("error", "couldn't read the pipeline")
            build = stage("unknown", "restart the runner to enable build status" if err == "not found" else err)
        elif st == "success":
            build = stage("done", f"build_customer_image succeeded in {round((b.get('duration') or 0) / 60, 1)} min")
        elif st in ("failed", "canceled"):
            build = stage("failed", f"build_customer_image {st}")
        elif st == "skipped" or pipeline.get("docker_status") == "skipped":
            build = stage("failed", "docker job skipped — commit had no docker/** change")
        else:
            build = stage("active", f"build_customer_image {st or pipeline.get('docker_status') or 'waiting to start'}")

    if any(f.status == "succeeded" for f in follow_ups):
        deploy = stage("done", f"{len(follow_ups)} attempt{'s' if len(follow_ups) != 1 else ''}")
    elif any(f.status == "running" for f in follow_ups):
        deploy = stage("active", "awsforcedeploy running")
    elif follow_ups:
        deploy = stage("failed", "last attempt failed")
    else:
        deploy = stage("pending")

    checks = [r for r in [root, *follow_ups] if r.post_checked_at]
    last = max(checks, key=lambda r: r.post_checked_at) if checks else None
    post = (stage("pending") if not last
            else stage("done", f"/info reports {last.post_check_release}") if last.post_check_ok
            else stage("active", f"/info still reports {last.post_check_release or 'nothing'}"))

    return {
        "upgrade_run_id": root.id, "environment": root.environment, "target_version": root.target_version,
        "stages": {"ecr": ecr, "push": push, "build": build, "deploy": deploy, "postcheck": post},
        # Lets the UI tell a rollout from *this* force deploy apart from the
        # service's previous (already stable) state.
        "last_deploy_at": follow_ups[-1].started_at if follow_ups else None,
        "pipeline": pipeline,
    }


@router.post("/runs/{run_id}/cancel")
async def cancel_run(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, run_id)
    if run.status != "running" or not run.runner_job_id:
        raise HTTPException(status_code=400, detail="Run is not running")
    await _runner("POST", f"/jobs/{run.runner_job_id}/cancel")
    db.add(AuditLog(actor="you", action="automation.cancelled", target_type="automation_run", target_id=str(run.id)))
    await db.commit()
    await _sync(db, run)
    return _run_out(await _get_run(db, run_id), since=0)


@router.post("/runs/{run_id}/post-check")
async def post_check(run_id: int, db: AsyncSession = Depends(get_db)):
    run = await _get_run(db, run_id)
    if not run.environment:
        raise HTTPException(status_code=400, detail="This run has no environment to check")
    probe = await _probe_info(await _probe_target(db, run.environment))
    run.post_check_release = probe.get("release")
    run.post_check_ok = probe["ok"] and _same_version(probe.get("release"), run.target_version)
    run.post_checked_at = datetime.now(timezone.utc)
    db.add(AuditLog(actor="you", action="automation.post_check", target_type="automation_run", target_id=str(run.id),
                    detail=f"/info release={probe.get('release') or probe.get('error')} target={run.target_version}"))
    await db.commit()
    return {**_run_out(await _get_run(db, run_id)), "probe": probe}
