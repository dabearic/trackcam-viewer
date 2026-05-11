<template>
  <div class="backdrop" @click.self="canClose && $emit('close')">
    <div class="modal">

      <div class="modal__header">
        <h2 class="modal__title">Add Photos</h2>
        <button class="modal__close" :disabled="!canClose" @click="$emit('close')">✕</button>
      </div>

      <!-- ── Form ── -->
      <form v-if="phase === 'form'" class="modal__form" @submit.prevent="submit">

        <!-- File picker (cloud) or folder path (local) -->
        <div v-if="AUTH_ENABLED" class="field">
          <label class="field__label">Images</label>
          <div
            class="field__dropzone"
            :class="{ 'field__dropzone--active': dragging }"
            @dragover.prevent="dragging = true"
            @dragleave="dragging = false"
            @drop.prevent="onDrop"
            @click="fileInput.click()"
          >
            <span v-if="files.length === 0">Click or drag &amp; drop image files here</span>
            <span v-else>{{ files.length }} file(s) selected — click to change</span>
          </div>
          <input
            ref="fileInput"
            type="file"
            multiple
            accept="image/*"
            class="field__file-hidden"
            @change="onFileChange"
          />
          <div class="field">
            <label class="field__label">Folder name <span class="field__hint">organises images in storage</span></label>
            <input v-model="folder" class="field__input" placeholder="Photos-4-001" required />
          </div>
        </div>

        <!-- Local mode: folder path + browse -->
        <div v-else class="field">
          <label class="field__label">Folder path</label>
          <div class="field__row">
            <input
              v-model="folder"
              class="field__input"
              placeholder="C:\Users\you\Downloads\Photos-4-001"
              required
            />
            <button type="button" class="btn btn--browse" :disabled="browsing" @click="browse">
              {{ browsing ? '…' : 'Browse' }}
            </button>
          </div>
        </div>

        <div class="field field--row">
          <div class="field">
            <label class="field__label">Country <span class="field__hint">ISO 3166-1 alpha-3 (optional)</span></label>
            <input v-model="country" class="field__input" placeholder="GBR" maxlength="3" />
          </div>
          <div v-if="country.toUpperCase() === 'USA'" class="field">
            <label class="field__label">State <span class="field__hint">abbreviation</span></label>
            <input v-model="admin1Region" class="field__input" placeholder="CA" maxlength="2" />
          </div>
        </div>

        <div class="field">
          <div class="field__label-row">
            <label class="field__label">Location <span class="field__hint">optional</span></label>
            <button type="button" class="btn btn--locate" :disabled="locating" @click="useCurrentLocation">
              {{ locating ? 'Locating…' : '⊕ Use my location' }}
            </button>
          </div>
          <div class="field--row">
            <input v-model.number="latitude"  type="number" step="any" class="field__input" placeholder="Latitude" />
            <input v-model.number="longitude" type="number" step="any" class="field__input" placeholder="Longitude" />
          </div>
          <p v-if="locationError" class="field__error">{{ locationError }}</p>
        </div>

        <div v-if="submitError" class="modal__error">{{ submitError }}</div>
        <button
          type="submit"
          class="btn btn--primary"
          :disabled="submitting || (AUTH_ENABLED && files.length === 0)"
        >
          {{ submitting ? 'Starting…' : (AUTH_ENABLED ? 'Upload &amp; Process' : 'Run SpeciesNet') }}
        </button>
      </form>

      <!-- ── Upload progress (cloud only) ──
           The inference container is already cold-starting in parallel,
           so surface the live job status underneath the upload bar. -->
      <div v-else-if="phase === 'uploading'" class="modal__progress">
        <div class="progress__status">
          <span class="progress__dot progress__dot--running"></span>
          <span class="progress__message">Uploading {{ uploadDone }}/{{ uploadTotal }} files…</span>
        </div>
        <div class="progress__stage-track" style="margin-top:4px">
          <div class="progress__stage-fill" :style="{ width: uploadPct + '%' }"></div>
        </div>
        <div v-if="job.message" class="progress__status" style="margin-top:10px">
          <span :class="`progress__dot progress__dot--${job.status}`"></span>
          <span class="progress__message">{{ job.message }}</span>
          <span v-if="elapsedSec !== null" class="progress__elapsed">
            {{ formatElapsed(elapsedSec) }}
          </span>
        </div>

        <!-- Streaming thumbnail of the most-recently-classified animal
             (≥50% confidence). Appears as soon as inference has produced
             at least one qualifying prediction; updates in place every
             time a new one lands. -->
        <div v-if="showLatestCrop" class="latest-crop">
          <img
            :src="latestCropUrl"
            :alt="job.latest_animal_crop.common_name"
            class="latest-crop__img"
          />
          <div class="latest-crop__meta">
            <span class="latest-crop__heading">Latest classification</span>
            <span class="latest-crop__name">{{ capitalize(job.latest_animal_crop.common_name) }}</span>
            <span class="latest-crop__score">{{ Math.round(job.latest_animal_crop.score * 100) }}% confidence</span>
          </div>
        </div>
      </div>

      <!-- ── Inference progress ── -->
      <div v-else-if="phase === 'processing'" class="modal__progress">
        <div class="progress__status">
          <span :class="`progress__dot progress__dot--${job.status}`"></span>
          <span class="progress__message">{{ job.message }}</span>
          <span v-if="elapsedSec !== null && job.status !== 'done'" class="progress__elapsed">
            {{ formatElapsed(elapsedSec) }}
          </span>
          <span v-if="job.status === 'done'" class="progress__count">✓</span>
        </div>

        <!-- Streaming thumbnail of the most-recently-classified animal
             (≥50% confidence). Same panel as in the upload phase; lives
             here too so it stays visible as predictions stream in
             throughout inference. -->
        <div v-if="showLatestCrop" class="latest-crop">
          <img
            :src="latestCropUrl"
            :alt="job.latest_animal_crop.common_name"
            class="latest-crop__img"
          />
          <div class="latest-crop__meta">
            <span class="latest-crop__heading">Latest classification</span>
            <span class="latest-crop__name">{{ capitalize(job.latest_animal_crop.common_name) }}</span>
            <span class="latest-crop__score">{{ Math.round(job.latest_animal_crop.score * 100) }}% confidence</span>
          </div>
        </div>

        <div v-if="overallProgress" class="progress__stage">
          <div class="progress__stage-header">
            <span class="progress__stage-label">Inference</span>
            <span class="progress__stage-pct" :class="overallProgress.percent === 100 ? 'progress__stage-pct--done' : ''">
              {{ overallProgress.percent }}%
            </span>
          </div>
          <div class="progress__stage-track">
            <div
              class="progress__stage-fill"
              :class="overallProgress.percent === 100 ? 'progress__stage-fill--done' : ''"
              :style="{ width: overallProgress.percent + '%' }"
            ></div>
          </div>
        </div>

        <div v-if="job.status === 'error'" class="progress__error">
          <strong>Error:</strong> {{ job.message }}
        </div>

        <!-- Summary shown when the inference job completes -->
        <section v-if="job.status === 'done' && job.summary" class="summary">
          <header class="summary__header">
            <span class="summary__count">
              {{ job.summary.total }} image{{ job.summary.total === 1 ? '' : 's' }} processed
            </span>
            <span v-if="categoryEntries.length" class="summary__badges">
              <span
                v-for="[cat, n] in categoryEntries"
                :key="cat"
                :class="`badge badge--${cat}`"
              >{{ cat }}: {{ n }}</span>
            </span>
          </header>

          <!-- Gallery of every animal crop the streaming pipeline showed
               while the job was running. The reactive list (`seenCrops`)
               accumulates each unique latest_animal_crop snapshot during
               polling, so by the time the user reaches this summary
               panel they can re-visit every classification at a glance
               without leaving the dialog. -->
          <div v-if="seenCrops.length" class="summary__crops">
            <div
              v-for="crop in seenCrops"
              :key="crop.crop_gcs_path"
              class="summary__crop"
              :title="`${crop.filename} — ${capitalize(crop.common_name)} (${Math.round(crop.score * 100)}%)`"
            >
              <img
                :src="imageUrl(crop.crop_gcs_path)"
                :alt="crop.common_name"
                class="summary__crop-img"
              />
              <span class="summary__crop-label">{{ capitalize(crop.common_name) }}</span>
            </div>
          </div>

          <div v-if="categorySlices.length || speciesSlices.length" class="summary__charts">
            <div v-if="categorySlices.length" class="summary__chart">
              <h4 class="summary__chart-title">Categories</h4>
              <div class="summary__chart-row">
                <svg viewBox="0 0 100 100" class="pie" aria-hidden="true">
                  <circle v-if="categorySlices.length === 1" cx="50" cy="50" r="48" :fill="categorySlices[0].color" />
                  <path v-else v-for="s in categorySlices" :key="s.label" :d="s.path" :fill="s.color" />
                </svg>
                <ul class="summary__legend">
                  <li v-for="s in categorySlices" :key="s.label" class="summary__legend-row">
                    <span class="summary__legend-swatch" :style="{ background: s.color }"></span>
                    <span class="summary__legend-label">{{ capitalize(s.label) }}</span>
                    <span class="summary__legend-count">{{ s.value }} ({{ s.percent }}%)</span>
                  </li>
                </ul>
              </div>
            </div>
            <div v-if="speciesSlices.length" class="summary__chart">
              <h4 class="summary__chart-title">Species detections</h4>
              <div class="summary__chart-row">
                <svg viewBox="0 0 100 100" class="pie" aria-hidden="true">
                  <circle v-if="speciesSlices.length === 1" cx="50" cy="50" r="48" :fill="speciesSlices[0].color" />
                  <path v-else v-for="s in speciesSlices" :key="s.label" :d="s.path" :fill="s.color" />
                </svg>
                <ul class="summary__legend">
                  <li v-for="s in speciesSlices" :key="s.label" class="summary__legend-row">
                    <span class="summary__legend-swatch" :style="{ background: s.color }"></span>
                    <span class="summary__legend-label">{{ capitalize(s.label) }}</span>
                    <span class="summary__legend-count">{{ s.value }} ({{ s.percent }}%)</span>
                  </li>
                </ul>
              </div>
            </div>
          </div>
        </section>

        <!-- Raw log — hidden by default; revealed via the "more details…"
             toggle at the bottom of the dialog. -->
        <pre
          v-if="showLog && job.log?.length"
          ref="logEl"
          class="progress__log"
        >{{ job.log.join('\n') }}</pre>

        <div class="progress__actions">
          <button v-if="job.status === 'done'" class="btn btn--primary" @click="$emit('done', AUTH_ENABLED ? folder.trim() : '')">
            Reload gallery
          </button>
          <button v-if="job.status === 'error' || job.status === 'done'" class="btn" @click="reset">
            Process another folder
          </button>
        </div>

        <!-- Details disclosure — stays at the very bottom regardless of
             job status so the log is never shown without the user
             opting in. -->
        <button
          v-if="job.log?.length"
          class="progress__details-toggle"
          type="button"
          @click="showLog = !showLog"
        >{{ showLog ? 'Hide details' : 'More details…' }}</button>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'
import { AUTH_ENABLED, apiFetch, imageUrl } from '../firebase.js'

const emit = defineEmits(['close', 'done'])

// Form state
const folder       = ref('')
const files        = ref([])   // File objects (cloud mode)
const fileInput    = ref(null)
const dragging     = ref(false)
const browsing     = ref(false)
const country      = ref('')
const admin1Region = ref('')
const locating     = ref(false)
const locationError = ref('')
const latitude     = ref(null)
const longitude    = ref(null)
const submitError  = ref('')
// True while submit() is in flight. Without this, a double-click (or pressing
// Enter twice quickly) re-enters submit() before the prepare request returns,
// which mints a second job and uploads everything again — visible as the
// upload counter ticking past uploadTotal.
const submitting   = ref(false)

// Phase: 'form' | 'uploading' | 'processing'
const phase = ref('form')

// Upload progress
const uploadDone  = ref(0)
const uploadTotal = ref(0)
const uploadPct   = computed(() =>
  uploadTotal.value ? Math.round((uploadDone.value / uploadTotal.value) * 100) : 0
)

// Job polling
const jobId = ref(null)
const job   = ref({ status: 'running', message: 'Queued', log: [], progress: {} })
const logEl = ref(null)
let pollTimer = null

// Elapsed-seconds clock that starts when the processing phase begins.
// Updating a reactive ref every second is enough to render a live timer;
// the user gets visible reassurance that the app is still working even
// when `job.message` hasn't changed in a while (cold-start, model load).
const elapsedSec      = ref(null)
const processingStart = ref(null)
let   elapsedTimer    = null

const canClose = computed(() =>
  phase.value === 'form' ||
  (phase.value === 'processing' && (job.value.status === 'done' || job.value.status === 'error'))
)

const progressEntries = computed(() => Object.entries(job.value.progress ?? {}))

// Aggregate the per-stage tqdm bars (detector_preprocess, classifier_*,
// etc.) into one overall percent. Each stage processes the same N
// images so summing `current` and `total` across stages weights them
// equally — a reasonable proxy for "overall pipeline progress." The
// streaming crop gallery already gives a more concrete signal of work
// completing, so a single aggregate bar is enough here.
const overallProgress = computed(() => {
  const entries = progressEntries.value
  if (!entries.length) return null
  let current = 0
  let total = 0
  for (const [, p] of entries) {
    current += p.current
    total += p.total
  }
  if (!total) return null
  return { percent: Math.round((current / total) * 100) }
})

// Summary tallies, sorted by count desc.
const categoryEntries = computed(() =>
  Object.entries(job.value.summary?.by_category ?? {}).sort((a, b) => b[1] - a[1])
)
// Common-name labels that aren't real species classifications — exclude
// from the species pie chart because they're category-level outcomes
// (blank/human/vehicle) or signal the absence of any detection
// (no-cv-detect) rather than a species the model picked.
const NON_SPECIES_LABELS = new Set(['blank', 'human', 'vehicle', 'no-cv-detect'])

const speciesEntries = computed(() =>
  Object.entries(job.value.summary?.by_species ?? {})
    .filter(([name]) => !NON_SPECIES_LABELS.has(name.toLowerCase()))
    .sort((a, b) => b[1] - a[1])
)

// Accumulate every distinct latest_animal_crop the polling sees over
// the course of the job. The backend last-writer-wins update overwrites
// `latest_animal_crop` each time a qualifying prediction lands, so
// without this client-side accumulator only the final entry would be
// available for the post-completion gallery. Deduped by crop_gcs_path
// in case the same job doc gets re-polled before the field changes.
const seenCrops = ref([])

watch(() => job.value.latest_animal_crop, (crop) => {
  if (!crop || !crop.crop_gcs_path) return
  if (seenCrops.value.some(c => c.crop_gcs_path === crop.crop_gcs_path)) return
  seenCrops.value.push({ ...crop })
})

// Pie-chart slices for the post-completion summary. Pure SVG —
// no chart-library dependency for what's a handful of slices.
//
// Geometry: each slice spans `start..end` on a unit circle; the SVG
// path is one straight edge from center to start point, an arc to
// end point, and another straight edge back. Single-slice case
// degenerates (start == end) so the template falls back to <circle>.
const CATEGORY_COLORS = {
  animal:  '#4ade80',  // matches --animal in style.css
  human:   '#fb923c',
  vehicle: '#60a5fa',
  blank:   '#6b7280',
}

function pieSlices(entries, colorFn) {
  if (!entries.length) return []
  const total = entries.reduce((sum, [, n]) => sum + n, 0)
  if (!total) return []
  if (entries.length === 1) {
    const [label, value] = entries[0]
    return [{ label, value, percent: 100, path: '', color: colorFn(label, 0) }]
  }
  const cx = 50, cy = 50, r = 48
  let cumulative = 0
  return entries.map(([label, n], i) => {
    const startA = (cumulative / total) * Math.PI * 2 - Math.PI / 2
    cumulative += n
    const endA = (cumulative / total) * Math.PI * 2 - Math.PI / 2
    const x1 = (cx + r * Math.cos(startA)).toFixed(2)
    const y1 = (cy + r * Math.sin(startA)).toFixed(2)
    const x2 = (cx + r * Math.cos(endA)).toFixed(2)
    const y2 = (cy + r * Math.sin(endA)).toFixed(2)
    const largeArc = (endA - startA) > Math.PI ? 1 : 0
    return {
      label,
      value: n,
      percent: Math.round((n / total) * 100),
      path: `M${cx},${cy} L${x1},${y1} A${r},${r} 0 ${largeArc} 1 ${x2},${y2} Z`,
      color: colorFn(label, i),
    }
  })
}

const categorySlices = computed(() =>
  pieSlices(categoryEntries.value, label => CATEGORY_COLORS[label] || '#888'),
)

const speciesSlices = computed(() =>
  pieSlices(speciesEntries.value, (label, i) => {
    // Reuse the category color when the species name happens to be a
    // category (`blank`, `human`, `vehicle`) so the two charts stay
    // visually consistent.
    const lower = label.toLowerCase()
    if (CATEGORY_COLORS[lower]) return CATEGORY_COLORS[lower]
    // Otherwise spread hues using the golden-angle (~137.5°) so
    // adjacent slices stay visually distinct even with many species.
    const hue = (i * 137.508) % 360
    return `hsl(${hue}, 65%, 60%)`
  }),
)

// Expand/collapse the raw log after success. Log stays visible by default
// while running or on error.
const showLog = ref(false)

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

// Streaming thumbnail: the inference job writes `latest_animal_crop` on
// every prediction that's an animal with ≥50% confidence (see job.py).
// Show it whenever there's something to show AND the job hasn't reached
// its final state — once status === 'done' the full summary panel takes
// over. Hidden if status === 'error' to avoid stale state alongside the
// error banner.
const showLatestCrop = computed(() =>
  job.value.latest_animal_crop
  && job.value.status !== 'done'
  && job.value.status !== 'error',
)
const latestCropUrl = computed(() =>
  job.value.latest_animal_crop
    ? imageUrl(job.value.latest_animal_crop.crop_gcs_path)
    : '',
)

function formatElapsed(s) {
  const m = Math.floor(s / 60)
  const r = s % 60
  return `${m}:${String(r).padStart(2, '0')}`
}

function startElapsed() {
  processingStart.value = Date.now()
  elapsedSec.value      = 0
  if (elapsedTimer) clearInterval(elapsedTimer)
  elapsedTimer = setInterval(() => {
    elapsedSec.value = Math.floor((Date.now() - processingStart.value) / 1000)
  }, 1000)
}

function stopElapsed() {
  if (elapsedTimer) { clearInterval(elapsedTimer); elapsedTimer = null }
}

// ── File handling (cloud) ─────────────────────────────────────────────────────

function onFileChange(e) {
  files.value = Array.from(e.target.files)
}

function onDrop(e) {
  dragging.value = false
  files.value = Array.from(e.dataTransfer.files).filter(f => f.type.startsWith('image/'))
}

// ── Local folder browse ───────────────────────────────────────────────────────

async function browse() {
  browsing.value = true
  try {
    const res  = await fetch('/api/browse-folder')
    const data = await res.json()
    if (data.folder) folder.value = data.folder
  } finally {
    browsing.value = false
  }
}

// ── Geolocation ───────────────────────────────────────────────────────────────

function useCurrentLocation() {
  if (!navigator.geolocation) { locationError.value = 'Geolocation not supported.'; return }
  locating.value = true
  locationError.value = ''
  navigator.geolocation.getCurrentPosition(
    pos => {
      latitude.value  = parseFloat(pos.coords.latitude.toFixed(5))
      longitude.value = parseFloat(pos.coords.longitude.toFixed(5))
      locating.value  = false
    },
    err => { locationError.value = `Could not get location: ${err.message}`; locating.value = false },
    { timeout: 10000 },
  )
}

// ── Submit ────────────────────────────────────────────────────────────────────

async function submit() {
  if (submitting.value) return
  submitting.value = true
  submitError.value = ''
  try {
    if (AUTH_ENABLED) {
      await submitCloud()
    } else {
      await submitLocal()
    }
  } catch (e) {
    submitError.value = e.message
  } finally {
    submitting.value = false
  }
}

async function submitCloud() {
  if (!files.value.length) throw new Error('Please select at least one image file.')
  if (!folder.value.trim()) throw new Error('Please enter a folder name.')

  // Single-shot kickoff: the backend now returns signed URLs AND fires
  // run_job right away. The Cloud Run Job cold-starts (30–60s) overlaps
  // with the browser upload instead of following it.
  const body = {
    folder:    folder.value.trim(),
    filenames: files.value.map(f => f.name),
  }
  if (country.value)        body.country       = country.value.toUpperCase()
  if (admin1Region.value)   body.admin1_region = admin1Region.value.toUpperCase()
  if (latitude.value  != null) body.latitude    = latitude.value
  if (longitude.value != null) body.longitude   = longitude.value

  const prepRes  = await apiFetch('/api/upload/prepare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const prepData = await prepRes.json()
  if (!prepRes.ok) throw new Error(prepData.detail ?? `HTTP ${prepRes.status}`)

  const uploads = prepData.uploads

  if (!prepData.job_id) {
    // Either everything was already processed or nothing supported.
    job.value = {
      status: 'done',
      message: prepData.message ?? 'Nothing to do',
      log: [], progress: {},
    }
    phase.value = 'processing'
    return
  }

  // Job is already cold-starting. Begin polling now so any "Loading AI
  // model…" / "Waiting for uploads…" messages surface while the user
  // watches their files upload.
  jobId.value = prepData.job_id
  phase.value = 'uploading'
  uploadTotal.value = uploads.length
  uploadDone.value  = 0
  startElapsed()
  startPolling()

  // Upload files to GCS. The inference container is already polling for
  // them and will proceed as soon as the last one lands.
  //
  // Worker pool: N workers pull from a shared cursor. 6 matches the
  // browser's per-origin HTTP/1.1 connection cap; GCS supports HTTP/2 so
  // in practice these run multiplexed. Pushing higher gives diminishing
  // returns and risks throttling on slow uplinks.
  const CONCURRENCY = 6
  let cursor = 0
  const uploadOne = async ({ filename, url }) => {
    const file = files.value.find(f => f.name === filename)
    if (!file) return
    const putRes = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'image/jpeg' },
      body: file,
    })
    if (!putRes.ok) throw new Error(`Failed to upload ${filename}: HTTP ${putRes.status}`)
    uploadDone.value++
  }
  const workers = Array.from(
    { length: Math.min(CONCURRENCY, uploads.length) },
    async () => {
      while (cursor < uploads.length) {
        const i = cursor++
        await uploadOne(uploads[i])
      }
    },
  )
  await Promise.all(workers)

  // All uploads done — switch to the richer processing view. The job
  // might already be running (or done!) by now.
  phase.value = 'processing'
}

async function submitLocal() {
  const body = { folder: folder.value }
  if (country.value)      body.country       = country.value.toUpperCase()
  if (admin1Region.value) body.admin1_region  = admin1Region.value.toUpperCase()
  if (latitude.value  != null) body.latitude  = latitude.value
  if (longitude.value != null) body.longitude = longitude.value

  const res  = await fetch('/api/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const data = await res.json()
  if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`)

  jobId.value = data.job_id
  phase.value = 'processing'
  startElapsed()
  startPolling()
}

// ── Polling ───────────────────────────────────────────────────────────────────

function startPolling() {
  pollTimer = setInterval(pollJob, 2000)
  pollJob()
}

async function pollJob() {
  try {
    const res  = await apiFetch(`/api/jobs/${jobId.value}`)
    const data = await res.json()
    job.value  = data
    if (data.status === 'done' || data.status === 'error') {
      clearInterval(pollTimer)
      pollTimer = null
      stopElapsed()
    }
  } catch { /* network blip — keep polling */ }
}

function reset() {
  phase.value      = 'form'
  jobId.value      = null
  job.value        = { status: 'running', message: 'Queued', log: [], progress: {} }
  files.value      = []
  uploadDone.value = 0
  uploadTotal.value = 0
  submitError.value = ''
  stopElapsed()
  elapsedSec.value      = null
  processingStart.value = null
  showLog.value         = false
  seenCrops.value       = []
}

// Auto-scroll log
watch(() => job.value.log, async () => {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  stopElapsed()
})
</script>

<style scoped>
.backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.75);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 100;
  padding: 16px;
}

.modal {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: min(520px, 100%);
  max-height: calc(100vh - 32px);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal__header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
  flex-shrink: 0;
}

.modal__title { font-size: 15px; font-weight: 700; }

.modal__close {
  background: none;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 14px;
  cursor: pointer;
}

.modal__close:disabled { opacity: 0.3; cursor: default; }
.modal__close:not(:disabled):hover { color: var(--text); }

.modal__form,
.modal__progress {
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  overflow-y: auto;
  min-height: 0;
}

.modal__error {
  font-size: 13px;
  color: #f87171;
  background: rgba(248,113,113,0.1);
  border: 1px solid rgba(248,113,113,0.3);
  border-radius: var(--radius);
  padding: 8px 12px;
}

/* Fields */
.field { display: flex; flex-direction: column; gap: 5px; }
.field--row { flex-direction: row; gap: 12px; }
.field--row > .field { flex: 1; }

.field__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.field__hint { font-weight: 400; text-transform: none; letter-spacing: 0; font-size: 11px; }

.field__input {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text);
  padding: 7px 10px;
  font: inherit;
  font-size: 13px;
  width: 100%;
}

.field__input:focus { outline: none; border-color: var(--animal); }

.field__label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.field__error { font-size: 12px; color: #f87171; margin-top: 2px; }

.field__row { display: flex; gap: 6px; }
.field__row .field__input { flex: 1; }

/* Drag-and-drop zone */
.field__dropzone {
  background: var(--surface2);
  border: 2px dashed var(--border);
  border-radius: var(--radius);
  padding: 24px 16px;
  text-align: center;
  font-size: 13px;
  color: var(--text-muted);
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s;
}

.field__dropzone:hover,
.field__dropzone--active {
  border-color: var(--animal);
  color: var(--text);
}

.field__file-hidden {
  display: none;
}

/* Buttons */
.btn {
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 8px 16px;
  font: inherit;
  font-size: 13px;
  cursor: pointer;
  transition: color 0.15s;
}

.btn:hover { color: var(--text); }
.btn:disabled { opacity: 0.4; cursor: default; }

.btn--primary {
  background: #14532d;
  border-color: var(--animal);
  color: var(--animal);
  font-weight: 600;
}

.btn--primary:hover:not(:disabled) { background: #166534; }

.btn--browse { flex-shrink: 0; padding: 7px 12px; }
.btn--locate { font-size: 12px; padding: 3px 9px; }

/* Progress */
.progress__status {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
}

.progress__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.progress__dot--running { background: var(--vehicle); animation: pulse 1.2s infinite; }
.progress__dot--done    { background: var(--animal); }
.progress__dot--error   { background: #f87171; }

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50%       { opacity: 0.3; }
}

.progress__message {
  flex: 1;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.progress__elapsed {
  flex-shrink: 0;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  font-size: 12px;
  padding: 1px 7px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--surface2);
}

/* Stage bars */
.progress__stages { display: flex; flex-direction: column; gap: 8px; }

.progress__stage { display: flex; flex-direction: column; gap: 3px; }

.progress__stage-header {
  display: flex;
  align-items: baseline;
  gap: 6px;
  font-size: 12px;
}

.progress__stage-label { flex: 1; color: var(--text-muted); }

.progress__stage-count {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  font-size: 11px;
}

.progress__stage-pct {
  width: 34px;
  text-align: right;
  font-variant-numeric: tabular-nums;
  color: var(--text-muted);
}

.progress__stage-pct--done { color: var(--animal); }

.progress__stage-track {
  height: 5px;
  background: var(--surface2);
  border-radius: 3px;
  overflow: hidden;
}

.progress__stage-fill {
  height: 100%;
  background: var(--vehicle);
  border-radius: 3px;
  transition: width 0.3s ease;
}

.progress__stage-fill--done { background: var(--animal); }

.progress__error {
  font-size: 13px;
  color: #f87171;
  background: rgba(248,113,113,0.1);
  border: 1px solid rgba(248,113,113,0.3);
  border-radius: var(--radius);
  padding: 8px 12px;
  white-space: pre-wrap;
  word-break: break-all;
}

.progress__log {
  background: #0a0a0a;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 11px;
  color: #a3a3a3;
  line-height: 1.6;
  max-height: 200px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  scrollbar-width: thin;
}

.progress__actions { display: flex; gap: 8px; flex-wrap: wrap; }

/* Summary panel */
.summary {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding: 12px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.summary__header {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}

.summary__count {
  font-weight: 600;
  color: var(--text);
}

.summary__badges {
  display: flex;
  gap: 4px;
  flex-wrap: wrap;
  margin-left: auto;
}

/* Post-completion crop gallery — shows every animal crop the
   streaming pipeline surfaced during the run. Auto-fit grid so the
   layout adapts to the modal width without manual breakpoints. */
.summary__crops {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(80px, 1fr));
  gap: 6px;
  max-height: 260px;
  overflow-y: auto;
  padding: 4px;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.summary__crop {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.summary__crop-img {
  width: 100%;
  aspect-ratio: 1 / 1;
  object-fit: cover;
  border-radius: 4px;
  background: var(--surface2);
}

.summary__crop-label {
  font-size: 11px;
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: center;
}

/* Pie-chart summary panels */
.summary__charts {
  display: flex;
  flex-direction: column;
  gap: 14px;
}

.summary__chart {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.summary__chart-title {
  margin: 0;
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.summary__chart-row {
  display: flex;
  align-items: center;
  gap: 14px;
}

.pie {
  width: 110px;
  height: 110px;
  flex-shrink: 0;
}

.summary__legend {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
  flex: 1;
  min-width: 0;
  max-height: 140px;
  overflow-y: auto;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.summary__legend-row {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.summary__legend-swatch {
  width: 10px;
  height: 10px;
  border-radius: 2px;
  flex-shrink: 0;
}

.summary__legend-label {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.summary__legend-count {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  flex-shrink: 0;
}

.progress__details-toggle {
  align-self: center;
  margin-top: 4px;
  background: none;
  border: none;
  color: var(--text-muted);
  font: inherit;
  font-size: 12px;
  padding: 4px 8px;
  cursor: pointer;
  transition: color 0.15s;
}

.progress__details-toggle:hover {
  color: var(--text);
  text-decoration: underline;
}

/* Streaming "latest classification" thumbnail panel */
.latest-crop {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px;
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
}

.latest-crop__img {
  width: 64px;
  height: 64px;
  object-fit: cover;
  border-radius: var(--radius);
  background: var(--surface);
  flex-shrink: 0;
}

.latest-crop__meta {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
}

.latest-crop__heading {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.latest-crop__name {
  font-size: 14px;
  font-weight: 600;
  color: var(--animal);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.latest-crop__score {
  font-size: 12px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}
</style>
