<template>
  <div class="backdrop" @click.self="canClose && $emit('close')">
    <div class="modal">

      <div class="modal__header">
        <h2 class="modal__title">Process New Folder</h2>
        <button class="modal__close" :disabled="!canClose" @click="$emit('close')">✕</button>
      </div>

      <!-- Form -->
      <form v-if="!jobId" class="modal__form" @submit.prevent="submit">
        <div class="field">
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
            <input
              v-model="country"
              class="field__input"
              placeholder="GBR"
              maxlength="3"
            />
          </div>
          <div v-if="country.toUpperCase() === 'USA'" class="field">
            <label class="field__label">State <span class="field__hint">abbreviation</span></label>
            <input
              v-model="admin1Region"
              class="field__input"
              placeholder="CA"
              maxlength="2"
            />
          </div>
        </div>
        <div class="field">
          <div class="field__label-row">
            <label class="field__label">Location <span class="field__hint">optional</span></label>
            <button
              type="button"
              class="btn btn--locate"
              :disabled="locating"
              @click="useCurrentLocation"
            >{{ locating ? 'Locating…' : '⊕ Use my location' }}</button>
          </div>
          <div class="field--row">
            <input v-model.number="latitude"  type="number" step="any" class="field__input" placeholder="Latitude" />
            <input v-model.number="longitude" type="number" step="any" class="field__input" placeholder="Longitude" />
          </div>
          <p v-if="locationError" class="field__error">{{ locationError }}</p>
        </div>
        <div v-if="submitError" class="modal__error">{{ submitError }}</div>
        <button type="submit" class="btn btn--primary">Run SpeciesNet</button>
      </form>

      <!-- Progress -->
      <div v-else class="modal__progress">
        <div class="progress__status">
          <span :class="`progress__dot progress__dot--${job.status}`"></span>
          <span class="progress__message">{{ job.message }}</span>
          <span v-if="job.status === 'done'" class="progress__count">✓</span>
        </div>

        <!-- Prominent error banner -->
        <div v-if="job.status === 'error'" class="progress__error">
          <strong>Error:</strong> {{ job.message }}
        </div>

        <pre ref="logEl" class="progress__log">{{ (job.log ?? []).join('\n') }}</pre>

        <div class="progress__actions">
          <button
            v-if="job.status === 'done'"
            class="btn btn--primary"
            @click="$emit('done')"
          >Reload gallery</button>
          <button
            v-if="job.status === 'error' || job.status === 'done'"
            class="btn"
            @click="reset"
          >Process another folder</button>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, nextTick, onUnmounted } from 'vue'

const emit = defineEmits(['close', 'done'])

const folder       = ref('')
const browsing     = ref(false)
const admin1Region = ref('')
const locating     = ref(false)
const locationError = ref('')
const country   = ref('')
const latitude  = ref(null)
const longitude = ref(null)
const submitError = ref('')

const jobId = ref(null)
const job   = ref({ status: 'running', message: 'Queued', log: [] })
const logEl = ref(null)

let pollTimer = null

const canClose = computed(() =>
  !jobId.value || job.value.status === 'done' || job.value.status === 'error'
)

function useCurrentLocation() {
  if (!navigator.geolocation) {
    locationError.value = 'Geolocation is not supported by this browser.'
    return
  }
  locating.value = true
  locationError.value = ''
  navigator.geolocation.getCurrentPosition(
    pos => {
      latitude.value  = parseFloat(pos.coords.latitude.toFixed(5))
      longitude.value = parseFloat(pos.coords.longitude.toFixed(5))
      locating.value  = false
    },
    err => {
      locationError.value = `Could not get location: ${err.message}`
      locating.value = false
    },
    { timeout: 10000 }
  )
}

async function browse() {
  browsing.value = true
  try {
    const res = await fetch('/api/browse-folder')
    const data = await res.json()
    if (data.folder) folder.value = data.folder
  } finally {
    browsing.value = false
  }
}

async function submit() {
  submitError.value = ''
  try {
    const body = { folder: folder.value }
    if (country.value)    body.country      = country.value.toUpperCase()
    if (admin1Region.value) body.admin1_region = admin1Region.value.toUpperCase()
    if (latitude.value  != null) body.latitude  = latitude.value
    if (longitude.value != null) body.longitude = longitude.value

    const res = await fetch('/api/process', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(body),
    })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail ?? `HTTP ${res.status}`)

    jobId.value = data.job_id
    startPolling()
  } catch (e) {
    submitError.value = e.message
  }
}

function startPolling() {
  pollTimer = setInterval(pollJob, 2000)
  pollJob()
}

async function pollJob() {
  try {
    const res = await fetch(`/api/jobs/${jobId.value}`)
    const data = await res.json()
    job.value = data
    if (data.status === 'done' || data.status === 'error') {
      clearInterval(pollTimer)
      pollTimer = null
    }
  } catch { /* network blip — keep polling */ }
}

function reset() {
  jobId.value = null
  job.value = { status: 'running', message: 'Queued', log: [] }
  submitError.value = ''
}

// Auto-scroll log to bottom when new lines arrive
watch(() => job.value.log, async () => {
  await nextTick()
  if (logEl.value) logEl.value.scrollTop = logEl.value.scrollHeight
})

onUnmounted(() => { if (pollTimer) clearInterval(pollTimer) })
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

.modal__title {
  font-size: 15px;
  font-weight: 700;
}

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

/* Form fields */
.field {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

.field--row {
  flex-direction: row;
  gap: 12px;
}

.field--row > .field { flex: 1; }

.field__label {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

.field__hint {
  font-weight: 400;
  text-transform: none;
  letter-spacing: 0;
  font-size: 11px;
}

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

.field__input:focus {
  outline: none;
  border-color: var(--animal);
}

.field__input--short { max-width: 100px; }

.field__label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.field__error {
  font-size: 12px;
  color: #f87171;
  margin-top: 2px;
}

.field__row {
  display: flex;
  gap: 6px;
}

.field__row .field__input {
  flex: 1;
}

.btn--browse {
  flex-shrink: 0;
  padding: 7px 12px;
}

.btn--locate {
  font-size: 12px;
  padding: 3px 9px;
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

.btn--primary {
  background: #14532d;
  border-color: var(--animal);
  color: var(--animal);
  font-weight: 600;
}

.btn--primary:hover { background: #166534; }

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

.progress__log {
  background: #0a0a0a;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 10px 12px;
  font-family: 'Consolas', 'Courier New', monospace;
  font-size: 11px;
  color: #a3a3a3;
  line-height: 1.6;
  max-height: 260px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  scrollbar-width: thin;
}

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

.progress__actions {
  display: flex;
  gap: 8px;
}
</style>
