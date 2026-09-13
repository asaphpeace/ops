<template>
  <div class="tw md-card">
    <div class="md-eyebrow">Case Mix by Status <span class="md-period">· real Jira status, open tickets only · click a bar to see what's in it</span></div>
    <div v-if="!mix.length" class="sub" style="font-size:11px;color:var(--text3)">No open cases.</div>
    <div v-for="m in mix" :key="m.status" class="cm-block">
      <button type="button" class="cm-row" @click="toggle(m.status)">
        <span class="cm-caret">{{ expanded === m.status ? '▾' : '▸' }}</span>
        <span class="cm-label">{{ m.status }}</span>
        <span class="cm-track" :title="`${m.status}: ${m.count} (${sharePct(m.count)}%)`">
          <span class="cm-fill" :style="{ width: sharePct(m.count) + '%' }"></span>
        </span>
        <span class="cm-count">{{ m.count }} · {{ sharePct(m.count) }}%<span v-if="m.your_count" class="cm-yours"> · {{ m.your_count }} yours</span></span>
      </button>
      <DrillList v-if="expanded === m.status" :tickets="m.cases" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { CaseMixEntry } from '@/api/client'
import DrillList from './DrillList.vue'

const props = defineProps<{ mix: CaseMixEntry[] }>()

const total = computed(() => props.mix.reduce((s, m) => s + m.count, 0) || 1)
function sharePct(count: number) {
  return Math.round((count / total.value) * 100)
}

// Which status bucket is currently expanded — one at a time, collapsed by
// default (this is a drill-down detail, not a summary you need open-by-default).
const expanded = ref<string | null>(null)
function toggle(status: string) {
  expanded.value = expanded.value === status ? null : status
}
</script>

<style scoped>
.cm-block { margin-bottom: 4px; }
.cm-row {
  display: flex; align-items: center; gap: 9px; width: 100%; margin-bottom: 4px; padding: 2px 0;
  background: none; border: none; cursor: pointer; font: inherit; text-align: left;
}
.cm-caret { font-size: 9px; color: var(--text3); width: 10px; flex-shrink: 0; }
.cm-label { font-size: 10.5px; color: var(--text2); width: 130px; flex-shrink: 0; }
.cm-track { flex: 1; height: 14px; background: var(--surface2); border-radius: 4px; overflow: hidden; display: block; }
.cm-fill { height: 100%; border-radius: 4px; background: var(--series-1); transition: width .3s ease; position: relative; box-shadow: 0 0 6px rgba(57,135,229,.35); display: block; }
.cm-fill::after { content: ''; position: absolute; inset: 0; background: linear-gradient(180deg, rgba(255,255,255,.16), transparent 60%); border-radius: inherit; }
.cm-count { font-size: 10px; color: var(--text3); width: 110px; text-align: right; flex-shrink: 0; font-variant-numeric: tabular-nums; }
.cm-yours { color: var(--accent); font-weight: 700; }
</style>
