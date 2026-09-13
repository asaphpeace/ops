<template>
  <div class="dl-detail">
    <div v-if="!tickets.length" class="sub" style="font-size:10.5px;color:var(--text3)">{{ emptyLabel ?? 'No ticket detail available.' }}</div>
    <div
      v-for="t in sortedTickets" :key="t.jira_ref" class="dl-row"
      :class="{ 'dl-mine': t.assignee_name === YOU }" @click="openCase(t.jira_ref)"
    >
      <span class="dl-assignee">{{ t.assignee_name ?? 'Unassigned' }}<span v-if="t.assignee_name === YOU" class="you-tag">you</span></span>
      <span class="jref">{{ t.jira_ref }}</span>
      <span class="dl-title">{{ t.title }}</span>
      <span class="dl-customer">{{ t.customer_name ?? 'Unknown' }}</span>
      <span class="dl-age">{{ t.days_open != null ? t.days_open + 'd' : '—' }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { DrillTicket } from '@/api/client'
import { useCaseDrill } from '@/composables/useCaseDrill'
import { YOU } from '@/config/team'

// Shared expand-in-place ticket list — the same visual pattern already
// used by Case Mix/Closed-Opened Tickets (assignee/ref/title/customer/age,
// your own tickets floated to the top), extracted so every new drillable
// stat tile reuses one implementation instead of copy-pasting a 4th/5th time.
const props = defineProps<{ tickets: DrillTicket[]; emptyLabel?: string }>()
const { openCase } = useCaseDrill()

const sortedTickets = props.tickets.length
  ? [...props.tickets].sort((a, b) => (a.assignee_name === YOU ? 0 : 1) - (b.assignee_name === YOU ? 0 : 1))
  : props.tickets
</script>

<style scoped>
.dl-detail { margin: 6px 0 0; padding: 6px 9px; background: var(--surface2); border-radius: 6px; max-height: 220px; overflow-y: auto; }
.dl-row { display: flex; align-items: center; gap: 8px; padding: 4px 0; border-top: 1px dashed var(--border2); cursor: pointer; font-size: 10.5px; }
.dl-row:first-child { border-top: none; }
.dl-row:hover { color: var(--accent); }
.dl-row.dl-mine { background: var(--surface); }
.dl-assignee { color: var(--text3); flex-shrink: 0; width: 90px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dl-title { flex: 1; color: var(--text2); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dl-customer { color: var(--text3); flex-shrink: 0; max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.dl-age { color: var(--text3); flex-shrink: 0; font-variant-numeric: tabular-nums; }
</style>
