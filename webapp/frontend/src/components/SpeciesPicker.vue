<template>
  <div class="species-picker">
    <input
      ref="searchRef"
      v-model="query"
      type="text"
      placeholder="Search species…"
      class="species-picker__search"
    />

    <!-- Tier 1: top-5 candidates from this photo -->
    <section v-if="!query && tierOne.length" class="species-picker__section">
      <h4 class="species-picker__heading">From this photo</h4>
      <button
        v-for="cls in tierOne"
        :key="cls.common_name"
        type="button"
        class="species-picker__row"
        :class="{ 'species-picker__row--selected': selected === cls.common_name }"
        @click="$emit('select', { common_name: cls.common_name, scientific: cls.scientific })"
      >
        <span class="species-picker__label">{{ cap(cls.common_name) }}</span>
        <span v-if="cls.scientific" class="species-picker__sci">{{ cls.scientific }}</span>
        <span v-if="cls.score != null" class="species-picker__score">
          {{ (cls.score * 100).toFixed(0) }}%
        </span>
      </button>
    </section>

    <!-- Tier 2: full species tree (or filtered flat list when searching) -->
    <section class="species-picker__section">
      <h4 class="species-picker__heading">
        {{ query ? 'Matches' : 'Known species' }}
      </h4>
      <div v-if="query && filteredFlat.length === 0" class="species-picker__empty">
        No matches.
      </div>
      <!-- Flat results when searching -->
      <template v-if="query">
        <button
          v-for="sp in filteredFlat"
          :key="sp.common_name"
          type="button"
          class="species-picker__row"
          :class="{ 'species-picker__row--selected': selected === sp.common_name }"
          @click="$emit('select', { common_name: sp.common_name, scientific: sp.scientific })"
        >
          <span class="species-picker__label">{{ cap(sp.common_name) }}</span>
          <span v-if="sp.scientific" class="species-picker__sci">{{ sp.scientific }}</span>
          <span v-if="sp.custom" class="species-picker__badge">custom</span>
        </button>
      </template>
      <!-- Tree when not searching -->
      <div v-else class="species-picker__tree">
        <SpeciesTreeNode
          v-for="root in tree"
          :key="root.key"
          :node="root"
          :selected="selected"
          @select="$emit('select', { common_name: $event.common_name, scientific: $event.scientific })"
        />
      </div>
    </section>

    <!-- Tier 3: add a new species -->
    <section class="species-picker__section">
      <button
        v-if="!addOpen"
        type="button"
        class="species-picker__add-btn"
        @click="addOpen = true"
      >+ Add new species</button>
      <div v-else class="species-picker__add-form">
        <label class="species-picker__field">
          <span>Common name *</span>
          <input v-model="newCommon" type="text" placeholder="e.g. Bobcat" />
        </label>
        <label class="species-picker__field">
          <span>Scientific (optional)</span>
          <input v-model="newScientific" type="text" placeholder="e.g. Lynx rufus" />
        </label>
        <p v-if="addError" class="species-picker__error">{{ addError }}</p>
        <div class="species-picker__add-actions">
          <button type="button" class="species-picker__btn" :disabled="adding" @click="cancelAdd">Cancel</button>
          <button type="button" class="species-picker__btn species-picker__btn--primary" :disabled="adding || !newCommon.trim()" @click="submitAdd">
            {{ adding ? 'Adding…' : 'Add' }}
          </button>
        </div>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import SpeciesTreeNode from './SpeciesTreeNode.vue'

const props = defineProps({
  // From useSpeciesCatalog
  topFive:    { type: Array,  default: () => [] },
  tree:       { type: Array,  default: () => [] },
  flatSpecies:{ type: Array,  default: () => [] },
  addCustom:  { type: Function, required: true },
  // Currently-selected common_name (for highlight)
  selected:   { type: String, default: '' },
  autofocus:  { type: Boolean, default: true },
})
const emit = defineEmits(['select'])

const searchRef = ref(null)
const query     = ref('')
const addOpen   = ref(false)
const newCommon     = ref('')
const newScientific = ref('')
const adding    = ref(false)
const addError  = ref('')

const tierOne = computed(() => props.topFive)

const filteredFlat = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return []
  return props.flatSpecies.filter(sp =>
    sp.common_name.toLowerCase().includes(q) ||
    sp.scientific?.toLowerCase().includes(q),
  )
})

function cap(s) { return s ? s.charAt(0).toUpperCase() + s.slice(1) : s }

function cancelAdd() {
  addOpen.value = false
  newCommon.value = ''
  newScientific.value = ''
  addError.value = ''
}

async function submitAdd() {
  const cn = newCommon.value.trim()
  if (!cn) return
  adding.value = true
  addError.value = ''
  try {
    const sp = await props.addCustom({
      common_name: cn,
      scientific:  newScientific.value.trim(),
    })
    addOpen.value = false
    newCommon.value = ''
    newScientific.value = ''
    emit('select', { common_name: sp.common_name, scientific: sp.scientific })
  } catch (e) {
    addError.value = `Add failed: ${e.message}`
  } finally {
    adding.value = false
  }
}

onMounted(() => {
  if (props.autofocus) searchRef.value?.focus()
})

// Reset the inline add-form whenever the picker is reused for a different
// detection — prevents stale text from leaking between popovers.
watch(() => props.selected, () => { addError.value = '' })
</script>

<style scoped>
.species-picker {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 280px;
  max-height: 60vh;
}

.species-picker__search {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 6px 10px;
  font: inherit;
  font-size: 13px;
  flex-shrink: 0;
}

.species-picker__search:focus {
  outline: none;
  border-color: var(--accent, #2d7d46);
}

.species-picker__section {
  display: flex;
  flex-direction: column;
  gap: 2px;
  flex-shrink: 0;
}

.species-picker__section:nth-child(3) {
  /* The tree is the only section that needs to scroll */
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.species-picker__heading {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  margin: 4px 0 2px;
}

.species-picker__row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 5px 8px;
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
  border-radius: 4px;
}

.species-picker__row:hover { background: var(--surface2); }

.species-picker__row--selected {
  background: var(--accent, #2d7d46);
  color: white;
}

.species-picker__label { flex: 1; }

.species-picker__sci {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

.species-picker__row--selected .species-picker__sci,
.species-picker__row--selected .species-picker__score,
.species-picker__row--selected .species-picker__badge { color: rgba(255,255,255,0.85); }

.species-picker__score {
  font-size: 11px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.species-picker__badge {
  font-size: 10px;
  background: var(--surface2);
  color: var(--text-muted);
  padding: 1px 5px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

.species-picker__empty {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
  padding: 6px 8px;
}

.species-picker__tree { display: flex; flex-direction: column; }

.species-picker__add-btn {
  background: var(--surface2);
  border: 1px dashed var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 6px 10px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.species-picker__add-btn:hover { color: var(--text); border-color: var(--accent, #2d7d46); }

.species-picker__add-form {
  display: flex;
  flex-direction: column;
  gap: 6px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px;
}

.species-picker__field {
  display: flex;
  flex-direction: column;
  gap: 3px;
  font-size: 11px;
  color: var(--text-muted);
}

.species-picker__field input {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 4px;
  color: var(--text);
  padding: 4px 8px;
  font: inherit;
  font-size: 12px;
}
.species-picker__field input:focus {
  outline: none;
  border-color: var(--accent, #2d7d46);
}

.species-picker__error {
  margin: 0;
  font-size: 11px;
  color: #f87171;
}

.species-picker__add-actions {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
}

.species-picker__btn {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 4px 10px;
  font: inherit;
  font-size: 12px;
  cursor: pointer;
}
.species-picker__btn:hover:not(:disabled) { background: var(--surface2); }
.species-picker__btn:disabled { opacity: 0.5; cursor: default; }
.species-picker__btn--primary {
  background: var(--accent, #2d7d46);
  border-color: var(--accent, #2d7d46);
  color: white;
}
.species-picker__btn--primary:hover:not(:disabled) { background: #246d3a; }
</style>
