<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal">

      <!-- Toolbar -->
      <div class="modal__toolbar">
        <span class="modal__filename">{{ image.filename }}</span>
        <div class="modal__toolbar-right">
          <button
            class="modal__toggle"
            :class="{ 'modal__toggle--off': !showBoxes }"
            :title="showBoxes ? 'Hide bounding boxes' : 'Show bounding boxes'"
            @click="showBoxes = !showBoxes"
          >{{ showBoxes ? 'Hide boxes' : 'Show boxes' }}</button>
          <button
            class="modal__delete"
            :disabled="deleting"
            title="Delete image"
            @click="confirmingDelete = true"
          >Delete</button>
          <button class="modal__close" @click="$emit('close')">✕</button>
        </div>
      </div>

      <!-- Delete confirmation overlay -->
      <div v-if="confirmingDelete" class="confirm-backdrop" @click.self="cancelDelete">
        <div class="confirm">
          <h3 class="confirm__title">Delete this image?</h3>
          <p class="confirm__body">
            <strong>{{ image.filename }}</strong> and any cropped versions will be
            permanently removed from storage. This cannot be undone.
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

      <div class="modal__body">
        <div class="modal__left">
        <!-- Image + bbox overlay -->
        <div class="modal__image-wrap" ref="wrapRef">
          <div
            class="modal__canvas-container"
            ref="containerRef"
            :style="containerStyle"
          >
            <img
              ref="imgRef"
              :src="imageUrl(image.filepath)"
              :alt="image.filename"
              class="modal__img"
              @load="onImageLoad"
            />
            <!-- Bbox overlays — rendered after image loads -->
            <template v-if="imageLoaded && showBoxes">
              <div
                v-for="(det, i) in significantDetections"
                :key="i"
                class="modal__bbox"
                :style="bboxStyle(det)"
                :title="`${detectionLabel(det)} ${(det.conf * 100).toFixed(0)}%`"
              >
                <span class="modal__bbox-label" :style="{ background: categoryColor(det.category) }">
                  {{ detectionLabel(det) }} {{ (det.conf * 100).toFixed(0) }}%
                </span>
              </div>
            </template>
          </div>

          <!-- Navigation arrows -->
          <button class="modal__nav modal__nav--prev" @click="navigate(-1)" :disabled="currentIndex <= 0">‹</button>
          <button class="modal__nav modal__nav--next" @click="navigate(1)" :disabled="currentIndex >= allImages.length - 1">›</button>
          <div class="modal__position">{{ currentIndex + 1 }} / {{ allImages.length }}</div>
        </div>

        <!-- Detection crop carousel -->
        <div v-if="significantDetections.length" class="modal__carousel">
          <DetectionCrop
            v-for="(det, i) in significantDetections"
            :key="i"
            :image-src="imageUrl(image.filepath)"
            :det="det"
            :color="categoryColor(det.category)"
            :label="detectionLabel(det)"
          />
        </div>
        </div><!-- end .modal__left -->

        <!-- Side panel -->
        <div class="modal__panel">
          <!-- Prediction summary -->
          <section class="panel__section">
            <h3 class="panel__heading">Prediction</h3>
            <div v-if="image.prediction" class="panel__prediction">
              <span :class="`badge badge--${getCategory(image)}`">
                {{ capitalize(image.prediction.common_name) }}
              </span>
              <span v-if="image.prediction.scientific" class="panel__scientific">
                {{ image.prediction.scientific }}
              </span>
            </div>
            <dl class="panel__meta">
              <template v-if="image.prediction_score != null">
                <dt>Score</dt>
                <dd>{{ (image.prediction_score * 100).toFixed(1) }}%</dd>
              </template>
              <template v-if="image.prediction_source">
                <dt>Source</dt>
                <dd>{{ image.prediction_source }}</dd>
              </template>
              <template v-if="image.model_version">
                <dt>Model</dt>
                <dd>{{ image.model_version }}</dd>
              </template>
              <template v-if="image.country">
                <dt>Country</dt>
                <dd>{{ image.country }}</dd>
              </template>
              <template v-if="image.latitude != null">
                <dt>Location</dt>
                <dd>{{ image.latitude.toFixed(4) }}, {{ image.longitude.toFixed(4) }}</dd>
              </template>
            </dl>
          </section>

          <!-- Top-5 classifications -->
          <section v-if="image.top5?.length" class="panel__section">
            <h3 class="panel__heading">Top-5 Classifications</h3>
            <div class="panel__top5">
              <div v-for="(cls, i) in image.top5" :key="i" class="panel__cls">
                <span class="panel__cls-name">{{ capitalize(cls.common_name) }}</span>
                <div class="panel__cls-bar-wrap">
                  <div class="panel__cls-bar" :style="{ width: `${cls.score * 100}%` }"></div>
                </div>
                <span class="panel__cls-score">{{ (cls.score * 100).toFixed(1) }}%</span>
              </div>
            </div>
          </section>

          <!-- Detections -->
          <section v-if="significantDetections.length" class="panel__section">
            <h3 class="panel__heading">Detections</h3>
            <div class="panel__detections">
              <div v-for="(det, i) in significantDetections" :key="i" class="panel__det">
                <span class="panel__det-dot" :style="{ background: categoryColor(det.category) }"></span>
                <span>{{ detectionLabel(det) }}</span>
                <span class="panel__det-conf">{{ (det.conf * 100).toFixed(0) }}%</span>
              </div>
            </div>
          </section>

          <!-- EXIF tags -->
          <section v-if="exifEntries.length || exifLoading" class="panel__section">
            <h3 class="panel__heading">EXIF</h3>
            <div v-if="exifLoading" class="panel__exif-loading">Reading…</div>
            <dl v-else class="panel__meta panel__exif">
              <template v-for="[k, v] in exifEntries" :key="k">
                <dt>{{ k }}</dt>
                <dd>{{ v }}</dd>
              </template>
            </dl>
          </section>

          <!-- Failures -->
          <section v-if="image.failures?.length" class="panel__section">
            <h3 class="panel__heading panel__heading--warn">Failures</h3>
            <div v-for="f in image.failures" :key="f" class="panel__failure">{{ f }}</div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onUnmounted } from 'vue'
import exifr from 'exifr'
import DetectionCrop from './DetectionCrop.vue'
import { imageUrl, apiFetch } from '../firebase.js'

const props = defineProps({
  image: Object,
  allImages: Array,
})
const emit = defineEmits(['close', 'navigate', 'deleted'])

const confirmingDelete = ref(false)
const deleting         = ref(false)
const deleteError      = ref('')
const showBoxes        = ref(true)

function cancelDelete() {
  if (deleting.value) return
  confirmingDelete.value = false
  deleteError.value = ''
}

async function doDelete() {
  deleting.value = true
  deleteError.value = ''
  try {
    const res = await apiFetch(
      `/api/predictions?path=${encodeURIComponent(props.image.filepath)}`,
      { method: 'DELETE' },
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const deletedImage = props.image
    confirmingDelete.value = false
    emit('deleted', deletedImage)
  } catch (e) {
    deleteError.value = `Delete failed: ${e.message}`
  } finally {
    deleting.value = false
  }
}

const imgRef = ref(null)
const containerRef = ref(null)
const wrapRef = ref(null)
const imageLoaded = ref(false)
const containerStyle = ref(null)
let resizeObserver = null

const currentIndex = computed(() => props.allImages.indexOf(props.image))

const significantDetections = computed(() =>
  (props.image.detections ?? []).filter(d => d.conf >= 0.1)
)

// ── EXIF tags ─────────────────────────────────────────────────────────────────
const exifTags    = ref(null)
const exifLoading = ref(false)

const exifEntries = computed(() => {
  if (!exifTags.value) return []
  return Object.entries(exifTags.value)
    .filter(([, v]) => v !== undefined && v !== null && v !== '')
    .map(([k, v]) => [k, formatExifValue(v)])
    .sort(([a], [b]) => a.localeCompare(b))
})

function formatExifValue(v) {
  if (v instanceof Date) return v.toISOString().replace('T', ' ').slice(0, 19)
  if (Array.isArray(v))  return v.map(formatExifValue).join(', ')
  if (typeof v === 'number') return Number.isInteger(v) ? String(v) : v.toFixed(4)
  if (typeof v === 'object') return JSON.stringify(v)
  return String(v)
}

async function loadExif() {
  exifTags.value = null
  exifLoading.value = true
  try {
    const url = imageUrl(props.image.filepath)
    const tags = await exifr.parse(url, { tiff: true, exif: true, gps: true, ifd0: true })
    exifTags.value = tags || {}
  } catch (e) {
    exifTags.value = {}
  } finally {
    exifLoading.value = false
  }
}

function getCategory(img) {
  const name = img.prediction?.common_name?.toLowerCase()
  if (!name) return 'unknown'
  if (name === 'blank') return 'blank'
  if (name === 'human') return 'human'
  if (name === 'vehicle') return 'vehicle'
  return 'animal'
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

const CATEGORY_COLORS = { '1': '#4ade80', '2': '#fb923c', '3': '#60a5fa' }
function categoryColor(cat) {
  return CATEGORY_COLORS[cat] ?? '#a78bfa'
}

const NON_SPECIES = new Set(['blank', 'human', 'vehicle'])

function detectionLabel(det) {
  // For animal detections, show the image's species prediction when it's
  // an actual species (not a blank/human/vehicle classifier fallback).
  if (det.category === '1') {
    const name = props.image.prediction?.common_name
    if (name && !NON_SPECIES.has(name.toLowerCase())) {
      return capitalize(name)
    }
  }
  return capitalize(det.label)
}

function bboxStyle(det) {
  const [x, y, w, h] = det.bbox
  return {
    left:   `${x * 100}%`,
    top:    `${y * 100}%`,
    width:  `${w * 100}%`,
    height: `${h * 100}%`,
    borderColor: categoryColor(det.category),
  }
}

function computeContainerSize() {
  const img = imgRef.value
  const wrap = wrapRef.value
  if (!img || !wrap || !img.naturalWidth || !img.naturalHeight) return
  const maxW = wrap.clientWidth
  const maxH = wrap.clientHeight
  const ar = img.naturalWidth / img.naturalHeight
  let w = maxW
  let h = w / ar
  if (h > maxH) {
    h = maxH
    w = h * ar
  }
  containerStyle.value = { width: `${w}px`, height: `${h}px` }
}

function onImageLoad() {
  imageLoaded.value = true
  computeContainerSize()
}

function navigate(delta) {
  const next = props.allImages[currentIndex.value + delta]
  if (next) {
    imageLoaded.value = false
    emit('navigate', next)
  }
}

function onKeydown(e) {
  if (e.key === 'Escape') {
    if (confirmingDelete.value) cancelDelete()
    else emit('close')
    return
  }
  if (confirmingDelete.value) return
  if (e.key === 'ArrowLeft')  navigate(-1)
  if (e.key === 'ArrowRight') navigate(1)
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  if (wrapRef.value && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => computeContainerSize())
    resizeObserver.observe(wrapRef.value)
  }
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  resizeObserver?.disconnect()
})

watch(() => props.image, () => {
  imageLoaded.value = false
  containerStyle.value = null
  confirmingDelete.value = false
  deleteError.value = ''
  loadExif()
}, { immediate: true })
</script>

<style scoped>
.modal-backdrop {
  position: fixed;
  inset: 0;
  background: rgba(0,0,0,0.85);
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
  display: flex;
  flex-direction: column;
  width: 100%;
  max-height: calc(100vh - 32px);
  overflow: hidden;
}

.modal__toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
  flex-shrink: 0;
}

.modal__filename {
  font-size: 13px;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.modal__toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
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
}

.modal__close:hover { color: var(--text); }

.modal__toggle,
.modal__delete {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 4px 10px;
  font-size: 12px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.modal__toggle:hover {
  color: var(--text);
}

.modal__toggle--off {
  color: var(--text);
  background: var(--surface2);
}

.modal__delete:hover:not(:disabled) {
  color: #fca5a5;
  border-color: #b91c1c;
  background: rgba(185, 28, 28, 0.12);
}

.modal__delete:disabled { opacity: 0.5; cursor: default; }

/* Confirmation overlay */
.confirm-backdrop {
  position: absolute;
  inset: 0;
  background: rgba(0, 0, 0, 0.6);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 10;
}

.confirm {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  padding: 18px 20px;
  width: min(420px, calc(100% - 32px));
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

.modal__body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.modal__left {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

.modal__carousel {
  display: flex;
  flex-direction: row;
  gap: 6px;
  padding: 8px 10px;
  background: #000;
  border-top: 1px solid var(--border);
  overflow-x: auto;
  flex-shrink: 0;
  scrollbar-width: thin;
  scrollbar-color: var(--border) transparent;
}

.modal__image-wrap {
  flex: 1;
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #000;
  overflow: hidden;
}

.modal__canvas-container {
  position: relative;
  display: block;
}

.modal__img {
  display: block;
  width: 100%;
  height: 100%;
}

.modal__bbox {
  position: absolute;
  border: 2px solid;
  pointer-events: none;
}

.modal__bbox-label {
  position: absolute;
  top: -22px;
  left: -1px;
  font-size: 11px;
  font-weight: 600;
  color: #000;
  padding: 2px 5px;
  white-space: nowrap;
  border-radius: 3px 3px 0 0;
}

.modal__nav {
  position: absolute;
  top: 50%;
  transform: translateY(-50%);
  background: rgba(0,0,0,0.5);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: #fff;
  font-size: 28px;
  width: 40px;
  height: 56px;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: background 0.15s;
  line-height: 1;
}

.modal__nav:hover:not(:disabled) { background: rgba(0,0,0,0.75); }
.modal__nav:disabled { opacity: 0.2; cursor: default; }
.modal__nav--prev { left: 8px; }
.modal__nav--next { right: 8px; }

.modal__position {
  position: absolute;
  bottom: 8px;
  left: 50%;
  transform: translateX(-50%);
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 12px;
  padding: 2px 8px;
  border-radius: 999px;
}

/* Side panel */
.modal__panel {
  width: 260px;
  flex-shrink: 0;
  overflow-y: auto;
  border-left: 1px solid var(--border);
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.panel__section { display: flex; flex-direction: column; gap: 8px; }

.panel__heading {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.panel__heading--warn { color: #f87171; }

.panel__prediction {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.panel__scientific {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.panel__meta {
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 3px 12px;
  font-size: 12px;
}

.panel__meta dt { color: var(--text-muted); }
.panel__meta dd { color: var(--text); font-variant-numeric: tabular-nums; }

.panel__top5 { display: flex; flex-direction: column; gap: 6px; }

.panel__cls {
  display: grid;
  grid-template-columns: 1fr 80px 36px;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.panel__cls-name {
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.panel__cls-bar-wrap {
  height: 4px;
  background: var(--surface2);
  border-radius: 2px;
  overflow: hidden;
}

.panel__cls-bar {
  height: 100%;
  background: var(--animal);
  border-radius: 2px;
  transition: width 0.3s;
}

.panel__cls-score {
  text-align: right;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.panel__detections { display: flex; flex-direction: column; gap: 5px; }

.panel__det {
  display: flex;
  align-items: center;
  gap: 7px;
  font-size: 12px;
}

.panel__det-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.panel__det-conf {
  margin-left: auto;
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.panel__failure {
  font-size: 12px;
  color: #f87171;
}

.panel__exif-loading {
  font-size: 12px;
  color: var(--text-muted);
  font-style: italic;
}

.panel__exif {
  grid-template-columns: minmax(90px, auto) 1fr;
  font-size: 11px;
  max-height: 260px;
  overflow-y: auto;
  padding-right: 4px;
}
.panel__exif dd {
  word-break: break-word;
  overflow-wrap: anywhere;
}
</style>
