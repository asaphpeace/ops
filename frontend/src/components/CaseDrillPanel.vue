<template>
  <DrillPanel :open="open" :tabs="tabs" :active-tab="activeTab" nested @close="close" @update:active-tab="activeTab = $event">
    <template #header>
      <div style="display:flex;align-items:center;gap:8px">
        <h3 v-if="detail" style="margin:0">{{ detail.jira_ref }}</h3>
        <h3 v-else style="margin:0">{{ jiraRef }}</h3>
        <a :href="jiraUrl(detail ? detail.jira_ref : jiraRef)" target="_blank" rel="noopener" class="jira-link" title="Open in Jira">↗ Jira</a>
      </div>
      <div v-if="detail" style="font-size:12px;color:var(--text2);margin-bottom:6px">{{ detail.title }}</div>
      <div v-if="detail" style="display:flex;gap:5px;align-items:center;flex-wrap:wrap">
        <span :class="['env-badge', envClass(detail.environment)]">{{ detail.environment }}</span>
        <span :class="detail.priority === 'High' ? 'priority-h' : detail.priority === 'Low' ? 'priority-l' : 'priority-m'">{{ detail.priority }}</span>
        <span style="font-size:10px;color:var(--text3)" :style="detail.status === 'Closed' ? 'color:var(--green)' : ''">{{ detail.status }}</span>
        <span v-if="detail.customer_name" style="font-size:10px;color:var(--text3)">· {{ detail.customer_name }}</span>
        <span v-if="detail.customer_tier" :class="['tier-badge', tierClass(detail.customer_tier)]">{{ detail.customer_tier }}</span>
      </div>
    </template>

    <template #body>
      <div v-if="loading" class="sub" style="color:var(--text3)">Loading…</div>
      <template v-else-if="detail">
        <!-- Overview -->
        <div v-if="activeTab === 'overview'">
          <div class="ds"><h4>Ticket</h4>
            <div class="fg-1col">
              <div class="fr"><span>Type</span> <span style="color:var(--text)">{{ detail.case_type }}</span></div>
              <div class="fr"><span>Days open</span> <span style="color:var(--text)">{{ detail.days_open }}d</span></div>
              <div class="fr"><span>SLA</span> <span style="color:var(--text)">{{ detail.sla_days ? detail.sla_days + 'd' : '—' }}</span></div>
              <div class="fr"><span>Assigned to</span> <span style="color:var(--text)">{{ detail.assigned_to ?? 'Unassigned' }}</span></div>
              <div class="fr"><span>TTFR</span> <span :style="detail.ttfr_breached ? 'color:var(--red);font-weight:700' : 'color:var(--text)'">
                {{ detail.ttfr_hours != null ? Math.round(detail.ttfr_hours) + 'h' : '—' }}
                <template v-if="detail.ttfr_breached"> · breached</template>
              </span></div>
              <div class="fr"><span>Created</span> <span style="color:var(--text)">{{ formatDate(detail.created_at) }}</span></div>
              <div class="fr" v-if="detail.resolved_at"><span>Resolved</span> <span style="color:var(--green)">{{ formatDate(detail.resolved_at) }}</span></div>
            </div>
          </div>
          <div class="ds" v-if="detail.defect_status || detail.root_cause">
            <h4>Defect</h4>
            <div class="fg-1col">
              <div class="fr" v-if="detail.defect_status"><span>Dev status</span> <span style="color:var(--amber)">{{ detail.defect_status }}</span></div>
              <div class="fr" v-if="detail.root_cause"><span>Root cause</span> <span style="color:var(--purple)">{{ detail.root_cause }}</span></div>
            </div>
          </div>
          <div class="ds" v-if="detail.related_cases.length">
            <h4>Related Tickets <span style="color:var(--text3);font-weight:600">· {{ detail.related_cases.length }}</span></h4>
            <div v-for="rc in detail.related_cases" :key="rc.jira_ref" :class="['jr', rc.title ? 'jr-click' : '']" @click="rc.title && openCase(rc.jira_ref)">
              <span class="jref">{{ rc.jira_ref }}</span>
              <span v-if="rc.title" class="jtitle">{{ rc.customer_name ?? 'Unknown' }} · {{ rc.title }}</span>
              <span v-else class="sub" style="color:var(--text3);font-size:10px">not yet synced locally</span>
            </div>
          </div>
          <div class="ds" v-if="detail.blocked">
            <h4>Blocked</h4>
            <div style="padding:9px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--red)">{{ detail.blocked_reason || 'No reason recorded' }}</div>
          </div>
          <div class="ds" v-if="detail.resolution_note">
            <h4>Resolution Note</h4>
            <div style="padding:9px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--text2)">{{ detail.resolution_note }}</div>
          </div>
          <div class="ds">
            <h4 style="display:flex;align-items:center;justify-content:space-between">
              <span>External Context</span>
              <span v-if="detail.rovo_context_at" class="sub" style="font-weight:600;color:var(--text3);text-transform:none;letter-spacing:0">{{ formatDate(detail.rovo_context_at) }}</span>
            </h4>
            <div v-if="detail.rovo_context && !editingRovo" style="padding:9px;background:var(--surface2);border-radius:6px;font-size:10px;color:var(--text2);white-space:pre-wrap">{{ detail.rovo_context }}</div>
            <textarea v-if="editingRovo" class="inp" rows="4" style="width:100%" placeholder="Paste context from Rovo Chat or elsewhere…" v-model="rovoContextDraft"></textarea>
            <div style="display:flex;gap:6px;margin-top:6px">
              <button class="btn btn-sm btn-g" @click="toggleRovoEdit">{{ editingRovo ? 'Cancel' : (detail.rovo_context ? 'Edit' : '+ Paste context') }}</button>
              <button v-if="editingRovo" class="btn btn-sm" :disabled="savingRovo" @click="saveRovoContext">{{ savingRovo ? 'Saving…' : 'Save' }}</button>
            </div>
          </div>
        </div>

        <!-- Mentions & Handoff -->
        <div v-if="activeTab === 'handoff'">
          <div class="ds"><h4>Who Has The Ball</h4>
            <div class="fg-1col">
              <div class="fr"><span>Last mention</span> <span style="color:var(--text)">{{ detail.last_mention_name ?? '—' }}</span></div>
              <div class="fr" v-if="detail.last_mention_at"><span>Mentioned</span> <span style="color:var(--text)">{{ formatDate(detail.last_mention_at) }}</span></div>
              <div class="fr"><span>Lane override</span> <span style="color:var(--text)">{{ detail.lane_override ?? 'None' }}</span></div>
              <div class="fr"><span>Comment count</span> <span style="color:var(--text)">{{ detail.comment_count }}</span></div>
              <div class="fr"><span>Needs CSM briefing</span> <span :style="detail.needs_csm_briefing ? 'color:var(--amber);font-weight:700' : 'color:var(--text3)'">{{ detail.needs_csm_briefing ? 'Yes' : 'No' }}</span></div>
              <div class="fr" v-if="detail.escalated_at"><span>Escalated</span> <span style="color:var(--red);font-weight:700">{{ formatDate(detail.escalated_at) }}</span></div>
              <div class="fr" v-if="detail.first_public_reply_at"><span>First reply</span> <span style="color:var(--text)">{{ formatDate(detail.first_public_reply_at) }}</span></div>
            </div>
          </div>
        </div>

        <!-- Linked Bug -->
        <div v-if="activeTab === 'bug'">
          <div v-if="bugLoading" class="sub" style="color:var(--text3)">Loading linked bug…</div>
          <template v-else-if="bug">
            <div class="ds"><h4>{{ bug.jira_ref }}</h4>
              <div class="fg-1col">
                <div class="fr"><span>Status</span> <span style="color:var(--text)">{{ bug.status }}</span></div>
                <div class="fr"><span>Fix version</span> <span :style="bug.fix_version ? 'color:var(--green)' : 'color:var(--text3)'">{{ bug.fix_version ?? 'not yet confirmed' }}</span></div>
              </div>
            </div>
            <div class="ds"><h4>Also affects</h4>
              <div v-if="!bug.affected_customers.length" class="sub" style="color:var(--text3);font-size:11px">No other customers linked.</div>
              <div v-for="name in bug.affected_customers" :key="name" style="font-size:11px;color:var(--text2);padding:2px 0">{{ name }}</div>
            </div>
            <div v-if="bug.ai_summary" class="ds">
              <h4>AI Summary</h4>
              <div style="padding:9px;background:var(--surface2);border-radius:6px;font-size:10.5px;color:var(--text2)">{{ bug.ai_summary }}</div>
            </div>
          </template>
        </div>

        <!-- Jira Activity — real comment history, separate from the
             Sedna-Ops-internal Timeline below -->
        <div v-if="activeTab === 'activity'">
          <div v-if="activityLoading" class="sub" style="color:var(--text3)">Loading real Jira activity…</div>
          <template v-else-if="activity">
            <div v-if="!activity.length" class="sub" style="color:var(--text3);font-size:11px;padding:8px 0">No comments on this ticket yet.</div>
            <div v-for="(a, i) in activity" :key="i" class="tl-item">
              <div class="tl-dot" :style="a.public ? 'background:var(--green)' : 'background:var(--accent)'"></div>
              <div class="tl-content">
                <div class="tl-what" style="display:flex;align-items:center;gap:6px;flex-wrap:wrap">
                  <b>{{ a.author }}</b>
                  <span class="flag-pill" :style="a.public ? 'background:var(--green-dim);color:var(--green)' : 'background:var(--surface3);color:var(--text3)'">{{ a.public ? 'customer-visible' : 'internal' }}</span>
                </div>
                <div style="white-space:pre-wrap;font-size:11px;color:var(--text2);margin-top:4px">{{ a.text || '(no text)' }}</div>
                <div class="tl-when">{{ a.created ? formatDate(a.created) : '' }}</div>
              </div>
            </div>
          </template>
        </div>

        <!-- Timeline -->
        <div v-if="activeTab === 'timeline'">
          <div v-if="!detail.timeline.length" class="sub" style="color:var(--text3);font-size:11px;padding:8px 0">No recorded events for this ticket yet.</div>
          <div v-for="(e, i) in detail.timeline" :key="i" class="tl-item">
            <div class="tl-dot" style="background:var(--accent)"></div>
            <div class="tl-content">
              <div class="tl-what">{{ e.action }}<span v-if="e.detail" style="color:var(--text3)"> — {{ e.detail }}</span></div>
              <div class="tl-when">{{ formatDate(e.created_at) }} · {{ e.actor }}</div>
            </div>
          </div>
        </div>
      </template>
    </template>
  </DrillPanel>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api, jiraUrl, type CaseDetail, type VmsBug, type CaseActivityEntry } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import DrillPanel from '@/components/DrillPanel.vue'

const { openRef, openCase, closeCase } = useCaseDrill()

const open = computed(() => openRef.value !== null)
const jiraRef = computed(() => openRef.value)
const detail = ref<CaseDetail | null>(null)
const loading = ref(false)
const bug = ref<VmsBug | null>(null)
const bugLoading = ref(false)
const activeTab = ref('overview')

const editingRovo = ref(false)
const savingRovo = ref(false)
const rovoContextDraft = ref('')

// Real Jira comment history — deliberately not part of the initial
// Promise chain below (a genuine live-Jira round trip), fetched only when
// the tab is actually opened, and independent of local Case sync state.
const activity = ref<CaseActivityEntry[] | null>(null)
const activityLoading = ref(false)

const tabs = computed(() => {
  const t = [
    { id: 'overview', label: 'Overview' },
    { id: 'handoff', label: 'Mentions & Handoff' },
  ]
  if (detail.value?.linked_vms_ref) t.push({ id: 'bug', label: 'Linked Bug' })
  t.push({ id: 'activity', label: 'Jira Activity' })
  t.push({ id: 'timeline', label: 'Timeline' })
  return t
})

watch(jiraRef, async (ref) => {
  detail.value = null
  bug.value = null
  activeTab.value = 'overview'
  editingRovo.value = false
  activity.value = null
  if (!ref) return
  loading.value = true
  try {
    const res = await api.cases.getByRef(ref)
    detail.value = res.data
    if (detail.value.linked_vms_ref) {
      bugLoading.value = true
      try {
        const bugRes = await api.bugs.get(detail.value.linked_vms_ref)
        bug.value = bugRes.data
      } finally {
        bugLoading.value = false
      }
    }
  } finally {
    loading.value = false
  }
})

watch(activeTab, async (tab) => {
  if (tab !== 'activity' || activity.value !== null || !jiraRef.value) return
  activityLoading.value = true
  try {
    const res = await api.cases.activity(jiraRef.value)
    activity.value = res.data
  } catch {
    activity.value = []
  } finally {
    activityLoading.value = false
  }
})

function close() {
  closeCase()
}

function toggleRovoEdit() {
  if (!editingRovo.value) rovoContextDraft.value = detail.value?.rovo_context ?? ''
  editingRovo.value = !editingRovo.value
}

async function saveRovoContext() {
  if (!detail.value) return
  savingRovo.value = true
  try {
    const res = await api.cases.patch(detail.value.id, { rovo_context: rovoContextDraft.value })
    detail.value.rovo_context = res.data.rovo_context
    detail.value.rovo_context_at = res.data.rovo_context_at
    editingRovo.value = false
  } finally {
    savingRovo.value = false
  }
}

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) +
    ' ' + new Date(d).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}
function envClass(env: string) {
  return env === 'PROD' ? 'ep' : env === 'TEST' ? 'et' : 'ed'
}
function tierClass(tier: string) {
  return tier === 'Premier' ? 'tp' : tier === 'Strategic' ? 'ts' : 'tsc'
}
</script>
