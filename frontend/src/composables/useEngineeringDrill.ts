import { ref } from 'vue'

// Module-level singleton, same pattern as useCustomerDrill/useCaseDrill/
// useBugDrill — mounted once at the App root. Deliberately a SEPARATE
// panel from CustomerDrillPanel (Support/CS's own 360) and BugDrillPanel —
// Engineering gets its own dedicated entity panel, matching the real
// mockup's architecture (one generic panel, config-driven per entity kind:
// customer or defect), not a reused Support-oriented component.
export type EngineeringDrillTarget =
  | { kind: 'customer'; id: number; focusEnv?: string }
  | { kind: 'defect'; vmsRef: string }

const target = ref<EngineeringDrillTarget | null>(null)

export function useEngineeringDrill() {
  function openEngineeringCustomer(id: number, focusEnv?: string) {
    target.value = { kind: 'customer', id, focusEnv }
  }
  function openEngineeringDefect(vmsRef: string) {
    target.value = { kind: 'defect', vmsRef }
  }
  function closeEngineeringPanel() {
    target.value = null
  }
  return { target, openEngineeringCustomer, openEngineeringDefect, closeEngineeringPanel }
}
