<template>
  <div class="crop">
    <canvas ref="canvasRef" class="crop__canvas" />
    <span class="crop__badge" :style="{ background: color }">
      {{ det.label }} {{ (det.conf * 100).toFixed(0) }}%
    </span>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'

const props = defineProps({
  imageSrc: String,
  det: Object,
  color: String,
})

const canvasRef = ref(null)
const TARGET_H = 110

function draw() {
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
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-radius: 4px;
  overflow: hidden;
  border: 1px solid var(--border);
}

.crop__canvas {
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
