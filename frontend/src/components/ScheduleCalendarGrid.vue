<template>
  <div class="scg">
    <div class="scg-nav">
      <button type="button" class="scg-nav-btn" @click="shiftMonth(-1)">‹</button>
      <div class="scg-month">{{ monthLabel }}</div>
      <button type="button" class="scg-nav-btn" @click="shiftMonth(1)">›</button>
    </div>
    <div class="scg-dow">
      <div v-for="d in DOW" :key="d" class="scg-dow-cell">{{ d }}</div>
    </div>
    <div class="scg-grid">
      <button
        v-for="cell in cells" :key="cell.iso" type="button" class="scg-cell"
        :class="{ 'scg-cell-out': !cell.inMonth, 'scg-cell-today': cell.isToday, 'scg-cell-active': cell.iso === selectedIso }"
        @click="selectedIso = cell.iso === selectedIso ? null : cell.iso"
      >
        <span class="scg-daynum">{{ cell.day }}</span>
        <span v-if="cell.count" class="scg-dot" :title="`${cell.count} slot${cell.count !== 1 ? 's' : ''}`">{{ cell.count }}</span>
      </button>
    </div>
    <div v-if="selectedIso" class="scg-detail">
      <div class="scg-detail-head">{{ selectedLabel }}</div>
      <div v-if="!selectedSlots.length" class="sub" style="font-size:11px;color:var(--text3)">Nothing scheduled.</div>
      <slot v-for="s in selectedSlots" :key="s.type + s.id" name="slot" :slot="s" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import type { ScheduleSlot } from '@/api/client'

const props = defineProps<{ slots: ScheduleSlot[]; month?: Date }>()

const DOW = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function toIso(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

const viewMonth = ref(new Date(props.month ?? new Date()))
function shiftMonth(delta: number) {
  viewMonth.value = new Date(viewMonth.value.getFullYear(), viewMonth.value.getMonth() + delta, 1)
}
const monthLabel = computed(() => viewMonth.value.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }))

const slotsByDay = computed(() => {
  const map: Record<string, ScheduleSlot[]> = {}
  for (const s of props.slots) {
    const iso = toIso(new Date(s.scheduled_at))
    ;(map[iso] ??= []).push(s)
  }
  return map
})

const selectedIso = ref<string | null>(null)
const selectedSlots = computed(() => (selectedIso.value ? slotsByDay.value[selectedIso.value] ?? [] : []))
const selectedLabel = computed(() => {
  if (!selectedIso.value) return ''
  return new Date(selectedIso.value + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'long', month: 'short', day: 'numeric' })
})

const cells = computed(() => {
  const y = viewMonth.value.getFullYear()
  const m = viewMonth.value.getMonth()
  const first = new Date(y, m, 1)
  // Monday-start week, matching this app's existing Mon-Fri work-week convention.
  const offset = (first.getDay() + 6) % 7
  const gridStart = new Date(y, m, 1 - offset)
  const todayIso = toIso(new Date())
  return Array.from({ length: 42 }, (_, i) => {
    const d = new Date(gridStart.getFullYear(), gridStart.getMonth(), gridStart.getDate() + i)
    const iso = toIso(d)
    return {
      iso,
      day: d.getDate(),
      inMonth: d.getMonth() === m,
      isToday: iso === todayIso,
      count: slotsByDay.value[iso]?.length ?? 0,
    }
  })
})
</script>

<style scoped>
.scg-nav { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
.scg-nav-btn { background: var(--surface2); border: 1px solid var(--border2); color: var(--text2); border-radius: 6px; width: 24px; height: 24px; cursor: pointer; font-size: 13px; line-height: 1; }
.scg-nav-btn:hover { color: var(--text); }
.scg-month { font-size: 11px; font-weight: 700; color: var(--text2); }
.scg-dow { display: grid; grid-template-columns: repeat(7, 1fr); margin-bottom: 4px; }
.scg-dow-cell { text-align: center; font-size: 8.5px; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; color: var(--text3); }
.scg-grid { display: grid; grid-template-columns: repeat(7, 1fr); gap: 3px; }
.scg-cell {
  position: relative; aspect-ratio: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
  background: var(--surface2); border: 1px solid transparent; border-radius: 6px; cursor: pointer; padding: 2px;
}
.scg-cell:hover { border-color: var(--border2); }
.scg-cell-out { opacity: .35; }
.scg-cell-today .scg-daynum { color: var(--accent); font-weight: 800; }
.scg-cell-active { border-color: var(--accent); background: var(--surface3, var(--surface2)); }
.scg-daynum { font-size: 10px; color: var(--text2); }
.scg-dot { font-size: 8px; font-weight: 800; color: #fff; background: var(--accent); border-radius: 8px; min-width: 13px; height: 13px; display: flex; align-items: center; justify-content: center; padding: 0 3px; margin-top: 1px; }
.scg-detail { margin-top: 12px; padding-top: 10px; border-top: 1px solid var(--border); }
.scg-detail-head { font-size: 10px; font-weight: 800; color: var(--text2); margin-bottom: 6px; text-transform: uppercase; letter-spacing: .05em; }
</style>
