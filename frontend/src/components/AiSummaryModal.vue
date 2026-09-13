<template>
  <Teleport to="body">
    <div v-if="open" class="asm-overlay" @click.self="$emit('close')">
      <div class="asm-modal">
        <div class="asm-head">
          <div>
            <div class="asm-eyebrow">✦ AI Summary</div>
            <h3 class="asm-title">{{ title }}</h3>
          </div>
          <button class="asm-close" @click="$emit('close')" title="Close">✕</button>
        </div>

        <div class="asm-body">
          <div v-if="loading" class="asm-loading">
            <div class="asm-spinner"></div>
            <span>Generating summary…</span>
          </div>
          <div v-else-if="error" class="asm-error">⚠ {{ error }}</div>
          <template v-else-if="summary">
            <p v-for="(para, i) in paragraphs" :key="i" class="asm-para">{{ para }}</p>
          </template>
          <div v-else class="asm-empty">No summary available.</div>
        </div>

        <div class="asm-foot">
          <span class="asm-generated" v-if="generatedAt">Generated {{ formatTime(generatedAt) }}</span>
          <span class="asm-generated" v-else></span>
          <div style="display:flex;gap:8px">
            <button class="btn btn-sm btn-g" :disabled="loading" @click="copy">{{ copied ? '✓ Copied' : 'Copy' }}</button>
            <button class="btn btn-sm btn-g" :disabled="loading" @click="$emit('regenerate')">↻ Regenerate</button>
          </div>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
// Generic AI-summary viewer — deliberately a centered modal via <Teleport>,
// not another DrillPanel instance: DrillPanel's slide-in/overlay z-index
// scheme only supports 2 stacking tiers (150/200 base, 170/220 nested,
// see main.css) and this needs to sit above whichever drill panel opened
// it (Customer, and later Bug/Case) regardless of nesting depth — a
// simpler, higher-z-index overlay sidesteps that rather than extending
// DrillPanel's nesting logic for a one-off viewer.
import { ref, computed, watch } from 'vue'

const props = defineProps<{
  open: boolean
  title: string
  summary: string | null
  generatedAt: string | null
  loading?: boolean
  error?: string | null
}>()
defineEmits<{ close: []; regenerate: [] }>()

const copied = ref(false)
watch(() => props.open, () => { copied.value = false })

// Prose from the backend arrives as one paragraph — split on sentence-ending
// punctuation followed by a capital letter to give it real paragraph rhythm
// instead of one dense block, without inventing structure the model didn't
// actually provide (no fake bullet points over free text).
const paragraphs = computed(() => {
  if (!props.summary) return []
  const sentences = props.summary.match(/[^.!?]+[.!?]+(\s+|$)/g) ?? [props.summary]
  const groups: string[] = []
  let current = ''
  sentences.forEach((s, i) => {
    current += s
    if ((i + 1) % 2 === 0) { groups.push(current.trim()); current = '' }
  })
  if (current.trim()) groups.push(current.trim())
  return groups.length ? groups : [props.summary]
})

async function copy() {
  if (!props.summary) return
  try {
    await navigator.clipboard.writeText(props.summary)
    copied.value = true
    setTimeout(() => { copied.value = false }, 1500)
  } catch { /* clipboard unavailable — silently no-op */ }
}

function formatTime(t: string): string {
  return new Date(t).toLocaleDateString('en-GB', { day: 'numeric', month: 'short', year: 'numeric' }) +
    ' at ' + new Date(t).toLocaleTimeString('en-GB', { hour: '2-digit', minute: '2-digit' })
}
</script>

<style scoped>
.asm-overlay {
  position: fixed; inset: 0; z-index: 400;
  background: rgba(0, 0, 0, .6);
  display: flex; align-items: center; justify-content: center;
  padding: 24px;
}
.asm-modal {
  width: 100%; max-width: 560px; max-height: 80vh;
  background: var(--surface); border: 1px solid var(--border); border-radius: 14px;
  box-shadow: 0 30px 80px rgba(0, 0, 0, .5);
  display: flex; flex-direction: column;
  overflow: hidden;
}
.asm-head {
  display: flex; align-items: flex-start; justify-content: space-between; gap: 12px;
  padding: 20px 22px 16px; border-bottom: 1px solid var(--border);
  background: linear-gradient(135deg, var(--accent-dim), transparent 60%);
}
.asm-eyebrow { font-size: 9px; font-weight: 800; text-transform: uppercase; letter-spacing: .12em; color: var(--accent); margin-bottom: 5px; }
.asm-title { font-size: 17px; font-weight: 800; color: var(--text); letter-spacing: -.01em; }
.asm-close { background: var(--surface2); border: 1px solid var(--border2); color: var(--text2); width: 26px; height: 26px; border-radius: 8px; cursor: pointer; font-size: 12px; flex-shrink: 0; }
.asm-close:hover { background: var(--surface3); color: var(--text); }

.asm-body { padding: 20px 22px; overflow-y: auto; flex: 1; }
.asm-para { font-size: 14px; line-height: 1.7; color: var(--text2); margin-bottom: 14px; }
.asm-para:last-child { margin-bottom: 0; }
.asm-empty { font-size: 12px; color: var(--text3); text-align: center; padding: 20px 0; }
.asm-error { font-size: 12.5px; color: var(--amber); background: var(--amber-dim); border-radius: 8px; padding: 12px 14px; }

.asm-loading { display: flex; align-items: center; gap: 10px; font-size: 12.5px; color: var(--text3); padding: 30px 0; justify-content: center; }
.asm-spinner { width: 14px; height: 14px; border-radius: 50%; border: 2px solid var(--border2); border-top-color: var(--accent); animation: asm-spin .7s linear infinite; }
@keyframes asm-spin { to { transform: rotate(360deg); } }

.asm-foot { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 12px 22px; border-top: 1px solid var(--border); background: var(--surface2); }
.asm-generated { font-size: 10px; color: var(--text3); }
</style>
