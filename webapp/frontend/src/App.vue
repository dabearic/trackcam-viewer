<template>
  <!-- Login screen -->
  <div v-if="authReady && !currentUser && AUTH_ENABLED" class="login-screen">
    <div class="login-card">
      <span class="login-card__icon">📷</span>
      <h1 class="login-card__title">TrailCam Viewer</h1>
      <p class="login-card__subtitle">Sign in to view your trail camera images</p>
      <button class="login-card__btn" :disabled="signingIn" @click="signIn">
        <svg class="login-card__google-icon" viewBox="0 0 24 24">
          <path fill="#4285F4" d="M22.56 12.25c0-.78-.07-1.53-.2-2.25H12v4.26h5.92c-.26 1.37-1.04 2.53-2.21 3.31v2.77h3.57c2.08-1.92 3.28-4.74 3.28-8.09z"/>
          <path fill="#34A853" d="M12 23c2.97 0 5.46-.98 7.28-2.66l-3.57-2.77c-.98.66-2.23 1.06-3.71 1.06-2.86 0-5.29-1.93-6.16-4.53H2.18v2.84C3.99 20.53 7.7 23 12 23z"/>
          <path fill="#FBBC05" d="M5.84 14.09c-.22-.66-.35-1.36-.35-2.09s.13-1.43.35-2.09V7.07H2.18C1.43 8.55 1 10.22 1 12s.43 3.45 1.18 4.93l3.66-2.84z"/>
          <path fill="#EA4335" d="M12 5.38c1.62 0 3.06.56 4.21 1.64l3.15-3.15C17.45 2.09 14.97 1 12 1 7.7 1 3.99 3.47 2.18 7.07l3.66 2.84c.87-2.6 3.3-4.53 6.16-4.53z"/>
        </svg>
        {{ signingIn ? 'Signing in…' : 'Sign in with Google' }}
      </button>
      <p v-if="signInError" class="login-card__error">{{ signInError }}</p>
    </div>
  </div>

  <!-- Main app -->
  <div v-else-if="authReady" class="app">
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
      <div class="app-header__right">
        <button class="app-header__process-btn" @click="showProcess = true">+ Add Photos</button>
        <button v-if="currentUser" class="app-header__user-btn" :title="`Sign out ${currentUser.email}`" @click="handleSignOut">
          <img v-if="currentUser.photoURL" :src="currentUser.photoURL" class="app-header__avatar" referrerpolicy="no-referrer" />
          <span v-else>{{ currentUser.email }}</span>
        </button>
      </div>
    </header>

    <div class="app-body">
      <FilterBar
        :species="allSpecies"
        :filters="filters"
        :total="predictions.length"
        :filtered="filteredPredictions.length"
        :date-from-min="dataDateFrom"
        :date-to-max="dataDateTo"
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
          @day-select="selectedDay = $event"
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

    <DaySummary
      v-if="selectedDay"
      :day="selectedDay"
      @close="selectedDay = null"
    />

    <ProcessModal
      v-if="showProcess"
      @close="showProcess = false"
      @done="onProcessDone"
    />
  </div>

  <!-- Auth initialising -->
  <div v-else class="state-msg">Loading…</div>
</template>

<script setup>
import { ref, reactive, computed, onMounted } from 'vue'
import FilterBar from './components/FilterBar.vue'
import ImageGallery from './components/ImageGallery.vue'
import ImageModal from './components/ImageModal.vue'
import DaySummary from './components/DaySummary.vue'
import ProcessModal from './components/ProcessModal.vue'
import { auth, AUTH_ENABLED, apiFetch, signInWithGoogle, signOutUser, onIdTokenChanged } from './firebase.js'

const predictions  = ref([])
const loading      = ref(false)
const error        = ref(null)
const selectedImage = ref(null)
const selectedDay  = ref(null)
const showProcess  = ref(false)
const dataDateFrom = ref('')
const dataDateTo   = ref('')

const currentUser  = ref(null)
const authReady    = ref(false)
const signingIn    = ref(false)
const signInError  = ref('')

const filters = reactive({
  species: '',
  minConfidence: 0,
  categories: ['animal', 'human', 'vehicle', 'blank', 'unknown'],
  dateFrom: '',
  dateTo: '',
})

// ── Auth ──────────────────────────────────────────────────────────────────────

async function signIn() {
  signingIn.value  = true
  signInError.value = ''
  try {
    await signInWithGoogle()
  } catch (e) {
    signInError.value = e.message
  } finally {
    signingIn.value = false
  }
}

async function handleSignOut() {
  await signOutUser()
  predictions.value = []
}

// ── Data loading ──────────────────────────────────────────────────────────────

async function loadPredictions() {
  loading.value = true
  error.value   = null
  try {
    const res = await apiFetch('/api/predictions')
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    predictions.value = data.predictions
    _updateDateBounds(data.predictions)
  } catch (e) {
    error.value = `Failed to load predictions: ${e.message}`
  } finally {
    loading.value = false
  }
}

function _updateDateBounds(preds) {
  const dates = preds.map(p => predDate(p)).filter(Boolean).sort()
  if (dates.length) {
    dataDateFrom.value = dates[0]
    dataDateTo.value   = dates[dates.length - 1]
    filters.dateFrom   = dates[0]
    filters.dateTo     = dates[dates.length - 1]
  }
}

// ── Filtering & grouping ──────────────────────────────────────────────────────

function getCategory(pred) {
  const name = pred.prediction?.common_name?.toLowerCase()
  if (!name) return 'unknown'
  if (name === 'blank') return 'blank'
  if (name === 'human') return 'human'
  if (name === 'vehicle') return 'vehicle'
  const hasAnimalDetection = pred.detections?.some(d => d.category === '1')
  if (hasAnimalDetection) return 'animal'
  return 'animal'
}

function timestampOf(pred) {
  // Prefer EXIF-derived captured_at; fall back to the first 14 chars of the filename.
  if (pred.captured_at) return pred.captured_at
  return pred.filename ? pred.filename.substring(0, 14) : ''
}

const filteredPredictions = computed(() => {
  const from = filters.dateFrom
  const to   = filters.dateTo
  return predictions.value.filter(p => {
    const cat = getCategory(p)
    if (!filters.categories.includes(cat)) return false
    if (filters.species && p.prediction?.common_name !== filters.species) return false
    if (filters.minConfidence > 0 && (p.prediction_score ?? 0) < filters.minConfidence / 100) return false
    if (from || to) {
      const ts = timestampOf(p).substring(0, 8)
      if (ts.length < 8) return false
      const date = `${ts.slice(0,4)}-${ts.slice(4,6)}-${ts.slice(6,8)}`
      if (from && date < from) return false
      if (to   && date > to)   return false
    }
    return true
  })
})

const groupedEvents = computed(() => {
  const groups = new Map()
  for (const pred of filteredPredictions.value) {
    const ts = timestampOf(pred)
    if (!groups.has(ts)) groups.set(ts, [])
    groups.get(ts).push(pred)
  }
  return Array.from(groups.entries())
    .map(([ts, images]) => ({ timestamp: ts, date: parseTimestamp(ts), images }))
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
})

const allSpecies = computed(() => {
  const names = predictions.value.map(p => p.prediction?.common_name).filter(Boolean)
  return [...new Set(names)].sort()
})

const stats = computed(() => ({
  events:  groupedEvents.value.length,
  images:  filteredPredictions.value.length,
  species: new Set(filteredPredictions.value.map(p => p.prediction?.common_name).filter(Boolean)).size,
}))

function parseTimestamp(ts) {
  const y = ts.slice(0,4), mo = ts.slice(4,6), d = ts.slice(6,8)
  const h = ts.slice(8,10), mi = ts.slice(10,12), s = ts.slice(12,14)
  return new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}`)
}

function predDate(pred) {
  const ts = timestampOf(pred).substring(0, 8)
  if (ts.length < 8) return ''
  return `${ts.slice(0,4)}-${ts.slice(4,6)}-${ts.slice(6,8)}`
}

function openModal(image) { selectedImage.value = image }

async function onProcessDone() {
  showProcess.value = false
  await loadPredictions()
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────

onMounted(() => {
  if (!AUTH_ENABLED) {
    // Local dev — skip auth, load immediately
    authReady.value = true
    loadPredictions()
    return
  }

  // Cloud — wait for Firebase auth state before loading
  onIdTokenChanged(auth, (user) => {
    const wasReady = authReady.value
    currentUser.value = user
    authReady.value   = true

    if (user && !wasReady) {
      // First sign-in / page load while signed in
      loadPredictions()
    } else if (!user) {
      predictions.value = []
    }
  })
})
</script>

<style scoped>
/* ── Login screen ─────────────────────────────────────────────────────────── */
.login-screen {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: var(--bg);
}

.login-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 40px 32px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
  width: min(380px, 90vw);
  text-align: center;
}

.login-card__icon { font-size: 48px; }

.login-card__title {
  font-size: 22px;
  font-weight: 700;
  margin: 0;
}

.login-card__subtitle {
  font-size: 14px;
  color: var(--text-muted);
  margin: 0;
}

.login-card__btn {
  display: flex;
  align-items: center;
  gap: 10px;
  background: #fff;
  color: #333;
  border: 1px solid #ddd;
  border-radius: var(--radius);
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  width: 100%;
  justify-content: center;
  transition: background 0.15s;
}

.login-card__btn:hover:not(:disabled) { background: #f5f5f5; }
.login-card__btn:disabled { opacity: 0.5; cursor: default; }

.login-card__google-icon { width: 18px; height: 18px; flex-shrink: 0; }

.login-card__error {
  font-size: 13px;
  color: #f87171;
  margin: 0;
}

/* ── Main app ─────────────────────────────────────────────────────────────── */
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

.app-header__icon { font-size: 20px; }

.app-header__stats {
  display: flex;
  gap: 20px;
  color: var(--text-muted);
  font-size: 13px;
}

.app-header__right {
  display: flex;
  align-items: center;
  gap: 10px;
}

.app-header__process-btn {
  background: #14532d;
  border: 1px solid var(--animal);
  border-radius: var(--radius);
  color: var(--animal);
  padding: 5px 14px;
  font: inherit;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.15s;
}

.app-header__process-btn:hover { background: #166534; }

.app-header__user-btn {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 3px;
  cursor: pointer;
  display: flex;
  align-items: center;
  font-size: 12px;
  gap: 6px;
}

.app-header__user-btn:hover { color: var(--text); }

.app-header__avatar {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  display: block;
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

.state-msg--error { color: #f87171; }
</style>
