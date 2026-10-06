"""add dev teams, members and vms modules (Teams & Routing)

Seeded with the real roster and module ownership from the L2 Support Hub
(dataloy_vms_hub_v11.html TEAMS / MODULES constants), so the Tools → Teams &
Routing tab is useful on first load. jira_name is only filled where the hub's
first name matched exactly one person in live Jira data (case assignees,
comment authors); ambiguous or unmatched names are left null to be confirmed
in the UI rather than guessed.

Revision ID: 47e4ba5efc6f
Revises: ccf80f00f3a3
Create Date: 2026-10-05

"""
from alembic import op
import sqlalchemy as sa

revision = "47e4ba5efc6f"
down_revision = "ccf80f00f3a3"
branch_labels = None
depends_on = None


TEAMS = [
    # key, name, emoji, members: (display_name, jira_name, role)
    ("aliens", "Aliens", "👽", [
        ("Bernhard", "Bernhard Hafting", "PM"),
        ("Ilona", "Ilona Belevica", "EL"),
        ("Enah", "Enah Grace Lanto", None),
        ("Narendra", "Narendra Mydur", None),
        ("Arsenii", "Arsenii Dmitriev", None),
        ("Simen", "Simen Carstensen", None),
        ("Jan Petter", None, None),  # two Jan Petters in Jira
    ]),
    ("visions", "Visions", "🔭", [
        ("Andrea", "Andrea Biasillo", "PM"),
        ("Ashleigh", "ashleigh.schaefer", "EL"),
        ("Karl", "Karl-André Dalby", None),
        ("Kjetil", None, None),  # two Kjetils in Jira
        ("Lakshimi", None, None),  # likely "lakshmi sujatha gajjarapu" — spelling differs, unconfirmed
        ("Idar", "Idar Hansen", None),
        ("Andreas", None, None),  # no match in Jira
        ("William", None, None),  # two Williams in Jira
    ]),
    ("rockets", "Rockets League", "🚀", [
        ("Vilde", "Vilde Martine Færøy", "PM"),
        ("Espen", "Espen Kuvås", "EL"),
        ("Raida", "Raida Talukdar", None),
        ("Sverre", "Sverre Hassel", None),
        ("Sebastian", "Sebastian Luedenbach", None),
        ("Torbjørn", "Torbjørn Vatnelid", None),
        ("Thomas", "Thomas Minsaas", None),
    ]),
]

MODULES = [
    # name, group, team key (None = unassigned)
    ("BL Execution Framework", "Framework", "visions"),
    ("DLP Cache", "Framework", "visions"),
    ("Webhooks", "Framework", "visions"),
    ("API Generic Functionalities", "Framework", "visions"),
    ("Deserializer", "Framework", "visions"),
    ("Access / Data Control", "Framework", "visions"),
    ("Smart BL", "Framework", "visions"),
    ("Security Layer", "Framework", "visions"),
    ("Cargoes", "Core", "rockets"),
    ("Port Calls", "Core", "aliens"),
    ("Vessels", "Core", "rockets"),
    ("Voyages", "Core", "aliens"),
    ("Broker Commissions", "Chartering", "aliens"),
    ("Contracts of Affreightment", "Chartering", "rockets"),
    ("Market Indices", "Chartering", "rockets"),
    ("Time Charter Contracts", "Chartering", "rockets"),
    ("Claims and Incidents", "Chartering", "aliens"),
    ("Accruals", "Finance", "rockets"),
    ("Bunker Transactions", "Finance", "rockets"),
    ("Invoices", "Finance", "rockets"),
    ("Attachments", "Generic Features", "visions"),
    ("Audit Log", "Generic Features", "visions"),
    ("Comments", "Generic Features", "visions"),
    ("Login", "Generic Features", "visions"),
    ("Accounts", "Master Data", "rockets"),
    ("Business Partners", "Master Data", "aliens"),
    ("Business Units", "Master Data", "aliens"),
    ("Commodities", "Master Data", "rockets"),
    ("Exchange Rates", "Master Data", "aliens"),
    ("Laytime Terms", "Master Data", "rockets"),
    ("Ports", "Master Data", "aliens"),
    ("Routes", "Master Data", "rockets"),
    ("Vessels (MD)", "Master Data", "rockets"),
    ("EU ETS", "Master Data", "aliens"),
    ("SOA", "SOA", "rockets"),
    ("Bills of Lading", "Operations", "rockets"),
    ("Bunker Orders", "Operations", "aliens"),
    ("Laytime Calculations", "Operations", "aliens"),
    ("Downtimes", "Operations", "rockets"),
    ("Services Orders", "Operations", "aliens"),
    ("Vessel Reports", "Operations", "aliens"),
    ("Voyage Analysis Dashboard", "Operations", "rockets"),
    ("Budgets", "Planning", "rockets"),
    ("Capacity Plan", "Planning", "rockets"),
    ("Fleet Plans", "Planning", "rockets"),
    ("Scenarios", "Planning", "rockets"),
    ("M2M Users", "Setup", "visions"),
    ("Security Groups", "Setup", "visions"),
    ("Security Roles", "Setup", "visions"),
    ("Users", "Setup", "visions"),
    ("Notifications", "Alerts", "visions"),
    ("Widgets", "Miscellaneous", "visions"),
    ("Middleware", "Miscellaneous", "visions"),
    ("BI", "Miscellaneous", None),
]


def upgrade() -> None:
    teams = op.create_table(
        "dev_teams",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("key", sa.String(40), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("emoji", sa.String(10), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    members = op.create_table(
        "dev_team_members",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("dev_teams.id", ondelete="CASCADE"), nullable=False),
        sa.Column("display_name", sa.String(200), nullable=False),
        sa.Column("jira_name", sa.String(200), nullable=True),
        sa.Column("role", sa.String(10), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_dev_team_members_team_id", "dev_team_members", ["team_id"])
    modules = op.create_table(
        "vms_modules",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(150), nullable=False, unique=True),
        sa.Column("group_name", sa.String(60), nullable=False),
        sa.Column("team_id", sa.Integer(), sa.ForeignKey("dev_teams.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Explicit ids so members/modules can reference teams without a lookup;
    # the sequence is moved past them below.
    team_ids = {key: i for i, (key, *_rest) in enumerate(TEAMS, start=1)}
    op.bulk_insert(teams, [
        {"id": team_ids[key], "key": key, "name": name, "emoji": emoji, "sort_order": team_ids[key]}
        for key, name, emoji, _m in TEAMS
    ])
    op.bulk_insert(members, [
        {"team_id": team_ids[key], "display_name": dn, "jira_name": jn, "role": role, "sort_order": i}
        for key, _n, _e, mlist in TEAMS
        for i, (dn, jn, role) in enumerate(mlist)
    ])
    op.bulk_insert(modules, [
        {"name": name, "group_name": group, "team_id": team_ids[tk] if tk else None}
        for name, group, tk in MODULES
    ])
    op.execute("SELECT setval(pg_get_serial_sequence('dev_teams', 'id'), (SELECT MAX(id) FROM dev_teams))")


def downgrade() -> None:
    op.drop_table("vms_modules")
    op.drop_index("ix_dev_team_members_team_id", table_name="dev_team_members")
    op.drop_table("dev_team_members")
    op.drop_table("dev_teams")
