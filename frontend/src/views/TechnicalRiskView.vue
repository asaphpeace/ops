<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Migration Priority</h2>
        <p>Infrastructure, incident, and defect exposure combined per customer — rule-based, not AI-computed. Framed as a bundling opportunity: who benefits most from doing the migration, upgrade, and incident remediation together in one window. Every number here is drillable — click a count to see the actual cases/bugs behind it.</p>
      </div>
    </div>

    <div v-if="loading" class="sub" style="font-size:11px;color:var(--text3)">Loading…</div>
    <div v-else-if="!result || !result.customers.length" class="sub" style="font-size:11px;color:var(--text3);text-align:center;padding:32px 0">No customers with enough real tenant data to rank yet.</div>

    <template v-else>
      <div class="mp-list">
        <div v-for="c in result.customers" :key="c.customer_id" class="tw mp-card">
          <div class="mp-head">
            <span class="mp-score" :title="scoreTitle(c)">{{ c.priority_score }}</span>
            <span style="font-size:12px;font-weight:700;color:var(--text);cursor:pointer" @click="openEngineeringCustomer(c.customer_id)">{{ c.customer_name }}</span>
            <span :class="['tier-badge', tierClass(c.customer_tier)]">{{ c.customer_tier }}</span>
            <span class="flag-pill" :style="c.infra === 'Old' ? 'background:var(--amber-dim);color:var(--amber)' : 'background:var(--surface2);color:var(--text3)'">{{ c.infra }} infra</span>
            <span
              class="flag-pill"
              :style="c.migration_tracked ? 'background:var(--surface2);color:var(--text3)' : 'background:var(--surface3);color:var(--text3);font-style:italic'"
              :title="c.migration_tracked ? 'A real migration project exists for this customer' : 'No migration project has ever been created for this customer — not the same as \'assessed and not yet begun\''"
            >{{ c.migration_stage }}{{ !c.migration_tracked ? ' (untracked)' : '' }}</span>
          </div>

          <div class="mp-detail">
            <span class="sub" style="font-size:10.5px;color:var(--text3)">
              {{ c.current_version }}<template v-if="c.is_behind_latest"> → {{ c.latest_version }} (behind)</template>
            </span>

            <span
              v-if="c.pending_upgrade_defect_count"
              class="flag-pill mp-click"
              style="background:var(--red-dim);color:var(--red)"
              title="Real defects this customer reported, already fixed, sitting undelivered pending their upgrade — click to see each one"
              @click="toggleExpanded(c.customer_id, 'defects')"
            >{{ c.pending_upgrade_defect_count }} real fix{{ c.pending_upgrade_defect_count === 1 ? '' : 'es' }} owed {{ expanded === mpKey(c.customer_id, 'defects') ? '▾' : '▸' }}</span>

            <span
              v-if="c.theoretical_exposure_count"
              class="flag-pill mp-click"
              style="background:var(--surface2);color:var(--text3)"
              title="Other known, already-shipped fixes this customer hasn't personally reported — a fleet-safety signal, not a confirmed personal impact. Excluded from the priority score."
              @click="toggleExpanded(c.customer_id, 'theoretical')"
            >+{{ c.theoretical_exposure_count }} other known fix{{ c.theoretical_exposure_count === 1 ? '' : 'es' }} not reported {{ expanded === mpKey(c.customer_id, 'theoretical') ? '▾' : '▸' }}</span>

            <span
              v-for="inc in c.open_incident_remediations" :key="inc.incident_id" class="flag-pill mp-click"
              :style="severityStyle(inc.severity)" :title="`Severity: ${inc.severity} — click to open Platform Incidents`"
              @click="router.push('/tools?tab=incidents')"
            >⚠ {{ inc.severity }} · {{ inc.title }}</span>
          </div>

          <div v-if="expanded === mpKey(c.customer_id, 'defects')" class="mp-drill">
            <div v-for="d in c.pending_upgrade_defects" :key="d.vms_ref" class="mp-drill-row">
              <span class="jref" @click="openCase(d.case_jira_ref)">{{ d.case_jira_ref }}</span>
              <span class="sub" style="color:var(--text2)">{{ d.case_title }}</span>
              <span class="jref" style="margin-left:auto" @click="openBug(d.vms_ref)">{{ d.vms_ref }}</span>
              <span class="sub" style="color:var(--text3)">fixed in {{ d.fix_version }}</span>
            </div>
          </div>

          <div v-if="expanded === mpKey(c.customer_id, 'theoretical')" class="mp-drill">
            <div v-for="b in c.theoretical_exposure" :key="b.vms_ref" class="mp-drill-row">
              <span class="jref" @click="openBug(b.vms_ref)">{{ b.vms_ref }}</span>
              <span class="sub" style="color:var(--text3);margin-left:auto">fixed in {{ b.fix_version }}</span>
            </div>
          </div>

          <div v-if="narrationFor(c.customer_id)" class="sub mp-narration">🤖 {{ narrationFor(c.customer_id) }}</div>
        </div>
      </div>

      <div class="sub" style="font-size:10px;color:var(--text3);margin-top:12px;text-align:center">
        {{ result.covered_count }} of {{ result.vms_customer_count }} real VMS customers have enough tenant data on file to appear here.
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { api, type MigrationPriorityResult, type MigrationPriorityItem, type AiObservation } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useBugDrill } from '@/composables/useBugDrill'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const router = useRouter()
const { openCase } = useCaseDrill()
const { openBug } = useBugDrill()
const { openEngineeringCustomer } = useEngineeringDrill()

const loading = ref(true)
const result = ref<MigrationPriorityResult | null>(null)
const observations = ref<AiObservation[]>([])
const expanded = ref<string | null>(null)

function mpKey(customerId: number, section: 'defects' | 'theoretical') {
  return `${customerId}:${section}`
}
function toggleExpanded(customerId: number, section: 'defects' | 'theoretical') {
  const key = mpKey(customerId, section)
  expanded.value = expanded.value === key ? null : key
}

function tierClass(tier?: string | null) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}

function severityStyle(severity: string) {
  if (severity === 'Critical') return 'background:var(--red-dim);color:var(--red)'
  if (severity === 'High') return 'background:var(--amber-dim);color:var(--amber)'
  return 'background:var(--surface2);color:var(--text3)'
}

function scoreTitle(c: MigrationPriorityItem) {
  const b = c.score_breakdown
  return `tier ${b.tier_weight} + infra ${b.infra_weight} + incident severity ${b.incident_severity_weight} + real defects (capped) ${b.defect_weight} = ${c.priority_score}`
}

function narrationFor(customerId: number): string | null {
  const obs = observations.value.find(o => o.kind === 'migration_priority' && o.customer_id === customerId)
  return obs ? obs.summary : null
}

onMounted(async () => {
  loading.value = true
  try {
    const res = await api.migrationPriority.get()
    result.value = res.data
    try {
      const obsRes = await api.aiObservations.list()
      observations.value = obsRes.data
    } catch { /* Ollama observations are optional — the ranked list works without them */ }
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.mp-list { display: flex; flex-direction: column; gap: 8px; }
.mp-card { padding: 12px 14px; }
.mp-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.mp-score {
  display: inline-flex; align-items: center; justify-content: center;
  min-width: 24px; height: 24px; padding: 0 6px; border-radius: 6px;
  background: var(--accent-dim); color: var(--accent); font-size: 12px; font-weight: 800;
  cursor: help;
}
.mp-detail { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; margin-top: 8px; }
.mp-click { cursor: pointer; }
.mp-drill { margin-top: 8px; padding: 8px 9px; background: var(--surface2); border-radius: 6px; display: flex; flex-direction: column; gap: 5px; }
.mp-drill-row { display: flex; align-items: center; gap: 8px; font-size: 10.5px; flex-wrap: wrap; }
.mp-narration { font-size: 10.5px; color: var(--text2); margin-top: 8px; padding: 7px 9px; background: var(--surface2); border-radius: 6px; }
</style>
