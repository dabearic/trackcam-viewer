<template>
  <div class="backdrop" @click.self="$emit('close')">
    <div class="summary">

      <div class="summary__header">
        <div>
          <h2 class="summary__date">{{ formatDate(day.date) }}</h2>
          <p class="summary__stat">{{ day.images.length }} images across {{ day.events.length }} event{{ day.events.length !== 1 ? 's' : '' }}</p>
        </div>
        <button class="summary__close" @click="$emit('close')">✕</button>
      </div>

      <div class="summary__charts">
        <div class="chart-block">
          <h3 class="chart-block__title">Predictions</h3>
          <div class="chart-block__body">
            <svg viewBox="0 0 100 100" class="donut">
              <circle cx="50" cy="50" r="35" fill="none" stroke="var(--surface2)" stroke-width="18" />
              <circle
                v-for="s in predictionSlices"
                :key="s.label"
                cx="50" cy="50" r="35"
                fill="none"
                :stroke="s.color"
                stroke-width="18"
                :stroke-dasharray="`${s.length} ${CIRCUMFERENCE}`"
                :stroke-dashoffset="-s.offset"
                transform="rotate(-90 50 50)"
              />
              <text x="50" y="54" text-anchor="middle" class="donut__total">{{ day.images.length }}</text>
            </svg>
            <ul class="legend">
              <li v-for="s in predictionSlices" :key="s.label" class="legend__item">
                <span class="legend__dot" :style="{ background: s.color }"></span>
                <span class="legend__label">{{ capitalize(s.label) }}</span>
                <span class="legend__count">{{ s.value }}</span>
                <span class="legend__pct">{{ pct(s.value, day.images.length) }}%</span>
              </li>
            </ul>
          </div>
        </div>

        <div class="chart-block">
          <h3 class="chart-block__title">Detections <span class="chart-block__sub">≥70% conf</span></h3>
          <div class="chart-block__body">
            <template v-if="detectionTotal > 0">
              <svg viewBox="0 0 100 100" class="donut">
                <circle cx="50" cy="50" r="35" fill="none" stroke="var(--surface2)" stroke-width="18" />
                <circle
                  v-for="s in detectionSlices"
                  :key="s.label"
                  cx="50" cy="50" r="35"
                  fill="none"
                  :stroke="s.color"
                  stroke-width="18"
                  :stroke-dasharray="`${s.length} ${CIRCUMFERENCE}`"
                  :stroke-dashoffset="-s.offset"
                  transform="rotate(-90 50 50)"
                />
                <text x="50" y="54" text-anchor="middle" class="donut__total">{{ detectionTotal }}</text>
              </svg>
              <ul class="legend">
                <li v-for="s in detectionSlices" :key="s.label" class="legend__item">
                  <span class="legend__dot" :style="{ background: s.color }"></span>
                  <span class="legend__label">{{ capitalize(s.label) }}</span>
                  <span class="legend__count">{{ s.value }}</span>
                  <span class="legend__pct">{{ pct(s.value, detectionTotal) }}%</span>
                </li>
              </ul>
            </template>
            <p v-else class="chart-block__empty">No detections above 70%</p>
          </div>
        </div>
      </div>

    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({ day: Object })
defineEmits(['close'])

const CIRCUMFERENCE = 2 * Math.PI * 35  // r=35

const CATEGORY_COLORS = {
  animal:  '#4ade80',
  human:   '#fb923c',
  vehicle: '#60a5fa',
  blank:   '#6b7280',
  unknown: '#a78bfa',
}

const DETECTION_LABEL = { '1': 'animal', '2': 'human', '3': 'vehicle' }

const DAY_NAMES   = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function formatDate(d) {
  if (!d) return ''
  return `${DAY_NAMES[d.getDay()]} ${d.getDate()} ${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

function pct(value, total) {
  return total > 0 ? Math.round((value / total) * 100) : 0
}

function toSlices(counts) {
  const total = Object.values(counts).reduce((a, b) => a + b, 0)
  if (total === 0) return []
  let offset = 0
  return Object.entries(counts)
    .filter(([, v]) => v > 0)
    .sort(([, a], [, b]) => b - a)
    .map(([label, value]) => {
      const length = (value / total) * CIRCUMFERENCE
      const slice = { label, value, color: CATEGORY_COLORS[label] ?? '#888', length, offset }
      offset += length
      return slice
    })
}

function getCategory(img) {
  const name = img.prediction?.common_name?.toLowerCase()
  if (!name) return 'unknown'
  if (name === 'blank')   return 'blank'
  if (name === 'human')   return 'human'
  if (name === 'vehicle') return 'vehicle'
  return 'animal'
}

const predictionSlices = computed(() => {
  const counts = {}
  for (const img of props.day.images) {
    const cat = getCategory(img)
    counts[cat] = (counts[cat] ?? 0) + 1
  }
  return toSlices(counts)
})

const detectionSlices = computed(() => {
  const counts = {}
  for (const img of props.day.images) {
    for (const det of img.detections ?? []) {
      if (det.conf < 0.7) continue
      const label = DETECTION_LABEL[det.category] ?? det.label
      counts[label] = (counts[label] ?? 0) + 1
    }
  }
  return toSlices(counts)
})

const detectionTotal = computed(() => detectionSlices.value.reduce((s, d) => s + d.value, 0))
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

.summary {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  width: min(680px, 100%);
  overflow: hidden;
}

.summary__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid var(--border);
  background: var(--surface2);
}

.summary__date {
  font-size: 18px;
  font-weight: 700;
}

.summary__stat {
  font-size: 13px;
  color: var(--text-muted);
  margin-top: 2px;
}

.summary__close {
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
  flex-shrink: 0;
}

.summary__close:hover { color: var(--text); }

.summary__charts {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1px;
  background: var(--border);
}

.chart-block {
  background: var(--surface);
  padding: 20px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.chart-block__title {
  font-size: 12px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}

.chart-block__sub {
  font-weight: 400;
  font-size: 11px;
  text-transform: none;
  letter-spacing: 0;
}

.chart-block__body {
  display: flex;
  align-items: center;
  gap: 20px;
}

.chart-block__empty {
  font-size: 13px;
  color: var(--text-muted);
}

.donut {
  width: 110px;
  height: 110px;
  flex-shrink: 0;
}

.donut__total {
  font-size: 16px;
  font-weight: 700;
  fill: var(--text);
}

.legend {
  list-style: none;
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
}

.legend__item {
  display: grid;
  grid-template-columns: 10px 1fr auto auto;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.legend__dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  flex-shrink: 0;
}

.legend__label {
  color: var(--text);
}

.legend__count {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
}

.legend__pct {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
  text-align: right;
  min-width: 30px;
}
</style>
