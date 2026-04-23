<template>
  <div class="species-view">
    <aside class="species-view__tree">
      <div class="species-view__tree-header">Species hierarchy</div>
      <TreeNode
        v-if="tree"
        :node="tree"
        :selected-path="selectedPath"
        @select="selectedPath = $event.path"
      />
    </aside>

    <section class="species-view__list">
      <div v-if="!selectedPath" class="state-msg">Select a node in the tree to see species.</div>
      <div v-else-if="speciesCards.length === 0" class="state-msg">No detections under this node.</div>
      <div v-else class="species-cards">
        <article v-for="card in speciesCards" :key="card.key" class="species-card">
          <header class="species-card__header">
            <span class="species-card__name">{{ card.commonName }}</span>
            <span v-if="card.scientific" class="species-card__scientific">{{ card.scientific }}</span>
            <span class="species-card__count">{{ card.count }} detection{{ card.count === 1 ? '' : 's' }}</span>
          </header>
          <div class="species-card__body">
            <div class="species-card__histogram">
              <div class="histogram__block">
                <div class="histogram__title">Time of Day</div>
                <div class="histogram__chart">
                  <div class="histogram__y-axis">
                    <span>{{ Math.max(...card.hours) }}</span>
                    <span>0</span>
                  </div>
                  <div class="histogram__bars-wrap">
                    <svg class="histogram__svg" viewBox="0 0 240 48" preserveAspectRatio="none">
                      <line x1="0" y1="0" x2="0" y2="48" class="histogram__axis" />
                      <rect
                        v-for="(n, h) in card.hours"
                        :key="h"
                        :x="h * 10 + 1"
                        :width="8"
                        :height="card.hours[h] === 0 ? 1 : Math.max(2, (n / Math.max(...card.hours)) * 44)"
                        :y="48 - (card.hours[h] === 0 ? 1 : Math.max(2, (n / Math.max(...card.hours)) * 44))"
                        :class="['histogram__bar', { 'histogram__bar--zero': n === 0, 'histogram__bar--hover': barHover?.id === `${card.key}-h${h}` }]"
                        @click="emit('filter', { species: card.rawName, hour: h })"
                        @mouseenter="barHover = { id: `${card.key}-h${h}`, label: `${h}:00–${h}:59`, count: n, x: $event.clientX, y: $event.clientY }"
                        @mousemove="barHover = { ...barHover, x: $event.clientX, y: $event.clientY }"
                        @mouseleave="barHover = null"
                      />
                    </svg>
                    <div class="histogram__labels">
                      <span>12a</span><span>6a</span><span>12p</span><span>6p</span><span>12a</span>
                    </div>
                  </div>
                </div>
              </div>

              <div class="histogram__block">
                <div class="histogram__title">Month of Year</div>
                <div class="histogram__chart">
                  <div class="histogram__y-axis">
                    <span>{{ Math.max(...card.months) }}</span>
                    <span>0</span>
                  </div>
                  <div class="histogram__bars-wrap">
                    <svg class="histogram__svg" viewBox="0 0 120 48" preserveAspectRatio="none">
                      <line x1="0" y1="0" x2="0" y2="48" class="histogram__axis" />
                      <rect
                        v-for="(n, m) in card.months"
                        :key="m"
                        :x="m * 10 + 1"
                        :width="8"
                        :height="card.months[m] === 0 ? 1 : Math.max(2, (n / Math.max(...card.months)) * 44)"
                        :y="48 - (card.months[m] === 0 ? 1 : Math.max(2, (n / Math.max(...card.months)) * 44))"
                        :class="['histogram__bar', { 'histogram__bar--zero': n === 0, 'histogram__bar--hover': barHover?.id === `${card.key}-m${m}` }]"
                        @mouseenter="barHover = { id: `${card.key}-m${m}`, label: MONTH_NAMES[m], count: n, x: $event.clientX, y: $event.clientY }"
                        @mousemove="barHover = { ...barHover, x: $event.clientX, y: $event.clientY }"
                        @mouseleave="barHover = null"
                      />
                    </svg>
                    <div class="histogram__labels">
                      <span>Jan</span><span>Apr</span><span>Jul</span><span>Oct</span><span>Dec</span>
                    </div>
                  </div>
                </div>
              </div>
            </div>

          <div class="species-card__crops">
            <button
              v-for="top in card.top"
              :key="imagePathOf(top.pred)"
              class="species-card__crop"
              @click="$emit('select', top.pred)"
              @mouseenter="showPreview(top, $event)"
              @mousemove="movePreview($event)"
              @mouseleave="hidePreview"
            >
              <img
                v-if="top.cropPath"
                :src="imageUrl(top.cropPath)"
                :alt="card.commonName"
                loading="lazy"
              />
              <div
                v-else-if="top.bbox"
                class="species-card__crop-bbox"
                :style="bboxStyle(top)"
              />
              <div v-else class="species-card__crop-placeholder">no crop</div>
              <div class="species-card__crop-meta">
                <span>{{ Math.round((top.pred.prediction_score ?? 0) * 100) }}%</span>
                <span v-if="top.when">{{ top.when }}</span>
              </div>
            </button>
          </div>
          </div>
        </article>
      </div>
    </section>

    <Teleport to="body">
      <img
        v-if="preview.src"
        class="species-view__preview"
        :src="preview.src"
        :style="{ left: preview.x + 'px', top: preview.y + 'px' }"
      />
      <div
        v-if="barHover"
        class="species-view__hist-tooltip"
        :style="{ left: barHover.x + 12 + 'px', top: barHover.y + 12 + 'px' }"
      >{{ barHover.label }} — {{ barHover.count }} detection{{ barHover.count === 1 ? '' : 's' }}</div>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, reactive, computed } from 'vue'

const preview  = reactive({ src: null, x: 0, y: 0 })
const barHover = ref(null)

const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function showPreview(top, e) {
  preview.src = top.cropPath ? imageUrl(top.cropPath) : null
  if (preview.src) movePreview(e)
}

function movePreview(e) {
  preview.x = e.clientX + 16
  preview.y = e.clientY + 16
}

function hidePreview() {
  preview.src = null
}
import TreeNode from './TreeNode.vue'
import { imageUrl } from '../firebase.js'

const props = defineProps({ predictions: Array })
const emit = defineEmits(['select', 'filter'])

const selectedPath = ref(null)

// ── Build the taxonomy tree from prediction.raw (semicolon-separated) ─────────
// SpeciesNet label format: "{uuid};{kingdom};{phylum};{class};{order};{family};{genus};{species};{common_name}"
function taxonomyChain(pred) {
  const raw = pred.prediction?.raw
  if (!raw) return null
  const parts = raw.split(';').map(p => p.trim())
  // Drop the uuid at index 0 and the common_name at the end (we'll attach it separately).
  const levels = parts.slice(1, -1).filter(Boolean)
  const commonName = parts[parts.length - 1] || pred.prediction?.common_name || 'unknown'
  return { levels, commonName, scientific: pred.prediction?.scientific || '' }
}

const tree = computed(() => {
  const root = { label: 'All species', path: '', children: [], count: 0, preds: [] }
  const indexByPath = new Map()
  indexByPath.set('', root)

  for (const pred of props.predictions) {
    if (!pred.prediction) continue
    const chain = taxonomyChain(pred)
    if (!chain) continue
    const segments = [...chain.levels, chain.commonName]

    let cur = root
    cur.count++
    cur.preds.push(pred)

    let path = ''
    for (let i = 0; i < segments.length; i++) {
      path = path + '/' + segments[i]
      let child = indexByPath.get(path)
      if (!child) {
        child = {
          label: capitalize(segments[i]),
          path,
          children: [],
          count: 0,
          preds: [],
        }
        cur.children.push(child)
        indexByPath.set(path, child)
      }
      child.count++
      child.preds.push(pred)
      cur = child
    }
  }

  sortRecursive(root)
  return root
})

function sortRecursive(node) {
  node.children.sort((a, b) => a.label.localeCompare(b.label))
  for (const child of node.children) sortRecursive(child)
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

// ── Right-hand list: species cards for every leaf under the selected node ────
const selectedNode = computed(() => {
  if (selectedPath.value == null) return null
  return findNode(tree.value, selectedPath.value)
})

function findNode(node, path) {
  if (node.path === path) return node
  for (const c of node.children) {
    const hit = findNode(c, path)
    if (hit) return hit
  }
  return null
}

const speciesCards = computed(() => {
  const node = selectedNode.value
  if (!node) return []

  // Gather by species (common name). If the selected node is itself a species,
  // this yields exactly one card.
  const groups = new Map()
  for (const pred of node.preds) {
    const name = pred.prediction?.common_name || 'unknown'
    if (!groups.has(name)) groups.set(name, [])
    groups.get(name).push(pred)
  }

  const cards = []
  for (const [commonName, preds] of groups.entries()) {
    const sorted = [...preds].sort((a, b) => {
      const sa = a.prediction_score ?? 0
      const sb = b.prediction_score ?? 0
      if (sb !== sa) return sb - sa
      const ta = timestampOf(a)
      const tb = timestampOf(b)
      return tb.localeCompare(ta)
    })
    const top = sorted.slice(0, 5).map(pred => {
      const det = bestDetection(pred)
      return {
        pred,
        cropPath: det?.crop_gcs_path || null,
        bbox: det?.bbox || null,
        when: formatTimestamp(timestampOf(pred)),
      }
    })
    const hours  = new Array(24).fill(0)
    const months = new Array(12).fill(0)
    for (const pred of preds) {
      const ts = timestampOf(pred)
      if (ts.length >= 10) {
        const h = parseInt(ts.slice(8, 10), 10)
        if (h >= 0 && h < 24) hours[h]++
      }
      if (ts.length >= 6) {
        const m = parseInt(ts.slice(4, 6), 10) - 1
        if (m >= 0 && m < 12) months[m]++
      }
    }
    cards.push({
      key: commonName,
      rawName: commonName,
      commonName: capitalize(commonName),
      scientific: preds[0].prediction?.scientific || '',
      count: preds.length,
      top,
      hours,
      months,
    })
  }

  cards.sort((a, b) => b.count - a.count)
  return cards
})

function timestampOf(pred) {
  if (pred.captured_at) return pred.captured_at
  return pred.filename ? pred.filename.substring(0, 14) : ''
}

function imagePathOf(pred) {
  return pred.gcs_path || pred.filepath || ''
}

function bestDetection(pred) {
  const dets = pred.detections || []
  let best = null
  for (const d of dets) {
    if (!d.bbox) continue
    if (!best || (d.conf ?? 0) > (best.conf ?? 0)) best = d
  }
  return best
}

function bboxStyle(top) {
  const [bx, by, bw, bh] = top.bbox
  if (!bw || !bh) return {}
  const sizeX = (100 / bw).toFixed(2)
  const sizeY = (100 / bh).toFixed(2)
  const posX  = (bx / (1 - bw) * 100).toFixed(2)
  const posY  = (by / (1 - bh) * 100).toFixed(2)
  return {
    backgroundImage: `url("${imageUrl(imagePathOf(top.pred))}")`,
    backgroundSize: `${sizeX}% ${sizeY}%`,
    backgroundPosition: `${isFinite(posX) ? posX : 0}% ${isFinite(posY) ? posY : 0}%`,
  }
}

function formatTimestamp(ts) {
  if (!ts || ts.length < 8) return ''
  const y = ts.slice(0, 4), mo = ts.slice(4, 6), d = ts.slice(6, 8)
  return `${y}-${mo}-${d}`
}
</script>

<style scoped>
.species-view {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  height: 100%;
  min-height: 0;
}

.species-view__tree {
  overflow-y: auto;
  border-right: 1px solid var(--border, #e0e0e0);
  padding: 8px 4px 8px 0;
}
.species-view__tree-header {
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  color: #888;
  letter-spacing: 0.05em;
  padding: 4px 6px 8px;
}

.species-view__list { overflow-y: auto; padding: 8px 12px; }

.state-msg { padding: 24px; color: #888; font-size: 14px; }

.species-cards { display: flex; flex-direction: column; gap: 16px; }

.species-card {
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 8px;
  padding: 12px;
  background: var(--surface);
  color: var(--text);
}
.species-card__header {
  display: flex;
  align-items: baseline;
  gap: 10px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.species-card__name { font-size: 16px; font-weight: 600; }
.species-card__scientific { font-size: 12px; color: #888; font-style: italic; }
.species-card__count { margin-left: auto; font-size: 12px; color: #666; }

.species-card__crops {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}
.species-card__crop {
  position: relative;
  flex: 0 0 auto;
  width: 210px;
  padding: 0;
  background: none;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 6px;
  cursor: pointer;
  display: flex;
  flex-direction: column;
}

.species-card__crop > img:first-of-type { border-radius: 6px 6px 0 0; }
.species-card__crop:hover { border-color: var(--accent, #2d7d46); }
.species-card__crop > img:first-of-type { display: block; width: 100%; height: 150px; object-fit: contain; background: var(--surface2); }
.species-card__crop-bbox {
  width: 100%;
  height: 150px;
  background-repeat: no-repeat;
  background-color: var(--surface2);
}
.species-card__crop-placeholder {
  height: 150px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-muted);
  font-size: 11px;
  background: var(--surface2);
}
.species-card__body {
  display: flex;
  gap: 12px;
  align-items: stretch;
}

.species-card__histogram {
  flex: 0 0 420px;
  display: flex;
  flex-direction: row;
  gap: 12px;
}
.histogram__block {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-height: 0;
}
.histogram__title {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-muted);
  text-align: center;
}
.histogram__chart {
  display: flex;
  gap: 4px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
}
.histogram__y-axis {
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  align-items: flex-end;
  font-size: 11px;
  color: var(--text-muted);
  padding-bottom: 16px;
}
.histogram__bars-wrap {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-height: 0;
}
.histogram__svg {
  display: block;
  width: 100%;
  flex: 1;
  min-height: 0;
  overflow: visible;
}
.histogram__axis {
  stroke: var(--border);
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.histogram__bar {
  fill: var(--accent, #2d7d46);
  opacity: 0.7;
  cursor: pointer;
  transition: opacity 0.1s;
}
.histogram__bar--zero { fill: var(--border); opacity: 0.4; }
.histogram__bar--hover { opacity: 1; fill: #4ade80; }
.histogram__labels {
  display: flex;
  justify-content: space-between;
  font-size: 10px;
  color: var(--text-muted);
  padding: 0 1px;
  margin-top: 2px;
}

.species-view__hist-tooltip {
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  background: var(--surface, #1c1c1c);
  border: 1px solid var(--border, #444);
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  color: var(--text);
  white-space: nowrap;
  box-shadow: 0 4px 12px rgba(0,0,0,0.5);
}

.species-view__preview {
  position: fixed;
  z-index: 9999;
  pointer-events: none;
  max-width: 80vw;
  max-height: 80vh;
  width: auto;
  height: auto;
  border: 1px solid var(--border, #444);
  border-radius: 6px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.7);
}

.species-card__crop-meta {
  display: flex;
  justify-content: space-between;
  padding: 4px 6px;
  font-size: 11px;
  color: var(--text-muted);
  background: var(--surface2);
}
</style>
