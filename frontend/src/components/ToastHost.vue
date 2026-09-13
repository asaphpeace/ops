<template>
  <div class="toast-host">
    <transition-group name="toast" tag="div" class="toast-stack">
      <div
        v-for="t in toasts"
        :key="t.id"
        :class="['toast', 'toast-' + t.type]"
        @click="dismiss(t.id)"
      >
        <span class="toast-icon">{{ t.type === 'error' ? '⚠' : t.type === 'success' ? '✓' : 'ℹ' }}</span>
        <span class="toast-msg">{{ t.message }}</span>
        <button class="toast-close" @click.stop="dismiss(t.id)">✕</button>
      </div>
    </transition-group>
  </div>
</template>

<script setup lang="ts">
import { useToast } from '@/composables/useToast'

const { toasts, dismiss } = useToast()
</script>

<style scoped>
.toast-host {
  position: fixed;
  bottom: 20px;
  right: 20px;
  z-index: 500;
  pointer-events: none;
}
.toast-stack { display: flex; flex-direction: column; gap: 8px; align-items: flex-end; }
.toast {
  pointer-events: auto;
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 10px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.4;
  max-width: 340px;
  box-shadow: 0 10px 30px rgba(0, 0, 0, .4);
  cursor: pointer;
  background: var(--surface2);
  border: 1px solid var(--border2);
  color: var(--text);
}
.toast-error   { border-color: rgba(232, 68, 90, .35); }
.toast-error .toast-icon { color: var(--red); }
.toast-success { border-color: rgba(15, 186, 129, .35); }
.toast-success .toast-icon { color: var(--green); }
.toast-info    { border-color: rgba(59, 127, 245, .35); }
.toast-info .toast-icon { color: var(--accent); }
.toast-msg { flex: 1; word-break: break-word; }
.toast-close {
  background: none;
  border: none;
  color: var(--text3);
  cursor: pointer;
  font-size: 11px;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
}
.toast-close:hover { color: var(--text); }

.toast-enter-active, .toast-leave-active { transition: all .2s ease; }
.toast-enter-from, .toast-leave-to { opacity: 0; transform: translateX(24px); }
</style>
