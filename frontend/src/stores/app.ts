import { defineStore } from 'pinia'
import { ref } from 'vue'

export const useAppStore = defineStore('app', () => {
  // Global UI state
  const panelOpen = ref(false)
  const panelCustomerId = ref<string | null>(null)

  function openPanel(id: string) {
    panelCustomerId.value = id
    panelOpen.value = true
  }

  function closePanel() {
    panelOpen.value = false
    panelCustomerId.value = null
  }

  return { panelOpen, panelCustomerId, openPanel, closePanel }
})
