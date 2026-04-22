<template>
  <div class="modal-backdrop" @click.self="$emit('close')">
    <div class="modal">

      <!-- Toolbar -->
      <div class="modal__toolbar">
        <span class="modal__filename">{{ image.filename }}</span>
        <div class="modal__toolbar-right">
          <button
            :class="['modal__toggle', { active: showPreview }]"
            :disabled="!hasPreview"
            :title="hasPreview ? 'Toggle annotated preview' : 'No preview available'"
            @click="togglePreview"
          >Annotated</button>
          <button class="modal__close" @click="$emit('close')">✕</button>
        </div>
      </div>

      <div class="modal__body">
        <div class="modal__left">
        <!-- Image + bbox overlay -->
        <div class="modal__image-wrap">
          <div class="modal__canvas-container" ref="containerRef">
            <img
              ref="imgRef"
              :src="imageSrc"
              :alt="image.filename"
              class="modal__img"
              @load="onImageLoad"
              @error="onImageError"
            />
            <!-- Bbox overlays — rendered after image loads -->
            <template v-if="imageLoaded && !showPreview">
              <div
                v-for="(det, i) in significantDetections"
                :key="i"
                class="modal__bbox"
                :style="bboxStyle(det)"
                :title="`${det.label} ${(det.conf * 100).toFixed(0)}%`"
              >
                <span class="modal__bbox-label" :style="{ background: categoryColor(det.category) }">
                  {{ det.label }} {{ (det.conf * 100).toFixed(0) }}%
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
            :image-src="imageSrc"
            :det="det"
            :color="categoryColor(det.category)"
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
                <span>{{ capitalize(det.label) }}</span>
                <span class="panel__det-conf">{{ (det.conf * 100).toFixed(0) }}%</span>
              </div>
            </div>
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
import DetectionCrop from './DetectionCrop.vue'

const props = defineProps({
  image: Object,
  allImages: Array,
})
const emit = defineEmits(['close', 'navigate'])

const imgRef = ref(null)
const containerRef = ref(null)
const imageLoaded = ref(false)
const showPreview = ref(false)
const hasPreview = ref(true)

const currentIndex = computed(() => props.allImages.indexOf(props.image))

const imageSrc = computed(() => {
  if (showPreview.value) {
    return `/api/preview?path=${encodeURIComponent(props.image.filepath)}`
  }
  return `/api/image?path=${encodeURIComponent(props.image.filepath)}`
})

const significantDetections = computed(() =>
  (props.image.detections ?? []).filter(d => d.conf >= 0.1)
)

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

function onImageLoad() {
  imageLoaded.value = true
}

function onImageError() {
  if (showPreview.value) {
    hasPreview.value = false
    showPreview.value = false
  }
}

function togglePreview() {
  imageLoaded.value = false
  showPreview.value = !showPreview.value
}

function navigate(delta) {
  const next = props.allImages[currentIndex.value + delta]
  if (next) {
    imageLoaded.value = false
    showPreview.value = false
    hasPreview.value = true
    emit('navigate', next)
  }
}

function onKeydown(e) {
  if (e.key === 'Escape') emit('close')
  if (e.key === 'ArrowLeft')  navigate(-1)
  if (e.key === 'ArrowRight') navigate(1)
}

onMounted(() => window.addEventListener('keydown', onKeydown))
onUnmounted(() => window.removeEventListener('keydown', onKeydown))

watch(() => props.image, () => {
  imageLoaded.value = false
  showPreview.value = false
  hasPreview.value = true
})
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
  width: min(1200px, 100%);
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

.modal__toggle {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 4px 10px;
  font-size: 12px;
  transition: color 0.15s, border-color 0.15s;
}

.modal__toggle.active {
  border-color: var(--animal);
  color: var(--animal);
}

.modal__toggle:disabled {
  opacity: 0.35;
  cursor: default;
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
  display: inline-flex;
  max-width: 100%;
  max-height: 100%;
}

.modal__img {
  display: block;
  max-width: 100%;
  max-height: calc(100vh - 160px);
  object-fit: contain;
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
</style>
