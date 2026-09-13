<template>
  <div class="cc-slot-row">
    <span class="flag-pill" :class="typeClass">{{ slot.type }}</span>
    <span
      class="td-name" :class="{ 'cc-slot-clickable': slot.customer_id != null }"
      @click="slot.customer_id != null && goToCustomer(slot.customer_id, 'overview')"
    >{{ slot.customer_name ?? 'Unknown' }}</span>
    <span v-if="slot.customer_tier" class="tier-badge" :class="tierClass">{{ slot.customer_tier }}</span>
    <span class="sub" style="color:var(--text3)">{{ slot.detail }}</span>
    <slot name="badge" />
    <span class="sub" style="margin-left:auto;white-space:nowrap">{{ formatted }}<template v-if="slot.duration_minutes"> · {{ slot.duration_minutes }}m</template></span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ScheduleSlot } from '@/api/client'
import { useCustomerDrill } from '@/composables/useCustomerDrill'

const props = defineProps<{ slot: ScheduleSlot }>()
const { openCustomer: goToCustomer } = useCustomerDrill()

const tierClass = computed(() => {
  const t = props.slot.customer_tier
  return t === 'Premier' ? 'tp' : t === 'Strategic' ? 'ts' : 'tsc'
})
const typeClass = computed(() => {
  if (props.slot.type === 'Upgrade') return 'type-s'
  if (props.slot.type === 'Migration') return 'type-c'
  return 'io'
})
const formatted = computed(() => {
  const d = new Date(props.slot.scheduled_at)
  return d.toLocaleDateString('en-GB', { day: 'numeric', month: 'short' }) + ' ' +
    d.toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
})
</script>

<style scoped>
.cc-slot-clickable { cursor: pointer; }
.cc-slot-clickable:hover { color: var(--accent); }
</style>
