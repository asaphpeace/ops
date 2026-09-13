<template>
  <li class="vsn-item">
    <div class="vsn-head">
      <span v-if="node.status === 'pending'" class="vsn-dot vsn-dot-pending" title="Fetching…"></span>
      <span v-else-if="node.status === 'error'" class="vsn-dot vsn-dot-error" title="Fetch failed"></span>
      {{ node.entity }} <span class="vsn-key">#{{ node.key }}</span>
    </div>
    <ul v-if="node.children.length" class="vsn-children">
      <VmsSnapshotNode v-for="(c, i) in node.children" :key="i" :node="c" />
    </ul>
  </li>
</template>

<script setup lang="ts">
export interface SnapshotNode {
  entity: string
  key: string
  data: unknown
  children: SnapshotNode[]
  // Only meaningful during/after an auto-crawl — a manually-fetched node
  // (via Send/chase-click) never sets this, since it's only ever added
  // once its data has already arrived successfully.
  status?: 'pending' | 'done' | 'error'
}

defineProps<{ node: SnapshotNode }>()
</script>

<style scoped>
.vsn-item { margin: 0; }
.vsn-head { font-size: 11px; color: var(--text2); padding: 3px 0; display: flex; align-items: center; gap: 5px; }
.vsn-key { color: var(--text3); font-variant-numeric: tabular-nums; }
.vsn-children { list-style: none; margin: 0; padding-left: 16px; border-left: 1px dashed var(--border2); }
.vsn-dot { width: 6px; height: 6px; border-radius: 50%; flex-shrink: 0; display: inline-block; }
.vsn-dot-pending { background: var(--amber); animation: vsn-pulse 1s ease-in-out infinite; }
.vsn-dot-error { background: var(--red); }
@keyframes vsn-pulse { 0%, 100% { opacity: 1; } 50% { opacity: .3; } }
</style>
