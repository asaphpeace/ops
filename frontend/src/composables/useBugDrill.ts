import { ref } from 'vue'

// Module-level singleton, same pattern as useCaseDrill — one shared panel
// instance regardless of which screen opens it.
const openRef = ref<string | null>(null)

export function useBugDrill() {
  function openBug(jiraRef: string) {
    openRef.value = jiraRef
  }
  function closeBug() {
    openRef.value = null
  }
  return { openRef, openBug, closeBug }
}
