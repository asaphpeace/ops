import { ref } from 'vue'

// Module-level singleton: whichever screen you're on, clicking a jira_ref
// opens the same panel. Deliberately not scoped per-component — that's the
// whole point of a *universal* drill-in instead of six bespoke overlays.
const openRef = ref<string | null>(null)

export function useCaseDrill() {
  function openCase(jiraRef: string) {
    openRef.value = jiraRef
  }
  function closeCase() {
    openRef.value = null
  }
  return { openRef, openCase, closeCase }
}
