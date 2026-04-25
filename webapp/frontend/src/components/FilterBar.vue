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
      <select class="filterbar__select" :value="filters.species" @change="emit('update', { species: $event.target.value })">
        <option value="">All species</option>
        <option v-for="s in species" :key="s" :value="s">{{ capitalize(s) }}</option>
      </select>
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

    <div class="filterbar__footer">
      <span class="filterbar__count">{{ filtered }} / {{ total }}</span>
      <button class="filterbar__clear" @click="clearFilters">Clear</button>
    </div>
  </aside>
</template>

<script setup>
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

const CATEGORIES = [
  { key: 'animal',  label: 'Animal' },
  { key: 'human',   label: 'Human' },
  { key: 'vehicle', label: 'Vehicle' },
  { key: 'blank',   label: 'Blank' },
  { key: 'unknown', label: 'Unknown' },
]

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
    dateFrom: props.dateFromMin ?? '',
    dateTo: props.dateToMax ?? '',
    hour: null,
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
