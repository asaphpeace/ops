<template>
  <div class="spark-wrap" @mousemove="onMove" @mouseleave="onLeave">
    <svg :viewBox="`0 0 ${width} ${height}`" class="spark" preserveAspectRatio="none">
      <defs>
        <linearGradient :id="gradientId" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" :stop-color="color" stop-opacity="0.32" />
          <stop offset="100%" :stop-color="color" stop-opacity="0" />
        </linearGradient>
      </defs>
      <path v-if="areaPath" :d="areaPath" :fill="`url(#${gradientId})`" stroke="none" />
      <path v-if="linePath" :d="linePath" fill="none" :stroke="color" stroke-width="1.6" stroke-linejoin="round" stroke-linecap="round" />
      <line v-if="hoverIndex !== null" :x1="coords[hoverIndex][0]" y1="0" :x2="coords[hoverIndex][0]" :y2="height" class="spark-guide" />
      <circle
        v-if="hoverIndex !== null"
        :cx="coords[hoverIndex][0]" :cy="coords[hoverIndex][1]" r="3"
        :fill="color" stroke="var(--surface)" stroke-width="1.5"
      />
      <circle v-else-if="lastPoint" :cx="lastPoint[0]" :cy="lastPoint[1]" r="2.5" :fill="color" stroke="var(--surface)" stroke-width="1" />
    </svg>
    <div v-if="hoverIndex !== null" class="spark-tip" :style="{ left: tipLeftPct + '%' }">{{ values[hoverIndex] }}</div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'

const props = withDefaults(defineProps<{
  values: number[]
  width?: number
  height?: number
  color?: string
}>(), {
  width: 64,
  height: 20,
  color: 'var(--accent)',
})

const gradientId = `spark-grad-${Math.random().toString(36).slice(2, 9)}`

const coords = computed(() => {
  const vals = props.values
  if (!vals.length) return [] as [number, number][]
  const min = Math.min(...vals)
  const max = Math.max(...vals)
  const range = max - min || 1
  const stepX = vals.length > 1 ? props.width / (vals.length - 1) : 0
  return vals.map((v, i) => {
    const x = i * stepX
    const y = props.height - ((v - min) / range) * (props.height - 4) - 2
    return [x, y] as [number, number]
  })
})

// Quadratic-midpoint smoothing — visits the midpoint between each pair of
// real points with the real point itself as the curve's control point, so
// the line never overshoots the data the way a full spline can.
function smoothPath(pts: [number, number][]): string {
  if (!pts.length) return ''
  if (pts.length === 1) return `M ${pts[0][0]} ${pts[0][1]}`
  if (pts.length === 2) return `M ${pts[0][0]} ${pts[0][1]} L ${pts[1][0]} ${pts[1][1]}`
  let d = `M ${pts[0][0]} ${pts[0][1]}`
  for (let i = 0; i < pts.length - 2; i++) {
    const cur = pts[i + 1]
    const next = pts[i + 2]
    const midX = (cur[0] + next[0]) / 2
    const midY = (cur[1] + next[1]) / 2
    d += ` Q ${cur[0]} ${cur[1]} ${midX} ${midY}`
  }
  const last = pts[pts.length - 1]
  d += ` L ${last[0]} ${last[1]}`
  return d
}

const linePath = computed(() => smoothPath(coords.value))
const areaPath = computed(() => {
  const pts = coords.value
  if (pts.length < 2) return ''
  const last = pts[pts.length - 1]
  const first = pts[0]
  return `${linePath.value} L ${last[0]} ${props.height} L ${first[0]} ${props.height} Z`
})
const lastPoint = computed(() => coords.value[coords.value.length - 1])

const hoverIndex = ref<number | null>(null)
function onMove(e: MouseEvent) {
  const pts = coords.value
  if (pts.length < 2) return
  const target = e.currentTarget as HTMLElement
  const rect = target.getBoundingClientRect()
  const relX = ((e.clientX - rect.left) / rect.width) * props.width
  let closest = 0
  let closestDist = Infinity
  for (let i = 0; i < pts.length; i++) {
    const dist = Math.abs(pts[i][0] - relX)
    if (dist < closestDist) {
      closestDist = dist
      closest = i
    }
  }
  hoverIndex.value = closest
}
function onLeave() {
  hoverIndex.value = null
}
const tipLeftPct = computed(() => {
  if (hoverIndex.value === null) return 50
  return (coords.value[hoverIndex.value][0] / props.width) * 100
})
</script>

<style scoped>
.spark-wrap { width: 100%; height: 100%; position: relative; }
.spark { width: 100%; height: 100%; display: block; overflow: visible; }
.spark-guide { stroke: var(--border2); stroke-width: 1; stroke-dasharray: 2 2; }
.spark-tip {
  position: absolute; top: -4px; transform: translate(-50%, -100%);
  background: var(--surface3); color: var(--text); font-size: 9px; font-weight: 700;
  padding: 2px 5px; border-radius: 4px; white-space: nowrap; pointer-events: none;
  font-variant-numeric: tabular-nums; box-shadow: 0 2px 6px rgba(0,0,0,.35);
  z-index: 5;
}
</style>
