<template>
  <div class="tw cp-card">
    <form class="cp-note-form" @submit.prevent="addNote">
      <textarea class="inp" v-model="text" rows="3" placeholder="Add a note about this customer…"></textarea>
      <div class="cp-row-end">
        <label class="cp-check cp-muted"><input type="checkbox" v-model="sticky"> 📌 Pin to the top of the profile</label>
        <button class="btn btn-sm" :disabled="!text.trim() || saving">{{ saving ? 'Saving…' : 'Add note' }}</button>
      </div>
    </form>
  </div>

  <div class="cp-filters">
    <button v-for="k in kinds" :key="k.id" class="cp-filter" :class="{ active: filter === k.id }" @click="filter = k.id">
      {{ k.label }} <span class="cp-muted">{{ k.count }}</span>
    </button>
  </div>

  <div v-if="loading" class="cp-muted">Loading activity…</div>
  <div v-else-if="!shown.length" class="cp-muted">Nothing here yet.</div>
  <div v-for="day in byDay" :key="day.label" class="cp-day">
    <div class="cp-day-head">{{ day.label }}</div>
    <div v-for="(a, i) in day.items" :key="i" class="cp-act">
      <span class="cp-act-kind" :class="a.kind">{{ KIND_LABEL[a.kind] }}</span>
      <span class="cp-act-time">{{ timeOf(a) }}</span>
      <div class="cp-act-body">
        <div class="cp-act-title">
          <span v-if="a.ref" class="jref" @click="openCase(a.ref!)">{{ a.ref }}</span>
          <RouterLink v-if="a.link" :to="a.link" class="cp-act-link">{{ a.title }}</RouterLink>
          <template v-else>{{ a.title }}</template>
          <span v-if="a.is_sticky" title="Pinned to the profile">📌</span>
          <span v-if="a.flag" class="cp-pill" :class="flagTone(a.flag)">{{ a.flag }}</span>
        </div>
        <div v-if="a.detail" class="cp-act-detail">{{ a.detail }}</div>
      </div>
      <div class="cp-act-side">
        <span v-if="a.actor" class="cp-muted">{{ a.actor }}</span>
        <button v-if="a.note_id" class="cp-link" :disabled="pinning === a.note_id" @click="togglePin(a)">{{ a.is_sticky ? 'Unpin' : 'Pin' }}</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
// What has happened with this customer, in order? One timeline that
// replaces the retired panel's Notes, Timeline, Comms and Education tabs:
// manual + ops notes, comms campaigns, training sessions, cases,
// escalations, upgrades, Upgrade Runner automations and system events.
import { ref, computed, watch } from 'vue'
import { api, type CustomerActivityItem } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'

const props = defineProps<{ customerId: number }>()
const emit = defineEmits<{ 'notes-changed': [] }>()
const { openCase } = useCaseDrill()

type Kind = CustomerActivityItem['kind']
const KIND_LABEL: Record<Kind, string> = {
  note: 'Note', comms: 'Comms', training: 'Training', escalation: 'Escalation', case: 'Case',
  upgrade: 'Upgrade', automation: 'Automation', system: 'System',
}
const ORDER: Kind[] = ['note', 'comms', 'training', 'escalation', 'case', 'upgrade', 'automation', 'system']

const items = ref<CustomerActivityItem[]>([])
const loading = ref(true)
const filter = ref<'all' | Kind>('all')
const text = ref('')
const sticky = ref(false)
const saving = ref(false)
const pinning = ref<number | null>(null)

const kinds = computed(() => [
  { id: 'all' as const, label: 'All', count: items.value.length },
  ...ORDER.map(k => ({ id: k, label: KIND_LABEL[k], count: items.value.filter(a => a.kind === k).length })).filter(k => k.count),
])
const shown = computed(() => (filter.value === 'all' ? items.value : items.value.filter(a => a.kind === filter.value)))
const byDay = computed(() => {
  const days: { label: string; items: CustomerActivityItem[] }[] = []
  for (const a of shown.value) {
    const label = new Date(a.when).toLocaleDateString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' })
    if (days[days.length - 1]?.label !== label) days.push({ label, items: [] })
    days[days.length - 1].items.push(a)
  }
  return days
})
// Training sessions are date-only (stored at noon) — no meaningful time.
function timeOf(a: CustomerActivityItem) {
  return a.kind === 'training' ? '' : new Date(a.when).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}
function flagTone(flag: string) {
  return /follow-up|draft/i.test(flag) ? 'warn' : /sent|resolved/i.test(flag) ? 'ok' : ''
}

async function load() {
  loading.value = true
  try {
    items.value = (await api.customers.activity(props.customerId)).data
  } finally {
    loading.value = false
  }
}
async function addNote() {
  saving.value = true
  try {
    await api.customers.addNote(props.customerId, text.value.trim(), sticky.value)
    text.value = ''
    sticky.value = false
    await load()
    emit('notes-changed')
  } finally {
    saving.value = false
  }
}
async function togglePin(a: CustomerActivityItem) {
  pinning.value = a.note_id
  try {
    await api.customers.setNoteSticky(props.customerId, a.note_id!, !a.is_sticky)
    a.is_sticky = !a.is_sticky
    emit('notes-changed')
  } finally {
    pinning.value = null
  }
}
watch(() => props.customerId, load, { immediate: true })
</script>
