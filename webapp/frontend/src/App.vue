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
      <div class="app-header__views">
        <button
          class="app-header__view-btn"
          :class="{ 'app-header__view-btn--active': view === 'gallery' }"
          @click="view = 'gallery'"
        >Gallery</button>
        <button
          class="app-header__view-btn"
          :class="{ 'app-header__view-btn--active': view === 'species' }"
          @click="view = 'species'"
        >Species</button>
      </div>
      <div class="app-header__right">
        <button
          v-if="view === 'gallery'"
          class="app-header__filter-toggle"
          :class="{ 'app-header__filter-toggle--active': filtersOpen }"
          @click="filtersOpen = !filtersOpen"
        >Filters</button>
        <button class="app-header__process-btn" @click="showProcess = true">+ Add Photos</button>
        <button v-if="currentUser" class="app-header__user-btn" :title="`Sign out ${currentUser.email}`" @click="handleSignOut">
          <img v-if="currentUser.photoURL" :src="currentUser.photoURL" class="app-header__avatar" referrerpolicy="no-referrer" />
          <span v-else>{{ currentUser.email }}</span>
        </button>
      </div>
    </header>

    <div class="app-body" :class="{ 'app-body--filters-open': filtersOpen }">
      <FilterBar
        v-if="view === 'gallery'"
        :species="allSpecies"
        :folders="allFolders"
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
        <template v-else-if="view === 'gallery'">
          <div v-if="groupedEvents.length === 0" class="state-msg">No images match the current filters.</div>
          <ImageGallery
            v-else
            :events="groupedEvents"
            @select="openModal"
            @day-select="selectedDay = $event"
            @delete="requestDelete"
          />
        </template>
        <SpeciesView
          v-else
          :predictions="predictions"
          @select="openModal"
          @filter="applyHistogramFilter"
        />
      </main>
    </div>

    <ImageModal
      v-if="selectedImage"
      :image="selectedImage"
      :all-images="filteredPredictions"
      :predictions="predictions"
      @close="selectedImage = null"
      @navigate="openModal"
      @deleted="onImageDeleted"
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

    <!-- Gallery-tile delete confirmation -->
    <div
      v-if="pendingDelete"
      class="confirm-backdrop"
      @click.self="cancelDelete"
    >
      <div class="confirm">
        <h3 class="confirm__title">Delete this image?</h3>
        <p class="confirm__body">
          <strong>{{ pendingDelete.filename }}</strong> and any cropped versions
          will be permanently removed from storage. This cannot be undone.
        </p>
        <p v-if="deleteError" class="confirm__error">{{ deleteError }}</p>
        <div class="confirm__actions">
          <button class="confirm__btn" :disabled="deleting" @click="cancelDelete">Cancel</button>
          <button class="confirm__btn confirm__btn--danger" :disabled="deleting" @click="doDelete">
            {{ deleting ? 'Deleting…' : 'Delete' }}
          </button>
        </div>
      </div>
    </div>
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
import SpeciesView from './components/SpeciesView.vue'
import { auth, AUTH_ENABLED, apiFetch, signInWithGoogle, signOutUser, onIdTokenChanged } from './firebase.js'

const predictions  = ref([])
const loading      = ref(false)
const error        = ref(null)
const selectedImage = ref(null)
const selectedDay  = ref(null)
const showProcess  = ref(false)
const filtersOpen  = ref(false)
const view         = ref('species')  // 'gallery' | 'species'
const dataDateFrom = ref('')
const dataDateTo   = ref('')

const currentUser  = ref(null)
const authReady    = ref(false)
const signingIn    = ref(false)
const signInError  = ref('')

const filters = reactive({
  folder: '',
  species: '',
  minConfidence: 0,
  categories: ['animal', 'human', 'vehicle', 'blank', 'unknown'],
  categoryMode: 'any',  // 'any' | 'all'
  dateFrom: '',
  dateTo: '',
  hour: null,
  month: null,
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
  const dates = preds.map(predDate).filter(Boolean).sort()
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

// All categories present on a prediction. Detections drive the multi-category
// case (e.g. an image with both a human and an animal detection); the image-
// level prediction adds blank/human/vehicle when it disagrees with detections,
// and 'animal' when the species classifier produced a name without a matching
// detection box. Used by the category filter's "all of" mode.
function getCategories(pred) {
  const cats = new Set()
  for (const d of (pred.detections ?? [])) {
    if (d.category === '1') cats.add('animal')
    else if (d.category === '2') cats.add('human')
    else if (d.category === '3') cats.add('vehicle')
  }
  const name = pred.prediction?.common_name?.toLowerCase()
  if (name === 'blank') cats.add('blank')
  else if (name === 'human') cats.add('human')
  else if (name === 'vehicle') cats.add('vehicle')
  else if (name && cats.size === 0) cats.add('animal')
  if (cats.size === 0) cats.add('unknown')
  return cats
}

const filteredPredictions = computed(() => {
  const from = filters.dateFrom
  const to   = filters.dateTo
  return predictions.value.filter(p => {
    if (filters.categories.length === 0) return false
    const cats = getCategories(p)
    const matches = filters.categoryMode === 'all'
      ? filters.categories.every(c => cats.has(c))
      : filters.categories.some(c => cats.has(c))
    if (!matches) return false
    if (filters.folder && p.folder !== filters.folder) return false
    if (filters.species && p.prediction?.common_name !== filters.species) return false
    if (filters.species) {
      // Match either image-level prediction OR a manual detection label.
      // Without the second leg, filtering by a species the user only added
      // via single-detection edit would return zero images.
      const matches =
        p.prediction?.common_name === filters.species ||
        (p.detections ?? []).some(d => d.manual && d.label === filters.species)
      if (!matches) return false
    }
    if (filters.minConfidence > 0 && (p.prediction_score ?? 0) < filters.minConfidence / 100) return false
    if (filters.hour !== null) {
      const h = predHour(p)
      if (h !== filters.hour) return false
    }
    if (filters.month !== null) {
      const m = predMonth(p)
      if (m !== filters.month) return false
    }
    if (from || to) {
      const date = predDate(p)
      if (!date) return false
      if (from && date < from) return false
      if (to   && date > to)   return false
    }
    return true
  })
})

const groupedEvents = computed(() => {
  const groups = new Map()
  for (const pred of filteredPredictions.value) {
    const ts = predTs(pred)
    if (!ts) continue
    if (!groups.has(ts)) groups.set(ts, [])
    groups.get(ts).push(pred)
  }
  return Array.from(groups.entries())
    .map(([ts, images]) => ({ timestamp: ts, date: parseTimestamp(ts), images }))
    .sort((a, b) => b.timestamp.localeCompare(a.timestamp))
})

// Distinct species names for the filter dropdown. Pulls from both the
// image-level inference prediction AND any manually-edited detection
// labels — without the second source the filter wouldn't surface species
// the user added by hand until they reloaded against new inference output.
function _speciesNamesFor(preds) {
  const names = new Set()
  for (const p of preds) {
    if (p.prediction?.common_name) names.add(p.prediction.common_name)
    for (const d of (p.detections ?? [])) {
      if (d.manual && d.label) names.add(d.label)
    }
  }
  return names
}

const allSpecies = computed(() =>
  [..._speciesNamesFor(predictions.value)].sort(),
)

const allFolders = computed(() => {
  const folders = predictions.value.map(p => p.folder).filter(Boolean)
  return [...new Set(folders)].sort()
})

const stats = computed(() => ({
  events:  groupedEvents.value.length,
  images:  filteredPredictions.value.length,
  species: _speciesNamesFor(filteredPredictions.value).size,
}))

function parseTimestamp(ts) {
  if (!ts || ts.length < 14) return null
  const y = ts.slice(0,4), mo = ts.slice(4,6), d = ts.slice(6,8)
  const h = ts.slice(8,10), mi = ts.slice(10,12), s = ts.slice(12,14)
  return new Date(`${y}-${mo}-${d}T${h}:${mi}:${s}`)
}

// Compact 14-char timestamp (YYYYMMDDHHMMSS) preferred from EXIF-derived
// taken_at, falling back to a YYYYMMDDHHMMSS filename prefix. Returns ''
// when neither is available.
function predTs(p) {
  if (p.taken_at) return p.taken_at.replace(/[-T:]/g, '').slice(0, 14)
  const m = p.filename?.match(/^(\d{14})/)
  return m ? m[1] : ''
}

function predDate(p) {
  const ts = predTs(p)
  if (!ts) return ''
  return `${ts.slice(0,4)}-${ts.slice(4,6)}-${ts.slice(6,8)}`
}

function predHour(p) {
  const ts = predTs(p)
  return ts.length >= 10 ? parseInt(ts.slice(8, 10), 10) : -1
}

function predMonth(p) {
  const ts = predTs(p)
  return ts.length >= 6 ? parseInt(ts.slice(4, 6), 10) - 1 : -1
}

function openModal(image) { selectedImage.value = image }

function onImageDeleted(image) {
  const remaining = filteredPredictions.value
  const idx       = remaining.indexOf(image)
  const next      = remaining[idx + 1] ?? remaining[idx - 1] ?? null
  predictions.value = predictions.value.filter(p => p !== image)
  selectedImage.value = next && next !== image ? next : null
}

// ── Gallery-tile delete ───────────────────────────────────────────────────────
const pendingDelete = ref(null)
const deleting      = ref(false)
const deleteError   = ref('')

function requestDelete(image) {
  pendingDelete.value = image
  deleteError.value   = ''
}

function cancelDelete() {
  if (deleting.value) return
  pendingDelete.value = null
  deleteError.value   = ''
}

async function doDelete() {
  const image = pendingDelete.value
  if (!image) return
  deleting.value = true
  deleteError.value = ''
  try {
    const res = await apiFetch(
      `/api/predictions?path=${encodeURIComponent(image.filepath)}`,
      { method: 'DELETE' },
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    predictions.value  = predictions.value.filter(p => p !== image)
    pendingDelete.value = null
  } catch (e) {
    deleteError.value = `Delete failed: ${e.message}`
  } finally {
    deleting.value = false
  }
}

function applyHistogramFilter({ species, hour = null, month = null }) {
  filters.species = species
  filters.hour    = hour
  filters.month   = month
  view.value      = 'gallery'
}

async function onProcessDone(folder) {
  showProcess.value = false
  await loadPredictions()
  if (folder && allFolders.value.includes(folder)) {
    filters.folder = folder
    view.value     = 'gallery'
  }
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

.app-header__views {
  display: flex;
  gap: 4px;
  background: var(--bg-alt, #111);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 2px;
}

.app-header__view-btn {
  background: none;
  border: none;
  color: var(--text-muted);
  padding: 4px 12px;
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  border-radius: 4px;
  transition: background 0.15s, color 0.15s;
}

.app-header__view-btn:hover { color: var(--text); }

.app-header__view-btn--active {
  background: var(--accent, #2d7d46);
  color: white;
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

.app-header__filter-toggle {
  display: none;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 5px 12px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
}

.app-header__filter-toggle--active {
  background: var(--accent, #2d7d46);
  color: white;
  border-color: var(--accent, #2d7d46);
}

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

/* ── Confirmation dialog (gallery-tile delete) ────────────────────────────── */
.confirm-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.7);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 16px;
}

.confirm {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  width: min(420px, 100%);
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.confirm__title {
  margin: 0;
  font-size: 15px;
  font-weight: 600;
  color: var(--text);
}

.confirm__body {
  margin: 0;
  font-size: 13px;
  color: var(--text-muted);
  line-height: 1.5;
}

.confirm__body strong { color: var(--text); }

.confirm__error {
  margin: 0;
  font-size: 12px;
  color: #f87171;
}

.confirm__actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 6px;
}

.confirm__btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 6px 14px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}

.confirm__btn:hover:not(:disabled) { background: var(--surface); }
.confirm__btn:disabled { opacity: 0.5; cursor: default; }

.confirm__btn--danger {
  background: #7f1d1d;
  border-color: #b91c1c;
  color: #fee2e2;
}

.confirm__btn--danger:hover:not(:disabled) {
  background: #991b1b;
}

/* ── Narrow viewports (portrait phones) ─────────────────────────────────────
   The FilterBar's 220px sidebar leaves almost no room for the gallery on a
   portrait phone, so collapse it into a togglable drawer above the gallery.
   The "Filters" button in the header is hidden on wide screens — there the
   sidebar is always visible. */
@media (max-width: 720px) {
  .app-header {
    padding: 10px 12px;
    gap: 8px;
    flex-wrap: wrap;
  }
  .app-header__stats { display: none; }
  .app-header__filter-toggle { display: inline-block; }

  .app-body { flex-direction: column; }
  .app-body :deep(.filterbar) {
    width: 100%;
    max-height: 50vh;
    border-right: none;
    border-bottom: 1px solid var(--border);
    display: none;
  }
  .app-body--filters-open :deep(.filterbar) {
    display: flex;
  }
  .app-main { padding: 10px; }
}
</style>
