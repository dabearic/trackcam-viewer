import { ref, computed } from 'vue'
import { apiFetch } from '../firebase.js'

// Common-name buckets that are NOT real species — these come from the
// MegaDetector / SpeciesNet category fallbacks and should be hidden from
// the species picker.
const NON_SPECIES = new Set(['blank', 'human', 'vehicle', 'animal'])

const cap = s => (s ? s.charAt(0).toUpperCase() + s.slice(1) : '')

/**
 * SpeciesNet labels look like:
 *   uuid;class;order;family;genus;species;common_name
 * Some entries are shorter (e.g. just `;blank` for the blank class), so we
 * defensively pad to length 7 and strip empties later.
 */
function parseTaxonomy(rawLabel) {
  if (!rawLabel) return null
  const parts = rawLabel.split(';')
  while (parts.length < 7) parts.push('')
  const [id, klass, order, family, genus, species, common_name] = parts
  const scientific = (genus && species)
    ? `${cap(genus)} ${species}`
    : cap(klass)
  return { id, class: klass, order, family, genus, species, common_name, scientific, raw: rawLabel }
}

/**
 * Builds three views of the species universe for the picker UI:
 *
 *  - topFive(image)  → the inference candidates for the current photo
 *  - flatSpecies     → every distinct species seen across loaded predictions
 *                      plus user-added custom species
 *  - tree            → flatSpecies grouped by class > order > family > leaf
 *
 * The composable owns a small bit of state (custom species fetched from
 * the backend) so callers don't have to.
 */
export function useSpeciesCatalog(predictionsRef) {
  const customSpecies = ref([])
  const customLoaded  = ref(false)

  async function loadCustom() {
    try {
      const res = await apiFetch('/api/species-custom')
      if (!res.ok) return
      const data = await res.json()
      customSpecies.value = data.species ?? []
    } catch {
      // Custom species are optional — silent failure, just leave the list empty
    } finally {
      customLoaded.value = true
    }
  }

  async function addCustom({ common_name, scientific = '', parent = '' }) {
    const res = await apiFetch('/api/species-custom', {
      method:  'POST',
      headers: { 'Content-Type': 'application/json' },
      body:    JSON.stringify({ common_name, scientific, parent }),
    })
    if (!res.ok) throw new Error(`HTTP ${res.status}`)
    const data = await res.json()
    const sp   = data.species
    // Backend de-dups by lower(common_name); only push if it's actually new
    if (!customSpecies.value.find(
      s => s.common_name.toLowerCase() === sp.common_name.toLowerCase()
    )) {
      customSpecies.value.push(sp)
    }
    return sp
  }

  /** Distinct species across all loaded predictions + custom additions. */
  const flatSpecies = computed(() => {
    const seen = new Map()  // lowercased common_name → entry
    const add = (cn, scientific, raw, extra = {}) => {
      if (!cn) return
      const key = cn.toLowerCase()
      if (NON_SPECIES.has(key) || seen.has(key)) return
      seen.set(key, { common_name: cn, scientific: scientific || '', raw: raw || '', ...extra })
    }
    for (const pred of predictionsRef.value ?? []) {
      for (const cls of (pred.top5 ?? [])) {
        add(cls.common_name, cls.scientific, cls.raw, { source: 'inferred' })
      }
      if (pred.prediction?.common_name) {
        add(pred.prediction.common_name, pred.prediction.scientific, pred.prediction.raw, { source: 'inferred' })
      }
      // Detection-level species (manual edits store species directly on the detection)
      for (const det of (pred.detections ?? [])) {
        if (det.label && det.category === '1') {
          add(det.label, det.scientific, '', { source: 'detection' })
        }
      }
    }
    for (const cs of customSpecies.value) {
      add(cs.common_name, cs.scientific, '', { custom: true, parent: cs.parent || '' })
    }
    return Array.from(seen.values()).sort(
      (a, b) => a.common_name.localeCompare(b.common_name),
    )
  })

  /** Hierarchical tree: class → order → family → species leaf. */
  const tree = computed(() => {
    const root = { children: new Map(), label: '', key: '' }

    function ensure(parent, key, label) {
      const k = key || '_unknown'
      if (!parent.children.has(k)) {
        parent.children.set(k, { children: new Map(), label: label || 'Other', key: k })
      }
      return parent.children.get(k)
    }

    for (const sp of flatSpecies.value) {
      const tax = parseTaxonomy(sp.raw)
      // Custom species may have `parent` like "mammalia;carnivora;felidae"
      const parentParts = (sp.parent || '').split(';').map(s => s.trim())
      const klass  = tax?.class  || parentParts[0] || ''
      const order  = tax?.order  || parentParts[1] || ''
      const family = tax?.family || parentParts[2] || ''

      const cNode = ensure(root, klass.toLowerCase(),  cap(klass))
      const oNode = order  ? ensure(cNode, order.toLowerCase(),  cap(order))  : cNode
      const fNode = family ? ensure(oNode, family.toLowerCase(), cap(family)) : oNode
      const leaf  = ensure(fNode, sp.common_name.toLowerCase(), cap(sp.common_name))
      leaf.species = sp
    }

    // Recursively convert nested Maps → arrays, sort siblings alphabetically.
    function toArr(node) {
      const children = Array.from(node.children.values())
        .map(toArr)
        .sort((a, b) => a.label.localeCompare(b.label))
      return { label: node.label, key: node.key, species: node.species, children }
    }
    return toArr(root).children
  })

  /** Inference candidates for one image — top-5 minus non-species buckets. */
  function topFive(image) {
    return (image?.top5 ?? []).filter(
      c => c.common_name && !NON_SPECIES.has(c.common_name.toLowerCase()),
    )
  }

  return {
    flatSpecies,
    tree,
    topFive,
    customSpecies,
    customLoaded,
    loadCustom,
    addCustom,
    NON_SPECIES,
  }
}
