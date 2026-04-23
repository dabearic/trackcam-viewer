<template>
  <div class="event">
    <div class="event__header">
      <span class="event__date">{{ formatDate(event.date) }}</span>
      <span class="event__time">{{ formatTime(event.date) }}</span>
      <span class="event__count">{{ event.images.length }} image{{ event.images.length !== 1 ? 's' : '' }}</span>
    </div>
    <div class="event__images">
      <button
        v-for="img in event.images"
        :key="img.filename"
        class="event__thumb"
        @click="$emit('select', img)"
      >
        <img
          :src="imageUrl(img.filepath)"
          :alt="img.filename"
          loading="lazy"
        />
        <div class="event__badge-row">
          <span v-if="img.prediction" :class="`badge badge--${getCategory(img)}`">
            {{ capitalize(img.prediction.common_name) }}
          </span>
          <span v-if="img.prediction_score != null" class="event__score">
            {{ (img.prediction_score * 100).toFixed(0) }}%
          </span>
        </div>
      </button>
    </div>
  </div>
</template>

<script setup>
import { imageUrl } from '../firebase.js'
defineProps({ event: Object })
defineEmits(['select'])

const DAY_NAMES = ['Sun','Mon','Tue','Wed','Thu','Fri','Sat']
const MONTH_NAMES = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec']

function formatDate(d) {
  if (!d) return ''
  return `${DAY_NAMES[d.getDay()]} ${d.getDate()} ${MONTH_NAMES[d.getMonth()]} ${d.getFullYear()}`
}

function formatTime(d) {
  if (!d) return ''
  return d.toTimeString().slice(0, 8)
}

function capitalize(s) {
  return s ? s.charAt(0).toUpperCase() + s.slice(1) : s
}

function getCategory(img) {
  const name = img.prediction?.common_name?.toLowerCase()
  if (!name) return 'unknown'
  if (name === 'blank') return 'blank'
  if (name === 'human') return 'human'
  if (name === 'vehicle') return 'vehicle'
  return 'animal'
}
</script>

<style scoped>
.event {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}

.event__header {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 12px;
  background: var(--surface2);
  border-bottom: 1px solid var(--border);
  font-size: 12px;
}

.event__date {
  font-weight: 600;
  color: var(--text);
}

.event__time {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.event__count {
  margin-left: auto;
  color: var(--text-muted);
}

.event__images {
  display: flex;
  gap: 2px;
  padding: 2px;
}

.event__thumb {
  flex: 1;
  position: relative;
  aspect-ratio: 4/3;
  background: #000;
  border: none;
  border-radius: 4px;
  overflow: hidden;
  padding: 0;
  min-width: 0;
  transition: opacity 0.15s;
}

.event__thumb:hover {
  opacity: 0.85;
}

.event__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.event__badge-row {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 4px 6px;
  background: linear-gradient(transparent, rgba(0,0,0,0.75));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.event__score {
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  opacity: 0.85;
}
</style>
