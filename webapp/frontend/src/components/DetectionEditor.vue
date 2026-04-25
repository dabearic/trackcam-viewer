<template>
  <div class="det-editor" @click.stop>
    <div class="det-editor__header">
      <span class="det-editor__title">{{ mode === 'add' ? 'Add detection' : 'Edit detection' }}</span>
      <button type="button" class="det-editor__close" @click="$emit('close')">✕</button>
    </div>

    <!-- Category -->
    <div class="det-editor__field">
      <span class="det-editor__label">Category</span>
      <div class="det-editor__radios">
        <label
          v-for="opt in CATEGORY_OPTIONS"
          :key="opt.value"
          class="det-editor__radio"
          :class="{ 'det-editor__radio--checked': category === opt.value }"
          :style="{ '--cat-color': opt.color }"
        >
          <input
            type="radio"
            :value="opt.value"
            v-model="category"
          />
          <span class="det-editor__radio-dot"></span>
          {{ opt.label }}
        </label>
      </div>
    </div>

    <!-- Species (animal only) -->
    <div v-if="category === '1'" class="det-editor__field">
      <span class="det-editor__label">Species</span>
      <SpeciesPicker
        :top-five="topFive"
        :flat-species="flatSpecies"
        :add-custom="addCustom"
        :selected="label"
        @select="onSpeciesSelect"
      />
    </div>

    <!-- Confidence -->
    <div class="det-editor__field">
      <span class="det-editor__label">
        Confidence
        <span class="det-editor__conf-value">{{ Math.round(conf * 100) }}%</span>
      </span>
      <input
        type="range"
        min="0"
        max="100"
        step="1"
        :value="Math.round(conf * 100)"
        @input="conf = Number($event.target.value) / 100"
        class="det-editor__slider"
      />
    </div>

    <p v-if="error" class="det-editor__error">{{ error }}</p>

    <!-- Actions -->
    <div class="det-editor__actions">
      <button
        v-if="mode === 'edit'"
        type="button"
        class="det-editor__btn det-editor__btn--danger"
        :disabled="busy"
        @click="$emit('delete')"
      >Delete</button>
      <span class="det-editor__spacer"></span>
      <button
        type="button"
        class="det-editor__btn"
        :disabled="busy"
        @click="$emit('close')"
      >Cancel</button>
      <button
        type="button"
        class="det-editor__btn det-editor__btn--primary"
        :disabled="busy || !canSave"
        @click="onSave"
      >{{ busy ? 'Saving…' : 'Save' }}</button>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'
import SpeciesPicker from './SpeciesPicker.vue'

const CATEGORY_OPTIONS = [
  { value: '1', label: 'Animal',  color: '#4ade80' },
  { value: '2', label: 'Human',   color: '#fb923c' },
  { value: '3', label: 'Vehicle', color: '#60a5fa' },
]

const props = defineProps({
  mode: { type: String, default: 'edit' },           // 'edit' | 'add'
  detection: { type: Object, default: null },         // existing det for edit
  topFive:    { type: Array, default: () => [] },
  flatSpecies:{ type: Array, default: () => [] },
  addCustom:  { type: Function, required: true },
  busy:       { type: Boolean, default: false },
  error:      { type: String, default: '' },
})
const emit = defineEmits(['save', 'delete', 'close'])

// ── Form state ──────────────────────────────────────────────────────────────
const category   = ref('1')
const label      = ref('')
const scientific = ref('')
const conf       = ref(1.0)

function reset() {
  if (props.detection) {
    category.value   = props.detection.category || '1'
    label.value      = props.detection.label || ''
    scientific.value = props.detection.scientific || ''
    // Per spec: confidence defaults to 100% when opening the editor, even
    // for inference detections. The user can dial it down deliberately.
    conf.value       = 1.0
  } else {
    category.value   = '1'
    label.value      = ''
    scientific.value = ''
    conf.value       = 1.0
  }
}
watch(() => props.detection, reset, { immediate: true })
watch(() => props.mode,      reset)

// Auto-set label for human/vehicle so the user doesn't have to pick a species.
watch(category, c => {
  if (c === '2') { label.value = 'human';   scientific.value = '' }
  if (c === '3') { label.value = 'vehicle'; scientific.value = '' }
})

function onSpeciesSelect(sp) {
  label.value      = sp.common_name
  scientific.value = sp.scientific || ''
}

const canSave = computed(() => {
  if (category.value === '1') return Boolean(label.value)
  return true
})

function onSave() {
  emit('save', {
    category:   category.value,
    label:      label.value,
    scientific: scientific.value,
    conf:       Number(conf.value),
  })
}

</script>

<style scoped>
.det-editor {
  /* Renders as a left-side dock inside .modal__body. Fixed width, full
     height of the parent flex container, internal vertical scroll when
     the form (mostly the species tree) is taller than the modal. */
  width: 320px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.det-editor__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.det-editor__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.det-editor__close {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  width: 22px;
  height: 22px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 12px;
  cursor: pointer;
}
.det-editor__close:hover { color: var(--text); }

.det-editor__field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.det-editor__label {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--text-muted);
}

.det-editor__conf-value {
  color: var(--text);
  font-variant-numeric: tabular-nums;
  text-transform: none;
  letter-spacing: 0;
  font-weight: 600;
}

.det-editor__radios {
  display: flex;
  gap: 6px;
}

.det-editor__radio {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 6px 8px;
  font-size: 12px;
  color: var(--text-muted);
  cursor: pointer;
  transition: background 0.12s, border-color 0.12s, color 0.12s;
}

.det-editor__radio input { display: none; }

.det-editor__radio-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--cat-color, var(--border));
  flex-shrink: 0;
}

.det-editor__radio--checked {
  border-color: var(--cat-color, var(--accent, #2d7d46));
  background: color-mix(in srgb, var(--cat-color, var(--accent, #2d7d46)) 15%, var(--surface));
  color: var(--text);
}

.det-editor__slider {
  width: 100%;
  accent-color: var(--accent, #2d7d46);
}

.det-editor__error {
  margin: 0;
  font-size: 12px;
  color: #f87171;
}

.det-editor__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.det-editor__spacer { flex: 1; }

.det-editor__btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 5px 12px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.det-editor__btn:hover:not(:disabled) { background: var(--surface); }
.det-editor__btn:disabled { opacity: 0.5; cursor: default; }

.det-editor__btn--primary {
  background: var(--accent, #2d7d46);
  border-color: var(--accent, #2d7d46);
  color: white;
}
.det-editor__btn--primary:hover:not(:disabled) { background: #246d3a; }

.det-editor__btn--danger {
  background: #7f1d1d;
  border-color: #b91c1c;
  color: #fee2e2;
}
.det-editor__btn--danger:hover:not(:disabled) { background: #991b1b; }
</style>
