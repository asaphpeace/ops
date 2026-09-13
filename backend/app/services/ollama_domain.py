"""Shared Sedna Ops / Dataloy VMS domain grounding for every Ollama prompt —
interactive chat (routers/ollama_chat.py) and supervisor narration
(ollama_supervisor.py) alike. Single-sourced here so the two prompt call
sites can't silently drift into different vocabulary/framing.

Facts below are pulled from the real code, not guessed: jira.py's
_STATUS_MAP/_map_type (case status/type vocabulary), customers.py's
TIER_UPGRADE_LIMITS (tier ordering), desk.py's SUPPORT_TEAM (team names)."""

DOMAIN_CONTEXT = (
    "Sedna Ops is an internal L2 support-operations tool for a small team supporting "
    "Dataloy VMS — maritime voyage management software (chartering, laytime, bunkering, "
    "cargo, invoicing, and related workflows for shipping companies).\n\n"
    "App vocabulary:\n"
    "- \"DSD-<number>\" refs are support/customer tickets (Jira project DSD); "
    "\"VMS-<number>\" refs are dev bugs/tasks in the VMS product codebase itself.\n"
    "- Case types: Support (general help), Defect (a real product bug a customer "
    "reported), Upgrade (a version-upgrade request), Training Gap (a customer needs "
    "training on a feature).\n"
    "- Case status: Active (open, being worked), Awaiting Customer (we're waiting on "
    "the customer to reply), Closed.\n"
    "- Customer tiers, low to high: Scale, Strategic, Premier — Premier gets the "
    "richest support package (most upgrade slots, after-hours eligibility).\n"
    "- The support team is Asaph Mulaisi, Gisele Wolff, and Yaseen Dolan."
)
