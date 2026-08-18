<template>
  <div class="view">
    <div class="sh">
      <div><h2>Customer Education</h2><p>Training gaps across your customer base · feeds Sedna Academy content priorities</p></div>
      <button class="btn">+ Log Training Session</button>
    </div>

    <!-- Stats row -->
    <div class="stats-row sr-4" v-if="stats">
      <div class="sc alert">
        <div class="lbl">Logged Gaps</div>
        <div class="val">{{ stats.total_gaps }}</div>
        <div class="sub">{{ stats.unique_areas }} unique areas</div>
      </div>
      <div class="sc warn">
        <div class="lbl">Follow-ups Due</div>
        <div class="val">{{ stats.follow_ups_due }}</div>
        <div class="sub">from sessions</div>
      </div>
      <div class="sc good">
        <div class="lbl">Sessions Delivered</div>
        <div class="val">{{ stats.total_sessions }}</div>
      </div>
      <div class="sc info">
        <div class="lbl">Top Gap Area</div>
        <div class="val" style="font-size:13px;line-height:1.2">{{ stats.top_areas[0]?.area ?? '—' }}</div>
      </div>
    </div>

    <div style="display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:4px">
      <!-- Training Gaps -->
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Training Gaps by Area</div>
        <div v-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-if="stats" style="margin-bottom:14px">
          <div v-for="item in stats.top_areas" :key="item.area" style="display:flex;align-items:center;gap:8px;margin-bottom:6px">
            <div style="flex:1;font-size:11px;color:var(--text2)">{{ item.area }}</div>
            <div style="background:var(--surface2);border-radius:2px;height:6px;width:80px;overflow:hidden">
              <div style="background:var(--amber);height:100%;border-radius:2px;transition:width .4s"
                   :style="{ width: barWidth(item.count) }"></div>
            </div>
            <div style="font-size:10px;font-weight:700;color:var(--text);width:16px;text-align:right">{{ item.count }}</div>
          </div>
        </div>

        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px;margin-top:14px">All Gaps</div>
        <div v-for="g in gaps" :key="g.id" class="jr" style="flex-direction:column;gap:3px;padding:7px 10px">
          <div style="display:flex;align-items:center;gap:6px">
            <span :class="['tier-badge', tierClass(g.customer_tier)]">{{ g.customer_tier }}</span>
            <span style="font-size:11px;font-weight:600;color:var(--text)">{{ g.customer_name }}</span>
            <span style="font-size:9px;color:var(--text3);margin-left:auto">{{ formatDate(g.logged_at) }}</span>
          </div>
          <div style="font-size:11px;color:var(--text2)">{{ g.area }}</div>
          <div style="display:flex;align-items:center;gap:6px;margin-top:2px">
            <span v-if="g.count > 1" class="type-badge type-c">×{{ g.count }} occurrences</span>
            <span v-if="g.source_case_ref" class="jp">{{ g.source_case_ref }}</span>
          </div>
        </div>
        <div v-if="!loading && !gaps.length" style="color:var(--text3);font-size:11px;padding:8px 0">No training gaps logged.</div>
      </div>

      <!-- Training Sessions -->
      <div>
        <div style="font-size:9px;font-weight:800;text-transform:uppercase;letter-spacing:.1em;color:var(--text3);margin-bottom:10px">Training Sessions</div>
        <div v-if="loading" style="color:var(--text3);font-size:11px">Loading…</div>
        <div v-for="s in sessions" :key="s.id" class="jr" style="flex-direction:column;gap:3px;padding:7px 10px">
          <div style="display:flex;align-items:center;gap:6px">
            <span :class="['tier-badge', tierClass(s.customer_tier)]">{{ s.customer_tier }}</span>
            <span style="font-size:11px;font-weight:600;color:var(--text)">{{ s.customer_name }}</span>
            <span style="font-size:9px;color:var(--text3);margin-left:auto">{{ formatDate(s.session_date) }}</span>
          </div>
          <div style="font-size:11px;color:var(--text2)">{{ s.topic_area }}</div>
          <div style="font-size:10px;color:var(--text3)">{{ s.format }} · {{ s.delivered_by }}</div>
          <div style="display:flex;align-items:center;gap:6px;margin-top:2px">
            <span v-if="s.outcome" :style="outcomeColor(s.outcome)" style="font-size:10px;font-weight:600">{{ s.outcome }}</span>
            <span v-if="s.follow_up_needed" class="type-badge type-c">Follow-up: {{ s.follow_up_text }}</span>
          </div>
        </div>
        <div v-if="!loading && !sessions.length" style="color:var(--text3);font-size:11px;padding:8px 0">No sessions logged.</div>
      </div>
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

function formatDate(d: string) {
  return new Date(d).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' })
}

function tierClass(t?: string | null) {
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
}

function outcomeColor(o: string) {
  return o === 'Resolved' ? 'color:var(--green)' : o === 'Partial' ? 'color:var(--amber)' : 'color:var(--text3)'
}
</script>
