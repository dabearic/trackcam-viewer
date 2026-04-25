<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal">

      <!-- Toolbar -->
      <div class="modal__toolbar">
        <span class="modal__filename">{{ image.filename }}</span>
        <div class="modal__toolbar-right">
          <button
            v-if="editMode"
            class="modal__toggle modal__toggle--draw"
            :class="{ 'modal__toggle--off': !drawMode }"
            :title="drawMode ? 'Cancel drawing' : 'Drag a rectangle on the image to add a detection'"
            @click="drawMode ? cancelDraw() : startAddDetection()"
          >{{ drawMode ? 'Cancel draw' : '+ Add detection' }}</button>
          <button
            class="modal__toggle"
            :class="{ 'modal__toggle--off': !editMode, 'modal__toggle--active': editMode }"
            :title="editMode ? 'Exit edit mode' : 'Edit detections'"
            @click="toggleEditMode"
          >{{ editMode ? 'Done editing' : 'Edit' }}</button>
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
        <!-- Detection editor — docks as a left panel only while edit mode
             is active AND a detection is selected (or being added). Hidden
             entirely otherwise so the modal layout matches view-mode 1:1. -->
        <DetectionEditor
          v-if="editMode && editingDet"
          class="modal__editor-dock"
          :mode="editorMode"
          :detection="editingDet"
          :top-five="topFiveFor(image)"
          :flat-species="flatSpecies"
          :add-custom="addCustom"
          :similar-count="similarCount"
          :busy="editorBusy"
          :error="editorError"
          @save="onEditorSave"
          @delete="onEditorDelete"
          @close="closeEditor"
        />
        <div class="modal__left">
        <!-- Image + bbox overlay -->
        <div
          class="modal__image-wrap"
          ref="wrapRef"
          @wheel.prevent="onWheel"
        >
          <div
            class="modal__canvas-container"
            ref="containerRef"
            :class="{ 'modal__canvas-container--zoomed': zoom > 1, 'modal__canvas-container--panning': isPanning }"
            :style="containerStyle"
            @mousedown="onMouseDown"
            @dblclick="onDoubleClick"
          >
            <img
              ref="imgRef"
              v-show="imageLoaded"
              :src="imageUrl(image.filepath)"
              :alt="image.filename"
              class="modal__img"
              draggable="false"
              @load="onImageLoad"
            />
          </div>

          <!-- Bbox overlay: lives OUTSIDE the scaled container so borders
               and labels render at true screen pixels at any zoom level.
               Each bbox's position is computed in screen-space from the
               current zoom/pan/baseSize, so the boxes still track the
               image exactly as it's panned or zoomed. -->
          <div
            v-if="imageLoaded && showBoxes && baseSize.w"
            class="modal__bbox-overlay"
            :class="{ 'modal__bbox-overlay--editable': editMode && !drawMode }"
          >
            <div
              v-for="(det, i) in significantDetections"
              :key="det.id || i"
              class="modal__bbox"
              :class="{
                'modal__bbox--manual':   det.manual,
                'modal__bbox--editing':  editingDet && det.id === editingDet.id,
              }"
              :style="bboxScreenStyle(det)"
              :title="`${detectionLabel(det)} ${(det.conf * 100).toFixed(0)}%${det.manual ? ' (manual)' : ''}`"
              @click.stop="openEditorForDet(det)"
            >
              <span
                class="modal__bbox-label"
                :style="{ background: categoryColor(det.category) }"
              >
                <span v-if="det.manual" class="modal__bbox-manual" title="Manual edit">✎</span>
                {{ detectionLabel(det) }} {{ (det.conf * 100).toFixed(0) }}%
              </span>
            </div>
          </div>

          <!-- Draw-mode capture layer: only present while the user is in
               draw mode. Sits above everything so a drag here doesn't
               trigger pan/zoom on the underlying image. -->
          <div
            v-if="drawMode && imageLoaded"
            class="modal__draw-layer"
            @mousedown="onDrawDown"
          >
            <div
              v-if="drawRectStyle"
              class="modal__draw-rect"
              :style="drawRectStyle"
            ></div>
          </div>


          <!-- Navigation arrows -->
          <button class="modal__nav modal__nav--prev" @click="navigate(-1)" :disabled="currentIndex <= 0">‹</button>
          <button class="modal__nav modal__nav--next" @click="navigate(1)" :disabled="currentIndex >= allImages.length - 1">›</button>
          <div class="modal__position">{{ currentIndex + 1 }} / {{ allImages.length }}</div>
          <div v-if="zoom > 1" class="modal__zoom-indicator">
            {{ Math.round(zoom * 100) }}%
            <button class="modal__zoom-reset" title="Reset zoom" @click="resetZoom">✕</button>
          </div>
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
            :class="{ 'crop--active': zoomedDetIndex === i }"
            role="button"
            tabindex="0"
            @click="onCropClick(i, det)"
            @keydown.enter.prevent="onCropClick(i, det)"
            @keydown.space.prevent="onCropClick(i, det)"
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
              <component
                :is="editMode ? 'button' : 'div'"
                v-for="(det, i) in significantDetections"
                :key="det.id || i"
                class="panel__det"
                :class="{
                  'panel__det--editable': editMode,
                  'panel__det--editing':  editingDet && det.id === editingDet.id,
                }"
                @click="editMode && openEditorForDet(det)"
              >
                <span class="panel__det-dot" :style="{ background: categoryColor(det.category) }"></span>
                <span>{{ detectionLabel(det) }}</span>
                <span v-if="det.manual" class="panel__det-manual" title="Manual edit">✎</span>
                <span class="panel__det-conf">{{ (det.conf * 100).toFixed(0) }}%</span>
              </component>
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
import DetectionEditor from './DetectionEditor.vue'
import { imageUrl, apiFetch } from '../firebase.js'
import { useSpeciesCatalog } from '../composables/useSpeciesCatalog.js'

const props = defineProps({
  image: Object,
  allImages: Array,
  // Full predictions list (not just filtered) so the species tree sees every
  // species ever observed, regardless of current gallery filters.
  predictions: { type: Array, default: () => [] },
})
const emit = defineEmits(['close', 'navigate', 'deleted', 'detections-changed'])

const confirmingDelete = ref(false)
const deleting         = ref(false)
const deleteError      = ref('')
const showBoxes        = ref(true)

// ── Edit mode ─────────────────────────────────────────────────────────────────
const editMode        = ref(false)
const drawMode        = ref(false)             // sub-state of editMode: drawing a new bbox
const editingDet      = ref(null)              // detection being edited (or {bbox} when adding)
const editorMode      = ref('edit')            // 'edit' | 'add'
const editorError     = ref('')
const editorBusy      = ref(false)
const drawStart       = ref(null)              // { nx, ny } image-normalised
const drawEnd         = ref(null)
const predictionsRef  = computed(() => props.predictions)
const speciesCatalog  = useSpeciesCatalog(predictionsRef)
const { topFive: topFiveFor, flatSpecies, addCustom, loadCustom } = speciesCatalog

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
const baseSize = ref({ w: 0, h: 0 })
const zoom = ref(1)
const panX = ref(0)
const panY = ref(0)
const isPanning = ref(false)
const zoomedDetIndex = ref(null)   // which crop (if any) the auto-zoom is centred on
let resizeObserver = null
let dragStart = null

const MAX_ZOOM = 8
const MIN_ZOOM = 1
const AUTO_MAX_ZOOM = 20           // crop-click can push past MAX_ZOOM for tiny detections
const CROP_FILL_FRACTION = 0.7     // target: bbox covers ~70% of the view's matching dim

const containerStyle = computed(() => {
  const { w, h } = baseSize.value
  if (!w || !h) return null
  return {
    width:           `${w}px`,
    height:          `${h}px`,
    transform:       `translate(${panX.value}px, ${panY.value}px) scale(${zoom.value})`,
    transformOrigin: '0 0',
  }
})

const currentIndex = computed(() => props.allImages.indexOf(props.image))

const significantDetections = computed(() =>
  (props.image.detections ?? []).filter(d => d.conf >= 0.1)
)

// How many detections share the open editor's category — used for the
// editor's "Apply to all N animal detections" checkbox. Counts every
// detection (including low-conf ones) since the bulk endpoint does too.
const similarCount = computed(() => {
  if (!editingDet.value || editorMode.value === 'add') return 0
  const cat = editingDet.value.category
  return (props.image?.detections ?? []).filter(d => d.category === cat).length
})

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
  // Manual edits store the species directly on the detection — prefer that
  // over the image-level prediction fallback below. Without this, the bbox
  // label silently ignored every manual edit because it kept rendering the
  // image-level inference output.
  if (det.manual && det.label) return capitalize(det.label)
  // Inference detections only carry a generic class label ("animal"), so
  // for animal-category detections we surface the image's species
  // prediction instead. Skipped for blank/human/vehicle predictions.
  if (det.category === '1') {
    const name = props.image.prediction?.common_name
    if (name && !NON_SPECIES.has(name.toLowerCase())) {
      return capitalize(name)
    }
  }
  return capitalize(det.label)
}

// ── Edit-mode helpers ────────────────────────────────────────────────────────
// All bbox coords stored in detections are normalised [0,1] relative to the
// image. The image renders inside a centred, scaled container, so these
// helpers convert between mouse position (wrap-local px) and image-norm space.

/** Mouse event → normalised image coords [0,1]. Null if the image isn't ready. */
function mouseToNormalised(e) {
  const wrap = wrapRef.value
  const { w: bw, h: bh } = baseSize.value
  if (!wrap || !bw || !bh) return null
  const rect  = wrap.getBoundingClientRect()
  const baseX = (wrap.clientWidth  - bw) / 2
  const baseY = (wrap.clientHeight - bh) / 2
  const imgX  = (e.clientX - rect.left - baseX - panX.value) / zoom.value
  const imgY  = (e.clientY - rect.top  - baseY - panY.value) / zoom.value
  return {
    nx: Math.max(0, Math.min(1, imgX / bw)),
    ny: Math.max(0, Math.min(1, imgY / bh)),
  }
}


/** Style object for an in-progress draw rectangle (image-norm → screen px). */
const drawRectStyle = computed(() => {
  if (!drawStart.value || !drawEnd.value) return null
  const wrap = wrapRef.value
  const { w: bw, h: bh } = baseSize.value
  if (!wrap || !bw || !bh) return null
  const x = Math.min(drawStart.value.nx, drawEnd.value.nx)
  const y = Math.min(drawStart.value.ny, drawEnd.value.ny)
  const w = Math.abs(drawEnd.value.nx - drawStart.value.nx)
  const h = Math.abs(drawEnd.value.ny - drawStart.value.ny)
  const baseX = (wrap.clientWidth  - bw) / 2
  const baseY = (wrap.clientHeight - bh) / 2
  return {
    left:   `${baseX + panX.value + x * bw * zoom.value}px`,
    top:    `${baseY + panY.value + y * bh * zoom.value}px`,
    width:  `${w * bw * zoom.value}px`,
    height: `${h * bh * zoom.value}px`,
  }
})

// ── Edit / delete / add handlers ─────────────────────────────────────────────

function toggleEditMode() {
  editMode.value = !editMode.value
  closeEditor()
  cancelDraw()
}

function openEditorForDet(det) {
  if (!editMode.value) return
  editingDet.value = det
  editorMode.value = 'edit'
  editorError.value = ''
}

function closeEditor() {
  editingDet.value = null
  editorError.value = ''
  editorBusy.value = false
}

async function onEditorSave(payload) {
  if (!editingDet.value) return
  editorBusy.value = true
  editorError.value = ''
  try {
    if (editorMode.value === 'add') {
      const res = await apiFetch(
        `/api/predictions/detections?path=${encodeURIComponent(props.image.filepath)}`,
        {
          method:  'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category:   payload.category,
            label:      payload.label,
            scientific: payload.scientific || undefined,
            bbox:       editingDet.value.bbox,
            conf:       payload.conf,
          }),
        },
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      props.image.detections = [...(props.image.detections ?? []), data.detection]
      emit('detections-changed', props.image)
    } else if (payload.applyToAll) {
      // Bulk: apply this edit to every detection sharing the edited
      // detection's category. Backend returns the full updated detections;
      // splice each back into local state by id so reactivity sees the change.
      const filterCat = editingDet.value.category
      const res = await apiFetch(
        `/api/predictions/detections/bulk?path=${encodeURIComponent(props.image.filepath)}`,
        {
          method:  'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category_filter: filterCat,
            category:        payload.category,
            label:           payload.label,
            scientific:      payload.scientific || undefined,
            conf:            payload.conf,
          }),
        },
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      const byId = new Map(data.detections.map(d => [d.id, d]))
      props.image.detections = (props.image.detections ?? []).map(
        d => byId.get(d.id) || d,
      )
      // Backend rewrites image-level prediction when the bulk includes a
      // species label. Apply it locally so the side-panel "Prediction"
      // section, the gallery filter dropdown, and SpeciesView all see the
      // change without a reload.
      if (data.prediction) props.image.prediction = data.prediction
      emit('detections-changed', props.image)
    } else {
      const det = editingDet.value
      const res = await apiFetch(
        `/api/predictions/detections?path=${encodeURIComponent(props.image.filepath)}&id=${encodeURIComponent(det.id)}`,
        {
          method:  'PATCH',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            category:   payload.category,
            label:      payload.label,
            scientific: payload.scientific || undefined,
            conf:       payload.conf,
          }),
        },
      )
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const data = await res.json()
      Object.assign(det, data.detection)
      emit('detections-changed', props.image)
    }
    closeEditor()
  } catch (e) {
    editorError.value = `Save failed: ${e.message}`
  } finally {
    editorBusy.value = false
  }
}

async function onEditorDelete() {
  const det = editingDet.value
  if (!det || !det.id) return closeEditor()
  editorBusy.value = true
  editorError.value = ''
  try {
    const res = await apiFetch(
      `/api/predictions/detections?path=${encodeURIComponent(props.image.filepath)}&id=${encodeURIComponent(det.id)}`,
      { method: 'DELETE' },
    )
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    props.image.detections = (props.image.detections ?? []).filter(d => d.id !== det.id)
    emit('detections-changed', props.image)
    closeEditor()
  } catch (e) {
    editorError.value = `Delete failed: ${e.message}`
  } finally {
    editorBusy.value = false
  }
}

// ── Draw-rectangle (add new detection) ───────────────────────────────────────

const MIN_BBOX = 0.01  // smaller than 1% in either dim is treated as a misclick

function startAddDetection() {
  drawMode.value = true
  closeEditor()
}

function cancelDraw() {
  drawMode.value = false
  drawStart.value = null
  drawEnd.value = null
}

function onDrawDown(e) {
  if (!drawMode.value || e.button !== 0) return
  const p = mouseToNormalised(e)
  if (!p) return
  drawStart.value = p
  drawEnd.value = p
  e.preventDefault()
  e.stopPropagation()
  window.addEventListener('mousemove', onDrawMove)
  window.addEventListener('mouseup',   onDrawUp)
}

function onDrawMove(e) {
  if (!drawStart.value) return
  const p = mouseToNormalised(e)
  if (p) drawEnd.value = p
}

function onDrawUp(e) {
  window.removeEventListener('mousemove', onDrawMove)
  window.removeEventListener('mouseup',   onDrawUp)
  if (!drawStart.value || !drawEnd.value) {
    cancelDraw()
    return
  }
  const x = Math.min(drawStart.value.nx, drawEnd.value.nx)
  const y = Math.min(drawStart.value.ny, drawEnd.value.ny)
  const w = Math.abs(drawEnd.value.nx - drawStart.value.nx)
  const h = Math.abs(drawEnd.value.ny - drawStart.value.ny)
  drawStart.value = null
  drawEnd.value = null
  drawMode.value = false
  if (w < MIN_BBOX || h < MIN_BBOX) return  // ignore stray clicks
  // Open editor pre-loaded with the drawn bbox; commit happens on Save.
  editingDet.value = { bbox: [x, y, w, h] }
  editorMode.value = 'add'
}

/**
 * Compute a bbox's rect in wrap-local screen pixels for the overlay.
 *
 * The overlay is a sibling of the scaled container (not a child), so it
 * doesn't participate in the CSS transform. Re-deriving `left/top/w/h`
 * from (zoom, panX, panY, baseSize) here lets the bbox track the image
 * exactly while its border and label render at native pixel size — no
 * counter-scaling, no bitmap-scale blur on composite layers.
 */
function bboxScreenStyle(det) {
  const wrap = wrapRef.value
  const { w: bw, h: bh } = baseSize.value
  if (!wrap || !bw || !bh) return null
  const [x, y, w, h] = det.bbox
  const baseX = (wrap.clientWidth  - bw) / 2
  const baseY = (wrap.clientHeight - bh) / 2
  const z     = zoom.value
  return {
    left:        `${baseX + panX.value + x * bw * z}px`,
    top:         `${baseY + panY.value + y * bh * z}px`,
    width:       `${w * bw * z}px`,
    height:      `${h * bh * z}px`,
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
  baseSize.value = { w, h }
  clampPan()
}

function onImageLoad() {
  imageLoaded.value = true
  computeContainerSize()
}

// ── Zoom + pan ────────────────────────────────────────────────────────────────
function resetZoom() {
  zoom.value = 1
  panX.value = 0
  panY.value = 0
  isPanning.value = false
  zoomedDetIndex.value = null
  dragStart = null
}

/**
 * Auto-zoom the viewport so that `det.bbox` fills ~CROP_FILL_FRACTION of
 * whichever view dimension the bbox is longer in, then centre the bbox.
 */
function zoomToDetection(det) {
  const wrap = wrapRef.value
  const { w: baseW, h: baseH } = baseSize.value
  if (!wrap || !baseW || !baseH || !det?.bbox) return
  const [bx, by, bw, bh] = det.bbox
  const bboxPxW = bw * baseW
  const bboxPxH = bh * baseH
  if (bboxPxW <= 0 || bboxPxH <= 0) return
  const wrapW = wrap.clientWidth
  const wrapH = wrap.clientHeight
  // Whichever constraint saturates first = bbox fills 70% of that view dim.
  const zoomA = (CROP_FILL_FRACTION * wrapW) / bboxPxW
  const zoomB = (CROP_FILL_FRACTION * wrapH) / bboxPxH
  const newZoom = Math.max(MIN_ZOOM, Math.min(AUTO_MAX_ZOOM, Math.min(zoomA, zoomB)))
  const baseX = (wrapW - baseW) / 2
  const baseY = (wrapH - baseH) / 2
  const centerX = (bx + bw / 2) * baseW
  const centerY = (by + bh / 2) * baseH
  panX.value = wrapW / 2 - baseX - centerX * newZoom
  panY.value = wrapH / 2 - baseY - centerY * newZoom
  zoom.value = newZoom
  clampPan()
}

function onCropClick(i, det) {
  // Toggle: clicking the currently-auto-zoomed crop resets; clicking any
  // other crop jumps to it.
  if (zoomedDetIndex.value === i && zoom.value > 1) {
    resetZoom()
    return
  }
  zoomToDetection(det)
  zoomedDetIndex.value = i
}

function clampPan() {
  const wrap = wrapRef.value
  if (!wrap) return
  const { w, h } = baseSize.value
  const s = zoom.value
  const scaledW = w * s
  const scaledH = h * s
  // Layout position of the unscaled container inside wrap (flex-centered):
  const baseX = (wrap.clientWidth  - w) / 2
  const baseY = (wrap.clientHeight - h) / 2
  // Image should always cover (or be centered within) wrap.
  const minX = scaledW > wrap.clientWidth  ? wrap.clientWidth  - scaledW - baseX : -baseX
  const maxX = scaledW > wrap.clientWidth  ? -baseX                              : -baseX
  const minY = scaledH > wrap.clientHeight ? wrap.clientHeight - scaledH - baseY : -baseY
  const maxY = scaledH > wrap.clientHeight ? -baseY                              : -baseY
  if (scaledW <= wrap.clientWidth)  panX.value = 0
  else panX.value = Math.min(maxX, Math.max(minX, panX.value))
  if (scaledH <= wrap.clientHeight) panY.value = 0
  else panY.value = Math.min(maxY, Math.max(minY, panY.value))
}

function onWheel(e) {
  const wrap = wrapRef.value
  if (!wrap || !baseSize.value.w) return
  const rect = wrap.getBoundingClientRect()
  const mouseX = e.clientX - rect.left
  const mouseY = e.clientY - rect.top
  const baseX = (wrap.clientWidth  - baseSize.value.w) / 2
  const baseY = (wrap.clientHeight - baseSize.value.h) / 2
  const factor = Math.exp(-e.deltaY * 0.0015)
  // Raise the wheel cap to the current zoom so a crop-click auto-zoom
  // (which may exceed MAX_ZOOM) isn't snapped back on the next scroll.
  const maxZoom = Math.max(MAX_ZOOM, zoom.value)
  const newZoom = Math.max(MIN_ZOOM, Math.min(maxZoom, zoom.value * factor))
  if (newZoom === zoom.value) return
  // Preserve the container-local point under the cursor.
  const cx = (mouseX - baseX - panX.value) / zoom.value
  const cy = (mouseY - baseY - panY.value) / zoom.value
  panX.value = mouseX - baseX - cx * newZoom
  panY.value = mouseY - baseY - cy * newZoom
  zoom.value = newZoom
  zoomedDetIndex.value = null
  clampPan()
}

function onDoubleClick(e) {
  const wrap = wrapRef.value
  if (!wrap || !baseSize.value.w) return
  if (zoom.value > 1) {
    resetZoom()
    return
  }
  const rect = wrap.getBoundingClientRect()
  const mouseX = e.clientX - rect.left
  const mouseY = e.clientY - rect.top
  const baseX = (wrap.clientWidth  - baseSize.value.w) / 2
  const baseY = (wrap.clientHeight - baseSize.value.h) / 2
  const newZoom = 2.5
  const cx = mouseX - baseX
  const cy = mouseY - baseY
  panX.value = mouseX - baseX - cx * newZoom
  panY.value = mouseY - baseY - cy * newZoom
  zoom.value = newZoom
  zoomedDetIndex.value = null
  clampPan()
}

function onMouseDown(e) {
  if (zoom.value <= 1 || e.button !== 0) return
  dragStart = { x: e.clientX - panX.value, y: e.clientY - panY.value }
  isPanning.value = true
  window.addEventListener('mousemove', onMouseMove)
  window.addEventListener('mouseup', onMouseUp)
  e.preventDefault()
}

function onMouseMove(e) {
  if (!dragStart) return
  panX.value = e.clientX - dragStart.x
  panY.value = e.clientY - dragStart.y
  // User panned manually — a follow-up click on any crop should re-zoom
  // rather than reset.
  zoomedDetIndex.value = null
  clampPan()
}

function onMouseUp() {
  dragStart = null
  isPanning.value = false
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
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
    if (confirmingDelete.value)        cancelDelete()
    else if (editingDet.value)         closeEditor()
    else if (drawMode.value)           cancelDraw()
    else                               emit('close')
    return
  }
  if (confirmingDelete.value || editingDet.value) return
  if (e.key === 'ArrowLeft')  navigate(-1)
  if (e.key === 'ArrowRight') navigate(1)
}

onMounted(() => {
  window.addEventListener('keydown', onKeydown)
  if (wrapRef.value && 'ResizeObserver' in window) {
    resizeObserver = new ResizeObserver(() => computeContainerSize())
    resizeObserver.observe(wrapRef.value)
  }
  loadCustom()
})
onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown)
  window.removeEventListener('mousemove', onMouseMove)
  window.removeEventListener('mouseup', onMouseUp)
  resizeObserver?.disconnect()
})

watch(() => props.image, () => {
  imageLoaded.value = false
  baseSize.value = { w: 0, h: 0 }
  resetZoom()
  confirmingDelete.value = false
  deleteError.value = ''
  // Reset edit state on navigation so an open editor doesn't carry over to
  // a different image, but stay in edit mode itself — the user is likely to
  // edit several images in one session.
  closeEditor()
  cancelDraw()
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

.modal__toggle--active {
  color: white;
  background: var(--accent, #2d7d46);
  border-color: var(--accent, #2d7d46);
}

.modal__toggle--draw:not(.modal__toggle--off) {
  color: #1f2937;
  background: #fbbf24;
  border-color: #d97706;
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

.modal__carousel > .crop {
  cursor: pointer;
  transition: box-shadow 0.15s, transform 0.15s;
}
.modal__carousel > .crop:hover {
  transform: translateY(-1px);
}
.modal__carousel > .crop--active {
  box-shadow: 0 0 0 2px var(--accent, #60a5fa);
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
  will-change: transform;
}

.modal__canvas-container--zoomed { cursor: grab; }
.modal__canvas-container--zoomed.modal__canvas-container--panning { cursor: grabbing; }
.modal__canvas-container--panning,
.modal__canvas-container--panning * { user-select: none; }

.modal__img {
  display: block;
  width: 100%;
  height: 100%;
  -webkit-user-drag: none;
  user-select: none;
}

/* Screen-space overlay for bounding boxes.
   Lives outside the scaled .modal__canvas-container so borders and
   labels always render at native pixel size, no matter how far we've
   zoomed in. wrap has overflow:hidden so off-screen boxes clip cleanly. */
.modal__bbox-overlay {
  position: absolute;
  inset: 0;
  pointer-events: none;
}

.modal__bbox {
  position: absolute;
  border: 2px solid;
  pointer-events: none;
  transition: box-shadow 0.12s, border-style 0.12s;
}

.modal__bbox--manual {
  border-style: dashed;
}

/* In edit mode, the overlay flips to pointer-events:auto so boxes are
   clickable. Boxes themselves opt-in via a hover halo. */
.modal__bbox-overlay--editable { pointer-events: none; }
.modal__bbox-overlay--editable .modal__bbox {
  pointer-events: auto;
  cursor: pointer;
}
.modal__bbox-overlay--editable .modal__bbox:hover {
  box-shadow: 0 0 0 3px rgba(255,255,255,0.35);
}
.modal__bbox--editing {
  box-shadow: 0 0 0 3px rgba(96,165,250,0.65);
}

.modal__bbox-label {
  position: absolute;
  bottom: 100%;
  left: -2px;
  font-size: 11px;
  font-weight: 600;
  color: #000;
  padding: 2px 5px;
  white-space: nowrap;
  border-radius: 3px 3px 0 0;
  display: flex;
  align-items: center;
  gap: 4px;
}

.modal__bbox-manual {
  font-size: 10px;
  line-height: 1;
}

/* Draw layer captures the drag for new detections without triggering
   pan-on-drag. Sits above the canvas container but below the editor. */
.modal__draw-layer {
  position: absolute;
  inset: 0;
  cursor: crosshair;
  z-index: 5;
  background: rgba(0,0,0,0.05);
}

.modal__draw-rect {
  position: absolute;
  border: 2px dashed #fbbf24;
  background: rgba(251,191,36,0.15);
  pointer-events: none;
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

.modal__zoom-indicator {
  position: absolute;
  bottom: 8px;
  right: 8px;
  display: flex;
  align-items: center;
  gap: 4px;
  background: rgba(0,0,0,0.6);
  color: #fff;
  font-size: 12px;
  padding: 2px 4px 2px 8px;
  border-radius: 999px;
  font-variant-numeric: tabular-nums;
}

.modal__zoom-reset {
  background: none;
  border: none;
  color: #fff;
  cursor: pointer;
  font-size: 11px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0;
  opacity: 0.7;
}
.modal__zoom-reset:hover { opacity: 1; background: rgba(255,255,255,0.15); }

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
  background: none;
  border: 1px solid transparent;
  color: var(--text);
  text-align: left;
  width: 100%;
  padding: 3px 6px;
  border-radius: 4px;
  font: inherit;
  font-size: 12px;
}

.panel__det--editable {
  cursor: pointer;
}
.panel__det--editable:hover {
  background: var(--surface2);
  border-color: var(--border);
}
.panel__det--editing {
  background: var(--surface2);
  border-color: #60a5fa;
}

.panel__det-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.panel__det-manual {
  font-size: 11px;
  color: var(--text-muted);
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
