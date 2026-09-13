<template>
  <div class="pb" :class="gridClass ?? 'pb-4'">
    <div v-for="stage in stages" :key="stage" class="pc">
      <div class="pc-h">
        <span class="cn">{{ stage }}</span>
        <span class="cb">{{ (itemsByStage[stage] ?? []).length }}</span>
      </div>
      <div class="pcards">
        <template v-for="item in itemsByStage[stage] ?? []" :key="item.id ?? item.customer_id">
          <slot name="card" :item="item" :stage="stage" />
        </template>
        <div v-if="!(itemsByStage[stage] ?? []).length" class="pc-empty">Empty</div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  stages: string[]
  itemsByStage: Record<string, any[]>
  gridClass?: string
}>()
</script>

<style scoped>
.pb   { display: grid; gap: 10px; margin-bottom: 20px; }
.pb-3 { grid-template-columns: repeat(3, 1fr); }
.pb-4 { grid-template-columns: repeat(4, 1fr); }
.pb-5 { grid-template-columns: repeat(5, 1fr); }
.pb-6 { grid-template-columns: repeat(6, 1fr); }
.pb-8 { grid-template-columns: repeat(8, 1fr); overflow-x: auto; }

.pc { background: var(--surface); border: 1px solid var(--border); border-radius: 9px; overflow: hidden; min-width: 155px; }
.pc-h { padding: 9px 12px; border-bottom: 1px solid var(--border); display: flex; align-items: center; justify-content: space-between; }
.pc-h .cn { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .1em; color: var(--text2); }
.cb { font-size: 9px; font-weight: 700; background: var(--surface2); border: 1px solid var(--border); border-radius: 8px; padding: 1px 6px; color: var(--text3); }
.pcards { padding: 8px; display: flex; flex-direction: column; gap: 7px; min-height: 70px; }
.pc-empty { color: var(--text3); font-size: 10px; padding: 6px; text-align: center; }
</style>
