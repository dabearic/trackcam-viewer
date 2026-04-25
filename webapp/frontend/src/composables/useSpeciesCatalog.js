import { ref, computed } from 'vue'
import { apiFetch } from '../firebase.js'

// Common-name buckets that are NOT real species — these come from the
// MegaDetector / SpeciesNet category fallbacks and should be hidden from
// the species picker.
const NON_SPECIES = new Set(['blank', 'human', 'vehicle', 'animal'])

/**
 * Builds two views of the species universe for the picker UI:
 *
 *  - topFive(image)  → the inference candidates for the current photo
 *  - flatSpecies     → every distinct species seen across loaded predictions
 *                      plus user-added custom species
 *
 * The composable owns a small bit of state (custom species fetched from
 * the backend) so callers don't have to. The frontend used to render a
 * class > order > family > leaf tree as well; that was dropped in favor
 * of search-only navigation, so taxonomy parsing/grouping lives only in
 * the backend lookup endpoints now.
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

  /** Inference candidates for one image — top-5 minus non-species buckets. */
  function topFive(image) {
    return (image?.top5 ?? []).filter(
      c => c.common_name && !NON_SPECIES.has(c.common_name.toLowerCase()),
    )
  }

  return {
    flatSpecies,
    topFive,
    customSpecies,
    customLoaded,
    loadCustom,
    addCustom,
    NON_SPECIES,
  }
}
