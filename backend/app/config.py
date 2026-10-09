from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://sedna:changeme@db:5432/sedna_ops"

    # Auth
    secret_key: str = "dev-secret-key-change-in-production"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 480  # 8 hours

    # CORS
    cors_origins: list[str] = ["http://localhost", "http://localhost:5173", "http://localhost:80"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v: object) -> object:
        if isinstance(v, str):
            return [o.strip() for o in v.split(",") if o.strip()]
        return v

    # Jira — optional; polling disabled if token is empty
    jira_base_url: str = ""
    jira_email: str = ""
    jira_api_token: str = ""

    # How long live-Jira aggregate queries (team_open_stats/team_resolved_
    # stats/customer_case_stats/real_resolved_stats/etc — every "ask Jira
    # directly instead of the local cases table" function) are cached
    # before re-hitting Jira. Bumped from 600s to 3600s (1h) — these are
    # slow-moving analytical aggregates (aging buckets, 90-day resolved
    # trends, per-customer case counts), not anything that needs to be
    # fresher than an hour, and Support Signals/Customer Drill Panel have
    # no frontend cache of their own, so every page visit hits this
    # directly. A cold fetch here can take 20-30s+ (hundreds of issues,
    # paginated) — worth avoiding on every reload within the hour, not
    # just every 10 minutes.
    jira_stats_cache_ttl_seconds: int = 3600

    # Slack — optional; notifications logged locally if empty
    slack_webhook_url: str = ""

    # Google OAuth — optional; auth disabled when client_id is empty
    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost/api/auth/google/callback"

    # Seed data — only allow /seed endpoint when explicitly enabled
    seed_enabled: bool = False

    # Anthropic — optional; AI use cases disabled if empty
    anthropic_api_key: str = ""

    # Google Calendar — optional; upgrade-slot booking logged locally (not
    # pushed) when empty. Service account JSON (as a raw string, not a path)
    # + the shared team calendar's id. Internal-only invites, one-way push.
    google_calendar_service_account_json: str = ""
    google_calendar_id: str = ""

    # Dataloy VMS M2M link — optional. Per-tenant client_id/client_secret
    # pairs live in the vms_api_credentials table (DB), not here. These two
    # settings are a single-tenant dev/fallback config for get_entity()/
    # list_entity() in services/dataloy_vms.py (the credential-row-based
    # path, not yet wired into any router) — they are NOT "the same for
    # every tenant": the real API host is confirmed to be per-tenant (each
    # customer's own subdomain + /ws/rest, e.g.
    # https://demonew.dataloy.com/ws/rest), matching the docs' own statement
    # that the base URL is customer-specific. The VMS Sandbox
    # (routers/vms_sandbox.py -> call_entity_direct) does NOT use these
    # settings — it takes a host per-request instead, since its whole
    # purpose is testing against whichever tenant a pasted token belongs to.
    # api.dataloy.com is NOT the API host — confirmed live, it's the GitBook
    # docs site. Left blank until a real single-tenant dev default is chosen.
    dataloy_vms_token_url: str = ""
    dataloy_vms_api_base_url: str = ""

    # Rovo MCP Server (Atlassian Teamwork Graph) — optional. Consumed, not
    # contributed to: services/rovo.py calls the remote MCP server to enrich
    # AI summaries with linked PRs/docs/deployments a case or bug connects
    # to, beyond what our own Jira polling captures. API-token auth (Basic
    # email:api_token) — Atlassian's own docs call this the intended path
    # for backend services/bots, not the interactive OAuth consent flow.
    # Endpoint is the current (post-30-Jun-2026) one; the old /v1/sse path
    # is no longer supported.
    rovo_api_email: str = ""
    rovo_api_token: str = ""
    rovo_mcp_url: str = "https://mcp.atlassian.com/v1/mcp/authv2"

    # Local Ollama server — optional, advisory-only "connecting layer" over
    # already-computed deterministic signals (services/observation_signals.py
    # does the joining; the model only narrates it — see
    # services/ollama_supervisor.py). Reached from inside the api container
    # via Docker Desktop's built-in host.docker.internal resolution
    # (Windows/Mac — no extra_hosts entry needed). Empty = disabled, same
    # convention as every other optional integration above.
    ollama_base_url: str = ""          # e.g. "http://host.docker.internal:11434"
    # Confirmed live via GET /api/tags against the user's real local Ollama
    # server: "gemma3:4b" (the name first given) doesn't exist there — the
    # real 4B model installed is "qwen3:4b" (server also has gemma4:latest
    # 8B, sentinel:latest 751M, qwen3:0.6b). Defaulting to the real tag.
    ollama_model: str = "qwen3:4b"

    # Chat-specific overrides — a user is waiting live here (unlike the
    # supervisor's background narration pass), so a shorter per-call timeout
    # than the supervisor's 180s; num_ctx is independent of the supervisor's
    # hardcoded 4096 since chat context bundles (entity record + comments +
    # prior turns) can be materially larger than a one-candidate prompt.
    ollama_chat_timeout_seconds: int = 60
    ollama_chat_num_ctx: int = 8192

    # Real, known DevOps capacity constraint (the user's own stated number,
    # not derived from anything) — informational only. Command Center's
    # schedule() surfaces "N of devops_slots_per_week booked this week"
    # alongside the real upcoming slots; nothing here blocks or warns on
    # overbooking, per the user's explicit choice.
    devops_slots_per_week: int = 6

    @property
    def auth_enabled(self) -> bool:
        return bool(self.google_client_id and self.google_client_secret)

    @property
    def jira_enabled(self) -> bool:
        return bool(self.jira_base_url and self.jira_api_token)

    @property
    def slack_enabled(self) -> bool:
        return bool(self.slack_webhook_url)

    @property
    def ai_enabled(self) -> bool:
        return bool(self.anthropic_api_key)

    @property
    def calendar_enabled(self) -> bool:
        return bool(self.google_calendar_service_account_json and self.google_calendar_id)

    @property
    def dataloy_vms_enabled(self) -> bool:
        return bool(self.dataloy_vms_token_url and self.dataloy_vms_api_base_url)

    # Host runner (runner/sedna_runner.py) — runs whitelisted aws-util scripts
    # on the Docker host, where the AWS SSO session, GitLab credentials and
    # ~/environments repos live. Empty = Upgrade Runner disabled.
    runner_url: str = ""               # e.g. "http://host.docker.internal:8765"
    runner_token: str = ""

    @property
    def runner_enabled(self) -> bool:
        return bool(self.runner_url and self.runner_token)

    @property
    def rovo_enabled(self) -> bool:
        return bool(self.rovo_api_email and self.rovo_api_token)

    @property
    def ollama_enabled(self) -> bool:
        return bool(self.ollama_base_url)


settings = Settings()
