<template>
  <div class="crop" :class="{ 'crop--editable': editable }">
    <button
      v-if="editable"
      type="button"
      class="crop__delete"
      title="Delete this detection"
      @click.stop="$emit('delete')"
      @keydown.enter.stop.prevent="$emit('delete')"
      @keydown.space.stop.prevent="$emit('delete')"
    >✕</button>
    <img
      v-if="det.crop_gcs_path"
      :src="imageUrl(det.crop_gcs_path)"
      class="crop__img"
      :alt="label"
    />
    <canvas v-else ref="canvasRef" class="crop__canvas" />
    <span class="crop__badge" :style="{ background: color }">
      {{ label }} {{ (det.conf * 100).toFixed(0) }}%
    </span>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { imageUrl } from '../firebase.js'

const props = defineProps({
  imageSrc: String,
  det: Object,
  color: String,
  label: String,
  editable: { type: Boolean, default: false },
})
defineEmits(['delete'])

const canvasRef = ref(null)
const TARGET_H = 110

function draw() {
  if (props.det.crop_gcs_path) return   // using <img>, nothing to paint
  const canvas = canvasRef.value
  if (!canvas) return

  const img = new Image()
  img.onload = () => {
    const [bx, by, bw, bh] = props.det.bbox
    const sx = bx * img.naturalWidth
    const sy = by * img.naturalHeight
    const sw = bw * img.naturalWidth
    const sh = bh * img.naturalHeight

    const targetW = Math.max(60, Math.round(TARGET_H * (sw / sh)))
    canvas.width  = targetW
    canvas.height = TARGET_H
    canvas.getContext('2d').drawImage(img, sx, sy, sw, sh, 0, 0, targetW, TARGET_H)
  }
  img.crossOrigin = 'anonymous'
  img.src = props.imageSrc
}

onMounted(draw)
watch(() => [props.imageSrc, props.det], draw)
</script>

<style scoped>
.crop {
  position: relative;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--border);
}

/* Quick-delete X — only visible while edit mode is on. Sits at the top-
   right of the crop; click.stop on the button keeps the parent crop's
   click handler (open-editor) from firing. */
.crop__delete {
  position: absolute;
  top: 4px;
  right: 4px;
  z-index: 2;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: 1px solid rgba(255,255,255,0.5);
  background: rgba(0,0,0,0.65);
  color: #fff;
  font-size: 11px;
  line-height: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  padding: 0;
  opacity: 0.7;
  transition: opacity 0.12s, background 0.12s, border-color 0.12s;
}
.crop__delete:hover {
  opacity: 1;
  background: #b91c1c;
  border-color: #fca5a5;
}

.crop__canvas,
.crop__img {
  display: block;
  height: 110px;
  width: auto;
}

.crop__badge {
  padding: 2px 5px;
  font-size: 10px;
  font-weight: 600;
  color: #000;
  text-align: center;
  white-space: nowrap;
  flex-shrink: 0;
}
</style>
