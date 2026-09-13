<template>
  <div :class="['overlay', open ? 'open' : '', nested ? 'overlay-nested' : '']" @click="$emit('close')"></div>
  <div :class="['dp', open ? 'open' : '', nested ? 'dp-nested' : '']" v-if="open">
    <div class="dp-h" style="position:relative">
      <button class="cbx" @click="$emit('close')">✕</button>
      <slot name="header" />
    </div>

    <div class="dp-tabs">
      <div v-for="tab in tabs" :key="tab.id" :class="['dt', activeTab === tab.id ? 'active' : '']" @click="$emit('update:activeTab', tab.id)">
        {{ tab.label }}
      </div>
    </div>

    <div class="dp-body">
      <slot name="body" :activeTab="activeTab" />
    </div>
  </div>
</template>

<script setup lang="ts">
// The shared chrome behind every drill-in panel in the app — same
// overlay + right-side slide-in + tab strip Customer Intelligence
// pioneered (main.css: .overlay/.dp/.dp-h/.dp-tabs/.dt/.dp-body).
// Entity-specific panels (CaseDrillPanel, and future Bug/Upgrade/
// Migration/Release panels) supply the header/body content and own
// their own data-fetching; this component owns only the interaction
// chrome so that never gets re-implemented per entity.
defineProps<{
  open: boolean
  tabs: { id: string; label: string }[]
  activeTab: string
  // A Case is a more specific drill target than a Customer — when both
  // happen to be open at once (drilling into a case from inside a
  // customer's Cases tab), the Case panel must stack visually above and
  // receive the overlay click, or it renders hidden underneath at the
  // same z-index and closing "it" actually closes the wrong panel.
  nested?: boolean
}>()
defineEmits<{ close: []; 'update:activeTab': [id: string] }>()
</script>
