import { reactive } from 'vue'

// Module-level singleton, same pattern as useCaseDrill/useCustomerDrill —
// any code anywhere (components, the axios interceptor in api/client.ts,
// even outside a component's setup()) can push a toast onto the one shared
// stack rendered by ToastHost.vue.
export interface Toast {
  id: number
  message: string
  type: 'error' | 'success' | 'info'
}

const toasts = reactive<Toast[]>([])
let nextId = 1

function dismiss(id: number) {
  const i = toasts.findIndex((t) => t.id === id)
  if (i !== -1) toasts.splice(i, 1)
}

function push(message: string, type: Toast['type'] = 'error', durationMs = 6000): number {
  const id = nextId++
  toasts.push({ id, message, type })
  setTimeout(() => dismiss(id), durationMs)
  return id
}

export function useToast() {
  return { toasts, push, dismiss }
}
