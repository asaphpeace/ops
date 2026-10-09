<template>
  <div class="cp-grid">
    <!-- Why upgrade -->
    <div class="tw cp-card">
      <div class="cp-card-head">
        <div class="md-eyebrow" style="margin:0">Why upgrade</div>
        <RouterLink to="/engineering?tab=technical-risk" class="jref">Technical Risk →</RouterLink>
      </div>
      <div v-if="techLoading" class="cp-muted">Loading…</div>
      <div v-else-if="!risk" class="cp-muted">Not enough tenant data on file for a Technical Risk score yet.</div>
      <template v-else>
        <div class="cp-risk-head">
          <span class="cp-risk-score">{{ risk.priority_score }}</span>
          <span class="cp-muted">risk score</span>
          <span class="cp-push cp-mono" :class="risk.is_behind_latest ? 'warn' : 'ok'">
            {{ risk.current_version || '?' }} → latest {{ risk.latest_version || '?' }}
          </span>
        </div>
        <div v-for="f in riskFactors" :key="f.label" class="cp-risk-bar">
          <div class="cp-risk-lbl"><span>{{ f.label }}</span><span>{{ f.value }}</span></div>
          <div class="cp-risk-track"><div class="cp-risk-fill" :style="{ width: `${Math.min(f.value / f.max * 100, 100)}%` }"></div></div>
        </div>
        <template v-if="path.length">
          <div class="md-eyebrow cp-gap">Upgrade path</div>
          <div class="cp-path">
            <span>{{ risk.current_version || '?' }}</span>
            <span class="cp-muted">→</span>
            <button v-if="path.length > 1" class="cp-link" @click="showPath = !showPath">{{ path.length - 1 }} release{{ path.length === 2 ? '' : 's' }} between</button>
            <span v-if="path.length > 1" class="cp-muted">→</span>
            <span class="ok">{{ path[path.length - 1] }}</span>
          </div>
          <div v-if="showPath" class="cp-path cp-gap-sm">
            <span v-for="v in path" :key="v" class="cp-chip">{{ v }}</span>
          </div>
        </template>
        <template v-if="risk.pending_upgrade_defects.length">
          <div class="md-eyebrow cp-gap">Fixed by upgrading</div>
          <div v-for="d in risk.pending_upgrade_defects" :key="d.vms_ref + d.case_jira_ref" class="cp-topic">
            <span class="jref" @click="openCase(d.case_jira_ref)">{{ d.case_jira_ref }}</span>
            <span class="cp-case-title">{{ d.case_title }}</span>
            <span class="cp-muted cp-push">{{ d.vms_ref }}{{ d.fix_version ? ` · ${d.fix_version}` : '' }}</span>
          </div>
        </template>
        <template v-if="tech!.peer_customers.length">
          <div class="md-eyebrow cp-gap">Peers in the same position</div>
          <div class="cp-chips">
            <button v-for="p in tech!.peer_customers.slice(0, 12)" :key="p.id" class="btn btn-g btn-sm" @click="openCustomer(p.id)">{{ p.name }}</button>
          </div>
        </template>
      </template>
    </div>

    <!-- Scheduling constraints -->
    <div class="tw cp-card">
      <div class="md-eyebrow">Scheduling constraints</div>
      <div class="cp-fact"><span>Upgrade allowance</span><b :class="usageTone(customer.upgrades_used, customer.upgrades_limit)">{{ customer.upgrades_used }} / {{ customer.upgrades_limit }} used</b></div>
      <div class="cp-fact">
        <span>After-hours</span>
        <b :class="customer.after_hours_eligible ? usageTone(customer.after_hours_used, customer.after_hours_limit) : 'cp-muted'">
          {{ customer.after_hours_eligible ? `${customer.after_hours_used} / ${customer.after_hours_limit} used this year` : 'Not eligible' }}
        </b>
      </div>
      <div class="cp-fact"><span>Preferred days</span><b>{{ customer.pref_days || 'not on record' }}</b></div>
      <div class="cp-fact"><span>Notice required</span><b>{{ customer.notice_required || 'not on record' }}</b></div>
      <div class="cp-fact"><span>Blackout periods</span><b :class="{ warn: hasBlackout }">{{ customer.blackout_periods || 'not on record' }}</b></div>
      <RouterLink to="/operations?tab=runner" class="btn btn-sm cp-gap" style="display:inline-block;text-decoration:none">Run an upgrade →</RouterLink>
    </div>
  </div>

  <!-- Projects -->
  <div class="cp-grid cp-gap">
    <div class="tw cp-card">
      <div class="md-eyebrow">Migration project</div>
      <div v-if="!migration" class="cp-muted">No migration project on record.</div>
      <template v-else>
        <div class="cp-fact"><span>Stage</span><b>{{ migration.stage }}</b></div>
        <div class="cp-fact"><span>Assignee</span><b>{{ migration.assignee ?? 'Unassigned' }}</b></div>
        <div class="cp-fact"><span>Complexity</span><b>{{ migration.complexity }}</b></div>
        <div class="cp-fact"><span>IP/FW required</span><b :class="{ bad: migration.ip_fw }">{{ migration.ip_fw ? 'Yes' : 'No' }}</b></div>
        <div class="cp-fact"><span>Needs upgrade first</span><b :class="{ warn: migration.requires_upgrade }">{{ migration.requires_upgrade ? 'Yes' : 'No' }}</b></div>
        <div class="cp-fact"><span>Stalled</span><b :class="{ bad: migration.stalled }">{{ migration.stalled ? `Yes — ${migration.stalled_days}d` : 'No' }}</b></div>
        <div v-if="migration.downtime_agreed_at" class="cp-fact"><span>Downtime agreed</span><b>{{ fmtDate(migration.downtime_agreed_at) }}</b></div>
        <div v-if="migration.completed_at" class="cp-fact"><span>Completed</span><b class="ok">{{ fmtDate(migration.completed_at) }}</b></div>
        <div v-if="migration.integration_notes" class="cp-notebox">{{ migration.integration_notes }}</div>
      </template>
    </div>

    <div class="tw cp-card">
      <div class="md-eyebrow">SSO onboarding</div>
      <div v-if="!sso" class="cp-muted">No SSO onboarding on record.</div>
      <template v-else>
        <div class="cp-fact"><span>Stage</span><b>{{ sso.display_stage }}</b></div>
        <div class="cp-fact"><span>Environments</span><b>{{ [sso.has_prod && 'PROD', sso.has_test && 'TEST'].filter(Boolean).join(' + ') || '—' }}</b></div>
        <div class="cp-fact"><span>IT contact</span><b>{{ sso.it_contact_name ?? '—' }}<span v-if="sso.it_contact_email" class="cp-muted"> · {{ sso.it_contact_email }}</span></b></div>
        <div v-if="sso.email_sent_at" class="cp-fact"><span>Email sent</span><b>{{ fmtDate(sso.email_sent_at) }}</b></div>
        <div class="cp-fact"><span>Guest invite sent</span><b :class="{ ok: sso.guest_invite_sent }">{{ sso.guest_invite_sent ? 'Yes' : 'No' }}</b></div>
        <div v-if="sso.reply_received_at" class="cp-fact"><span>Reply received</span><b class="ok">{{ fmtDate(sso.reply_received_at) }}</b></div>
        <div v-if="sso.field_domain" class="cp-fact"><span>Domain</span><b>{{ sso.field_domain }}</b></div>
        <div v-if="sso.field_client_id" class="cp-fact"><span>Client ID</span><b class="cp-mono">{{ sso.field_client_id }}</b></div>
        <div v-if="sso.field_app_id_uri" class="cp-fact"><span>App ID URI</span><b class="cp-mono">{{ sso.field_app_id_uri }}</b></div>
        <div v-if="sso.devops_started_at" class="cp-fact"><span>DevOps started</span><b>{{ fmtDate(sso.devops_started_at) }}</b></div>
        <div v-if="sso.switchover_at" class="cp-fact"><span>Switchover</span><b>{{ fmtDate(sso.switchover_at) }}<template v-if="sso.switchover_duration_mins"> · {{ sso.switchover_duration_mins }} min</template></b></div>
        <div v-if="sso.follow_up_date" class="cp-fact"><span>Follow-up due</span><b class="warn">{{ fmtDate(sso.follow_up_date) }}</b></div>
        <div v-if="sso.overdue_days" class="cp-fact"><span>Overdue</span><b class="bad">{{ sso.overdue_days }}d</b></div>
        <div v-if="sso.notes" class="cp-notebox">{{ sso.notes }}</div>
      </template>
    </div>
  </div>
  <!-- Upgrade history -->
  <div class="tw cp-gap">
    <div class="ttb"><span class="md-eyebrow" style="margin:0">Upgrade history</span><span class="cp-muted">{{ upgrades.length }}</span></div>
    <div v-if="upgrades.length" class="cp-scroll-x">
    <table>
      <thead><tr><th>Env</th><th>Version</th><th>Type</th><th>Stage</th><th>Scheduled</th><th>Done</th><th>Ticket</th></tr></thead>
      <tbody>
        <tr v-for="u in shownUpgrades" :key="u.id">
          <td><span class="cp-env" :class="u.environment.toLowerCase()">{{ u.environment }}</span></td>
          <td class="cp-mono cp-nowrap">{{ u.from_version || '?' }} → {{ u.to_version }}</td>
          <td>{{ u.upgrade_type }}</td>
          <td>{{ u.stage }}<div v-if="u.blocked" class="cp-bad-text">⊘ {{ u.blocked_reason }}</div></td>
          <td class="cp-nowrap">{{ u.scheduled_at ? fmtDateTime(u.scheduled_at) : '—' }}</td>
          <td class="cp-nowrap">{{ u.date_done ? fmtDate(u.date_done) : '—' }}</td>
          <td><span v-if="u.jira_ref" class="jref" @click="openCase(u.jira_ref!)">{{ u.jira_ref }}</span><span v-else>—</span></td>
        </tr>
      </tbody>
    </table>
    </div>
    <div v-else class="cp-muted cp-card">No upgrades on record.</div>
    <div v-if="upgrades.length > HISTORY_PREVIEW" class="cp-card" style="padding-top:8px;padding-bottom:10px">
      <button class="cp-link" @click="showAllHistory = !showAllHistory">{{ showAllHistory ? 'Show recent only' : `Show all ${upgrades.length}` }}</button>
    </div>
  </div>

</template>

<script setup lang="ts">
// What's changing for this customer, and what constrains it? Upgrades,
// the reasons to do one (Technical Risk), the constraints that apply when
// scheduling, and the two change projects (migration, SSO onboarding).
// Current per-environment versions live in Connectivity, not repeated here.
import { ref, computed, watch } from 'vue'
import { api, type Customer, type Upgrade, type MigrationProject, type SSORecord, type CustomerTechnical } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'
import { fmtDate, fmtDateTime, usageTone, versionAtLeast } from './profileUtils'

const props = defineProps<{ customer: Customer; tech: CustomerTechnical | null; techLoading: boolean }>()
const { openCase } = useCaseDrill()
const { openCustomer } = useCustomerDrill()

const upgrades = ref<Upgrade[]>([])
const migration = ref<MigrationProject | null>(null)
const sso = ref<SSORecord | null>(null)

const risk = computed(() => props.tech?.risk ?? null)
const riskFactors = computed(() => {
  const b = risk.value?.score_breakdown
  if (!b) return []
  return [
    { label: 'Tier weight', value: b.tier_weight, max: 3 },
    { label: 'Infra weight', value: b.infra_weight, max: 2 },
    { label: 'Incident severity', value: b.incident_severity_weight, max: 4 },
    { label: 'Defect weight', value: b.defect_weight, max: 5 },
  ]
})
// The engineering endpoint returns every release it knows of, unordered —
// sort them and keep only what's newer than the current PROD version.
const showPath = ref(false)
const path = computed(() => {
  const current = risk.value?.current_version
  const cmp = (a: string, b: string) => (versionAtLeast(a, (b.match(/\d+/g) ?? []).map(Number)) ? (a === b ? 0 : 1) : -1)
  return [...new Set(props.tech?.upgrade_path ?? [])]
    .filter(v => !current || (versionAtLeast(v, (current.match(/\d+/g) ?? []).map(Number)) && v !== current))
    .sort(cmp)
})
const HISTORY_PREVIEW = 10
const showAllHistory = ref(false)
const shownUpgrades = computed(() => (showAllHistory.value ? upgrades.value : upgrades.value.slice(0, HISTORY_PREVIEW)))
const hasBlackout = computed(() => !!props.customer.blackout_periods && props.customer.blackout_periods !== 'None')

async function load() {
  const id = props.customer.id
  const [u, m, s] = await Promise.all([
    api.upgrades.list({ customer_id: String(id) }), api.migrations.list(), api.sso.list(),
  ])
  upgrades.value = u.data.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  migration.value = m.data.find(x => x.customer_id === id) ?? null
  sso.value = s.data.find(x => x.customer_id === id) ?? null
}
watch(() => props.customer.id, load, { immediate: true })
</script>
