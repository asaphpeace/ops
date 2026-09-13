<template>
  <div class="view">
    <div class="sh">
      <div>
        <h2>Troubleshoot</h2>
        <p>Paste a ticket ref or describe what the customer sees. Every line below is a real, already-computed fact — no simulated replay, no invented confidence score.</p>
      </div>
    </div>

    <div class="tw" style="padding:15px 17px;margin-bottom:14px">
      <label class="sub" style="font-size:9px;text-transform:uppercase;letter-spacing:.08em;color:var(--text3);display:block;margin-bottom:6px">Ticket ref or symptom</label>
      <textarea
        class="inp" style="width:100%;min-height:70px;resize:vertical"
        v-model="query" :disabled="loading"
        placeholder="e.g. VMS-25447, DSD-28129, or &quot;demurrage lands at zero after the second edit&quot;"
      ></textarea>
      <div style="display:flex;align-items:center;gap:10px;margin-top:8px">
        <button class="btn" :disabled="!query.trim() || loading" @click="run">
          {{ loading ? 'Looking…' : '🔍 Reproduce & diagnose' }}
        </button>
        <span v-if="error" class="sub" style="color:var(--red);font-size:11px">{{ error }}</span>
      </div>
    </div>

    <template v-if="result">
      <!-- INVESTIGATION STEPS -->
      <div class="tw" style="padding:15px 17px;margin-bottom:14px">
        <div class="md-eyebrow">Investigation Steps</div>
        <div v-for="(s, i) in result.steps" :key="i" class="ts-step">
          <span class="ts-check">✓</span>
          <div>
            <div class="ts-step-label">{{ s.label }}</div>
            <div class="sub" style="font-size:11px;color:var(--text2)">{{ s.detail }}</div>
          </div>
        </div>
      </div>

      <!-- NOT FOUND -->
      <div v-if="result.resolution_path === 'not_found'" class="info-bar">
        No matching case, bug, or note found for this — try pasting the exact Jira ref.
      </div>

      <!-- DIAGNOSIS -->
      <template v-else>
        <div class="tw ts-diagnosis" style="padding:15px 17px">
          <div class="md-eyebrow">Diagnosis</div>

          <div v-if="result.case" class="ts-block">
            <div class="ts-block-head">
              <span class="jref" @click="openCase(result.case.jira_ref)">{{ result.case.jira_ref }}</span>
              <span class="sub" style="color:var(--text2)">{{ result.case.title }}</span>
            </div>
            <div class="sub" style="font-size:11px;color:var(--text3)">
              {{ result.case.status }} · {{ result.case.customer_name ?? 'Unknown customer' }} · {{ result.case.days_open }}d open
            </div>
          </div>

          <div v-if="result.bug" class="ts-block">
            <div class="ts-block-head">
              <span class="jref" @click="openBug(result.bug.vms_ref)">{{ result.bug.vms_ref }}</span>
              <span class="flag-pill" style="background:var(--surface2);color:var(--text2)">{{ result.bug.status }}</span>
              <span v-if="result.bug.sprint_name" class="sub" style="font-size:10.5px;color:var(--text3)">{{ result.bug.sprint_name }}</span>
              <span v-if="result.bug.assignee" class="sub" style="font-size:10.5px;color:var(--text3)">· {{ result.bug.assignee }}</span>
            </div>

            <div class="sub" style="font-size:12px;color:var(--text2);margin-top:6px">
              <template v-if="!result.bug.fix_version">No fix version set yet.</template>
              <template v-else-if="result.bug.matched_release">Fix version {{ result.bug.fix_version }} — released as {{ result.bug.matched_release }}.</template>
              <template v-else>Fixed in {{ result.bug.fix_version }} — <span style="color:var(--amber)">not yet formally released</span>.</template>
            </div>

            <div class="sub" style="font-size:12px;color:var(--text2);margin-top:4px">
              {{ exposureSentence }}
            </div>

            <div v-if="result.bug.reported_customers.length || result.bug.silently_exposed_customers.length" class="ts-chip-wrap">
              <span
                v-for="c in result.bug.reported_customers" :key="'r' + c.id" class="flag-chip"
                title="Reported it" @click="goToCustomer(c.id, 'overview')"
              >{{ c.name }}</span>
              <span
                v-for="c in result.bug.silently_exposed_customers" :key="'s' + c.id" class="flag-chip ts-chip-silent"
                :title="`On ${c.prod_version} — hasn't reported it`" @click="goToCustomer(c.id, 'overview')"
              >{{ c.name }}</span>
            </div>

            <div v-if="result.incident" class="sub" style="font-size:11px;color:var(--text3);margin-top:6px">
              Tracked by Platform Incident
              <RouterLink to="/tools?tab=incidents" style="color:var(--accent)">#{{ result.incident.id }}</RouterLink>
              — {{ result.incident.status }}, phase {{ result.incident.phase }}.
            </div>

            <div v-if="result.narration" class="ts-narration">{{ result.narration }}</div>
          </div>

          <div class="ts-actions">
            <a v-if="primaryRef" :href="jiraUrl(primaryRef)" target="_blank" rel="noopener" class="btn btn-sm btn-g">Open in Jira</a>
            <RouterLink
              v-if="result.bug && (result.bug.reported_customers.length || result.bug.silently_exposed_customers.length)"
              :to="`/customers/comms?vms_ref=${result.bug.vms_ref}`" class="btn btn-sm"
            >📢 Notify affected tenants</RouterLink>
          </div>
        </div>
      </template>
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { api, jiraUrl, type TroubleshootResult } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useBugDrill } from '@/composables/useBugDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCase } = useCaseDrill()
const { openBug } = useBugDrill()
const { openCustomer: goToCustomer } = useCustomerDrill()

const query = ref('')
const loading = ref(false)
const error = ref('')
const result = ref<TroubleshootResult | null>(null)

const primaryRef = computed(() => result.value?.bug?.vms_ref ?? result.value?.case?.jira_ref ?? null)

const exposureSentence = computed(() => {
  const bug = result.value?.bug
  if (!bug) return ''
  const n = bug.reported_customers.length
  const m = bug.silently_exposed_customers.length
  if (!n && !m) return 'No real customer exposure found for this bug yet.'
  return `Reported by ${n} customer${n === 1 ? '' : 's'} · ${m} more ${m === 1 ? 'is' : 'are'} on affected versions and haven't reported it.`
})

async function run() {
  if (!query.value.trim()) return
  loading.value = true
  error.value = ''
  result.value = null
  try {
    const res = await api.troubleshoot.investigate(query.value.trim())
    result.value = res.data
  } catch {
    error.value = 'Lookup failed — try again.'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.ts-step { display: flex; align-items: flex-start; gap: 9px; padding: 6px 0; border-bottom: 1px dashed var(--border2); }
.ts-step:last-child { border-bottom: none; }
.ts-check { color: var(--green); font-weight: 700; margin-top: 1px; flex-shrink: 0; }
.ts-step-label { font-size: 11px; font-weight: 700; color: var(--text); }

.ts-diagnosis { border-left: 3px solid var(--accent); }
.ts-block { margin-bottom: 12px; }
.ts-block-head { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.ts-chip-wrap { display: flex; flex-wrap: wrap; gap: 5px 10px; margin-top: 8px; }
.ts-chip-silent { color: var(--text3); }
.ts-narration { font-size: 11px; color: var(--text2); background: var(--surface2); border-radius: 7px; padding: 8px 10px; margin-top: 8px; }
.ts-actions { display: flex; gap: 8px; margin-top: 10px; }
</style>
