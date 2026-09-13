<template>
  <div class="bell-wrap">
    <button class="bell-btn" @click="toggleOpen" :title="observations.length ? `${observations.length} new AI observation(s)` : 'No new AI observations'">
      🤖
      <span v-if="observations.length > 0" class="bell-badge">{{ observations.length > 9 ? '9+' : observations.length }}</span>
    </button>

    <template v-if="open">
      <div class="bell-backdrop" @click="open = false"></div>
      <div class="bell-dropdown">
        <div class="bell-head">
          <span>AI Observations <span class="bell-count">{{ observations.length }}</span></span>
          <button class="bell-recompute" :disabled="recomputing" @click.stop="recompute">
            {{ recomputing ? 'Thinking…' : '↻ Recompute' }}
          </button>
        </div>
        <div class="bell-filter-row">
          <button
            v-for="s in (['New', 'Reviewed', 'Dismissed'] as const)" :key="s"
            type="button" :class="{ active: statusFilter === s }" @click.stop="statusFilter = s"
          >{{ s }}</button>
        </div>
        <div v-if="!observations.length" class="bell-empty">
          No {{ statusFilter.toLowerCase() }} observations.
        </div>
        <div v-else class="bell-list">
          <div v-for="o in observations" :key="o.id" class="bell-item ai-item">
            <div class="ai-item-head">
              <span class="ai-item-kind">{{ aiObservationKindLabel(o.kind) }}</span>
              <span class="ai-item-ref" @click="openRef(o)">{{ o.refs }}</span>
            </div>
            <div class="bell-item-text">{{ o.summary }}</div>
            <div v-if="o.status === 'New'" class="ai-item-actions">
              <button type="button" @click.stop="review(o.id)">Mark Reviewed</button>
              <button type="button" @click.stop="dismiss(o.id)">Dismiss</button>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
// Global "push" surface for the Ollama supervisor's advisory findings —
// previously the ONLY way to see these was a collapsed panel at the bottom
// of Release Intelligence (already the busiest page in the app), which is
// why 78 of 79 real observations ever generated sat unreviewed. This bell
// makes the same data reachable from anywhere, right next to
// NotificationBell, without changing anything about the deterministic
// detection or the model's narration — review/dismiss here hit the exact
// same GET/POST /ai-observations endpoints Release Intelligence's own
// panel already uses.
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { api, aiObservationKindLabel, type AiObservation } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const { openCase } = useCaseDrill()
const { openCustomer } = useCustomerDrill()

const open = ref(false)
const statusFilter = ref<'New' | 'Reviewed' | 'Dismissed'>('New')
const observations = ref<AiObservation[]>([])
const recomputing = ref(false)

async function fetchObservations() {
  try {
    const res = await api.aiObservations.list(statusFilter.value)
    observations.value = res.data
  } catch { /* keep showing last-known state */ }
}

function toggleOpen() {
  open.value = !open.value
}

async function review(id: number) {
  await api.aiObservations.review(id)
  await fetchObservations()
}

async function dismiss(id: number) {
  await api.aiObservations.dismiss(id)
  await fetchObservations()
}

async function recompute() {
  if (recomputing.value) return
  recomputing.value = true
  try {
    await api.aiObservations.recompute()
    await fetchObservations()
  } catch { /* toast already handled by the global axios interceptor if configured; this bell fails quietly */ } finally {
    recomputing.value = false
  }
}

function openRef(o: AiObservation) {
  if (o.kind === 'fixed_but_open') {
    openCase(o.refs)
  } else if (o.customer_id != null) {
    openCustomer(o.customer_id, 'overview')
  }
  open.value = false
}

watch(statusFilter, fetchObservations)

let intervalId: ReturnType<typeof setInterval> | undefined
onMounted(() => {
  fetchObservations()
  // 5 min — the supervisor pass itself only runs every 2h, no need to poll faster.
  intervalId = setInterval(fetchObservations, 5 * 60 * 1000)
})
onUnmounted(() => {
  if (intervalId) clearInterval(intervalId)
})
</script>

<style scoped>
.bell-wrap { position: relative; }
.bell-btn {
  position: relative;
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text2);
  width: 30px; height: 30px; border-radius: 8px; cursor: pointer; font-size: 14px;
  display: flex; align-items: center; justify-content: center;
}
.bell-btn:hover { background: var(--surface3); color: var(--text); }
.bell-badge {
  position: absolute; top: -4px; right: -4px;
  background: var(--accent); color: white; font-size: 9px; font-weight: 800;
  min-width: 15px; height: 15px; border-radius: 999px;
  display: flex; align-items: center; justify-content: center; padding: 0 3px;
}
.bell-backdrop { position: fixed; inset: 0; z-index: 349; }
.bell-dropdown {
  position: absolute; top: 38px; right: 0; z-index: 350;
  width: 380px; max-height: 460px; overflow-y: auto;
  background: var(--surface); border: 1px solid var(--border); border-radius: 10px;
  box-shadow: 0 20px 50px rgba(0, 0, 0, .4);
}
.bell-head {
  display: flex; align-items: center; justify-content: space-between; gap: 8px;
  padding: 10px 12px; border-bottom: 1px solid var(--border);
  font-size: 11px; font-weight: 800; color: var(--text);
}
.bell-count { color: var(--text3); font-weight: 600; margin-left: 4px; }
.bell-recompute {
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text2);
  font-size: 9px; font-weight: 700; padding: 3px 8px; border-radius: 5px; cursor: pointer;
}
.bell-recompute:disabled { opacity: .6; cursor: default; }
.bell-filter-row { display: flex; gap: 3px; padding: 8px 12px 0; }
.bell-filter-row button {
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text3);
  font-size: 9px; font-weight: 700; padding: 2px 8px; border-radius: 5px; cursor: pointer;
}
.bell-filter-row button.active { background: var(--accent-dim); color: var(--accent); border-color: var(--accent); }
.bell-empty { padding: 24px 12px; text-align: center; font-size: 11px; color: var(--text3); }
.bell-list { display: flex; flex-direction: column; }
.bell-item {
  display: flex; flex-direction: column; gap: 4px;
  padding: 9px 12px; border-bottom: 1px solid var(--border);
}
.bell-item:last-child { border-bottom: none; }
.ai-item-head { display: flex; align-items: center; gap: 6px; flex-wrap: wrap; }
.ai-item-kind { font-size: 8.5px; font-weight: 800; text-transform: uppercase; letter-spacing: .06em; color: var(--accent); }
.ai-item-ref { font-size: 10px; font-weight: 700; color: var(--text2); cursor: pointer; }
.ai-item-ref:hover { color: var(--text); text-decoration: underline; }
.bell-item-text { font-size: 11px; color: var(--text2); }
.ai-item-actions { display: flex; gap: 6px; margin-top: 2px; }
.ai-item-actions button {
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text3);
  font-size: 9px; font-weight: 700; padding: 2px 8px; border-radius: 5px; cursor: pointer;
}
.ai-item-actions button:hover { color: var(--text); }
</style>
