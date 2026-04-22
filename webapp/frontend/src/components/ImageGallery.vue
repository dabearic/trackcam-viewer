<template>
  <div class="gallery">
    <template v-for="event in events" :key="event.timestamp">
      <!-- Date/time header spanning all columns -->
      <div class="gallery__header">
        <span class="gallery__date">{{ formatDate(event.date) }}</span>
        <span class="gallery__time">{{ formatTime(event.date) }}</span>
        <span class="gallery__count">{{ event.images.length }} image{{ event.images.length !== 1 ? 's' : '' }}</span>
      </div>

      <!-- Individual image cells flow into the grid -->
      <button
        v-for="img in event.images"
        :key="img.filename"
        class="gallery__thumb"
        @click="$emit('select', img)"
      >
        <img
          :src="`/api/image?path=${encodeURIComponent(img.filepath)}`"
          :alt="img.filename"
          loading="lazy"
        />
        <div class="gallery__badge-row">
          <span v-if="img.prediction" :class="`badge badge--${getCategory(img)}`">
            {{ capitalize(img.prediction.common_name) }}
          </span>
          <span v-if="img.prediction_score != null" class="gallery__score">
            {{ (img.prediction_score * 100).toFixed(0) }}%
          </span>
        </div>
      </button>
    </template>
  </div>
</template>

<script setup>
defineProps({ events: Array })
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
.gallery {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 4px;
}

.gallery__header {
  grid-column: 1 / -1;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 6px 4px 2px;
  font-size: 12px;
  margin-top: 8px;
}

.gallery__header:first-child {
  margin-top: 0;
}

.gallery__date {
  font-weight: 600;
  color: var(--text);
}

.gallery__time {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.gallery__count {
  margin-left: auto;
  color: var(--text-muted);
}

.gallery__thumb {
  position: relative;
  aspect-ratio: 4/3;
  background: #000;
  border: none;
  border-radius: 4px;
  overflow: hidden;
  padding: 0;
  cursor: pointer;
  transition: opacity 0.15s;
}

.gallery__thumb:hover {
  opacity: 0.85;
}

.gallery__thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

.gallery__badge-row {
  position: absolute;
  bottom: 0;
  left: 0;
  right: 0;
  padding: 4px 5px;
  background: linear-gradient(transparent, rgba(0,0,0,0.75));
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 4px;
}

.gallery__score {
  font-size: 11px;
  font-weight: 600;
  color: #fff;
  opacity: 0.85;
}
</style>
