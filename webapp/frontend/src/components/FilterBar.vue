<template>
  <aside class="filterbar">
    <div v-if="folders.length" class="filterbar__section">
      <label class="filterbar__label">Folder</label>
      <select class="filterbar__select" :value="filters.folder" @change="emit('update', { folder: $event.target.value })">
        <option value="">All folders</option>
        <option v-for="f in folders" :key="f" :value="f">{{ f }}</option>
      </select>
    </div>

    <div class="filterbar__section">
      <label class="filterbar__label">Species</label>
      <div class="filterbar__combo">
        <input
          ref="speciesInput"
          v-model="speciesQuery"
          type="text"
          class="filterbar__select"
          placeholder="All species"
          @focus="onSpeciesFocus"
          @keydown.esc="closeSpecies"
          @keydown.enter.prevent="commitFirstMatch"
        />
        <button
          v-if="filters.species"
          type="button"
          class="filterbar__combo-clear"
          title="Clear species filter"
          @mousedown.prevent="selectSpecies('')"
        >✕</button>
        <ul v-if="speciesOpen" class="filterbar__combo-list">
          <li
            class="filterbar__combo-item"
            :class="{ 'is-active': filters.species === '' }"
            @mousedown.prevent="selectSpecies('')"
          >All species</li>
          <li
            v-for="s in filteredSpecies"
            :key="s"
            class="filterbar__combo-item"
            :class="{ 'is-active': filters.species === s }"
            @mousedown.prevent="selectSpecies(s)"
          >{{ capitalize(s) }}</li>
          <li v-if="filteredSpecies.length === 0" class="filterbar__combo-empty">No matches</li>
        </ul>
      </div>
    </div>

    <div class="filterbar__section">
      <label class="filterbar__label">
        Min confidence
        <span class="filterbar__value">{{ filters.minConfidence }}%</span>
      </label>
      <input
        type="range"
        class="filterbar__range"
        :value="filters.minConfidence"
        min="0" max="100" step="5"
        @input="emit('update', { minConfidence: +$event.target.value })"
      />
    </div>

    <div class="filterbar__section">
      <label class="filterbar__label">Date range</label>
      <input
        type="date"
        class="filterbar__date"
        :value="filters.dateFrom"
        :min="dateFromMin"
        :max="filters.dateTo || dateToMax"
        @change="emit('update', { dateFrom: $event.target.value })"
      />
      <input
        type="date"
        class="filterbar__date"
        :value="filters.dateTo"
        :min="filters.dateFrom || dateFromMin"
        :max="dateToMax"
        @change="emit('update', { dateTo: $event.target.value })"
      />
    </div>

    <div class="filterbar__section">
      <label class="filterbar__label">Category</label>
      <div class="filterbar__mode">
        <label class="filterbar__mode-radio">
          <input
            type="radio"
            value="any"
            :checked="filters.categoryMode !== 'all'"
            @change="emit('update', { categoryMode: 'any' })"
          />
          any of
        </label>
        <label class="filterbar__mode-radio">
          <input
            type="radio"
            value="all"
            :checked="filters.categoryMode === 'all'"
            @change="emit('update', { categoryMode: 'all' })"
          />
          all of
        </label>
      </div>
      <div class="filterbar__checks">
        <label v-for="cat in CATEGORIES" :key="cat.key" class="filterbar__check">
          <input
            type="checkbox"
            :checked="filters.categories.includes(cat.key)"
            @change="toggleCategory(cat.key)"
          />
          <span :class="`badge badge--${cat.key}`">{{ cat.label }}</span>
        </label>
      </div>
    </div>

    <div v-if="filters.hour !== null" class="filterbar__section">
      <label class="filterbar__label">Hour filter</label>
      <div class="filterbar__chip">
        {{ filters.hour }}:00–{{ filters.hour }}:59
        <button class="filterbar__chip-clear" @click="emit('update', { hour: null })">✕</button>
      </div>
    </div>

    <div v-if="filters.month !== null" class="filterbar__section">
      <label class="filterbar__label">Month filter</label>
      <div class="filterbar__chip">
        {{ MONTH_NAMES[filters.month] }}
        <button class="filterbar__chip-clear" @click="emit('update', { month: null })">✕</button>
      </div>
    </div>

    <div class="filterbar__footer">
      <span class="filterbar__count">{{ filtered }} / {{ total }}</span>
      <button class="filterbar__clear" @click="clearFilters">Clear</button>
    </div>
  </aside>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'

const props = defineProps({
  species: Array,
  folders: { type: Array, default: () => [] },
  filters: Object,
  total: Number,
  filtered: Number,
  dateFromMin: String,
  dateToMax: String,
})

const emit = defineEmits(['update'])

const speciesInput = ref(null)
const speciesQuery = ref(capitalize(props.filters.species))
const speciesOpen  = ref(false)

watch(() => props.filters.species, (sp) => {
  if (!speciesOpen.value) speciesQuery.value = capitalize(sp)
})

const filteredSpecies = computed(() => {
  const q = speciesQuery.value.trim().toLowerCase()
  const selectedDisplay = capitalize(props.filters.species).toLowerCase()
  // When the input still shows the current selection, list everything so the
  // user can browse without having to clear first.
  if (!q || q === selectedDisplay) return props.species
  return props.species.filter(s => s.toLowerCase().includes(q))
})

function onSpeciesFocus(e) {
  speciesOpen.value = true
  e.target.select()
}

function closeSpecies() {
  speciesOpen.value = false
  speciesQuery.value = capitalize(props.filters.species)
  speciesInput.value?.blur()
}

function selectSpecies(s) {
  emit('update', { species: s })
  speciesQuery.value = capitalize(s)
  speciesOpen.value = false
  speciesInput.value?.blur()
}

function commitFirstMatch() {
  const match = filteredSpecies.value[0]
  if (match) selectSpecies(match)
  else selectSpecies('')
}

function onDocClick(e) {
  if (!speciesOpen.value) return
  if (speciesInput.value?.parentElement?.contains(e.target)) return
  closeSpecies()
}

onMounted(() => document.addEventListener('mousedown', onDocClick))
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocClick))

const CATEGORIES = [
  { key: 'animal',  label: 'Animal' },
  { key: 'human',   label: 'Human' },
  { key: 'vehicle', label: 'Vehicle' },
  { key: 'blank',   label: 'Blank' },
  { key: 'unknown', label: 'Unknown' },
]

const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

function toggleCategory(key) {
  const cats = props.filters.categories.includes(key)
    ? props.filters.categories.filter(c => c !== key)
    : [...props.filters.categories, key]
  emit('update', { categories: cats })
}

function clearFilters() {
  emit('update', {
    folder: '',
    species: '',
    minConfidence: 0,
    categories: CATEGORIES.map(c => c.key),
    categoryMode: 'any',
    dateFrom: props.dateFromMin ?? '',
    dateTo: props.dateToMax ?? '',
    hour: null,
    month: null,
  })
}
</script>

<style scoped>
.filterbar {
  width: 220px;
  flex-shrink: 0;
  background: var(--surface);
  border-right: 1px solid var(--border);
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 20px;
  overflow-y: auto;
}

.filterbar__section {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.filterbar__label {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
  display: flex;
  justify-content: space-between;
}

.filterbar__value {
  font-weight: 400;
  color: var(--text);
}

.filterbar__select {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 6px 10px;
  width: 100%;
  font: inherit;
}
.filterbar__select:focus {
  outline: none;
  border-color: var(--accent, #2d7d46);
}

.filterbar__combo {
  position: relative;
}
.filterbar__combo-clear {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  font-size: 12px;
  line-height: 1;
  padding: 2px 4px;
}
.filterbar__combo-clear:hover { color: var(--text); }
.filterbar__combo-list {
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  margin: 2px 0 0;
  padding: 2px 0;
  list-style: none;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 8px 20px rgba(0,0,0,0.35);
  max-height: 240px;
  overflow-y: auto;
  z-index: 30;
}
.filterbar__combo-item {
  padding: 5px 10px;
  font-size: 13px;
  color: var(--text);
  cursor: pointer;
}
.filterbar__combo-item:hover { background: var(--surface2); }
.filterbar__combo-item.is-active {
  background: var(--accent, #2d7d46);
  color: white;
}
.filterbar__combo-empty {
  padding: 6px 10px;
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.filterbar__range {
  width: 100%;
  accent-color: var(--animal);
}

.filterbar__date {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 6px 8px;
  width: 100%;
  color-scheme: dark;
}

.filterbar__checks {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.filterbar__mode {
  display: flex;
  gap: 12px;
  font-size: 12px;
  color: var(--text);
}
.filterbar__mode-radio {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  cursor: pointer;
}
.filterbar__mode-radio input[type="radio"] {
  accent-color: var(--animal);
  width: 13px;
  height: 13px;
  cursor: pointer;
}

.filterbar__check {
  display: flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
}

.filterbar__check input[type="checkbox"] {
  accent-color: var(--animal);
  width: 14px;
  height: 14px;
  cursor: pointer;
}

.filterbar__chip {
  display: flex;
  align-items: center;
  justify-content: space-between;
  background: var(--surface2);
  border: 1px solid var(--accent, #2d7d46);
  border-radius: var(--radius);
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text);
}
.filterbar__chip-clear {
  background: none;
  border: none;
  color: var(--text-muted);
  cursor: pointer;
  padding: 0 0 0 6px;
  font-size: 12px;
  line-height: 1;
}
.filterbar__chip-clear:hover { color: var(--text); }

.filterbar__footer {
  margin-top: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.filterbar__count {
  font-size: 12px;
  color: var(--text-muted);
}

.filterbar__clear {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 4px 10px;
  font-size: 12px;
  transition: color 0.15s;
}

.filterbar__clear:hover {
  color: var(--text);
}
</style>
