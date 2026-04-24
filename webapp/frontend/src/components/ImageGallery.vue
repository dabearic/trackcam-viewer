<template>
  <div class="gallery">
    <template v-for="event in events" :key="event.timestamp">
      <!-- Date/time header spanning all columns -->
      <div class="gallery__header">
        <button class="gallery__date" @click="$emit('day-select', dayData(event))">{{ formatDate(event.date) }}</button>
        <span class="gallery__time">{{ formatTime(event.date) }}</span>
        <span class="gallery__count">{{ event.images.length }} image{{ event.images.length !== 1 ? 's' : '' }}</span>
      </div>

      <!-- Individual image cells flow into the grid -->
      <div
        v-for="img in event.images"
        :key="img.filename"
        class="gallery__tile"
      >
        <button
          class="gallery__thumb"
          @click="$emit('select', img)"
        >
          <img
            :src="imageUrl(img.filepath)"
            :alt="img.filename"
            loading="lazy"
          />
          <div class="gallery__badge-row">
            <span
              v-for="det in detectionCounts(img)"
              :key="det.label"
              :class="`badge badge--${det.label}`"
            >{{ det.label +": " }} {{ det.count}} </span>
          </div>
        </button>
        <button
          class="gallery__delete"
          title="Delete image"
          @click.stop="$emit('delete', img)"
        >
          <svg viewBox="0 0 16 16" fill="currentColor" aria-hidden="true">
            <path d="M5.5 5.5A.5.5 0 0 1 6 6v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5Zm2.5 0a.5.5 0 0 1 .5.5v6a.5.5 0 0 1-1 0V6a.5.5 0 0 1 .5-.5Zm3 .5a.5.5 0 0 0-1 0v6a.5.5 0 0 0 1 0V6Z"/>
            <path d="M14.5 3a1 1 0 0 1-1 1H13v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V4h-.5a1 1 0 0 1-1-1V2a1 1 0 0 1 1-1H6a1 1 0 0 1 1-1h2a1 1 0 0 1 1 1h3.5a1 1 0 0 1 1 1v1ZM4.118 4 4 4.059V13a1 1 0 0 0 1 1h6a1 1 0 0 0 1-1V4.059L11.882 4H4.118ZM2.5 3h11V2h-11v1Z"/>
          </svg>
        </button>
      </div>
    </template>
  </div>
</template>

<script setup>
import { imageUrl } from '../firebase.js'
const props = defineProps({ events: Array })
defineEmits(['select', 'day-select', 'delete'])

function dayData(event) {
  const dayPrefix = event.timestamp.substring(0, 8)
  const dayEvents = props.events.filter(e => e.timestamp.startsWith(dayPrefix))
  return {
    date: event.date,
    events: dayEvents,
    images: dayEvents.flatMap(e => e.images),
  }
}

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

// category key matches CSS badge classes: animal / human / vehicle
const CATEGORY_LABEL = { '1': 'animal', '2': 'human', '3': 'vehicle' }

function detectionCounts(img) {
  const counts = {}
  for (const det of img.detections ?? []) {
    if (det.conf < 0.7) continue
    const label = CATEGORY_LABEL[det.category] ?? det.label
    counts[label] = (counts[label] ?? 0) + 1
  }
  return Object.entries(counts).map(([label, count]) => ({ label, count }))
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
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  text-decoration: underline;
  text-decoration-color: transparent;
  text-underline-offset: 3px;
  transition: text-decoration-color 0.15s, color 0.15s;
}

.gallery__date:hover {
  color: var(--animal);
  text-decoration-color: var(--animal);
}

.gallery__time {
  color: var(--text-muted);
  font-variant-numeric: tabular-nums;
}

.gallery__count {
  margin-left: auto;
  color: var(--text-muted);
}

.gallery__tile {
  position: relative;
}

.gallery__tile:hover .gallery__delete {
  opacity: 1;
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
  width: 100%;
  display: block;
}

.gallery__thumb:hover {
  opacity: 0.85;
}

.gallery__delete {
  position: absolute;
  top: 6px;
  right: 6px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(153, 27, 27, 0.9);
  border: 1px solid rgba(255, 255, 255, 0.2);
  border-radius: 4px;
  color: #fff;
  padding: 0;
  cursor: pointer;
  opacity: 0;
  transition: opacity 0.15s, background 0.15s;
  z-index: 2;
}

.gallery__delete:focus,
.gallery__tile:focus-within .gallery__delete {
  opacity: 1;
}

.gallery__delete:hover {
  background: #b91c1c;
}

.gallery__delete svg {
  width: 15px;
  height: 15px;
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
  justify-content: flex-start;
  flex-wrap: wrap;
  gap: 3px;
}

</style>
