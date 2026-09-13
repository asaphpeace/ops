<template>
  <div class="fp-row">
    <button
      type="button" class="fp-pill" :class="{ active: modelValue === '' }"
      @click="$emit('update:modelValue', '')"
    >{{ allLabel }}</button>
    <button
      v-for="opt in options" :key="opt.value" type="button"
      class="fp-pill" :class="{ active: modelValue === opt.value }"
      @click="$emit('update:modelValue', opt.value)"
    >{{ opt.label }}</button>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  options: { value: string; label: string }[]
  modelValue: string
  allLabel: string
}>()
defineEmits<{ (e: 'update:modelValue', value: string): void }>()
</script>

<style scoped>
.fp-row { display: flex; gap: 5px; flex-wrap: wrap; }
.fp-pill {
  background: var(--surface2); border: 1px solid var(--border2); color: var(--text3);
  font-size: 10px; font-weight: 700; padding: 5px 11px; border-radius: 20px; cursor: pointer;
  transition: background .15s, color .15s, border-color .15s;
}
.fp-pill:hover { color: var(--text2); }
.fp-pill.active { background: var(--accent); border-color: var(--accent); color: #fff; }
</style>
