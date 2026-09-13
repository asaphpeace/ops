import { computed, onUnmounted, ref, type Ref } from 'vue'

// One shared ticking clock for the whole app, not one setInterval per widget.
// Started lazily on first use, stopped when the last consumer unmounts.
const now = ref(Date.now())
let intervalId: ReturnType<typeof setInterval> | null = null
let subscribers = 0

function start() {
  subscribers++
  if (intervalId === null) {
    intervalId = setInterval(() => { now.value = Date.now() }, 1000)
  }
}
function stop() {
  subscribers--
  if (subscribers <= 0 && intervalId !== null) {
    clearInterval(intervalId)
    intervalId = null
  }
}

export interface Countdown {
  days: number
  hours: number
  minutes: number
  seconds: number
  isPast: boolean
  label: string
}

export function useCountdown(target: Ref<Date | null>) {
  start()
  onUnmounted(stop)

  const countdown = computed<Countdown | null>(() => {
    if (!target.value) return null
    const diffMs = target.value.getTime() - now.value
    const isPast = diffMs <= 0
    const abs = Math.abs(diffMs)
    const days = Math.floor(abs / 86400000)
    const hours = Math.floor((abs % 86400000) / 3600000)
    const minutes = Math.floor((abs % 3600000) / 60000)
    const seconds = Math.floor((abs % 60000) / 1000)
    const label = days > 0 ? `${isPast ? '-' : ''}${days}d ${hours}h` : `${isPast ? '-' : ''}${hours}h ${minutes}m`
    return { days, hours, minutes, seconds, isPast, label }
  })

  return { countdown }
}
