<template>
  <div :class="['overlay', target ? 'open' : '']" @click="closeEngineeringPanel"></div>
  <div :class="['eng-panel', target ? 'open' : '']" v-if="target">
    <div v-if="loading" class="eng-h">
      <button class="cbx" @click="closeEngineeringPanel">✕</button>
      <div class="sub" style="font-size:11px">Loading…</div>
    </div>

    <template v-else-if="customerData">
      <div class="eng-h">
        <button class="cbx" @click="closeEngineeringPanel">✕</button>
        <div class="eng-kicker">{{ customerData.kicker }}</div>
        <div class="eng-title">{{ customerData.title }}</div>
        <div class="sub eng-sub">{{ customerData.sub }}</div>
      </div>

      <div class="eng-body">
        <!-- Customer Reports (triage) -->
        <div class="eng-section" :style="{ borderLeftColor: customerData.triage.color }">
          <div class="eng-eyebrow">Customer reports</div>
          <div class="eng-verdict">{{ customerData.triage.verdict }}</div>
          <div v-for="(c, i) in customerData.triage.checks" :key="i" class="eng-check">
            <span :style="{ color: c.color }">{{ c.mark }}</span>
            <span :style="{ color: c.color }" style="font-weight:600">{{ c.label }}</span>
            <span class="sub eng-check-detail">{{ c.detail }}</span>
          </div>
        </div>

        <!-- Environments side by side -->
        <div>
          <div class="eng-h3-row"><span class="eng-h3">Environments side by side</span><span class="sub eng-h3-note">{{ customerData.drift.note }}</span></div>
          <div class="eng-drift">
            <div class="eng-drift-grid eng-drift-head">
              <div></div><div>PROD</div><div>TEST</div><div>DEV</div>
            </div>
            <div v-for="row in customerData.drift.rows" :key="row.label" class="eng-drift-grid eng-drift-row">
              <div class="sub">{{ row.label }}</div>
              <div v-for="env in ['PROD','TEST','DEV']" :key="env" class="eng-drift-cell">{{ row.cells[env] ?? '—' }}</div>
            </div>
          </div>
        </div>

        <!-- Load profile -->
        <div v-if="!customerData.load_available" class="eng-load-unavailable sub">
          Load profile vs. baseline — no application-level metrics import exists yet for this account.
        </div>

        <!-- What changed -->
        <div>
          <div class="eng-h3-row"><span class="eng-h3">What changed</span><span class="sub eng-h3-note">deploys, upgrades and config against incidents</span></div>
          <div v-for="(t, i) in customerData.timeline" :key="i" class="eng-timeline-row">
            <span class="eng-mono sub">{{ t.when }}</span>
            <span :style="{ color: t.color }">{{ t.mark }}</span>
            <div>
              <div style="font-size:12.5px">{{ t.what }}</div>
              <div v-if="t.link" class="sub" style="font-size:10.5px">{{ t.link }}</div>
            </div>
          </div>
          <div v-if="!customerData.timeline.length" class="sub" style="font-size:11px">No recent change history on file.</div>
        </div>

        <!-- Incident & case history -->
        <div>
          <div class="eng-h3-row"><span class="eng-h3">Incident & case history</span><span class="sub eng-h3-note">{{ customerData.repeat }}</span></div>
          <div v-for="(h, i) in customerData.history" :key="i" class="eng-history-row">
            <span class="sub">{{ h.when }}</span>
            <span class="eng-mono" style="color:var(--accent)">{{ h.ref }}</span>
            <span style="font-size:12px">{{ h.what }}</span>
            <span :style="{ color: h.color }" style="text-align:right;font-size:11px">{{ h.state }}</span>
          </div>
          <div v-if="!customerData.history.length" class="sub" style="font-size:11px">No incident or case history on file.</div>
        </div>

        <!-- Technical risk -->
        <div v-if="customerData.risk" class="eng-section" :style="{ borderLeftColor: riskColor(customerData.risk.priority_score) }">
          <div style="display:flex;align-items:baseline;gap:8px">
            <span class="eng-eyebrow" style="margin-bottom:0">Technical risk · production</span>
            <span style="font-weight:700;font-size:14px" :style="{ color: riskColor(customerData.risk.priority_score) }">{{ riskLabel(customerData.risk.priority_score) }}</span>
            <span class="sub" style="margin-left:auto;font-size:11px">{{ customerData.risk.priority_score }} / 100</span>
          </div>
          <div class="cd-risk-bars" style="margin-top:10px">
            <div v-for="f in riskFactorList(customerData.risk)" :key="f.label" class="cd-risk-bar">
              <div style="display:flex;justify-content:space-between;font-size:10.5px"><span class="sub">{{ f.label }}</span><span>{{ f.value }}</span></div>
              <div class="cd-risk-track"><div class="cd-risk-fill" :style="{ width: `${Math.min(f.value / f.max * 100, 100)}%` }"></div></div>
            </div>
          </div>
          <div class="sub" style="font-size:10.5px;margin-top:8px">Score is the sum of these factors — no black box.</div>
        </div>

        <!-- Blocks -->
        <div v-for="b in customerData.blocks" :key="b.title">
          <div class="eng-h3" style="margin-bottom:8px">{{ b.title }}</div>
          <div v-for="r in b.rows" :key="r.k" class="eng-block-row">
            <span class="sub eng-block-k">{{ r.k }}</span>
            <span :style="r.color ? { color: r.color } : {}" style="font-size:12.5px;flex:1">{{ r.v }}</span>
          </div>
        </div>

        <!-- Known issues & runbooks -->
        <div v-if="customerData.knowledge.length">
          <div class="eng-h3" style="margin-bottom:8px">Known issues & runbooks for this customer</div>
          <div v-for="(k, i) in displayedKnowledge" :key="i" class="eng-know-row" @click="k.kind === 'Known issue' ? openEngineeringDefect(k.what) : undefined">
            <span :style="{ color: k.color }" style="font-size:10.5px;min-width:74px">{{ k.kind }}</span>
            <span style="font-size:12.5px;flex:1">{{ k.what }}</span>
            <span class="sub" style="font-size:10.5px">{{ k.meta }}</span>
          </div>
          <div v-if="customerData.knowledge.length > knowledgeLimit" class="eng-show-more" @click="knowledgeExpanded = !knowledgeExpanded">
            {{ knowledgeExpanded ? 'Show fewer' : `Show all ${customerData.knowledge.length}` }}
          </div>
        </div>

        <!-- Connected -->
        <div v-if="customerData.connected_defects.length || customerData.peer_customers.length">
          <div class="eng-h3" style="margin-bottom:8px">Connected</div>
          <div v-if="customerData.connected_defects.length" style="display:flex;flex-wrap:wrap;gap:5px;margin-bottom:8px">
            <button v-for="d in customerData.connected_defects.slice(0, 20)" :key="d.vms_ref" class="eng-chip" :class="{ dim: !d.reported }" @click="openEngineeringDefect(d.vms_ref)">
              {{ d.vms_ref }}<span v-if="!d.reported" class="sub" style="font-size:8.5px"> (exposed)</span>
            </button>
            <span v-if="customerData.connected_defects.length > 20" class="sub" style="font-size:10px;align-self:center">+{{ customerData.connected_defects.length - 20 }} more</span>
          </div>
          <div v-if="customerData.peer_customers.length" style="display:flex;flex-wrap:wrap;gap:5px">
            <button v-for="p in customerData.peer_customers.slice(0, 12)" :key="p.id" class="eng-chip" @click="openEngineeringCustomer(p.id)">{{ p.name }}</button>
          </div>
        </div>
      </div>
    </template>

    <template v-else-if="defectData">
      <div class="eng-h">
        <button class="cbx" @click="closeEngineeringPanel">✕</button>
        <div class="eng-kicker">{{ defectData.kicker }}</div>
        <div class="eng-title">{{ defectData.title }}</div>
        <div class="sub eng-sub">{{ defectData.sub }}</div>
      </div>

      <div class="eng-body">
        <div>
          <div class="eng-h3" style="margin-bottom:8px">Impact chain</div>
          <div v-for="(c, i) in defectData.chain" :key="i" class="eng-chain-card" :style="{ borderLeftColor: c.color }">
            <span class="eng-chain-count">{{ c.count }}</span>
            <div>
              <div style="font-size:13px">{{ c.label }}</div>
              <div class="sub" style="font-size:11px">{{ c.detail }}</div>
            </div>
          </div>
        </div>

        <div v-if="defectData.affected_customers.length">
          <div class="eng-h3" style="margin-bottom:8px">Exposed customers — open the 360</div>
          <div style="display:flex;flex-wrap:wrap;gap:5px">
            <button v-for="c in defectData.affected_customers" :key="c.id" class="eng-chip" @click="openEngineeringCustomer(c.id)">{{ c.name }}</button>
          </div>
        </div>

        <div style="display:flex;flex-wrap:wrap;gap:6px">
          <RouterLink to="/engineering?tab=logs" class="btn btn-g btn-sm" style="text-decoration:none">Search logs for this signature</RouterLink>
          <RouterLink to="/engineering?tab=matrix" class="btn btn-g btn-sm" style="text-decoration:none">Filter matrix to exposed rows</RouterLink>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api, type EngineeringCustomerPanel, type EngineeringDefectPanel, type CustomerTechnicalRisk } from '@/api/client'
import { useEngineeringDrill } from '@/composables/useEngineeringDrill'

const { target, openEngineeringCustomer, openEngineeringDefect, closeEngineeringPanel } = useEngineeringDrill()

const loading = ref(false)
const customerData = ref<EngineeringCustomerPanel | null>(null)
const defectData = ref<EngineeringDefectPanel | null>(null)
const knowledgeExpanded = ref(false)
const knowledgeLimit = 8

const displayedKnowledge = computed(() => {
  if (!customerData.value) return []
  return knowledgeExpanded.value ? customerData.value.knowledge : customerData.value.knowledge.slice(0, knowledgeLimit)
})

function riskLabel(score: number): string {
  if (score >= 70) return 'Critical'
  if (score >= 48) return 'High'
  if (score >= 26) return 'Medium'
  return 'Low'
}
function riskColor(score: number): string {
  if (score >= 70) return 'var(--red)'
  if (score >= 48) return 'var(--amber)'
  if (score >= 26) return 'var(--accent)'
  return 'var(--green)'
}
function riskFactorList(r: CustomerTechnicalRisk) {
  const b = r.score_breakdown
  return [
    { label: 'Tier weight', value: b.tier_weight, max: 3 },
    { label: 'Infra weight', value: b.infra_weight, max: 2 },
    { label: 'Incident severity', value: b.incident_severity_weight, max: 4 },
    { label: 'Defect weight', value: b.defect_weight, max: 5 },
  ]
}

watch(target, async (t) => {
  knowledgeExpanded.value = false
  customerData.value = null
  defectData.value = null
  if (!t) return
  loading.value = true
  try {
    if (t.kind === 'customer') {
      const res = await api.engineering.customerPanel(t.id, t.focusEnv)
      customerData.value = res.data
    } else {
      const res = await api.engineering.defectPanel(t.vmsRef)
      defectData.value = res.data
    }
  } finally {
    loading.value = false
  }
}, { immediate: true })
</script>

<style scoped>
.eng-panel { display: none; position: fixed; top: 0; right: 0; bottom: 0; width: min(820px, 100%); background: var(--surface); border-left: 1px solid var(--border); z-index: 200; overflow-y: auto; box-shadow: -24px 0 60px rgba(0, 0, 0, .6); }
.eng-panel.open { display: block; }
.eng-h { padding: 18px 22px; border-bottom: 1px solid var(--border); position: sticky; top: 0; background: var(--surface); z-index: 10; }
.eng-kicker { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: var(--accent); }
.eng-title { font-size: 20px; font-weight: 700; line-height: 1.2; margin-top: 3px; }
.eng-sub { margin-top: 3px; font-size: 12px; }
.eng-body { padding: 18px 22px 34px; display: flex; flex-direction: column; gap: 20px; }

.eng-section { background: var(--surface2); border-radius: 8px; padding: 16px; border-left: 2px solid var(--accent); }
.eng-eyebrow { font-size: 10px; letter-spacing: .1em; text-transform: uppercase; color: var(--text2); margin-bottom: 10px; }
.eng-verdict { font-size: 15px; line-height: 1.4; }
.eng-check { display: grid; grid-template-columns: 16px 1.1fr 2fr; gap: 10px; align-items: baseline; padding: 7px 0; font-size: 12.5px; }
.eng-check-detail { font-size: 11.5px; }

.eng-h3 { font-size: 12px; letter-spacing: .06em; text-transform: uppercase; color: var(--text2); }
.eng-h3-row { display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }
.eng-h3-note { font-size: 10.5px; margin-left: auto; }

.eng-drift { background: var(--surface2); border-radius: 8px; overflow: hidden; }
.eng-drift-grid { display: grid; grid-template-columns: 1.1fr repeat(3, 1fr); padding: 8px 14px; font-size: 12px; }
.eng-drift-head { font-size: 9px; text-transform: uppercase; letter-spacing: .06em; color: var(--text3); box-shadow: inset 0 -1px 0 var(--border); }
.eng-drift-row { box-shadow: inset 0 -1px 0 var(--border2); }
.eng-drift-row:last-child { box-shadow: none; }
.eng-drift-cell { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.eng-load-unavailable { background: var(--surface2); border-radius: 8px; padding: 12px 14px; font-size: 11.5px; }

.eng-timeline-row { display: grid; grid-template-columns: 86px 14px 1fr; gap: 10px; align-items: baseline; padding: 7px 0; }
.eng-mono { font-family: ui-monospace, monospace; font-size: 11px; }

.eng-history-row { display: grid; grid-template-columns: 60px 70px 1fr 80px; gap: 10px; align-items: baseline; padding: 7px 0; box-shadow: inset 0 -1px 0 var(--border2); }
.eng-history-row:last-child { box-shadow: none; }

.eng-block-row { display: flex; align-items: baseline; gap: 10px; padding: 5px 0; box-shadow: inset 0 -1px 0 var(--border2); }
.eng-block-k { min-width: 130px; font-size: 11.5px; }

.eng-know-row { display: flex; align-items: baseline; gap: 10px; padding: 7px 0; box-shadow: inset 0 -1px 0 var(--border2); cursor: pointer; }
.eng-know-row:hover { opacity: .8; }
.eng-show-more { font-size: 10.5px; color: var(--accent); cursor: pointer; padding-top: 6px; }

.eng-chip { font-size: 10.5px; padding: 4px 9px; border-radius: 6px; background: var(--surface2); border: 1px solid var(--border2); color: var(--text2); cursor: pointer; }
.eng-chip:hover { border-color: var(--accent); }
.eng-chip.dim { opacity: .65; }

.eng-chain-card { display: flex; align-items: center; gap: 11px; padding: 9px 12px; background: var(--surface2); border-radius: 8px; margin-bottom: 5px; border-left: 2px solid var(--accent); }
.eng-chain-count { font-weight: 700; font-size: 18px; min-width: 40px; font-variant-numeric: tabular-nums; }
</style>
