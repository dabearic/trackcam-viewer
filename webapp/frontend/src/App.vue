<template>
  <div class="app">
    <header class="app-header">
      <div class="app-header__title">
        <span class="app-header__icon">📷</span>
        TrailCam Viewer
      </div>
      <div v-if="!loading" class="app-header__stats">
        <span>{{ stats.events }} events</span>
        <span>{{ stats.images }} images</span>
        <span>{{ stats.species }} species</span>
      </div>
    </header>

    <div class="app-body">
      <FilterBar
        :species="allSpecies"
        :filters="filters"
        :total="predictions.length"
        :filtered="filteredPredictions.length"
        @update="Object.assign(filters, $event)"
      />

      <main class="app-main">
        <div v-if="loading" class="state-msg">Loading predictions…</div>
        <div v-else-if="error" class="state-msg state-msg--error">{{ error }}</div>
        <div v-else-if="groupedEvents.length === 0" class="state-msg">No images match the current filters.</div>
        <ImageGallery
          v-else
          :events="groupedEvents"
          @select="openModal"
        />
      </main>
    </div>

    <ImageModal
      v-if="selectedImage"
      :image="selectedImage"
      :all-images="filteredPredictions"
      @close="selectedImage = null"
      @navigate="openModal"
    />
  </div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import FilterBar from './components/FilterBar.vue'
import ImageGallery from './components/ImageGallery.vue'
import ImageModal from './components/ImageModal.vue'

const predictions = ref([])
const loading = ref(true)
const error = ref(null)
const selectedImage = ref(null)

const filters = reactive({
  species: '',
  minConfidence: 0,
  categories: ['animal', 'human', 'vehicle', 'blank', 'unknown'],
})

function getCategory(pred) {
  const name = pred.prediction?.common_name?.toLowerCase()
  if (!name) return 'unknown'
  if (name === 'blank') return 'blank'
  if (name === 'human') return 'human'
  if (name === 'vehicle') return 'vehicle'
  // animal = anything with a top detection category "1" or non-human/vehicle species
  const hasAnimalDetection = pred.detections?.some(d => d.category === '1')
  if (hasAnimalDetection) return 'animal'
  return 'animal'
}

const filteredPredictions = computed(() => {
  return predictions.value.filter(p => {
    const cat = getCategory(p)
    if (!filters.categories.includes(cat)) return false
    if (filters.species && p.prediction?.common_name !== filters.species) return false
    if (filters.minConfidence > 0 && (p.prediction_score ?? 0) < filters.minConfidence / 100) return false
    return true
  })
})

// Group images by timestamp prefix (first 14 chars of filename = YYYYMMDDHHMMSS)
const groupedEvents = computed(() => {
  const groups = new Map()
  for (const pred of filteredPredictions.value) {
    const ts = pred.filename.substring(0, 14)
    if (!groups.has(ts)) groups.set(ts, [])
    groups.get(ts).push(pred)
  }
  return Array.from(groups.entries())
    .map(([ts, images]) => ({ timestamp: ts, date: parseTimestamp(ts), images }))
    .sort((a, b) => a.timestamp.localeCompare(b.timestamp))
})

const allSpecies = computed(() => {
  const names = predictions.value
    .map(p => p.prediction?.common_name)
    .filter(Boolean)
  return [...new Set(names)].sort()
})

const stats = computed(() => ({
  events: groupedEvents.value.length,
  images: filteredPredictions.value.length,
  species: new Set(filteredPredictions.value.map(p => p.prediction?.common_name).filter(Boolean)).size,
}))

function parseTimestamp(ts) {
  // "20260330190432" → Date
  const y = ts.slice(0, 4), mo = ts.slice(4, 6), d = ts.slice(6, 8)
  const h = ts.slice(8, 10), mi = ts.slice(10, 12), s = ts.slice(12, 14)
  return new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}`)
}

function openModal(image) {
  selectedImage.value = image
}

onMounted(async () => {
  try {
    const res = await fetch('/api/predictions')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    predictions.value = data.predictions
  } catch (e) {
    error.value = `Failed to load predictions: ${e.message}`
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.app {
  display: flex;
  flex-direction: column;
  height: 100vh;
  overflow: hidden;
}

.app-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 12px 20px;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.app-header__title {
  font-size: 18px;
  font-weight: 700;
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-header__icon {
  font-size: 20px;
}

.app-header__stats {
  display: flex;
  gap: 20px;
  color: var(--text-muted);
  font-size: 13px;
}

.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.app-main {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.state-msg {
  text-align: center;
  padding: 60px 20px;
  color: var(--text-muted);
  font-size: 15px;
}

.state-msg--error {
  color: #f87171;
}
</style>
