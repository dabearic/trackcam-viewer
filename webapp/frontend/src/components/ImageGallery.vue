<template>
  <div class="gallery">
    <EventGroup
      v-for="event in events"
      :key="event.timestamp"
      :event="event"
      @select="$emit('select', $event)"
    />
  </div>
</template>

<script setup>
import EventGroup from './EventGroup.vue'

defineProps({ events: Array })
defineEmits(['select'])
</script>

<style scoped>
.gallery {
  display: flex;
  flex-direction: column;
  gap: 12px;
}
</style>
