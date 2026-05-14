import { ref, computed } from 'vue'
import { apiFetch } from '../firebase.js'
import {Category, ImageInfo, Kind, Taxon} from "../model/model.ts";

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
export function useSpeciesCatalog(predictionsRef: Array<ImageInfo>) {
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
  const flatSpecies = computed((): Taxon[] => {
    const seen = new Map<string, any>()  // lowercased common_name → entry
    const add = (cn: String, scientific: string, raw: string, extra = {}) => {
      if (!cn) return
      const key: string= cn.toLowerCase()
      if (Category.contains(key) || seen.has(key)) return
      seen.set(key, { common_name: cn, scientific: scientific || '', raw: raw || '', ...extra })
    }
    for (const pred of predictionsRef ?? []) {
      for (const [cls, score] of pred.prediction.top5) {
        add(Kind.label(cls), Kind.getSpecies(cls).scientific, Kind.getSpecies(cls).raw, { source: 'inferred' })
      }
      if (pred.prediction.isSpecies()) {
        const taxon = pred.prediction.classification as Taxon
        add(taxon.common_name, taxon.scientific, taxon.raw, { source: 'inferred' })
      }
      // Detection-level species (manual edits store species directly on the detection)
      for (const det of (pred.detections ?? [])) {
        if (det.label && det.category == Category.ANIMAL) {
          add(det.label(), det.classification.scientific, '', { source: 'detection' })
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
  function topFive(image: ImageInfo): Array<Taxon> {
    return (image?.prediction?.top5Array() ?? []).filter(
      c => c instanceof Taxon
    )
  }

  return {
    flatSpecies,
    topFive,
    customSpecies,
    customLoaded,
    loadCustom,
    addCustom
  }
}
