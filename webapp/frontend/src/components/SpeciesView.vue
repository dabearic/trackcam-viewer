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
          <div class="species-card__crops">
            <button
              v-for="top in card.top"
              :key="top.pred.gcs_path"
              class="species-card__crop"
              @click="$emit('select', top.pred)"
            >
              <img
                v-if="top.cropPath"
                :src="imageUrl(top.cropPath)"
                :alt="card.commonName"
                loading="lazy"
              />
              <div v-else class="species-card__crop-placeholder">no crop</div>
              <div class="species-card__crop-meta">
                <span>{{ Math.round((top.pred.prediction_score ?? 0) * 100) }}%</span>
                <span v-if="top.when">{{ top.when }}</span>
              </div>
            </button>
          </div>
        </article>
      </div>
    </section>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import TreeNode from './TreeNode.vue'
import { imageUrl } from '../firebase.js'

const props = defineProps({ predictions: Array })
defineEmits(['select'])

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
    const top = sorted.slice(0, 5).map(pred => ({
      pred,
      cropPath: bestCropPath(pred),
      when: formatTimestamp(timestampOf(pred)),
    }))
    cards.push({
      key: commonName,
      commonName: capitalize(commonName),
      scientific: preds[0].prediction?.scientific || '',
      count: preds.length,
      top,
    })
  }

  cards.sort((a, b) => b.count - a.count)
  return cards
})

function timestampOf(pred) {
  if (pred.captured_at) return pred.captured_at
  return pred.filename ? pred.filename.substring(0, 14) : ''
}

function bestCropPath(pred) {
  const dets = pred.detections || []
  let best = null
  for (const d of dets) {
    if (!d.crop_gcs_path) continue
    if (!best || (d.conf ?? 0) > (best.conf ?? 0)) best = d
  }
  return best?.crop_gcs_path || null
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
  background: white;
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
}
.species-card__crop {
  flex: 0 0 auto;
  width: 140px;
  padding: 0;
  background: none;
  border: 1px solid var(--border, #e0e0e0);
  border-radius: 6px;
  overflow: hidden;
  cursor: pointer;
  display: flex;
  flex-direction: column;
}
.species-card__crop:hover { border-color: var(--accent, #2d7d46); }
.species-card__crop img { display: block; width: 100%; height: 100px; object-fit: cover; }
.species-card__crop-placeholder {
  height: 100px;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #aaa;
  font-size: 11px;
  background: #f5f5f5;
}
.species-card__crop-meta {
  display: flex;
  justify-content: space-between;
  padding: 4px 6px;
  font-size: 11px;
  color: #666;
  background: #fafafa;
}
</style>
