import axios from 'axios'
import { useToast } from '@/composables/useToast'

// Real configured Jira base URL (dataloy-cloud.atlassian.net — same instance
// every backend Jira call this app makes already points at). Only the
// trailing ref changes per ticket.
export const JIRA_BASE_URL = 'https://dataloy-cloud.atlassian.net'
export function jiraUrl(jiraRef: string): string {
  return `${JIRA_BASE_URL}/browse/${jiraRef}`
}

// Real Dataloy plan allowances (dataloy-systems.com/plans, confirmed
// 2026-08-25): Starter/Growth/Professional/Enterprise. Sedna's tiers map
// onto these 1:1 (Scale=Starter, Strategic=Professional, Premier=Enterprise)
// — guaranteed non-blank, unlike the free-text `plan` (specific edition)
// field. Shared across every view that shows a customer's commercial plan
// instead of raw ARR.
export const TIER_PLAN_NAMES: Record<string, string> = { Scale: 'Starter', Strategic: 'Professional', Premier: 'Enterprise' }
export function planName(tier: string): string {
  return TIER_PLAN_NAMES[tier] ?? tier
}

// Two-tier engagement flag, derived client-side from the real, weekly-refreshed
// Customer.last_case_activity_at (see backend scheduler.py::_customer_engagement_refresh)
// rather than stored separately — keeps the 6mo/12mo thresholds changeable
// without a migration.
export type EngagementTier = 'dormant' | 'quiet' | null
export function engagementTier(lastCaseActivityAt: string | null): EngagementTier {
  if (!lastCaseActivityAt) return 'dormant' // never raised a case at all
  const days = (Date.now() - new Date(lastCaseActivityAt).getTime()) / 86400000
  if (days >= 365) return 'dormant'
  if (days >= 180) return 'quiet'
  return null
}

const client = axios.create({
  baseURL: '/api',
  // 30s — a cold-cache My Desk fetch (team_open_stats' full Jira pagination,
  // ~4-5s/page x 6 pages) can approach the old 15s limit; the backend now
  // pre-warms this cache every 5 min so a cold hit should be rare, but the
  // client-side timeout stays generous rather than racing it.
  timeout: 30000,
  headers: { 'Content-Type': 'application/json' },
})

// Auth token injection (Phase 2 onwards)
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('so_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

// Turns whatever shape the backend/network handed back into one readable
// line — FastAPI's plain `{"detail": "..."}`, pydantic's 422 validation
// list (`{"detail": [{"loc": [...], "msg": "..."}]}`), or no response at
// all (timeout/offline).
function extractErrorMessage(err: any): string {
  if (!err.response) {
    return err.code === 'ECONNABORTED'
      ? 'Request timed out — try again.'
      : 'Network error — check your connection and try again.'
  }
  const detail = err.response.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail) && detail.length) {
    const first = detail[0]
    const loc = Array.isArray(first?.loc) ? first.loc : []
    const field = loc[loc.length - 1]
    return field ? `${field}: ${first.msg}` : (first?.msg ?? 'Validation error')
  }
  return `Request failed (${err.response.status})`
}

// Global error handling — every failed request (validation errors, business-
// rule 400/409s, timeouts) surfaces as a toast, not just a silently swallowed
// console error. 401 stays a hard redirect (no toast, page is leaving anyway).
client.interceptors.response.use(
  (res) => res,
  (err) => {
    if (err.response?.status === 401) {
      localStorage.removeItem('so_token')
      window.location.href = '/login'
      return Promise.reject(err)
    }
    useToast().push(extractErrorMessage(err), 'error')
    return Promise.reject(err)
  },
)

export default client

// ── Types ─────────────────────────────────────────────────

export interface Customer {
  id: number
  name: string
  tier: string
  csm: string
  arr_gbp: number
  status: 'Active' | 'Cancelled'
  product: string | null
  plan: string | null
  region: string | null
  timezone: string | null
  contacts: string | null
  renewal_date: string | null
  seats: number
  sla_tier: string
  health_score: number
  sentiment: string
  churn_risk: string
  hypercare_until: string | null
  hypercare_reason: string | null
  last_case_activity_at: string | null
  upgrades_used: number
  upgrades_limit: number
  after_hours_eligible: boolean
  after_hours_limit: number
  after_hours_used: number
  prod_version: string | null
  test_version: string | null
  infra: string
  ip_fw: boolean
  wildfly8: boolean
  sso: string
  integrations: string
  api_customer: boolean
  pref_days: string | null
  notice_required: string | null
  blackout_periods: string | null
  tenant_login_notes?: string | null
  ai_summary: string | null
  ai_summary_at: string | null
  // Still on the old Java desktop client rather than the modern web app —
  // confirmed from the validated VMS customer list, not a guess.
  jvm_client: boolean
}

export interface CustomerContact {
  name: string | null
  email: string | null
  primary: boolean
}

export interface CustomerContactResolution {
  customer_id: number
  customer_name: string
  jira_org_matched: boolean
  org_name: string | null
  contacts: CustomerContact[]
  email_count: number
  member_count: number
  // The single email an outbound send actually goes to — the designated
  // main/technical contact, or the sole contact when there's only one.
  // Null when 2+ real contacts exist and none has been designated yet.
  primary_contact_email: string | null
}

export interface Campaign {
  id: number
  name: string
  message: string
  status: 'Draft' | 'Sent'
  customer_count: number
  incident_id: number | null
  created_at: string
  sent_at: string | null
}

export interface CampaignDetail extends Campaign {
  customers: { id: number; name: string | null }[]
}

export interface Incident {
  id: number
  title: string
  source: 'code' | 'infra' | 'ai-tooling' | 'product'
  severity: 'Critical' | 'High' | 'Medium' | 'Low'
  phase: 'Detected' | 'Fix Identified' | 'Fix Released' | 'Remediating Customers' | 'Closed'
  linked_vms_ref: string | null
  affected_below_version: string | null
  detail: string
  impact: string | null
  root_cause: string | null
  resolution: string | null
  lessons_learned: string | null
  detection_gap: string | null
  status: 'Open' | 'Resolved'
  detected_at: string
  resolved_at: string | null
  created_at: string
}

export interface IncidentRemediation {
  id: number
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  upgrade_id: number | null
  upgrade_stage: string | null
  upgrade_to_version: string | null
  manually_resolved: boolean
  notes: string | null
  mitigation_type: 'accepted_risk' | 'workaround_applied' | null
  mitigation_owner: string | null
  mitigation_note: string | null
  review_by_date: string | null
  derived_status: string
  notified: boolean
}

export interface IncidentDetail extends Incident {
  remediations: IncidentRemediation[]
}

export interface IncidentTimelineEntry {
  action: string
  detail: string | null
  actor: string
  created_at: string
}

export interface IncidentCustomerCandidate {
  id: number
  name: string
  tier: string
  prod_version: string
}

export interface CustomerCampaignSummary {
  id: number
  name: string
  status: 'Draft' | 'Sent'
  created_at: string
  sent_at: string | null
}

export interface TenantInfo {
  id: number
  customer_id: number
  environment: string
  subdomain: string
  release: string | null
  reported_environment: string | null
  is_azure_installation: boolean | null
  is_auth0_installation: boolean | null
  is_jvms_mode: boolean | null
  is_pure_web: boolean | null
  last_synced_at: string | null
  last_sync_error: string | null
  cert_expires_at: string | null
  cert_issuer: string | null
  cert_checked_at: string | null
  cert_check_error: string | null
  created_at: string
  updated_at: string
  matched_incidents: { incident_id: number; incident_title: string }[]
}

export type CertStatus = 'valid' | 'expiring' | 'critical' | 'expired' | 'error' | 'never_checked'

export interface CertRow {
  id: number
  customer_id: number
  customer_name: string | null
  tier: string | null
  environment: string
  subdomain: string
  hostname: string
  cert_expires_at: string | null
  days_until_expiry: number | null
  cert_issuer: string | null
  cert_checked_at: string | null
  cert_check_error: string | null
  status: CertStatus
}

export interface CertSummary {
  total: number
  valid: number
  expiring: number
  critical: number
  expired: number
  error: number
  never_checked: number
  last_scan_at: string | null
  scan_running: boolean
  warn_days: number
  critical_days: number
}

export interface CertificatesResult {
  summary: CertSummary
  rows: CertRow[]
}

export interface DeskExpiringCert {
  id: number
  customer_id: number
  customer_name: string | null
  environment: string
  subdomain: string
  expires_at: string | null
  days_until_expiry: number | null
  issuer: string | null
}

export interface AuditLogEntry {
  id: number
  actor: string
  action: string
  target_type: string | null
  target_id: string | null
  detail: string | null
  created_at: string
}

// Weekly Ops Report — a stored per-ISO-week snapshot pulling together
// Support/Bug/Upgrade/Migration/Incident impact + customers affected for
// the recurring DevOps priority meeting. The `snapshot` shape below
// mirrors backend/app/services/weekly_report.py::build_weekly_report()'s
// real return dict exactly — most sub-sections reuse an existing rollup's
// own shape wholesale (e.g. `upgrades.pipeline` is the same object
// GET /upgrades/pipeline already returns), so they're typed loosely here
// rather than re-declaring every existing interface a second time; the
// handful of genuinely-new shapes (RAG grid, customers-at-risk) are typed
// precisely since nothing else already covers them.
export interface WeeklyReportMeta {
  id: number
  week: string
  period_start: string
  period_end: string
  generated_at: string
  status: 'Draft' | 'Published'
}

export interface WeeklyReportCustomerAtRisk {
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  signals: string[]
}

export interface WeeklyReportSnapshot {
  week: string
  period_start: string
  period_end: string
  bluf: string
  rag: Record<'Support' | 'Bugs' | 'Upgrades' | 'Migrations' | 'Incidents', 'Red' | 'Amber' | 'Green'>
  support: {
    scorecard: {
      logged_count: number
      resolved_count: number
      fresh_resolved_count: number | null
      assigned_count: number | null
      fresh_assigned_count: number | null
      replies_count: number | null
      comments_count: number | null
      sla_breach_tickets: unknown[]
      sla_breach_count: number | null
      ttfr_median_hours: number | null
      ttr_median_hours: number | null
      median_time_to_first_move_hours: number | null
      waiting_on_me_median_hours: number | null
      open_load: number | null
      open_load_baseline: number | null
      open_load_vs_baseline_pct: number | null
      by_engineer: Record<string, { assigned: number | null; fresh_assigned: number | null; resolved: number | null; fresh_resolved: number | null; replies: number | null; comments: number | null; logged: number | null } | null>
      case_mix: { status: string; count: number; your_count: number }[]
      aged_cases: { label: string; count: number; example_refs: string[] }[]
      [key: string]: unknown
    }
    aging: { total_open: number; [key: string]: unknown }
    blocked_cases: { jira_ref: string; title: string; blocked_reason: string | null; customer_id: number | null; customer_name: string | null; customer_tier: string | null }[]
  }
  bugs: {
    fix_to_relief: { median_days: number | null; mean_days: number | null; resolved_count: number; still_waiting_count: number; cases: unknown[] }
    version_exposure: { vms_ref: string; fix_version: string | null; assignee: string | null; sprint_name: string | null; matched_release: string | null; reported_customers: { id: number; name: string; tier: string | null }[]; silently_exposed_customers: { id: number; name: string; tier: string | null; prod_version: string }[] }[]
    engineer_impact: { assignee: string; bugs_fixed: number; customers_impacted: number; top_bug: string | null; top_bug_customers: number; bugs_fixed_90d: number; customers_impacted_90d: number }[]
    missing_releases: { fix_version: string; bug_count: number; customer_count: number; bugs: Record<string, unknown>[] }[]
    defect_dev_status: Record<string, unknown>[]
    bug_fix_upgrades_overdue: { id: number; jira_ref: string | null; customer_id: number | null; customer_name: string | null; customer_tier: string | null; stage: string; days_stale: number | null }[]
  }
  upgrades: {
    pipeline: { stages: Record<string, Record<string, unknown>[]>; active_total: number; blocked: number; unconfirmed_slots: number; done_this_month: number; devops_slots_per_week: number }
    superseded: { id: number; jira_ref: string | null; customer_id: number; customer_name: string | null; customer_tier: string | null; environment: string; stage: string; wants_version: string; done_version: string; done_jira_ref: string | null; done_verified_at: string | null }[]
    unconfirmed: { id: number; customer_id: number; customer_name: string | null; customer_tier: string | null; jira_ref: string | null; stage: string; scheduled_at: string | null; devops_confirmed: boolean; customer_confirmed: boolean }[]
    pending_missing_case: { id: number; customer_id: number; customer_name: string | null; customer_tier: string | null; jira_ref: string | null; environment: string; linked_vms_ref: string | null }[]
    overdue_bug_fix: { id: number; customer_id: number; customer_name: string | null; customer_tier: string | null; jira_ref: string | null; linked_vms_ref: string | null; stage: string; days_stale: number | null }[]
  }
  migrations: {
    board: { stages: Record<string, Record<string, unknown>[]>; candidates: Record<string, unknown>[]; stats: Record<string, number> }
    priority: { customers: { customer_id: number; customer_name: string; customer_tier: string | null; infra: string | null; migration_stage: string; migration_tracked: boolean; current_version: string; latest_version: string | null; is_behind_latest: boolean; open_incident_remediations: { incident_id: number; title: string; severity: string }[]; pending_upgrade_defects: Record<string, unknown>[]; pending_upgrade_defect_count: number; theoretical_exposure: Record<string, unknown>[]; theoretical_exposure_count: number; priority_score: number; score_breakdown: Record<string, number> }[]; vms_customer_count: number; covered_count: number }
  }
  incidents: {
    open: { id: number; title: string; source: string; severity: string; phase: string; status: string; remediations: { id: number; customer_id: number; customer_name: string | null; customer_tier: string | null; derived_status: string }[] }[]
    stalled: { id: number; title: string; severity: string; phase: string; days_stale: number | null }[]
  }
  customers_at_risk: WeeklyReportCustomerAtRisk[]
  customer_arr_stats: Record<string, unknown>
  cross_signal: Record<string, unknown>[]
}

export interface TenantDiscoveryResult {
  customer_id: number
  customer_name: string
  environment: string
  tried: string[]
  matched_candidate: string | null
  release: string | null
  reported_environment: string | null
  env_matches_guess: boolean
  is_azure_installation: boolean | null
  is_auth0_installation: boolean | null
  is_jvms_mode: boolean | null
  is_pure_web: boolean | null
  error: string | null
}

export interface CustomerNoteEntry {
  id: number
  text: string
  author: string
  created_at: string
}

// A structured, stored email contact for this customer — distinct from
// CustomerContactResolution (a live, on-demand Jira-org lookup used by the
// Notify Customers flow). This is the validated, persisted contact list
// shown on the Customer panel's own Contacts tab.
export interface CustomerContactEntry {
  id: number
  email: string
  source: string
  is_primary: boolean
  primary_contact_reason: string | null
  created_at: string
}

export interface Case {
  id: number
  customer_id: number
  jira_ref: string
  title: string
  case_type: string
  environment: string
  status: string
  priority: string
  sla_days: number | null
  days_open: number
  defect_status: string | null
  root_cause: string | null
  blocked: boolean
  blocked_reason: string | null
  linked_case_ref: string | null
  assigned_to: string | null
  resolution_note: string | null
  rovo_context?: string | null
  rovo_context_at?: string | null
  needs_csm_briefing: boolean
  comment_count: number
  escalated_at: string | null
  status_changed_at: string | null
  last_mention_name?: string | null
  last_mention_at?: string | null
  lane_override?: string | null
  first_public_reply_at?: string | null
  ttfr_hours?: number | null
  ttfr_breached?: boolean | null
  jira_customer_name?: string | null
  linked_vms_ref?: string | null
  linked_vms_refs?: string | null
  related_case_refs?: string | null
  resolved_at?: string | null
  created_at: string
  updated_at: string
  customer_name: string | null
  customer_tier: string | null
}

export interface CaseTimelineEntry {
  action: string
  detail: string | null
  actor: string
  created_at: string
}

export interface RelatedCaseSummary {
  jira_ref: string
  title: string | null
  customer_name: string | null
  status: string | null
}

export interface CaseDetail extends Case {
  timeline: CaseTimelineEntry[]
  related_cases: RelatedCaseSummary[]
}

export interface CaseActivityEntry {
  author: string
  created: string | null
  text: string
  public: boolean | null
}

export interface Upgrade {
  id: number
  customer_id: number
  jira_ref: string | null
  environment: string
  from_version: string | null
  to_version: string
  upgrade_type: string
  stage: string
  source: string
  blocked: boolean
  blocked_reason: string | null
  linked_vms_ref: string | null
  scheduled_at: string | null
  confirmed_at: string | null
  devops_confirmed_at: string | null
  customer_confirmed_at: string | null
  devops_engineer: string | null
  verified_at: string | null
  date_done: string | null
  after_hours: boolean
  after_hours_billed_hours: number | null
  after_hours_billing_note: string | null
  created_at: string
  updated_at: string
  customer_name: string | null
  customer_tier: string | null
  // Computed — true when this upgrade's (customer, environment) is
  // self-serviceable (CustomerTenantInfo.self_serviceable), meaning the
  // user can run it themself, no DevOps engineer needed.
  is_self_service: boolean
  // Real, live-synced CustomerTenantInfo.release for this customer+
  // environment right now — only populated on the Verified Done history
  // bucket (pipeline_summary()), deliberately separate from to_version
  // (this ticket's recorded target, which can be stale/"Unknown").
  current_version?: string | null
  current_version_synced_at?: string | null
}

export interface UpgradeSuggestion {
  id: number
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  jira_ref: string | null
  environment: string
  is_self_service: boolean
  current_stage: string
  suggested_stage: string
  reason: string
}

export interface UpgradeRequestTypeDrift {
  id: number
  jira_ref: string
  title: string
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  stored_request_type: string | null
  live_request_type: string | null
  detected_at?: string | null
}

export interface SupersededUpgrade {
  id: number
  jira_ref: string | null
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  environment: string
  stage: string
  wants_version: string
  done_version: string
  done_jira_ref: string | null
  done_verified_at: string | null
}

export interface UpgradeLineupRequest {
  jira_ref: string
  title: string
  environment: string
  days_open: number
  customer_id: number
  customer_name: string
  customer_tier: string | null
  connected_signal_refs: string[]
}

export interface UpgradeLineupSignal {
  jira_ref: string
  title: string
  environment: string
  days_open: number
  linked_vms_ref: string | null
  customer_id: number
  customer_name: string
  customer_tier: string | null
  connected_request_ref: string | null
}

export interface UpgradeLineupGroup {
  customer_id: number
  customer_name: string
  customer_tier: string | null
  requests: UpgradeLineupRequest[]
  signals: UpgradeLineupSignal[]
}

export interface OverdueBugFixUpgrade {
  id: number
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  jira_ref: string | null
  linked_vms_ref: string | null
  stage: string
  days_stale: number | null
}

export interface UnconfirmedUpgrade {
  id: number
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  jira_ref: string | null
  stage: string
  scheduled_at: string | null
  devops_confirmed: boolean
  customer_confirmed: boolean
}

export interface PendingUpgradeMissingCase {
  id: number
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  jira_ref: string | null
  environment: string
  linked_vms_ref: string | null
}

export interface UnmatchedUpgradeCustomer {
  id: number
  customer_name: string
  ticket_count: number
  sample_jira_refs: string[]
  first_seen_at: string
  last_seen_at: string
}

export interface UpgradeSyncResult {
  created: number
  updated: number
  customers_recomputed: number
  unmatched_customers: string[]
  errors: number
}

export interface Release {
  id: number
  version: string
  released_at: string
  defects_fixed: number
  improvements: number
  notes: string | null
  is_latest: boolean
  created_at: string
}

export interface ReleaseComingNext {
  vms_ref: string
  status: string
  target_version: string | null
  confirmed: boolean
  sprint_name: string | null
  sprint_state: string | null
  assignee: string | null
}

export interface ReleaseDefects {
  version: string
  curated_defects_fixed: number | null
  live_defect_count: number
  defects: { vms_ref: string; status: string; sprint_name: string | null; customers: string[] }[]
}

export interface PendingUpgradeBug {
  vms_ref: string
  status: string
  fix_version: string | null
  sprint_name: string | null
  sprint_state: string | null
  assignee: string | null
  matched_release: string | null
  fixed_not_released: boolean
}

export interface PendingUpgradeQueueItem {
  jira_ref: string
  customer_id: number
  customer_name: string | null
  customer_tier: string | null
  bugs: PendingUpgradeBug[]
}

export interface EngineerImpact {
  assignee: string
  bugs_fixed: number
  customers_impacted: number
  top_bug: string | null
  top_bug_customers: number
  bugs_fixed_90d: number
  customers_impacted_90d: number
}

export interface DefectDevStatusBug {
  vms_ref: string
  status: string
  dev_assignee: string | null
  sprint_name: string | null
  fix_version: string | null
  matched_release: string | null
  fixed_not_released: boolean
}

export interface DefectDevStatusItem {
  jira_ref: string
  title: string
  assignee_name: string | null
  customer_name: string | null
  days_open: number | null
  resolution: string | null
  bug: DefectDevStatusBug | null
}

export interface MissingReleaseBug {
  vms_ref: string
  status: string
  sprint_name: string | null
  assignee: string | null
}

export interface MissingRelease {
  fix_version: string
  bug_count: number
  customer_count: number
  bugs: MissingReleaseBug[]
}

export interface CustomerBelowLatest {
  id: number
  name: string
  tier: string
  prod_version: string
  renewal_date: string | null
}

export interface CustomersBelowLatestStats {
  latest_version: string | null
  customers: CustomerBelowLatest[]
  no_data_count: number
}

export interface VersionDistributionBucket {
  label: string
  cls: string
  count: number
  pct: number
}

export interface VersionDistributionStats {
  vms_customer_count: number
  buckets: VersionDistributionBucket[]
}

export interface PendingUpgradeDefect {
  case_jira_ref: string
  case_title: string
  vms_ref: string
  fix_version: string
}

export interface TheoreticalExposureBug {
  vms_ref: string
  fix_version: string
}

export interface MigrationPriorityItem {
  customer_id: number
  customer_name: string
  customer_tier: string
  infra: string
  migration_stage: string
  migration_tracked: boolean
  current_version: string
  latest_version: string | null
  is_behind_latest: boolean
  open_incident_remediations: { incident_id: number; title: string; severity: string }[]
  pending_upgrade_defects: PendingUpgradeDefect[]
  pending_upgrade_defect_count: number
  theoretical_exposure: TheoreticalExposureBug[]
  theoretical_exposure_count: number
  priority_score: number
  score_breakdown: { tier_weight: number; infra_weight: number; incident_severity_weight: number; defect_weight: number }
}

export interface MigrationPriorityResult {
  customers: MigrationPriorityItem[]
  vms_customer_count: number
  covered_count: number
}

// Engineering — real customer technical state: fleet version/defect
// intelligence (reused wholesale from Release Intelligence's own
// functions, never recomputed) plus the two genuinely new pieces: the
// Environment Matrix and real AWS resource inventory/matching. See
// backend/app/routers/engineering.py for the exact reuse boundary.
export interface AwsResource {
  id: number
  resource_type: 'EC2' | 'RDS'
  resource_id: string
  name: string | null
  region: string | null
  aws_environment: 'Old' | 'New'
  instance_type: string | null
  engine: string | null
  engine_version: string | null
  state: string | null
  endpoint_or_ip: string | null
  launched_at: string | null
  customer_id: number | null
  customer_name: string | null
  customer_environment: string | null
  suggested_customer_id: number | null
  match_status: 'unmatched' | 'confirmed' | 'internal'
  match_method: 'name_heuristic' | 'manual' | null
  imported_at: string
}

export interface InfraAccountCard {
  name: string
  region: string | null
  summary: string
  state: string
  state_color: string
  needs_import: boolean
  import_copy: string | null
  import_cmd: string | null
}

export interface HostingModelRow {
  label: string
  count: number
  share: string
  color: string
  note: string
}

export interface DependencyLifecycleRow {
  name: string
  envs: string
  state: string
  color: string
}

export interface InfrastructureSummary {
  accounts: InfraAccountCard[]
  hosting: HostingModelRow[]
  dependency_lifecycle: DependencyLifecycleRow[]
}

export interface VersionListItem {
  version: string
  status: string | null
  released_at: string
  envs: number
  share: string
  known_defect_count: number
}

export interface VersionKnownDefect {
  vms_ref: string
  fix_version: string | null
  reported_count: number
  critical: boolean
}

export interface VersionDetail {
  version: string
  status: string | null
  released_at: string
  age_days: number
  previous_version: string | null
  next_version: string | null
  stats: {
    environments: number
    customers: number
    estate_share: string
    known_defects: number
    critical: number
    live_incidents: number
  }
  exposure_sentence: string
  affected_customers: { id: number; name: string }[]
  known_defects: VersionKnownDefect[]
}

export interface DefectRow {
  vms_ref: string
  title: string
  critical: boolean
  status: string
  affects_count: number
  fix_version: string | null
  fix_released: boolean
  age_days: number | null
  case_count: number
  incident_count: number
  exposed_env_count: number
  chain: string
}

export interface DeploymentRow {
  id: number
  verified_at: string
  customer_id: number
  customer_name: string | null
  environment: string
  move: string
  duration_minutes: number
  status: string
  note: string
}

export interface RolloutBucket {
  label: string
  count: number
  share: string
  color: string
  note: string
}

export interface DeploymentsResult {
  stats: {
    last_7_days: number
    success_rate: string
    failed_cancelled_7d: number
    manual_deploys_remaining: number
  }
  deployments: DeploymentRow[]
  rollout: { target_version: string | null; buckets: RolloutBucket[] }
  upcoming: { when: string; what: string }[]
}

export interface CustomerTechnicalRisk {
  customer_id: number
  customer_name: string
  customer_tier: string
  infra: string
  migration_stage: string
  current_version: string | null
  latest_version: string | null
  is_behind_latest: boolean
  open_incident_remediations: { incident_id: number; title: string; severity: string }[]
  pending_upgrade_defects: { case_jira_ref: string; case_title: string; vms_ref: string; fix_version: string | null }[]
  pending_upgrade_defect_count: number
  theoretical_exposure_count: number
  priority_score: number
  score_breakdown: { tier_weight: number; infra_weight: number; incident_severity_weight: number; defect_weight: number }
}

export interface Runbook {
  id: number
  ref: string
  title: string
  trigger_hosting_model: string | null
  trigger_engine_contains: string | null
  body: string
  created_at: string
  updated_at: string
}

export interface EngineeringTriageCheck {
  mark: string
  color: string
  label: string
  detail: string
}

export interface EngineeringDriftRow {
  label: string
  cells: Record<string, string | null>
}

export interface EngineeringTimelineEntry {
  when: string
  mark: string
  color: string
  what: string
  link: string
}

export interface EngineeringHistoryEntry {
  when: string
  ref: string
  what: string
  state: string
  color: string
}

export interface EngineeringBlockRow {
  k: string
  v: string
  color: string | null
}

export interface EngineeringBlock {
  title: string
  rows: EngineeringBlockRow[]
}

export interface EngineeringKnowledgeEntry {
  kind: string
  color: string
  what: string
  meta: string
}

export interface EngineeringCustomerPanel {
  kind: 'customer'
  kicker: string
  title: string
  sub: string
  triage: { color: string; verdict: string; checks: EngineeringTriageCheck[] }
  drift: { rows: EngineeringDriftRow[]; note: string }
  load_available: boolean
  timeline: EngineeringTimelineEntry[]
  history: EngineeringHistoryEntry[]
  repeat: string
  risk: CustomerTechnicalRisk | null
  blocks: EngineeringBlock[]
  knowledge: EngineeringKnowledgeEntry[]
  connected_defects: { vms_ref: string; fix_version: string | null; reported: boolean }[]
  peer_customers: { id: number; name: string }[]
}

export interface EngineeringChainStep {
  count: number
  label: string
  detail: string
  color: string
}

export interface EngineeringDefectPanel {
  kind: 'defect'
  kicker: string
  title: string
  sub: string
  severity: string
  status: string
  fix_version: string | null
  fix_released: boolean
  age_days: number | null
  chain: EngineeringChainStep[]
  affected_customers: { id: number; name: string }[]
  sprint_name: string | null
  assignee: string | null
}

export interface CustomerTechnical {
  customer_id: number
  risk: CustomerTechnicalRisk | null
  upgrade_path: string[]
  env_diff: Record<string, { release: string | null; has_data: boolean; is_jvms_mode: boolean | null }>
  material_diff: boolean
  connected_defects: { vms_ref: string; fix_version: string | null; reported: boolean }[]
  peer_customers: { id: number; name: string }[]
}

export interface EngineeringAttentionSignal {
  customer_id: number
  customer_name: string
  customer_tier: string
  priority_score: number
  signals: { type: 'old_infra' | 'high_risk' | 'open_incident' | 'hot_resource' | 'error_logs'; detail: string }[]
  narrative: string
}

export interface EstateKpi {
  value: number
  delta: number | null
  since: string | null
}

export interface VersionInfraMatrixRow {
  band: string
  by_hosting: Record<string, number>
  total: number
}

export interface EngineeringOverview {
  attention_signals: EngineeringAttentionSignal[]
  kpis: {
    estate: EstateKpi
    on_current_release: EstateKpi
    customer_exposure: EstateKpi
    legacy_footprint: EstateKpi
  }
  version_infra_matrix: {
    hosting_types: string[]
    rows: VersionInfraMatrixRow[]
  }
  coverage: {
    vms_customer_count: number
    tenant_info_covered_count: number
    aws_resource_count: number
    aws_matched_customer_count: number
  }
  aws_coverage: {
    ec2_count: number
    rds_count: number
    confirmed_match_count: number
    unmatched_count: number
    internal_count: number
  }
  infra_flag_cross_check: { customer_id: number; customer_name: string; flagged_infra: string; real_aws_environment: string; resource_name: string }[]
  legacy_infra_customer_count: number
  resources_under_load: number
  version_exposure: VersionExposureItem[]
  engineer_impact: EngineerImpact[]
  missing_releases: MissingRelease[]
  customers_below_latest: CustomersBelowLatestStats
  version_distribution: VersionDistributionStats
  bug_fix_upgrades_overdue: OverdueBugFixUpgrade[]
  pending_upgrade_queue_count: number
  technical_risk_top: MigrationPriorityItem[]
  technical_risk_covered_count: number
  technical_risk_vms_customer_count: number
}

export interface EnvironmentMatrixRow {
  customer_id: number
  customer_name: string
  customer_tier: string
  customer_infra: string
  environment: 'PROD' | 'TEST' | 'DEV'
  has_data: boolean
  subdomain: string | null
  release: string | null
  // JVM-mode tenants don't reliably expose the real running version on the
  // /info endpoint this app's sync probes — confirmed live (one JVM
  // tenant's /info reported a legacy "6.38.3-R" while its real version
  // was 8.30.1). true/false when known, null when never successfully synced.
  is_jvms_mode: boolean | null
  reported_environment: string | null
  last_synced_at: string | null
  aws_resource: AwsResource | null
  hosting_model: 'Docker / ECS' | 'EC2' | 'RDS' | 'Legacy VM' | null
  release_status: 'Current' | 'Supported' | 'Ageing' | 'Legacy' | 'End of life' | 'Unknown' | null
  behind_current: boolean
  cpu_utilization_pct: number | null
  known_issues_count: number | null
  reported_issues_count: number
  open_incident_count: number
  risk_score: number | null
  risk_label: 'Critical' | 'High' | 'Medium' | 'Low' | null
}

export interface EnvironmentMatrixResult {
  rows: EnvironmentMatrixRow[]
  vms_customer_count: number
  tenant_row_count: number
  matched_aws_count: number
}

export interface AwsImportRequest {
  aws_environment: 'Old' | 'New'
  region?: string
  ec2?: unknown
  rds?: unknown
  cloudwatch?: unknown
}

export interface AwsImportResult {
  created: number
  updated: number
  suggested: number
}

// Logs — a scoped substitute for a real log platform (Humio/Falcon
// LogScale), not a replica: real AWS log events (CloudWatch Logs +
// CloudTrail) imported from a periodic manual export, full-text
// searchable. No live tail, no query language, no continuous ingest.
export type LogType = 'application' | 'rds' | 'cloudtrail' | 'vpc_flow'

export interface LogEntry {
  id: number
  log_type: LogType
  source_group: string
  event_id: string
  timestamp: string
  message: string
  level: string | null
  aws_resource_id: number | null
  aws_resource_name: string | null
  customer_id: number | null
  customer_name: string | null
  imported_at: string
}

export interface LogImportRequest {
  log_type: LogType
  source_group: string
  aws_resource_id?: number
  entries: unknown
}

export interface LogImportResult {
  created: number
  skipped: number
}

export interface LogSearchResult {
  entries: LogEntry[]
  total_imported: number
}

export interface AiObservation {
  id: number
  kind: string // "fixed_but_open" | "cross_signal" | "migration_priority" | "training_priority"
  summary: string
  refs: string
  customer_id: number | null
  customer_name: string | null
  status: string // "New" | "Reviewed" | "Dismissed"
  model_used: string
  created_at: string
  reviewed_at: string | null
}

const AI_OBSERVATION_KIND_LABELS: Record<string, string> = {
  fixed_but_open: 'Fixed but open',
  cross_signal: 'Cross-signal',
  migration_priority: 'Migration priority',
  training_priority: 'Training priority',
}
export function aiObservationKindLabel(kind: string): string {
  return AI_OBSERVATION_KIND_LABELS[kind] ?? kind
}

export interface OllamaConversation {
  id: number
  title: string
  created_at: string
  updated_at: string
}

export interface OllamaMessage {
  id: number
  role: string // "user" | "assistant"
  content: string
  model_used: string | null
  created_at: string
}

export interface OllamaCallLog {
  id: number
  purpose: string // "chat" | "supervisor_fixed_but_open" | "supervisor_cross_signal"
  model_used: string
  success: boolean
  error_message: string | null
  duration_ms: number | null
  prompt_eval_count: number | null
  eval_count: number | null
  created_at: string
}

export interface OllamaStatus {
  enabled: boolean
  model: string
  base_url: string
}

export interface OllamaMetrics {
  total_calls: number
  avg_duration_ms: number | null
  success_rate: number | null
  last_call_at: string | null
  purpose_breakdown: Record<string, number>
}

export interface KnowledgeExtract {
  id: number
  category: string // "Trend" | "System" | "Process" | "Procedure" | "Challenge" | "Relationship"
  summary: string
  source_note_id: number
  source_label: string | null
  customer_id: number | null
  jira_ref: string | null
  model_used: string
  dismissed: boolean
  created_at: string
}

export interface OpsNote {
  id: number
  text: string
  source_label: string | null
  customer_id: number | null
  customer_name: string | null
  jira_ref: string | null
  created_at: string
}

export interface FixToReliefCase {
  jira_ref: string
  vms_ref: string
  customer_name: string
  reported_at: string
  relieved_at: string
  days: number
}

export interface FixToReliefStats {
  median_days: number | null
  mean_days: number | null
  resolved_count: number
  still_waiting_count: number
  cases: FixToReliefCase[]
}

export interface VersionExposureCustomer {
  id: number
  name: string
  tier: string | null
}

export interface VersionExposureSilentCustomer extends VersionExposureCustomer {
  prod_version: string | null
}

export interface VersionExposureItem {
  vms_ref: string
  fix_version: string | null
  assignee: string | null
  sprint_name: string | null
  matched_release: string | null
  reported_customers: VersionExposureCustomer[]
  silently_exposed_customers: VersionExposureSilentCustomer[]
}

export interface TroubleshootStep {
  label: string
  detail: string
}

export interface TroubleshootCase {
  jira_ref: string
  title: string
  status: string
  customer_name: string | null
  days_open: number
}

export interface TroubleshootBug {
  vms_ref: string
  status: string
  fix_version: string | null
  sprint_name: string | null
  assignee: string | null
  matched_release: string | null
  reported_customers: VersionExposureCustomer[]
  silently_exposed_customers: VersionExposureSilentCustomer[]
}

export interface TroubleshootIncident {
  id: number
  title: string
  status: string
  phase: string
}

export interface TroubleshootResult {
  resolution_path: 'case_ref' | 'vms_ref' | 'fulltext' | 'not_found'
  case: TroubleshootCase | null
  bug: TroubleshootBug | null
  incident: TroubleshootIncident | null
  steps: TroubleshootStep[]
  narration: string | null
}

export interface BugTimelineEntry {
  action: string
  detail: string | null
  actor: string
  created_at: string
}

export interface SSORecord {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  customer_csm: string
  has_prod: boolean
  has_test: boolean
  stage: string
  display_stage: string
  it_contact_name: string | null
  it_contact_email: string | null
  email_sent_at: string | null
  guest_invite_sent: boolean
  reply_received_at: string | null
  field_domain: string | null
  field_client_id: string | null
  field_secret: string | null
  field_reply_url: string | null
  field_app_id_uri: string | null
  devops_started_at: string | null
  switchover_at: string | null
  switchover_duration_mins: number | null
  follow_up_date: string | null
  overdue_days: number | null
  notes: string | null
  source_jira_ref: string | null
}

export interface SSOStats {
  total: number
  by_stage: Record<string, number>
  avg_switchover_mins: number | null
}

export interface TriageStats {
  sla_breaching: number
  awaiting_dev: number
  awaiting_customer: number
  resolved_today: number
  total_active: number
}

export interface CustomerStats {
  total: number
  arr_old_infra: number
  arr_red_health: number
  arr_renewal_risk: number
  arr_open_defects: number
  old_infra_count: number
  red_health_count: number
  vms_old_infra_count: number
  migration_active_count: number
  stalled_migration_count: number
  confirmed_outdated_count: number
  tenant_known_count: number
  vms_customer_count: number
  latest_version: string | null
}

export interface MigrationProject {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  customer_infra: string
  customer_arr_gbp: number
  customer_renewal_date: string | null
  stage: string
  assignee: string | null
  complexity: string
  ip_fw: boolean
  requires_upgrade: boolean
  stalled: boolean
  stalled_days: number
  downtime_agreed_at: string | null
  completed_at: string | null
  ip_notes: string | null
  integration_notes: string | null
  customer_prod_version: string | null
  initiated_at: string | null
  has_test_dev?: boolean
}

export interface Cancellation {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  customer_arr_gbp: number
  customer_csm: string
  stage: 'Requested' | 'DevOps Notified' | 'Decommissioned'
  requested_at: string
  reason: string | null
  jira_ref: string | null
  effective_date: string
  devops_contact: string | null
  devops_notified_at: string | null
  decommissioned_at: string | null
  notes: string | null
  overdue: boolean
  days_until_effective: number
}

export interface MigrationBoard {
  stages: Record<string, MigrationProject[]>
  candidates: MigrationProject[]
  stats: {
    on_old_infra: number
    in_pipeline: number
    needs_upgrade_first: number
    completed: number
    stalled: number
    candidates_count: number
  }
}

export interface TrainingGap {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  area: string
  description: string | null
  source_case_ref: string | null
  count: number
  logged_at: string
}

export interface TrainingSession {
  id: number
  customer_id: number
  customer_name: string
  customer_tier: string
  session_date: string
  topic_area: string
  format: string | null
  delivered_by: string
  outcome: string | null
  follow_up_needed: boolean
  follow_up_text: string | null
  customer_csm: string | null
}

export interface EducationStats {
  total_gaps: number
  unique_areas: number
  total_sessions: number
  follow_ups_due: number
  top_areas: { area: string; count: number }[]
}

export interface ReleaseNoteFeatureOut {
  version: string
  ticket_id: string | null
  title: string
  category: string | null
  description: string | null
  topic_area: string
}

export interface TrainingRecommendation {
  customer_id: number
  customer_name: string
  customer_tier: string
  current_version: string
  latest_version: string
  crossed_versions: string[]
  features: ReleaseNoteFeatureOut[]
  feature_count: number
}

export interface TrainingRecommendationsResult {
  customers: TrainingRecommendation[]
  vms_customer_count: number
  covered_count: number
}

export interface ReleaseNotesRefreshResult {
  already_cached: string[]
  fetched: string[]
  empty: string[]
  failed: string[]
  recovered_via_ask?: string[]
  note?: string
}

export interface JiraUnmatched {
  jira_ref: string
  title: string
  issue_type: string
  case_type: string
  priority: string
  labels: string[]
  days_open: number
  jira_customer_name: string | null
  request_type: string | null
  first_seen_at: string
  last_seen_at: string
}

export interface CustomerTriageCard {
  id: number
  name: string
  tier: string
  arr_gbp: number
  infra: string
  wildfly8: boolean
  sso: string
  prod_version: string | null
  temperature: number
  security_score: number
  renewal_days: number | null
  risk: 'high' | 'action' | 'monitor'
  training_gap_count: number
  sla_breaching_count: number
  active_case_count: number
  active_cases: { id: number; jira_ref: string; sla_breaching: boolean }[]
  hypercare_until: string | null
  hypercare_reason: string | null
}

export type Lane = 'me' | 'defect' | 'devops' | 'dev' | 'customer' | 'csm' | 'escalated' | 'unassigned'

export interface LaneRow {
  // null for a real open Jira ticket that has no local Case row yet — it
  // still shows up (see backend desk.py::_live_open_cases), just with no
  // local PK to PATCH against, so the row-level actions are unavailable.
  id: number | null
  jira_ref: string
  title: string
  priority: string
  days_open: number
  status: string
  assigned_to: string | null
  last_mention_name: string | null
  lane_override: string | null
  customer_id: number | null
  customer_name: string | null
  tier: string | null
  csm: string | null
  renewal_flag: boolean
  migration_flag: boolean
  hypercare_flag: boolean
  hypercare_overdue: boolean
  hypercare_reason: string | null
}

export interface LaneBucket {
  lane: Lane
  label: string
  count: number
  oldest_days: number
  share_pct: number
  rows: LaneRow[]
}

export interface DeskLanes {
  total_open: number
  lanes: LaneBucket[]
}

export interface QueueSla {
  completed: boolean
  breached: boolean
  remaining_minutes: number | null
  goal_minutes: number | null
  elapsed_minutes?: number | null
}

export interface QueueRow {
  id: number | null
  jira_ref: string
  title: string
  customer_id: number | null
  customer_name: string | null
  customer_tier: string | null
  priority: string
  status: string
  raw_status: string
  assigned_to: string | null
  created: string | null
  days_open: number
  sla: QueueSla | null
  lane: Lane
  lane_label: string
  last_reply_by: string | null
  last_reply_at: string | null
}

export interface DeskQueue {
  total: number
  rows: QueueRow[]
}

export interface DeskSummary {
  open_load: number
  open_load_source: 'jira_live' | 'local_fallback'
  open_load_baseline: number | null
  open_load_vs_baseline_pct: number | null
  calibrating: boolean
  arrivals_7d: number
  closures_7d: number
  median_time_to_first_move_hours: number | null
  closed_last_7_days: number
  ttfr_median_hours: number | null
  ttfr_breach_count: number
  ttr_median_hours: number | null
  resolved_today: number
  updated_today: number
}

export interface DeskEngineer {
  name: string
  open: number
  open_age_mean_days: number | null
  open_age_median_days: number | null
  resolved: number
  updated_today: number
  ttfr_median_hours: number | null
  ttr_median_hours: number | null
  // Fresh/backlog split — see team_resolved_stats()'s docstring. fresh_resolved
  // is the subset of `resolved` actually worked in this window;
  // *_median_hours_fresh/backlog split the TTR/TTFR duration medians the
  // same way, so a batch of old tickets closed together doesn't quietly
  // drag stale durations into "this window's" numbers.
  fresh_resolved: number | null
  ttr_median_hours_fresh: number | null
  ttr_median_hours_backlog: number | null
  ttfr_median_hours_fresh: number | null
  ttfr_median_hours_backlog: number | null
  // Windowed mirror of open/open_age_*_days — open tickets CREATED within
  // the selected period/month, still open. Exists specifically for Team
  // Load Split's donut/table: the plain (always-live) fields above answer
  // "how much do you currently have," which lets a large historical
  // backlog dominate the pie regardless of the period toggle — this
  // answers "of what came in during this window, how much is still open."
  open_in_window: number
  open_age_mean_days_in_window: number | null
  open_age_median_days_in_window: number | null
  // How many tickets this engineer currently holds that were CREATED in
  // the same window (regardless of status) — the denominator that turns
  // open_in_window from a raw count into a self-anchored rate ("10 of 39
  // opened this week are still open"), instead of a number that only means
  // something compared to a neighbor's slice.
  created: number
  // Real per-ticket detail behind open_in_window/created/resolved above —
  // powers Team Load Split's drillable cells. tickets_open is the SAME
  // population as open_in_window (created this window, still open);
  // tickets_created/tickets_resolved likewise mirror created/resolved.
  tickets_open: DrillTicket[]
  tickets_created: DrillTicket[]
  tickets_resolved: DrillTicket[]
}

export type DeskTeamPeriod = 'day' | 'week' | 'month' | 'quarter' | 'year'

export interface DeskTeam {
  period: DeskTeamPeriod
  month: string | null
  resolved_source: 'jira_live' | 'local_fallback'
  open_source: 'jira_live' | 'local_fallback'
  created_source: 'jira_live' | 'local_fallback'
  team: DeskEngineer
  engineers: DeskEngineer[]
  unassigned_open: number
  other_open: number
  unassigned_open_in_window: number
  other_open_in_window: number
  // Live (unwindowed) ticket detail behind Unassigned/Other — "needs
  // triage" is urgent regardless of when a ticket arrived, so these stay
  // live rather than windowed like tickets_open above.
  unassigned_tickets: DrillTicket[]
  other_tickets: DrillTicket[]
}

export interface DeskDecision {
  text: string
  detail: string
  jira_ref: string | null
}

export interface DeskStalledMigration {
  id: number
  customer_id: number
  customer_name: string | null
}

export interface DeskFlags {
  sla_breach_count: number
  sla_breach_refs: string[]
  sla_breach_tickets: DrillTicket[]
  renewal_under_60d_count: number
  renewal_under_60d_customers: DrillCustomer[]
  stalled_migration_count: number
  stalled_migrations: DeskStalledMigration[]
  cancellation_overdue_count: number
  cancellation_overdue_customers: DrillCustomer[]
  hypercare_count: number
  hypercare_customers: DrillCustomer[]
  certs_expiring_count: number
  certs_expiring: DeskExpiringCert[]
  bug_fix_upgrade_overdue_count: number
  bug_fix_upgrade_overdue: OverdueBugFixUpgrade[]
  unconfirmed_upgrade_count: number
  unconfirmed_upgrades: UnconfirmedUpgrade[]
  pending_upgrade_missing_case_count: number
  pending_upgrade_missing_case: PendingUpgradeMissingCase[]
  superseded_upgrade_count: number
  superseded_upgrades: SupersededUpgrade[]
  stalled_incident_count: number
  stalled_incidents: { id: number; title: string; severity: string; phase: string; days_stale: number | null }[]
  stale_count: number
  stale_tickets: DrillTicket[]
  chase_needed_count: number
  chase_needed_tickets: (DrillTicket & { days_waiting: number })[]
  blocked_upgrade_count: number
  blocked_upgrades: { id: number; jira_ref: string | null; customer_id: number | null; customer_name: string | null; blocked_reason: string | null }[]
  mentioned_count: number
  mentioned_tickets: (DrillTicket & { mentioned_name: string | null })[]
  recent_comment_count: number
  recent_comments: { jira_ref: string; author: string; created: string; text: string; customer_name: string | null; assignee_name: string | null }[]
}

export interface DeskActivityEvent {
  time: string
  action: string
  target: string | null
  detail: string | null
}

export interface DeskBriefing {
  flags: DeskFlags
  needs_decision: DeskDecision[]
  activity: DeskActivityEvent[]
}

export interface VmsBugCase {
  jira_ref: string
  title: string
  priority: string
  days_open: number
  customer_name: string | null
  customer_tier: string | null
}

export interface VmsBug {
  jira_ref: string
  issue_type: string
  status: string
  fix_version: string | null
  sprint_name: string | null
  sprint_state: string | null
  assignee: string | null
  labels: string[]
  affected_customers: string[]
  linked_cases: VmsBugCase[]
  ai_summary: string | null
  ai_summary_at: string | null
  rovo_context: string | null
  rovo_context_at: string | null
}

export interface CustomerCaseSummary {
  customer_id: number
  customer_name: string
  // 'jira_live' = real, complete counts (customer_case_stats()); 'local_fallback'
  // = the local `cases` table only (Jira disabled/unreachable) — badly
  // undercounts real volume, since that table only holds manually-mapped
  // tickets. logged_months is null on the fallback path (not computable
  // locally, not fabricated).
  source: 'jira_live' | 'local_fallback'
  logged_months: number | null
  open_count: number
  by_case_type: Record<string, number>
  by_priority: Record<string, number>
  oldest_days: number
  open_tickets: { jira_ref: string; title: string; priority: string; days_open: number }[]
  monthly_counts: { month: string; count: number }[]
  top_topics: { topic: string; count: number }[]
  recurring_topics: { topic: string; count: number }[]
  volume_spike: { month: string; count: number; prior_average: number } | null
}

export interface AgingBucket {
  label: string
  count: number
  share_pct: number
}

export interface AgingBuckets {
  total_open: number
  over_90_days: number
  buckets: AgingBucket[]
}

export interface VolumeAccount {
  customer_id: number
  customer_name: string
  open_count: number
  baseline: number | null
  multiplier: number | null
  label: 'loud' | 'quiet' | 'steady' | 'calibrating'
  calibrating: boolean
}

export interface ExchangeCase {
  jira_ref: string
  title: string
  customer_name: string | null
  comment_count: number
}

export interface ResolvedStats {
  window_days: number
  total_resolved_90d: number
  resolved_this_week: number
  resolved_this_month: number
  ttr_median_hours: number | null
  top_resolved_accounts: { customer_name: string; count: number }[]
  weekly_trend: { week_ending: string; count: number }[]
}

export type CommandWindow = 'week' | 'month' | 'quarter' | 'year'

export interface CaseMixCase {
  jira_ref: string
  title: string
  assignee_name: string | null
  customer_name: string | null
  days_open: number | null
}

// Shared shape for every "click a number, see the real tickets behind it"
// drill-down across My Desk and Command Center (Team Load Split, SLA
// Breaching, Cases Logged, Resolved, Unassigned/Other, etc.) — same fields
// CaseMixCase already used, given one common name so DrillList.vue only
// needs one prop type.
export type DrillTicket = CaseMixCase

// A customer (not ticket) behind a flag — Renewal/Overdue/Hypercare rows,
// which drill into the Customer panel, not a Case.
export interface DrillCustomer {
  id: number
  name: string
}

// Real per-ticket detail behind one day's closed/opened count — powers the
// drillable Closed/Opened Tickets panels (same "click a bucket, see what's
// in it" idea as Case Mix, just no days_open since that's not meaningful
// for a single day's bucket). `fresh` is only set on closed tickets (was
// this ticket's last real activity inside the window it's credited to, or
// was it just a stale close) — undefined on opened tickets, where the
// concept doesn't apply.
export interface DailyTicket {
  jira_ref: string
  title: string
  assignee_name: string | null
  customer_name: string | null
  fresh?: boolean
}

export interface CaseMixEntry {
  status: string
  count: number
  your_count: number
  cases: CaseMixCase[]
}

export interface AgedCaseBucket {
  label: string
  count: number
  example_refs: string[]
}

export interface ScorecardStats {
  window: CommandWindow
  upgrades_completed: number
  migrations_completed: number
  sso_live: number
  cancellations_decommissioned: number
  support: {
    resolved_count: number | null
    fresh_resolved_count: number | null
    assigned_count: number | null
    fresh_assigned_count: number | null
    replies_count: number | null
    comments_count: number | null
    logged_count: number | null
    // Real per-ticket detail behind the tiles above — logged_tickets/
    // resolved_tickets are scoped to the named SUPPORT_TEAM roster (not
    // logged_count's/resolved_count's own broader/team-summed totals), same
    // "roster, not everyone" boundary as desk_team()'s ticket lists.
    logged_tickets: DrillTicket[]
    resolved_tickets: DrillTicket[]
    sla_breach_tickets: DrillTicket[]
    by_engineer: Record<string, DailyOpsMetrics | null>
    daily_closed_series: { date: string; closed: number; fresh_closed: number; tickets: DailyTicket[] }[]
    daily_opened_series: { date: string; opened: number; tickets: DailyTicket[] }[]
    ttfr_median_hours: number | null
    ttr_median_hours: number | null
    median_time_to_first_move_hours: number | null
    sla_breach_count: number
    open_load: number
    open_load_baseline: number | null
    open_load_vs_baseline_pct: number | null
    waiting_on_me_median_hours: number | null
    case_mix: CaseMixEntry[]
    aged_cases: AgedCaseBucket[]
  }
}

export interface DailySeriesPoint {
  date: string
  open_count: number
  created_count: number
  closed_count: number
}

export interface DailyOpsMetrics {
  assigned: number
  fresh_assigned: number
  resolved: number
  fresh_resolved: number
  replies: number
  comments: number
  logged: number | null
}

export interface DailyOpsDay {
  date: string
  engineers: Record<string, DailyOpsMetrics>
  // Real per-ticket detail behind that day's resolved/opened counts — the
  // backend already returns these (used internally by daily_ops_stats()'s
  // consumers), just never declared here before. Powers the "Resolved
  // Today" tile's drill-down (today = the last entry in `series`).
  resolved_tickets: DailyTicket[]
  opened_tickets: DailyTicket[]
}

export interface DailyOpsStats {
  days: number
  source: 'jira_live' | 'unavailable'
  series: DailyOpsDay[]
  totals: Record<string, DailyOpsMetrics>
  // Real UTC time of the oldest of the four underlying Jira fetches behind
  // this response — null only if unavailable. The backend caches these
  // fetches for up to 5 minutes (jira_stats_cache_ttl_seconds), so numbers
  // can lag real Jira activity by that much; this tells the reader exactly
  // how stale, instead of a silently-wrong "0" after just closing tickets.
  fetched_at: string | null
}

export interface VmsCredentialStatus {
  has_credential: boolean
  label: string | null
  client_id: string | null
  audience: string | null
}

export interface VmsEntityResult {
  data: unknown
  message: string | null
}

export interface VmsSandboxRequest {
  token: string
  entity: string
  host: string
  method: 'GET' | 'POST' | 'PUT' | 'DELETE'
  key?: string
  filter?: string
  body?: Record<string, unknown>
}

export interface VmsSandboxResult {
  status: number | null
  data: unknown
  message: string | null
}


export interface ScheduleSlot {
  type: 'Upgrade' | 'Migration' | 'SSO'
  customer_name: string | null
  customer_tier: string | null
  customer_id: number | null
  scheduled_at: string
  duration_minutes: number | null
  detail: string
  id: number
  // Only present on type: 'Upgrade' rows.
  stage?: string
  devops_confirmed?: boolean
  customer_confirmed?: boolean
}

export interface ScheduleCancellationDue {
  customer_name: string | null
  customer_tier: string | null
  customer_id: number | null
  effective_date: string
  overdue: boolean
  stage: string
  id: number
}

export interface ScheduleStats {
  window: CommandWindow
  slots: ScheduleSlot[]
  cancellations_due: ScheduleCancellationDue[]
  devops_slots_this_week: number
  devops_slots_per_week: number
}

export interface BriefingEvent {
  action: string
  target_type: string | null
  target_id: string | null
  customer_name: string | null
  detail: string | null
  created_at: string
}

export interface BriefingStats {
  window: CommandWindow
  events: BriefingEvent[]
}

// ── Typed API helpers ─────────────────────────────────────

export const api = {
  health: () => client.get('/health'),
  healthDb: () => client.get('/health/db'),

  customers: {
    list: (params?: Record<string, string>) => client.get<Customer[]>('/customers', { params }),
    get: (id: number) => client.get<Customer>(`/customers/${id}`),
    stats: () => client.get<CustomerStats>('/customers/stats'),
    openCaseCounts: () => client.get<{ counts: Record<number, number>; source: 'jira_live' | 'local_fallback' }>('/customers/open-case-counts'),
    triage: () => client.get<CustomerTriageCard[]>('/customers/triage'),
    patch: (id: number, data: Record<string, unknown>) => client.patch<Customer>(`/customers/${id}`, data),
    caseSummary: (id: number) => client.get<CustomerCaseSummary>(`/customers/${id}/case-summary`),
    summarize: (id: number) => client.post<{ summary: string | null; message?: string }>(`/customers/${id}/summarize`, {}),
    create: (data: Record<string, unknown>) => client.post<Customer>('/customers', data),
    tenantInfo: (id: number) => client.get<TenantInfo[]>(`/customers/${id}/tenant-info`),
    setTenantSubdomain: (id: number, environment: string, subdomain: string) =>
      client.post<TenantInfo>(`/customers/${id}/tenant-info`, { environment, subdomain }),
    syncTenantInfo: (id: number, environment: string) =>
      client.post<TenantInfo>(`/customers/${id}/tenant-info/${environment}/sync`, {}),
    notes: (id: number) => client.get<CustomerNoteEntry[]>(`/customers/${id}/notes`),
    addNote: (id: number, text: string) => client.post<CustomerNoteEntry>(`/customers/${id}/notes`, { text }),
    contacts: (id: number) => client.get<CustomerContactEntry[]>(`/customers/${id}/contacts`),
    addContact: (id: number, email: string) => client.post<CustomerContactEntry>(`/customers/${id}/contacts`, { email }),
    deleteContact: (id: number, contactId: number) => client.delete(`/customers/${id}/contacts/${contactId}`),
    clearHypercare: (id: number) => client.post<Customer>(`/customers/${id}/clear-hypercare`, {}),
    getVmsCredential: (id: number) => client.get<VmsCredentialStatus>(`/customers/${id}/vms-credential`),
    setVmsCredential: (id: number, data: { client_id: string; client_secret: string; audience?: string; label?: string }) =>
      client.post<VmsCredentialStatus>(`/customers/${id}/vms-credential`, data),
    getVmsEntity: (id: number, entity: string, key: string, demo?: boolean) =>
      client.get<VmsEntityResult>(`/customers/${id}/vms-entity`, { params: { entity, key, demo: demo ? 'true' : undefined } }),
    resolveContacts: (customerIds: number[]) =>
      client.post<CustomerContactResolution[]>('/customers/notify/resolve-contacts', { customer_ids: customerIds }),
    campaigns: (id: number) => client.get<CustomerCampaignSummary[]>(`/customers/${id}/campaigns`),
  },

  tenantDiscovery: {
    run: (customerIds?: number[]) =>
      client.post<TenantDiscoveryResult[]>('/tenant-discovery/run', { customer_ids: customerIds ?? null }),
    accept: (data: {
      customer_id: number; environment: string; subdomain: string; release?: string | null
      reported_environment?: string | null; is_azure_installation?: boolean | null
      is_auth0_installation?: boolean | null; is_jvms_mode?: boolean | null; is_pure_web?: boolean | null
    }) => client.post<TenantInfo>('/tenant-discovery/accept', data),
  },

  campaigns: {
    list: (incidentId?: number) => client.get<Campaign[]>('/campaigns', { params: incidentId ? { incident_id: incidentId } : {} }),
    get: (id: number) => client.get<CampaignDetail>(`/campaigns/${id}`),
    create: (data: { name: string; message: string; customer_ids: number[]; incident_id?: number }) =>
      client.post<Campaign>('/campaigns', data),
    patch: (id: number, data: Record<string, unknown>) => client.patch<Campaign>(`/campaigns/${id}`, data),
  },

  incidents: {
    list: () => client.get<Incident[]>('/incidents'),
    get: (id: number) => client.get<IncidentDetail>(`/incidents/${id}`),
    create: (data: { title: string; source: string; severity: string; detail: string; impact?: string; detected_at?: string; linked_vms_ref?: string; affected_below_version?: string }) =>
      client.post<Incident>('/incidents', data),
    patch: (id: number, data: Record<string, unknown>) => client.patch<Incident>(`/incidents/${id}`, data),
    addRemediation: (incidentId: number, data: { customer_id: number; upgrade_id?: number }) =>
      client.post<IncidentRemediation>(`/incidents/${incidentId}/remediations`, data),
    patchRemediation: (incidentId: number, remediationId: number, data: Record<string, unknown>) =>
      client.patch<IncidentRemediation>(`/incidents/${incidentId}/remediations/${remediationId}`, data),
    notifyRemediation: (incidentId: number, remediationId: number) =>
      client.post<{ notified: boolean }>(`/incidents/${incidentId}/remediations/${remediationId}/notify`, {}),
    suggestCustomers: (incidentId: number, minVersion?: string) =>
      client.get<IncidentCustomerCandidate[]>(`/incidents/${incidentId}/suggest-customers`, { params: minVersion ? { min_version: minVersion } : {} }),
    logDecision: (incidentId: number, text: string) =>
      client.post<{ logged: boolean }>(`/incidents/${incidentId}/decisions`, { text }),
    timeline: (incidentId: number) => client.get<IncidentTimelineEntry[]>(`/incidents/${incidentId}/timeline`),
  },

  vmsSandbox: {
    request: (data: VmsSandboxRequest) => client.post<VmsSandboxResult>('/vms-sandbox/request', data),
  },

  auditLog: {
    list: (params?: { q?: string; action?: string; target_type?: string; before?: string; limit?: number }) =>
      client.get<{ rows: AuditLogEntry[] }>('/audit-log', { params }),
    actions: () => client.get<{ actions: string[] }>('/audit-log/actions'),
  },

  weeklyReport: {
    list: () => client.get<WeeklyReportMeta[]>('/weekly-report'),
    generate: (week?: string) => client.post<WeeklyReportMeta>('/weekly-report/generate', null, { params: week ? { week } : undefined }),
    get: (week: string) => client.get<WeeklyReportMeta & { snapshot: WeeklyReportSnapshot }>(`/weekly-report/${week}`),
    patch: (week: string, data: { status: 'Draft' | 'Published' }) => client.patch<WeeklyReportMeta>(`/weekly-report/${week}`, data),
  },

  cases: {
    list: (params?: Record<string, string | number>) => client.get<Case[]>('/cases', { params }),
    triage: () => client.get<TriageStats>('/cases/triage'),
    getByRef: (jiraRef: string) => client.get<CaseDetail>(`/cases/by-ref/${jiraRef}`),
    activity: (jiraRef: string) => client.get<CaseActivityEntry[]>(`/cases/by-ref/${jiraRef}/activity`),
    patch: (id: number, data: Record<string, unknown>) => client.patch<Case>(`/cases/${id}`, data),
    create: (data: Record<string, unknown>) => client.post<Case>('/cases', data),
  },

  upgrades: {
    list: (params?: Record<string, string | boolean>) => client.get<Upgrade[]>('/upgrades', { params }),
    pipeline: () => client.get('/upgrades/pipeline'),
    patch: (id: number, data: Record<string, unknown>) => client.patch<Upgrade>(`/upgrades/${id}`, data),
    create: (data: Record<string, unknown>) => client.post<Upgrade>('/upgrades', data),
    syncFromJira: () => client.post<UpgradeSyncResult>('/upgrades/sync-from-jira', {}),
    unmatchedCustomers: () => client.get<UnmatchedUpgradeCustomer[]>('/upgrades/unmatched-customers'),
    assignUnmatchedCustomer: (id: number, customerId: number) =>
      client.post<UpgradeSyncResult>(`/upgrades/unmatched-customers/${id}/assign`, { customer_id: customerId }),
    createCustomerFromUnmatched: (id: number, data: { tier: string; csm: string }) =>
      client.post<UpgradeSyncResult>(`/upgrades/unmatched-customers/${id}/create-customer`, data),
    dismissUnmatchedCustomer: (id: number) =>
      client.post<{ status: string }>(`/upgrades/unmatched-customers/${id}/dismiss`, {}),
    suggestions: () => client.get<{ suggestions: UpgradeSuggestion[] }>('/upgrades/suggestions'),
    approveSuggestion: (id: number) => client.post<Upgrade>(`/upgrades/${id}/approve-suggestion`, {}),
    requestTypeDrift: () => client.get<{ drifted: UpgradeRequestTypeDrift[] }>('/upgrades/request-type-drift'),
    recentRequestTypeDrift: () => client.get<{ drifted: UpgradeRequestTypeDrift[] }>('/upgrades/request-type-drift/recent'),
    superseded: () => client.get<{ superseded: SupersededUpgrade[] }>('/upgrades/superseded'),
    lineup: () => client.get<UpgradeLineupGroup[]>('/upgrades/lineup'),
  },

  releases: {
    list: () => client.get<Release[]>('/releases'),
    latest: () => client.get<Release | null>('/releases/latest'),
    defects: (version: string) => client.get<ReleaseDefects>(`/releases/${version}/defects`),
    comingNext: () => client.get<ReleaseComingNext[]>('/releases/coming-next'),
    pendingUpgradeQueue: () => client.get<PendingUpgradeQueueItem[]>('/releases/pending-upgrade-queue'),
    engineerImpact: () => client.get<EngineerImpact[]>('/releases/engineer-impact'),
    versionExposure: () => client.get<VersionExposureItem[]>('/releases/version-exposure'),
    missingReleases: () => client.get<MissingRelease[]>('/releases/missing'),
    fixToRelief: () => client.get<FixToReliefStats>('/releases/fix-to-relief'),
    customersBelowLatest: () => client.get<CustomersBelowLatestStats>('/releases/customers-below-latest'),
    versionDistribution: () => client.get<VersionDistributionStats>('/releases/version-distribution'),
    defectDevStatus: () => client.get<DefectDevStatusItem[]>('/releases/defect-dev-status'),
    bugFixUpgradesOverdue: () => client.get<OverdueBugFixUpgrade[]>('/releases/bug-fix-upgrades-overdue'),
    create: (data: Record<string, unknown>) => client.post<Release>('/releases', data),
  },

  migrationPriority: {
    get: () => client.get<MigrationPriorityResult>('/migration-priority'),
  },

  troubleshoot: {
    investigate: (query: string) => client.post<TroubleshootResult>('/troubleshoot/investigate', { query }),
  },

  engineering: {
    overview: () => client.get<EngineeringOverview>('/engineering/overview'),
    matrix: () => client.get<EnvironmentMatrixResult>('/engineering/environment-matrix'),
    resources: (matchStatus?: string) => client.get<AwsResource[]>('/engineering/aws-resources', { params: matchStatus ? { match_status: matchStatus } : {} }),
    infrastructure: () => client.get<InfrastructureSummary>('/engineering/infrastructure'),
    certificates: () => client.get<CertificatesResult>('/engineering/certificates'),
    scanCertificates: () => client.post<{ started: boolean; reason?: string }>('/engineering/certificates/scan', {}),
    versions: () => client.get<VersionListItem[]>('/engineering/versions'),
    versionDetail: (version: string) => client.get<VersionDetail>(`/engineering/versions/${encodeURIComponent(version)}`),
    defects: () => client.get<DefectRow[]>('/engineering/defects'),
    deployments: () => client.get<DeploymentsResult>('/engineering/deployments'),
    customerTechnical: (customerId: number) => client.get<CustomerTechnical>(`/engineering/customer-technical/${customerId}`),
    customerPanel: (customerId: number, focusEnv?: string) => client.get<EngineeringCustomerPanel>(`/engineering/customer-panel/${customerId}`, { params: focusEnv ? { focus_env: focusEnv } : {} }),
    defectPanel: (vmsRef: string) => client.get<EngineeringDefectPanel>(`/engineering/defects/${encodeURIComponent(vmsRef)}`),
    versionSync: () => client.post<{ synced: number; skipped_no_date: number; error?: string }>('/releases/sync-from-jira', {}),
    runbooks: {
      list: () => client.get<Runbook[]>('/engineering/runbooks'),
      create: (data: Record<string, unknown>) => client.post<Runbook>('/engineering/runbooks', data),
      update: (id: number, data: Record<string, unknown>) => client.patch<Runbook>(`/engineering/runbooks/${id}`, data),
      delete: (id: number) => client.delete(`/engineering/runbooks/${id}`),
    },
    importAws: (data: AwsImportRequest) => client.post<AwsImportResult>('/engineering/aws-import', data),
    confirmMatch: (id: number, data: { customer_id: number; environment: string }) => client.post<AwsResource>(`/engineering/aws-resources/${id}/confirm-match`, data),
    markInternal: (id: number) => client.post<AwsResource>(`/engineering/aws-resources/${id}/mark-internal`, {}),
    importLogs: (data: LogImportRequest) => client.post<LogImportResult>('/engineering/log-import', data),
    searchLogs: (params: { q?: string; log_type?: string; aws_resource_id?: number; since?: string; until?: string; limit?: number }) =>
      client.get<LogSearchResult>('/engineering/logs', { params }),
  },

  aiObservations: {
    list: (status?: string) => client.get<AiObservation[]>('/ai-observations', { params: status ? { status } : {} }),
    review: (id: number) => client.post<AiObservation>(`/ai-observations/${id}/review`, {}),
    dismiss: (id: number) => client.post<AiObservation>(`/ai-observations/${id}/dismiss`, {}),
    recompute: () => client.post<{ created: number }>('/ai-observations/recompute', {}),
  },

  opsNotes: {
    list: (params?: { customer_id?: number; jira_ref?: string }) => client.get<OpsNote[]>('/ops-notes', { params }),
    create: (data: Record<string, unknown>) => client.post<OpsNote>('/ops-notes', data),
    delete: (id: number) => client.delete<void>(`/ops-notes/${id}`),
  },

  ollamaChat: {
    createConversation: () => client.post<OllamaConversation>('/ollama-chat/conversations', {}),
    listConversations: () => client.get<OllamaConversation[]>('/ollama-chat/conversations'),
    getMessages: (id: number) => client.get<OllamaMessage[]>(`/ollama-chat/conversations/${id}/messages`),
    escalate: (id: number) => client.post<OllamaMessage>(`/ollama-chat/conversations/${id}/escalate`, {}),
    // sendMessage is deliberately NOT here — streaming needs a raw fetch()
    // + ReadableStream reader (EventSource can't carry the Authorization
    // header this app's axios interceptor relies on), handled directly in
    // OllamaControlView.vue.
  },

  knowledge: {
    list: (params?: { category?: string; include_dismissed?: boolean }) =>
      client.get<KnowledgeExtract[]>('/knowledge', { params }),
    dismiss: (id: number) => client.post<{ id: number; dismissed: boolean }>(`/knowledge/${id}/dismiss`, {}),
    extractNow: () => client.post<{ started: boolean }>('/knowledge/extract-now', {}),
  },

  ollamaMetrics: {
    status: () => client.get<OllamaStatus>('/ollama-chat/status'),
    metrics: (window?: string) => client.get<OllamaMetrics>('/ollama-chat/metrics', { params: window ? { window } : {} }),
    recentCalls: (limit?: number) => client.get<OllamaCallLog[]>('/ollama-chat/recent-calls', { params: limit ? { limit } : {} }),
    reindex: () => client.post<{ indexed: number }>('/ollama-chat/reindex', {}),
  },

  migrations: {
    board: () => client.get<MigrationBoard>('/migrations/board'),
    list: () => client.get<MigrationProject[]>('/migrations'),
    patch: (id: number, data: Record<string, unknown>) => client.patch<MigrationProject>(`/migrations/${id}`, data),
    create: (data: Record<string, unknown>) => client.post<MigrationProject>('/migrations', data),
    initiate: (id: number) => client.post<MigrationProject>(`/migrations/${id}/initiate`, {}),
  },

  cancellations: {
    list: () => client.get<Cancellation[]>('/cancellations'),
    create: (data: Record<string, unknown>) => client.post<Cancellation>('/cancellations', data),
    update: (id: number, data: Record<string, unknown>) => client.patch<Cancellation>(`/cancellations/${id}`, data),
  },

  education: {
    gaps: () => client.get<TrainingGap[]>('/education/gaps'),
    sessions: () => client.get<TrainingSession[]>('/education/sessions'),
    stats: () => client.get<EducationStats>('/education/stats'),
    createSession: (data: Record<string, unknown>) => client.post<TrainingSession>('/education/sessions', data),
    trainingRecommendations: () => client.get<TrainingRecommendationsResult>('/education/training-recommendations'),
    refreshReleaseNotes: () => client.post<ReleaseNotesRefreshResult>('/education/refresh-release-notes', {}),
  },

  sso: {
    list: () => client.get<SSORecord[]>('/sso'),
    stats: () => client.get<SSOStats>('/sso/stats'),
    patch: (id: number, data: Record<string, unknown>) => client.patch<SSORecord>(`/sso/${id}`, data),
    logReply: (id: number, data: Record<string, unknown>) => client.post<SSORecord>(`/sso/${id}/log-reply`, data),
    create: (data: Record<string, unknown>) => client.post<SSORecord>('/sso', data),
    seed: () => client.post('/sso/seed', {}),
  },

  jira: {
    unmatched: () => client.get<JiraUnmatched[]>('/jira/unmatched'),
    assign: (jira_ref: string, data: Record<string, unknown>) =>
      client.post(`/jira/unmatched/${jira_ref}/assign`, data),
    dismiss: (jira_ref: string) =>
      client.delete(`/jira/unmatched/${jira_ref}`),
    poll: () => client.post<{ updated: number; skipped: number; errors: number }>('/jira/poll', {}),
  },

  auth: {
    me: () => client.get('/auth/me'),
  },

  snapshot: {
    brief: () => client.post<{ text: string; posted: boolean }>('/snapshot/brief', {}),
    full: () => client.post<{ text: string; posted: boolean }>('/snapshot/full', {}),
  },

  desk: {
    lanes: () => client.get<DeskLanes>('/desk/lanes'),
    queue: () => client.get<DeskQueue>('/desk/queue'),
    summary: () => client.get<DeskSummary>('/desk/summary'),
    team: (period?: DeskTeamPeriod, month?: string) =>
      client.get<DeskTeam>('/desk/team', { params: { ...(period ? { period } : {}), ...(month ? { month } : {}) } }),
    briefing: (since?: string, scope?: 'me' | 'team') =>
      client.get<DeskBriefing>('/desk/briefing', { params: { ...(since ? { since } : {}), ...(scope ? { scope } : {}) } }),
    dailySeries: (days?: number) => client.get<{ days: DailySeriesPoint[] }>('/desk/daily-series', { params: days ? { days } : {} }),
    dailyOps: (days?: number) => client.get<DailyOpsStats>('/desk/daily-ops', { params: days ? { days } : {} }),
  },

  supportSignals: {
    aging: () => client.get<AgingBuckets>('/support-signals/aging'),
    volume: () => client.get<{ accounts: VolumeAccount[] }>('/support-signals/volume'),
    exchanges: () => client.get<{ threshold: number; cases: ExchangeCase[] }>('/support-signals/exchanges'),
    resolved: () => client.get<ResolvedStats>('/support-signals/resolved'),
  },

  bugs: {
    list: () => client.get<VmsBug[]>('/bugs'),
    get: (ref: string) => client.get<VmsBug>(`/bugs/${ref}`),
    timeline: (ref: string) => client.get<BugTimelineEntry[]>(`/bugs/${ref}/timeline`),
    summarize: (ref: string) => client.post<{ summary: string | null; message?: string }>(`/bugs/${ref}/summarize`, {}),
    patch: (ref: string, data: Record<string, unknown>) => client.patch<VmsBug>(`/bugs/${ref}`, data),
  },

  commandCenter: {
    scorecard: (window: CommandWindow) => client.get<ScorecardStats>('/command-center/scorecard', { params: { window } }),
    schedule: (window: CommandWindow) => client.get<ScheduleStats>('/command-center/schedule', { params: { window } }),
    briefing: (window: CommandWindow) => client.get<BriefingStats>('/command-center/briefing', { params: { window } }),
    exportUrl: (window: CommandWindow) => `/api/command-center/export?window=${window}`,
  },
}
