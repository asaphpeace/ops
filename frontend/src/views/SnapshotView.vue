<template>
  <div class="view">
    <div class="sh">
      <div><h2>End of Day Snapshot</h2><p>Generated from live database state · {{ today }}</p></div>
      <div style="display:flex;gap:6px">
        <button class="btn btn-g btn-sm" @click="copyText">Copy as text</button>
        <button class="btn" @click="shareGisele">Share with Gisele</button>
      </div>
    </div>

    <div v-if="loading" class="info-bar">Generating snapshot from live data…</div>

    <div v-if="!loading" style="display:grid;grid-template-columns:1fr 1fr;gap:16px">
      <!-- Left: urgent items -->
      <div>
        <!-- SLA Breaching -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--red);margin-bottom:8px">
          🔴 SLA Breaching ({{ slaBreaching.length }})
        </div>
        <div v-if="!slaBreaching.length" style="color:var(--text3);font-size:11px;margin-bottom:12px">None — all cases within SLA.</div>
        <div v-for="c in slaBreaching" :key="c.id" class="jr jr-click" style="margin-bottom:4px" @click="openCase(c.jira_ref)">
          <a class="jref" :href="jiraUrl(c.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>↗ {{ c.jira_ref }}</a>
          <div style="flex:1">
            <div class="jtitle">{{ c.title }}</div>
            <div style="font-size:9px;color:var(--text3)">{{ c.customer_name }} · {{ c.days_open }}d open</div>
          </div>
          <span :class="['tier-badge', tierClass(c.customer_tier)]">{{ c.customer_tier }}</span>
        </div>

        <!-- Blocked upgrades -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--amber);margin-bottom:8px;margin-top:16px">
          ⊘ Blocked Upgrades ({{ blockedUpgrades.length }})
        </div>
        <div v-if="!blockedUpgrades.length" style="color:var(--text3);font-size:11px;margin-bottom:12px">None blocked.</div>
        <div v-for="u in blockedUpgrades" :key="u.id" class="jr" style="margin-bottom:4px">
          <a v-if="u.jira_ref" class="jref" :href="jiraUrl(u.jira_ref)" target="_blank" rel="noopener" title="Open in Jira">{{ u.jira_ref }}</a>
          <span v-else class="jref">—</span>
          <div style="flex:1">
            <div class="jtitle">{{ u.customer_name }} {{ u.environment }} → {{ u.to_version }}</div>
            <div style="font-size:9px;color:var(--amber)">{{ u.blocked_reason }}</div>
          </div>
          <span :class="['env-badge', envClass(u.environment)]">{{ u.environment }}</span>
        </div>

        <!-- Stalled migrations -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--amber);margin-bottom:8px;margin-top:16px">
          ⏸ Stalled Migrations ({{ stalledMigrations.length }})
        </div>
        <div v-if="!stalledMigrations.length" style="color:var(--text3);font-size:11px">None stalled.</div>
        <div v-for="m in stalledMigrations" :key="m.id" class="jr" style="margin-bottom:4px">
          <div style="flex:1">
            <div class="jtitle">{{ m.customer_name }}</div>
            <div style="font-size:9px;color:var(--amber)">Stalled {{ m.stalled_days }}d · {{ m.stage }} · {{ m.assignee ?? 'Unassigned' }}</div>
          </div>
          <span :class="['tier-badge', tierClass(m.customer_tier)]">{{ m.customer_tier }}</span>
        </div>
      </div>

      <!-- Right: activity + follow-ups -->
      <div>
        <!-- Awaiting DevOps / Customer -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:8px">
          📋 Awaiting Action ({{ awaitingAction.length }})
        </div>
        <div v-if="!awaitingAction.length" style="color:var(--text3);font-size:11px;margin-bottom:12px">Nothing pending.</div>
        <div v-for="c in awaitingAction" :key="c.id" class="jr jr-click" style="margin-bottom:4px" @click="openCase(c.jira_ref)">
          <a class="jref" :href="jiraUrl(c.jira_ref)" target="_blank" rel="noopener" title="Open in Jira" @click.stop>↗ {{ c.jira_ref }}</a>
          <div style="flex:1">
            <div class="jtitle">{{ c.title }}</div>
            <div style="font-size:9px;color:var(--text3)">{{ c.customer_name }}</div>
          </div>
          <span class="jst" style="color:var(--amber)">{{ c.status }}</span>
        </div>

        <!-- Training follow-ups -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:8px;margin-top:16px">
          🎓 Training Follow-ups ({{ followUpSessions.length }})
        </div>
        <div v-if="!followUpSessions.length" style="color:var(--text3);font-size:11px">No follow-ups pending.</div>
        <div v-for="s in followUpSessions" :key="s.id" class="jr" style="margin-bottom:4px">
          <div style="flex:1">
            <div class="jtitle">{{ s.customer_name }} · {{ s.topic_area }}</div>
            <div style="font-size:9px;color:var(--amber)">{{ s.follow_up_text }}</div>
          </div>
          <span style="font-size:9px;color:var(--text3)">{{ formatDate(s.session_date) }}</span>
        </div>

        <!-- Active pipeline count -->
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:8px;margin-top:16px">
          📊 Today's Numbers
        </div>
        <div style="display:flex;flex-direction:column;gap:4px">
          <div class="fr">Active cases <span style="color:var(--text)">{{ triage?.total_active ?? '—' }}</span></div>
          <div class="fr">SLA breaching <span style="color:var(--red)">{{ triage?.sla_breaching ?? '—' }}</span></div>
          <div class="fr">Awaiting dev <span style="color:var(--amber)">{{ triage?.awaiting_dev ?? '—' }}</span></div>
          <div class="fr">Awaiting customer <span style="color:var(--amber)">{{ triage?.awaiting_customer ?? '—' }}</span></div>
          <div class="fr">Resolved today <span style="color:var(--green)">{{ triage?.resolved_today ?? '—' }}</span></div>
        </div>
      </div>
    </div>

    <!-- Copied toast -->
    <div v-if="copied" style="position:fixed;bottom:20px;left:50%;transform:translateX(-50%);background:var(--green);color:#000;font-size:11px;font-weight:700;padding:7px 16px;border-radius:6px;z-index:1000">
      ✓ Copied to clipboard
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, jiraUrl, type Case, type Upgrade, type TrainingSession, type TriageStats, type MigrationProject } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'

const { openCase } = useCaseDrill()

const cases = ref<Case[]>([])
const upgrades = ref<Upgrade[]>([])
const sessions = ref<TrainingSession[]>([])
const migrations = ref<MigrationProject[]>([])
const triage = ref<TriageStats | null>(null)
const loading = ref(true)
const copied = ref(false)

onMounted(async () => {
  try {
    const [cRes, uRes, sRes, mRes, tRes] = await Promise.all([
      api.cases.list(),
      api.upgrades.list(),
      api.education.sessions(),
      api.migrations.list(),
      api.cases.triage(),
    ])
    cases.value = cRes.data
    upgrades.value = uRes.data
    sessions.value = sRes.data
    migrations.value = mRes.data
    triage.value = tRes.data
  } finally {
    loading.value = false
  }
})

const slaBreaching = computed(() =>
  cases.value.filter(c =>
    c.sla_days && c.days_open > c.sla_days && c.status !== 'Closed'
  )
)

const blockedUpgrades = computed(() =>
  upgrades.value.filter(u => u.blocked && u.stage !== 'Verified Done')
)

const stalledMigrations = computed(() =>
  migrations.value.filter(m => m.stalled)
)

const awaitingAction = computed(() =>
  cases.value.filter(c =>
    (c.status === 'Awaiting DevOps' || c.status === 'Awaiting Customer') && c.status !== 'Closed'
  )
)

const followUpSessions = computed(() =>
  sessions.value.filter(s => s.follow_up_needed)
)

const today = computed(() =>
  new Date().toLocaleDateString('en-GB', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' })
)

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short' })
}

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

function envClass(e: string) {
  return e === 'PROD' ? 'ep' : e === 'TEST' ? 'et' : 'ed'
}

function snapshotLines(): string[] {
  return [
    `SEDNA OPS SNAPSHOT — ${today.value}`,
    '',
    `SLA BREACHING (${slaBreaching.value.length}):`,
    ...slaBreaching.value.map(c => `  • ${c.jira_ref} — ${c.title} [${c.customer_name}, ${c.days_open}d open]`),
    '',
    `BLOCKED UPGRADES (${blockedUpgrades.value.length}):`,
    ...blockedUpgrades.value.map(u => `  • ${u.jira_ref ?? '—'} — ${u.customer_name} ${u.environment} → ${u.to_version} [${u.blocked_reason}]`),
    '',
    `STALLED MIGRATIONS (${stalledMigrations.value.length}):`,
    ...stalledMigrations.value.map(m => `  • ${m.customer_name} [${m.stage}, stalled ${m.stalled_days}d, assignee: ${m.assignee ?? 'None'}]`),
    '',
    `TRAINING FOLLOW-UPS (${followUpSessions.value.length}):`,
    ...followUpSessions.value.map(s => `  • ${s.customer_name} — ${s.topic_area}: ${s.follow_up_text}`),
    '',
    `NUMBERS: ${triage.value?.total_active ?? '?'} active · ${triage.value?.sla_breaching ?? '?'} SLA breaching · ${triage.value?.awaiting_dev ?? '?'} awaiting dev · ${triage.value?.resolved_today ?? '?'} resolved today`,
  ]
}

async function copyText() {
  try {
    await navigator.clipboard.writeText(snapshotLines().join('\n'))
    copied.value = true
    setTimeout(() => { copied.value = false }, 2500)
  } catch { /* clipboard blocked */ }
}

function shareGisele() {
  const text = snapshotLines().join('\n')
  const subject = encodeURIComponent(`Sedna Ops Snapshot — ${today.value}`)
  const body = encodeURIComponent(text)
  window.open(`mailto:?subject=${subject}&body=${body}`, '_blank')
}
</script>
