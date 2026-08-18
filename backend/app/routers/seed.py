"""Seed endpoint — POST /seed to populate DB with prototype data. Dev only."""
from datetime import date, datetime, timedelta
from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.customer import Customer
from app.models.case import Case
from app.models.upgrade import Upgrade
from app.models.migration_project import MigrationProject
from app.models.release import Release
from app.models.training import TrainingGap, TrainingSession
from app.models.note import CustomerNote

router = APIRouter(prefix="/seed", tags=["dev"])

TODAY = date.today()


async def _already_seeded(db: AsyncSession) -> bool:
    result = await db.execute(select(Customer).limit(1))
    return result.scalar_one_or_none() is not None


@router.post("")
async def seed_database(db: AsyncSession = Depends(get_db)):
    if await _already_seeded(db):
        return {"status": "already seeded"}

    # ── RELEASES ─────────────────────────────────────────────
    releases = [
        Release(version="8.30.1-R", released_at=date(2026, 8, 2), defects_fixed=12, improvements=3,
                notes="Fixes: DSD-31622 (accruals) · DSD-31651 (fleet plan) · DSD-31489 (laytime calc) + 9 more",
                is_latest=True),
        Release(version="8.29.1-R", released_at=date(2026, 7, 14), defects_fixed=7,
                notes="Fixes: DSD-31401 (invoice posting) · DSD-31388 (TC rate) + 5 more"),
        Release(version="8.28.2-R", released_at=date(2026, 7, 1), defects_fixed=4,
                notes="Fixes: DSD-31290 (bunker calc) · DSD-31271 (port call dates) + 2 more"),
    ]
    for r in releases:
        db.add(r)

    # ── CUSTOMERS ────────────────────────────────────────────
    nat = Customer(
        name="NAT Chartering AS", tier="Strategic", csm="Kjersti", arr_gbp=58848,
        product="VMS", plan="Time Charter Edition", region="Europe · Norway",
        timezone="Europe/Oslo (UTC+2)", contacts="Bjorn Hagen (Primary) · IT Dept (Technical)",
        renewal_date=date(2027, 1, 31), seats=12, sla_tier="Standard",
        health_score=24, sentiment="Frustrated", churn_risk="High",
        upgrades_used=2, upgrades_limit=10, prod_version="8.14.2-R", test_version="8.14.2-R",
        infra="Old", ip_fw=False, wildfly8=True, sso="None", integrations="None",
        pref_days="Mon, Tue", notice_required="5 business days", blackout_periods="Year-end Dec",
    )
    bbc = Customer(
        name="BBC Chartering GmbH", tier="Premier", csm="Marie-Therese", arr_gbp=248800,
        product="Email, VMS", plan="Bulk Edition (Wet)", region="Europe · Germany",
        timezone="Europe/Berlin (UTC+2)", contacts="James T. (Primary) · IT Dept (Technical)",
        renewal_date=date(2027, 3, 31), seats=45, sla_tier="Premium (5d)",
        health_score=51, sentiment="Neutral", churn_risk="Medium",
        upgrades_used=7, upgrades_limit=10, prod_version="8.28.1-R", test_version="8.30.1-R",
        infra="Mixed", ip_fw=False, wildfly8=False, sso="Auth0", integrations="SAP (accounting)",
        api_customer=True, pref_days="Monday mornings", notice_required="48 hours",
        blackout_periods="Q4 year-end",
    )
    balena = Customer(
        name="Balena Shipping DMCC", tier="Strategic", csm="Musthafa", arr_gbp=134433,
        product="Email + VMS", plan="Bulk Edition (Wet/Dry)", region="Middle East · Dubai",
        timezone="Asia/Dubai (UTC+4)", contacts="Operations Manager (Primary)",
        renewal_date=date(2026, 9, 30), seats=22, sla_tier="Standard",
        health_score=58, sentiment="Neutral", churn_risk="High",
        upgrades_used=4, upgrades_limit=10, prod_version="8.25.3-R", test_version="8.25.3-R",
        infra="Old", ip_fw=True, wildfly8=False, sso="None", integrations="Custom firewall",
        pref_days="Tue, Wed", notice_required="1 week", blackout_periods="Ramadan period",
    )
    bp = Customer(
        name="BP Oil International", tier="Premier", csm="Grace", arr_gbp=670291,
        product="Email", plan="Broker Edition", region="Europe · UK",
        timezone="Europe/London (UTC+1)", contacts="Operations Lead (Primary)",
        renewal_date=date(2027, 4, 30), seats=120, sla_tier="Premium (5d)",
        health_score=88, sentiment="Happy", churn_risk="Low",
        upgrades_used=9, upgrades_limit=10, prod_version="8.29.0-R", test_version="8.30.1-R",
        infra="New", ip_fw=False, wildfly8=False, sso="Auth0", integrations="None",
        api_customer=True, pref_days="Any", notice_required="24 hours", blackout_periods="None",
    )
    gibson = Customer(
        name="Gibson Shipbrokers Ltd", tier="Premier", csm="Marie-Therese", arr_gbp=203300,
        product="VMS", plan="Broker Edition", region="Europe · UK",
        timezone="Europe/London (UTC+1)", contacts="IT Manager (Primary)",
        renewal_date=date(2027, 2, 28), seats=35, sla_tier="Premium (5d)",
        health_score=82, sentiment="Happy", churn_risk="Low",
        upgrades_used=3, upgrades_limit=10, prod_version="8.28.2-R", test_version="8.28.2-R",
        infra="New", ip_fw=False, wildfly8=False, sso="Auth0", integrations="None",
        pref_days="Mon, Wed", notice_required="48 hours", blackout_periods="None",
    )
    aquavita = Customer(
        name="Aquavita International", tier="Strategic", csm="Angelos", arr_gbp=62839,
        product="VMS", plan="Bulk Edition", region="Europe · Greece",
        timezone="Europe/Athens (UTC+3)", contacts="IT Director (Primary)",
        renewal_date=date(2026, 11, 30), seats=18, sla_tier="Standard",
        health_score=62, sentiment="Neutral", churn_risk="Medium",
        upgrades_used=6, upgrades_limit=10, prod_version="8.28.0-R", test_version="8.28.0-R",
        infra="Old", ip_fw=True, wildfly8=False, sso="None", integrations="Custom firewall",
        pref_days="Tue, Thu", notice_required="1 week", blackout_periods="None",
    )
    for c in [nat, bbc, balena, bp, gibson, aquavita]:
        db.add(c)

    await db.flush()  # get IDs

    # ── CASES ────────────────────────────────────────────────
    cases = [
        Case(customer_id=nat.id, jira_ref="DSD-31667", title="TC rate calculation off on Worldscale voyages",
             case_type="Defect", environment="PROD", status="Awaiting Dev", priority="High",
             sla_days=10, days_open=12, defect_status="In Development · targeted 8.30.2"),
        Case(customer_id=nat.id, jira_ref="DSD-31651", title="Fleet plan not showing correct vessel position",
             case_type="Defect", environment="PROD", status="Awaiting Dev", priority="High",
             sla_days=10, days_open=9, defect_status="In Development"),
        Case(customer_id=nat.id, jira_ref="DSD-31640", title="Performance very slow on voyage list",
             case_type="Support", environment="PROD", status="Active", priority="Medium", days_open=7),
        Case(customer_id=nat.id, jira_ref="DSD-31622", title="Cannot post accruals at period end",
             case_type="Defect", environment="PROD", status="Awaiting Dev", priority="High",
             sla_days=10, days_open=18, defect_status="Released in 8.30.1 — upgrade needed"),
        Case(customer_id=nat.id, jira_ref="DSD-31688", title="Upgrade TEST to 8.30.1 — complex upgrade",
             case_type="Upgrade", environment="TEST", status="Awaiting DevOps", priority="Medium", days_open=4),
        Case(customer_id=bbc.id, jira_ref="DSD-31705", title="Upgrade PROD to 8.30.1",
             case_type="Upgrade", environment="PROD", status="Requested", priority="Medium", days_open=1),
        Case(customer_id=bbc.id, jira_ref="DSD-31690", title="Voyage calculation defect on multi-port cargo",
             case_type="Defect", environment="PROD", status="Awaiting Dev", priority="High",
             sla_days=5, days_open=6, defect_status="In Development · urgent",
             blocked=True, blocked_reason="Test not confirmed · DSD-31690"),
        Case(customer_id=bbc.id, jira_ref="DSD-31683", title="User unable to post invoice after period close",
             case_type="Support", environment="PROD", status="Awaiting Customer", priority="Medium",
             sla_days=5, days_open=3, root_cause="Training Gap — period-end closing"),
        Case(customer_id=balena.id, jira_ref="DSD-31692", title="Sedna VMS upgrade request — PROD to 8.30.1",
             case_type="Upgrade", environment="PROD", status="Active", priority="Medium", days_open=2),
    ]
    for c in cases:
        db.add(c)

    # ── UPGRADES ─────────────────────────────────────────────
    upgrades = [
        # Pipeline — active
        Upgrade(customer_id=bbc.id, jira_ref="DSD-31705", environment="PROD",
                from_version="8.28.1", to_version="8.30.1", upgrade_type="Small", stage="Requested"),
        Upgrade(customer_id=balena.id, jira_ref="DSD-31692", environment="TEST",
                from_version="8.25.3", to_version="8.30.1", upgrade_type="Small", stage="Requested"),
        Upgrade(customer_id=nat.id, jira_ref="DSD-31688", environment="TEST",
                from_version="8.14.2", to_version="8.30.1", upgrade_type="Complex", stage="Requested"),
        Upgrade(customer_id=bp.id, jira_ref="DSD-31703", environment="PROD",
                from_version="8.29.0", to_version="8.30.1", upgrade_type="Small", stage="Cust. Confirmed",
                confirmed_at=datetime.utcnow() - timedelta(days=2)),
        Upgrade(customer_id=gibson.id, jira_ref="DSD-31702", environment="PROD",
                from_version="8.28.2", to_version="8.30.1", upgrade_type="Small", stage="Scheduled",
                scheduled_at=datetime(2026, 8, 19, 9, 30)),
        # Verified history
        Upgrade(customer_id=nat.id, environment="PROD", from_version="8.10.0", to_version="8.14.2",
                upgrade_type="Small", stage="Verified Done", source="Customer request",
                date_done=datetime(2024, 11, 4), verified_at=datetime(2024, 11, 4)),
        Upgrade(customer_id=bbc.id, environment="PROD", from_version="8.27.0", to_version="8.28.1",
                upgrade_type="Small", stage="Verified Done", source="Customer request",
                date_done=datetime(2026, 5, 2), verified_at=datetime(2026, 5, 2)),
        Upgrade(customer_id=bp.id, environment="PROD", from_version="8.28.0", to_version="8.29.0",
                upgrade_type="Small", stage="Verified Done", source="Customer request",
                date_done=datetime(2026, 6, 4), verified_at=datetime(2026, 6, 4)),
        Upgrade(customer_id=bp.id, environment="TEST", from_version="8.29.0", to_version="8.30.1",
                upgrade_type="Small", stage="Verified Done", source="Customer request",
                date_done=datetime(2026, 6, 10), verified_at=datetime(2026, 6, 10)),
    ]
    for u in upgrades:
        db.add(u)

    # ── MIGRATION PROJECTS ───────────────────────────────────
    migrations = [
        MigrationProject(customer_id=nat.id, stage="Not Started", ip_fw=False, complexity="High",
                         requires_upgrade=True,
                         integration_notes="WildFly 8 active — legacy reporting dependency. Must verify reporting after migration."),
        MigrationProject(customer_id=bbc.id, stage="Customer Contacted", assignee="Elias", ip_fw=False,
                         complexity="High", stalled=True, stalled_days=18,
                         integration_notes="SAP integration — IP whitelisting required. SAP team needs 48h notice. Contact: James T."),
        MigrationProject(customer_id=balena.id, stage="Not Started", ip_fw=True, complexity="Very High",
                         ip_notes="Custom firewall rules — full integration assessment required before migration. Coordinate with customer IT dept."),
        MigrationProject(customer_id=bp.id, stage="Complete", assignee="Martin", ip_fw=False,
                         complexity="Low", completed_at=datetime(2026, 3, 2)),
        MigrationProject(customer_id=gibson.id, stage="Complete", assignee="Martin", ip_fw=False,
                         complexity="Low", completed_at=datetime(2026, 4, 14)),
        MigrationProject(customer_id=aquavita.id, stage="Assessed", assignee="Elias", ip_fw=True,
                         complexity="High"),
    ]
    for m in migrations:
        db.add(m)

    # ── TRAINING GAPS ─────────────────────────────────────────
    gaps = [
        TrainingGap(customer_id=nat.id, area="Laytime & Demurrage", count=3,
                    source_case_ref="DSD-31683", logged_at=date(2026, 5, 28)),
        TrainingGap(customer_id=nat.id, area="Fleet Plan & Scheduling", count=1, logged_at=date(2026, 6, 1)),
        TrainingGap(customer_id=nat.id, area="Finance · Period-End Closing", count=1, logged_at=date(2026, 6, 1)),
        TrainingGap(customer_id=bbc.id, area="Finance · Period-End Closing", count=2,
                    source_case_ref="DSD-31683", logged_at=date(2026, 6, 12)),
        TrainingGap(customer_id=bbc.id, area="Voyage Management", count=1, logged_at=date(2026, 7, 1)),
        TrainingGap(customer_id=balena.id, area="API Integration", count=2, logged_at=date(2026, 7, 15)),
        TrainingGap(customer_id=aquavita.id, area="Voyage Management", count=2, logged_at=date(2026, 5, 14)),
    ]
    for g in gaps:
        db.add(g)

    # ── TRAINING SESSIONS ────────────────────────────────────
    sessions = [
        TrainingSession(customer_id=bbc.id, session_date=date(2026, 6, 12),
                        topic_area="Finance · Period-End Closing", format="Video call · 1h",
                        delivered_by="Asaph", outcome="Partial", follow_up_needed=True,
                        follow_up_text="Period-end guide"),
        TrainingSession(customer_id=nat.id, session_date=date(2026, 5, 28),
                        topic_area="Laytime Calculation", format="Screen share · 45m",
                        delivered_by="Asaph", outcome="Resolved", follow_up_needed=False),
        TrainingSession(customer_id=aquavita.id, session_date=date(2026, 5, 14),
                        topic_area="Voyage Management", format="Video call · 1.5h",
                        delivered_by="Asaph", outcome="Partial", follow_up_needed=True,
                        follow_up_text="Multi-port cargo guide"),
    ]
    for s in sessions:
        db.add(s)

    # ── NOTES ────────────────────────────────────────────────
    notes = [
        CustomerNote(customer_id=nat.id, text="WildFly 8 active — legacy reporting. Must test reports after migration. Coordinate with Elias.", created_at=datetime(2026, 6, 14)),
        CustomerNote(customer_id=nat.id, text="Below 8.17 — complex upgrade. Upgrade and migrate in same window.", created_at=datetime(2026, 6, 14)),
        CustomerNote(customer_id=bbc.id, text="SAP integration — migration requires SAP team (James T.) with 48h notice minimum.", created_at=datetime(2026, 6, 1)),
        CustomerNote(customer_id=bbc.id, text="Customer prefers Monday morning downtime windows.", created_at=datetime(2026, 5, 10)),
        CustomerNote(customer_id=balena.id, text="Renews Sep 2026 — churn risk. Prioritise migration and upgrade before renewal conversation.", created_at=datetime(2026, 8, 18)),
        CustomerNote(customer_id=balena.id, text="IP/firewall requirements — need Elias for pre-migration assessment.", created_at=datetime(2026, 6, 8)),
        CustomerNote(customer_id=bp.id, text="At upgrade limit — 9/10. Any further upgrade requests need manager approval before proceeding.", created_at=datetime(2026, 6, 10)),
    ]
    for n in notes:
        db.add(n)

    await db.commit()
    return {"status": "seeded", "customers": 6, "cases": len(cases), "upgrades": len(upgrades)}
