"""Weekly ops report — a stored, presentable, PDF-exportable snapshot of
Support/Bug/Upgrade/Migration/Incident impact and customers affected, for
the recurring DevOps priority meeting. See services/weekly_report.py for
the actual computation (this router is thin: generate/fetch/list/publish
+ render the stored snapshot to PDF)."""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.weekly_report import WeeklyReport
from app.services.weekly_report import build_weekly_report, current_iso_week, iso_week_bounds

router = APIRouter(prefix="/weekly-report", tags=["weekly-report"])


def _enrich(r: WeeklyReport) -> dict:
    return {
        "id": r.id,
        "week": r.week,
        "period_start": r.period_start,
        "period_end": r.period_end,
        "generated_at": r.generated_at,
        "status": r.status,
    }


@router.get("")
async def list_weekly_reports(db: AsyncSession = Depends(get_db)):
    """Metadata only (no snapshot body) — history browsing, not the full
    document. Fetch GET /weekly-report/{week} for the real content."""
    result = await db.execute(select(WeeklyReport).order_by(WeeklyReport.period_start.desc()))
    return [_enrich(r) for r in result.scalars().all()]


@router.post("/generate")
async def generate_weekly_report(week: str | None = None, db: AsyncSession = Depends(get_db)):
    """Idempotent: returns the existing Draft/Published report for that
    week if one already exists, rather than silently re-rolling it — a
    report already shown in a meeting shouldn't change under someone's
    feet. Defaults to the current ISO week when `week` isn't given."""
    week = week or current_iso_week()
    existing = (await db.execute(select(WeeklyReport).where(WeeklyReport.week == week))).scalar_one_or_none()
    if existing:
        return _enrich(existing)

    period_start, period_end = iso_week_bounds(week)
    snapshot = await build_weekly_report(db, week)

    report = WeeklyReport(
        week=week, period_start=period_start, period_end=period_end,
        status="Draft", snapshot=snapshot,
    )
    db.add(report)
    db.add(AuditLog(actor="system", action="weekly_report.generated", target_type="weekly_report", target_id=week))
    await db.commit()
    await db.refresh(report)
    return _enrich(report)


@router.get("/{week}")
async def get_weekly_report(week: str, db: AsyncSession = Depends(get_db)):
    report = (await db.execute(select(WeeklyReport).where(WeeklyReport.week == week))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No report generated for this week yet")
    out = _enrich(report)
    out["snapshot"] = report.snapshot
    return out


@router.patch("/{week}")
async def update_weekly_report(week: str, data: dict, db: AsyncSession = Depends(get_db)):
    report = (await db.execute(select(WeeklyReport).where(WeeklyReport.week == week))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No report generated for this week yet")

    new_status = data.get("status")
    if new_status and new_status not in ("Draft", "Published"):
        raise HTTPException(status_code=400, detail="status must be Draft or Published")
    if new_status:
        report.status = new_status
        if new_status == "Published":
            db.add(AuditLog(actor="you", action="weekly_report.published", target_type="weekly_report", target_id=week))

    await db.commit()
    await db.refresh(report)
    return _enrich(report)


@router.get("/{week}/pdf")
async def weekly_report_pdf(week: str, db: AsyncSession = Depends(get_db)):
    report = (await db.execute(select(WeeklyReport).where(WeeklyReport.week == week))).scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="No report generated for this week yet")

    from app.services.weekly_report_pdf import render_pdf

    pdf_bytes = render_pdf(report.snapshot)
    filename = f"sedna-ops-weekly-report-{week}.pdf"
    return Response(
        content=pdf_bytes,
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
