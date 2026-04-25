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
        <button type="submit" class="btn btn--primary" :disabled="AUTH_ENABLED && files.length === 0">
          {{ AUTH_ENABLED ? 'Upload &amp; Process' : 'Run SpeciesNet' }}
        </button>
      </form>

      <!-- ── Upload progress (cloud only) ── -->
      <div v-else-if="phase === 'uploading'" class="modal__progress">
        <div class="progress__status">
          <span class="progress__dot progress__dot--running"></span>
          <span class="progress__message">Uploading {{ uploadDone }}/{{ uploadTotal }} files…</span>
        </div>
        <div class="progress__stage-track" style="margin-top:4px">
          <div class="progress__stage-fill" :style="{ width: uploadPct + '%' }"></div>
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

        <!-- Cold-start / preparing hint while we're waiting for SpeciesNet
             to start emitting progress bars -->
        <p v-if="showWaitingHint" class="progress__hint">
          Loading the AI model. This typically takes 30–60 seconds on the
          first upload and is much faster on subsequent runs.
        </p>

        <div v-if="progressEntries.length" class="progress__stages">
          <div v-for="[label, p] in progressEntries" :key="label" class="progress__stage">
            <div class="progress__stage-header">
              <span class="progress__stage-label">{{ label }}</span>
              <span class="progress__stage-count">{{ p.current }}/{{ p.total }}</span>
              <span class="progress__stage-pct" :class="p.percent === 100 ? 'progress__stage-pct--done' : ''">
                {{ p.percent }}%
              </span>
            </div>
            <div class="progress__stage-track">
              <div
                class="progress__stage-fill"
                :class="p.percent === 100 ? 'progress__stage-fill--done' : ''"
                :style="{ width: p.percent + '%' }"
              ></div>
            </div>
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

          <div v-if="speciesEntries.length" class="summary__species">
            <span
              v-for="[name, n] in speciesEntries"
              :key="name"
              class="summary__species-chip"
            >{{ capitalize(name) }} × {{ n }}</span>
          </div>

          <ul v-if="job.summary.images?.length" class="summary__list">
            <li
              v-for="(img, i) in job.summary.images"
              :key="i"
              class="summary__row"
            >
              <span class="summary__filename" :title="img.filename">{{ img.filename }}</span>
              <span
                v-if="img.category"
                :class="`badge badge--${img.category} summary__label`"
              >{{ img.common_name ? capitalize(img.common_name) : img.category }}</span>
              <span v-else class="summary__label summary__label--empty">—</span>
              <span v-if="img.score" class="summary__score">{{ Math.round(img.score * 100) }}%</span>
            </li>
          </ul>
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
import { AUTH_ENABLED, apiFetch } from '../firebase.js'

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

// Summary tallies, sorted by count desc.
const categoryEntries = computed(() =>
  Object.entries(job.value.summary?.by_category ?? {}).sort((a, b) => b[1] - a[1])
)
const speciesEntries = computed(() =>
  Object.entries(job.value.summary?.by_species ?? {}).sort((a, b) => b[1] - a[1])
)

// Expand/collapse the raw log after success. Log stays visible by default
// while running or on error.
const showLog = ref(false)

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

// Show the cold-start/warm-up hint until SpeciesNet starts reporting tqdm
// progress (or the job finishes). The hint is the key signal that the app
// is still working during the silent model-load stretch.
const showWaitingHint = computed(() =>
  phase.value === 'processing'
  && (job.value.status === 'pending' || job.value.status === 'running')
  && progressEntries.value.length === 0,
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
  submitError.value = ''
  try {
    if (AUTH_ENABLED) {
      await submitCloud()
    } else {
      await submitLocal()
    }
  } catch (e) {
    submitError.value = e.message
  }
}

async function submitCloud() {
  if (!files.value.length) throw new Error('Please select at least one image file.')
  if (!folder.value.trim()) throw new Error('Please enter a folder name.')

  // 1. Get signed upload URLs
  const prepRes = await apiFetch('/api/upload/prepare', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ folder: folder.value.trim(), filenames: files.value.map(f => f.name) }),
  })
  const prepData = await prepRes.json()
  if (!prepRes.ok) throw new Error(prepData.detail ?? `HTTP ${prepRes.status}`)

  const uploads = prepData.uploads
  if (!uploads.length) throw new Error('No supported image files found.')

  // 2. Upload files directly to GCS
  phase.value    = 'uploading'
  uploadTotal.value = uploads.length
  uploadDone.value  = 0

  const gcsPaths = []
  for (const { filename, url, gcs_path } of uploads) {
    const file = files.value.find(f => f.name === filename)
    if (!file) continue
    const putRes = await fetch(url, {
      method: 'PUT',
      headers: { 'Content-Type': 'image/jpeg' },
      body: file,
    })
    if (!putRes.ok) throw new Error(`Failed to upload ${filename}: HTTP ${putRes.status}`)
    gcsPaths.push(gcs_path)
    uploadDone.value++
  }

  // 3. Trigger inference job
  const body = {
    folder:    folder.value.trim(),
    gcs_paths: gcsPaths,
  }
  if (country.value)      body.country       = country.value.toUpperCase()
  if (admin1Region.value) body.admin1_region  = admin1Region.value.toUpperCase()
  if (latitude.value  != null) body.latitude  = latitude.value
  if (longitude.value != null) body.longitude = longitude.value

  const procRes  = await apiFetch('/api/process', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const procData = await procRes.json()
  if (!procRes.ok) throw new Error(procData.detail ?? `HTTP ${procRes.status}`)

  if (!procData.job_id) {
    // Everything already processed
    job.value = { status: 'done', message: procData.message, log: [], progress: {} }
    phase.value = 'processing'
    return
  }

  jobId.value = procData.job_id
  phase.value = 'processing'
  startElapsed()
  startPolling()
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

.progress__hint {
  margin: 0;
  padding: 8px 12px;
  font-size: 12px;
  line-height: 1.5;
  color: var(--text-muted);
  background: var(--surface2);
  border: 1px solid var(--border);
  border-radius: var(--radius);
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

.summary__species {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.summary__species-chip {
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--surface);
  border: 1px solid var(--border);
  color: var(--text);
  font-variant-numeric: tabular-nums;
}

.summary__list {
  list-style: none;
  margin: 0;
  padding: 0;
  max-height: 220px;
  overflow-y: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--surface);
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.summary__row {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 8px;
  padding: 5px 10px;
  font-size: 12px;
  border-bottom: 1px solid var(--border);
}

.summary__row:last-child { border-bottom: none; }

.summary__filename {
  color: var(--text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.summary__label {
  font-size: 11px;
}

.summary__label--empty {
  color: var(--text-muted);
}

.summary__score {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  min-width: 32px;
  text-align: right;
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
</style>
