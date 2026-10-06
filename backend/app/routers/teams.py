"""Teams & Routing — the Dataloy dev team roster and which team owns which
VMS module, so support knows who to route a ticket to once the affected
module is known. Ported from the L2 Support Hub, but database-backed and
editable instead of a hardcoded constant. Every write is audit-logged."""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.database import get_db
from app.models.audit_log import AuditLog
from app.models.dev_team import DevTeam, DevTeamMember, VmsModule

router = APIRouter(prefix="/teams", tags=["teams"])

_ROLES = {"PM", "EL"}


def _member_out(m: DevTeamMember) -> dict:
    return {
        "id": m.id, "team_id": m.team_id, "display_name": m.display_name,
        "jira_name": m.jira_name, "role": m.role, "sort_order": m.sort_order,
    }


def _team_out(t: DevTeam) -> dict:
    return {
        "id": t.id, "key": t.key, "name": t.name, "emoji": t.emoji, "notes": t.notes,
        "sort_order": t.sort_order, "members": [_member_out(m) for m in t.members],
    }


def _module_out(m: VmsModule) -> dict:
    return {"id": m.id, "name": m.name, "group_name": m.group_name, "team_id": m.team_id, "notes": m.notes}


def _clean(v: object) -> str | None:
    s = (v or "").strip() if isinstance(v, str) else None
    return s or None


def _role(v: object) -> str | None:
    r = _clean(v)
    if r is None:
        return None
    r = r.upper()
    if r not in _ROLES:
        raise HTTPException(status_code=400, detail="role must be PM, EL or empty")
    return r


def _audit(db: AsyncSession, action: str, target_type: str, target_id: object, detail: str | None = None) -> None:
    db.add(AuditLog(actor="you", action=action, target_type=target_type, target_id=str(target_id), detail=detail))


async def _get_team(db: AsyncSession, team_id: int) -> DevTeam:
    team = (await db.execute(
        select(DevTeam).options(selectinload(DevTeam.members)).where(DevTeam.id == team_id)
    )).scalar_one_or_none()
    if not team:
        raise HTTPException(status_code=404, detail="Team not found")
    return team


@router.get("")
async def list_teams(db: AsyncSession = Depends(get_db)):
    """Teams with members and modules in one call — the whole dataset is a
    few dozen rows, so the UI searches/filters it client-side."""
    teams = (await db.execute(
        select(DevTeam).options(selectinload(DevTeam.members)).order_by(DevTeam.sort_order, DevTeam.name)
    )).scalars().all()
    modules = (await db.execute(select(VmsModule).order_by(VmsModule.group_name, VmsModule.name))).scalars().all()
    return {"teams": [_team_out(t) for t in teams], "modules": [_module_out(m) for m in modules]}


# ── Teams ────────────────────────────────────────────────────────────────

@router.patch("/{team_id}")
async def update_team(team_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    team = await _get_team(db, team_id)
    if "name" in data:
        name = _clean(data["name"])
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        team.name = name
    if "emoji" in data:
        team.emoji = _clean(data["emoji"])
    if "notes" in data:
        team.notes = _clean(data["notes"])
    _audit(db, "team.updated", "dev_team", team.key)
    await db.commit()
    return _team_out(await _get_team(db, team_id))


# ── Members ──────────────────────────────────────────────────────────────

@router.post("/{team_id}/members", status_code=201)
async def add_member(team_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    team = await _get_team(db, team_id)
    display_name = _clean(data.get("display_name"))
    if not display_name:
        raise HTTPException(status_code=400, detail="display_name is required")
    member = DevTeamMember(
        team_id=team.id, display_name=display_name, jira_name=_clean(data.get("jira_name")),
        role=_role(data.get("role")), sort_order=max((m.sort_order for m in team.members), default=-1) + 1,
    )
    db.add(member)
    _audit(db, "team.member_added", "dev_team", team.key, display_name)
    await db.commit()
    await db.refresh(member)
    return _member_out(member)


@router.patch("/members/{member_id}")
async def update_member(member_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    member = await db.get(DevTeamMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    if "display_name" in data:
        dn = _clean(data["display_name"])
        if not dn:
            raise HTTPException(status_code=400, detail="display_name is required")
        member.display_name = dn
    if "jira_name" in data:
        member.jira_name = _clean(data["jira_name"])
    if "role" in data:
        member.role = _role(data["role"])
    if "team_id" in data and data["team_id"] != member.team_id:
        await _get_team(db, int(data["team_id"]))
        member.team_id = int(data["team_id"])
    _audit(db, "team.member_updated", "dev_team_member", member.id, member.display_name)
    await db.commit()
    await db.refresh(member)
    return _member_out(member)


@router.delete("/members/{member_id}", status_code=204)
async def remove_member(member_id: int, db: AsyncSession = Depends(get_db)):
    member = await db.get(DevTeamMember, member_id)
    if not member:
        raise HTTPException(status_code=404, detail="Member not found")
    _audit(db, "team.member_removed", "dev_team_member", member.id, member.display_name)
    await db.delete(member)
    await db.commit()


# ── Modules ──────────────────────────────────────────────────────────────

async def _check_team_id(db: AsyncSession, team_id: object) -> int | None:
    if team_id in (None, ""):
        return None
    tid = int(team_id)
    if not await db.get(DevTeam, tid):
        raise HTTPException(status_code=400, detail="Unknown team_id")
    return tid


async def _check_unique_name(db: AsyncSession, name: str, exclude_id: int | None = None) -> None:
    q = select(VmsModule).where(func.lower(VmsModule.name) == name.lower())
    existing = (await db.execute(q)).scalar_one_or_none()
    if existing and existing.id != exclude_id:
        raise HTTPException(status_code=409, detail=f"Module '{existing.name}' already exists")


@router.post("/modules", status_code=201)
async def create_module(data: dict, db: AsyncSession = Depends(get_db)):
    name, group = _clean(data.get("name")), _clean(data.get("group_name"))
    if not name or not group:
        raise HTTPException(status_code=400, detail="name and group_name are required")
    await _check_unique_name(db, name)
    module = VmsModule(name=name, group_name=group, team_id=await _check_team_id(db, data.get("team_id")),
                       notes=_clean(data.get("notes")))
    db.add(module)
    _audit(db, "module.created", "vms_module", name)
    await db.commit()
    await db.refresh(module)
    return _module_out(module)


@router.patch("/modules/{module_id}")
async def update_module(module_id: int, data: dict, db: AsyncSession = Depends(get_db)):
    module = await db.get(VmsModule, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    changes = []
    if "name" in data:
        name = _clean(data["name"])
        if not name:
            raise HTTPException(status_code=400, detail="name is required")
        await _check_unique_name(db, name, exclude_id=module.id)
        module.name = name
    if "group_name" in data:
        group = _clean(data["group_name"])
        if not group:
            raise HTTPException(status_code=400, detail="group_name is required")
        module.group_name = group
    if "team_id" in data:
        new_tid = await _check_team_id(db, data["team_id"])
        if new_tid != module.team_id:
            old_t = await db.get(DevTeam, module.team_id) if module.team_id else None
            new_t = await db.get(DevTeam, new_tid) if new_tid else None
            changes.append(f"team {old_t.name if old_t else 'unassigned'} → {new_t.name if new_t else 'unassigned'}")
        module.team_id = new_tid
    if "notes" in data:
        module.notes = _clean(data["notes"])
    _audit(db, "module.updated", "vms_module", module.name, "; ".join(changes) or None)
    await db.commit()
    await db.refresh(module)
    return _module_out(module)


@router.delete("/modules/{module_id}", status_code=204)
async def delete_module(module_id: int, db: AsyncSession = Depends(get_db)):
    module = await db.get(VmsModule, module_id)
    if not module:
        raise HTTPException(status_code=404, detail="Module not found")
    _audit(db, "module.deleted", "vms_module", module.name)
    await db.delete(module)
    await db.commit()
