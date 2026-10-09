<template>
  <div class="cp-grid">
    <div class="tw cp-card">
      <div class="cp-card-head">
        <div class="md-eyebrow" style="margin:0">Contacts <span class="cp-muted">{{ contacts.length }}</span></div>
        <button v-if="contacts.length" class="btn btn-g btn-sm" @click="revealed = !revealed">{{ revealed ? 'Hide' : '👁 Show details' }}</button>
      </div>

      <div v-if="loading" class="cp-muted">Loading…</div>
      <div v-else-if="!contacts.length" class="cp-muted">No contacts on file yet.</div>
      <!-- Hidden by default (GDPR / screen-sharing): addresses only render once revealed. -->
      <div v-else-if="!revealed" class="cp-muted cp-hidden-note">
        {{ contacts.length }} contact{{ contacts.length === 1 ? '' : 's' }} on file{{ primaryCount ? `, ${primaryCount} primary` : ', no primary set' }} — hidden by default.
      </div>
      <template v-else>
        <div v-for="c in sorted" :key="c.id" class="cp-contact">
          <a :href="`mailto:${c.email}`" class="cp-email">{{ c.email }}</a>
          <span v-if="c.is_primary" class="cp-pill ok" :title="c.primary_contact_reason || 'Customer Comms sends here, not to every contact'">Primary</span>
          <span class="cp-muted">{{ c.source === 'manual' ? 'added manually' : 'found via Jira' }} · {{ fmtDate(c.created_at) }}</span>
          <button class="btn btn-g btn-sm cp-push" :disabled="removing === c.id" @click="remove(c.id)">{{ removing === c.id ? '…' : '✕' }}</button>
        </div>
      </template>

      <form class="cp-inline-form" @submit.prevent="add">
        <input class="inp" v-model="newEmail" type="email" placeholder="name@company.com">
        <button class="btn btn-sm" :disabled="!newEmail.includes('@') || adding">{{ adding ? 'Adding…' : '+ Add contact' }}</button>
      </form>
      <div v-if="error" class="cp-error">⚠ {{ error }}</div>
    </div>

    <div class="tw cp-card">
      <div class="md-eyebrow">Account</div>
      <div v-for="f in facts" :key="f.label" class="cp-fact">
        <span>{{ f.label }}</span>
        <b>{{ f.value }}<span v-if="f.note" class="cp-muted"> · {{ f.note }}</span></b>
      </div>
      <div v-if="missing.length" class="cp-muted cp-missing">Not on record: {{ missing.join(', ') }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
// Who do I talk to, and what have they bought? Upgrade allowance, after-
// hours and scheduling preferences live under Upgrades & Projects (they're
// constraints you need when scheduling), SSO/integrations under
// Connectivity — so nothing here repeats another section.
import { ref, computed, watch } from 'vue'
import { api, planName, type Customer, type CustomerContactEntry } from '@/api/client'
import { fmtDate, fmtMonth, formatArr } from './profileUtils'

const props = defineProps<{ customer: Customer }>()

const contacts = ref<CustomerContactEntry[]>([])
const loading = ref(true)
const revealed = ref(false)
const newEmail = ref('')
const adding = ref(false)
const removing = ref<number | null>(null)
const error = ref('')

const sorted = computed(() => [...contacts.value].sort((a, b) => Number(b.is_primary) - Number(a.is_primary) || a.email.localeCompare(b.email)))
const primaryCount = computed(() => contacts.value.filter(c => c.is_primary).length)

const candidates = computed(() => {
  const c = props.customer
  return [
    { label: 'Package', value: planName(c.tier) },
    { label: 'Edition', value: c.plan },
    { label: 'ARR', value: formatArr(c.arr_gbp) },
    { label: 'SLA', value: c.sla_tier },
    { label: 'Seats', value: c.seats ? String(c.seats) : null },
    { label: 'Region', value: c.region },
    { label: 'Timezone', value: c.timezone },
    // Renewal dates are real but unverified data — labelled, never presented as authoritative.
    { label: 'Renewal', value: c.renewal_date ? fmtMonth(c.renewal_date) : null, note: 'unverified' },
    { label: 'Status', value: c.status },
  ]
})
const facts = computed(() => candidates.value.filter(f => f.value) as { label: string; value: string; note?: string }[])
const missing = computed(() => candidates.value.filter(f => !f.value).map(f => f.label))

async function load() {
  loading.value = true
  revealed.value = false
  try {
    contacts.value = (await api.customers.contacts(props.customer.id)).data
  } finally {
    loading.value = false
  }
}
async function add() {
  adding.value = true
  error.value = ''
  try {
    const res = await api.customers.addContact(props.customer.id, newEmail.value.trim())
    contacts.value = [...contacts.value, res.data]
    newEmail.value = ''
    revealed.value = true
  } catch (e: any) {
    error.value = e?.response?.data?.detail ?? 'Failed to add contact.'
  } finally {
    adding.value = false
  }
}
async function remove(contactId: number) {
  if (!confirm('Remove this contact?')) return
  removing.value = contactId
  try {
    await api.customers.deleteContact(props.customer.id, contactId)
    contacts.value = contacts.value.filter(c => c.id !== contactId)
  } finally {
    removing.value = null
  }
}
watch(() => props.customer.id, load, { immediate: true })
</script>
