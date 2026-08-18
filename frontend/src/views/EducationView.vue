<template>
  <div class="view">
    <div class="sh">
      <div><h2>Customer Education</h2><p>Training gaps across your customer base · feeds Sedna Academy content priorities</p></div>
      <button class="btn">+ Log Training Session</button>
    </div>
    <div class="info-bar">ℹ Training gap data here feeds directly into the Sedna Academy LMS content roadmap. The most common gaps = the most needed course modules.</div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-bottom:20px">
      <!-- Top Training Gaps -->
      <div class="tc">
        <h4>Top Training Gaps — Fleet Wide (last 90 days)</h4>
        <template v-if="stats">
          <div v-for="item in stats.top_areas" :key="item.area" class="gap-bar">
            <div class="gap-label">{{ item.area }}</div>
            <div class="gap-track">
              <div class="gap-fill" :style="{ width: barWidth(item.count) }">{{ item.count }} cases</div>
            </div>
          </div>
          <div style="margin-top:12px;font-size:10px;color:var(--text3)">→ Priority for Sedna Academy: {{ stats.top_areas.slice(0, 3).map(a => a.area).join(' · ') }}</div>
        </template>
        <div v-else-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-else style="color:var(--text3);font-size:11px">No gap data.</div>
      </div>

      <!-- Customers with Recurring Gaps -->
      <div class="tc">
        <h4>Customers with Recurring Gaps (2+ in same area)</h4>
        <template v-if="recurringGaps.length">
          <div v-for="item in recurringGaps" :key="item.customer_name + item.area" class="tli">
            <span class="tli-n">{{ item.customer_name }}</span>
            <div style="display:flex;gap:6px;align-items:center">
              <span :class="['tier-badge', tierClass(item.customer_tier)]">{{ item.customer_tier }}</span>
              <span style="font-size:10px;color:var(--purple);font-weight:700">{{ item.area }} (×{{ item.count }})</span>
            </div>
          </div>
          <div style="margin-top:12px;padding:9px;background:var(--purple-dim);border:1px solid rgba(155,108,245,.2);border-radius:6px;font-size:10px;color:var(--purple)">
            {{ recurringGaps.length }} customer{{ recurringGaps.length > 1 ? 's' : '' }} recommended for dedicated training sessions. Consider proactive outreach via CSM.
          </div>
        </template>
        <div v-else-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-else style="color:var(--text3);font-size:11px;padding:8px 0">No recurring gaps identified.</div>
      </div>
    </div>

    <!-- Training Log -->
    <div class="sh"><div><h2>Training Log</h2><p>All sessions delivered</p></div></div>
    <div class="tw">
      <table>
        <thead>
          <tr>
            <th>Date</th><th>Customer</th><th>Tier</th><th>CSM</th>
            <th>Topic Area</th><th>Format</th><th>Delivered By</th><th>Follow-up Needed</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="s in sessions" :key="s.id">
            <td style="color:var(--text3)">{{ formatDate(s.session_date) }}</td>
            <td class="td-name">{{ s.customer_name }}</td>
            <td><span :class="['tier-badge', tierClass(s.customer_tier)]">{{ s.customer_tier }}</span></td>
            <td>{{ s.customer_csm ?? '—' }}</td>
            <td>{{ s.topic_area }}</td>
            <td>{{ s.format ?? '—' }}</td>
            <td>{{ s.delivered_by }}</td>
            <td>
              <span v-if="s.follow_up_needed" style="color:var(--amber)">Yes · {{ s.follow_up_text ?? '' }}</span>
              <span v-else style="color:var(--green)">Resolved</span>
            </td>
          </tr>
          <tr v-if="loading">
            <td colspan="8" style="text-align:center;color:var(--text3);padding:20px">Loading…</td>
          </tr>
          <tr v-else-if="!sessions.length">
            <td colspan="8" style="text-align:center;color:var(--text3);padding:20px">No sessions logged.</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { api, type TrainingGap, type TrainingSession, type EducationStats } from '@/api/client'

const gaps = ref<TrainingGap[]>([])
const sessions = ref<TrainingSession[]>([])
const stats = ref<EducationStats | null>(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const [gapRes, sessRes, statRes] = await Promise.all([
      api.education.gaps(),
      api.education.sessions(),
      api.education.stats(),
    ])
    gaps.value = gapRes.data
    sessions.value = sessRes.data
    stats.value = statRes.data
  } finally {
    loading.value = false
  }
})

const maxCount = computed(() => {
  if (!stats.value?.top_areas.length) return 1
  return Math.max(...stats.value.top_areas.map(a => a.count))
})

function barWidth(count: number) {
  return `${Math.round((count / maxCount.value) * 100)}%`
}

// Customers with 2+ gaps in the same area
const recurringGaps = computed(() => {
  const byCustomerArea: Record<string, { customer_name: string; customer_tier: string; area: string; count: number }> = {}
  for (const g of gaps.value) {
    const key = `${g.customer_name}|${g.area}`
    if (!byCustomerArea[key]) {
      byCustomerArea[key] = { customer_name: g.customer_name, customer_tier: g.customer_tier, area: g.area, count: 0 }
    }
    byCustomerArea[key].count += g.count
  }
  return Object.values(byCustomerArea).filter(x => x.count >= 2).sort((a, b) => b.count - a.count)
})

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}
</script>
