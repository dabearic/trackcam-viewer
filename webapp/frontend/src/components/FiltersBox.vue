<script setup lang="ts" >

import {ref, defineEmits, defineProps, useTemplateRef} from 'vue'
import FilterSlider from "./FilterSlider.vue";

const props = defineProps(['filterTypes'])
const emit = defineEmits(['styles-update'])
const styles = ref({})
const sliders = useTemplateRef('sliders')

function update_style(src: string) {
  styles.value[src[0]] = src[1]
  const filtersString =  Object.values(styles.value).reduce((r, c) => r + " " + c, "")
  emit("styles-update",{filter: filtersString})
}

</script>

<template>
  <div id="main">

    <FilterSlider class="individual-filter" v-for="(filter) in props.filterTypes" :name="filter" ref="sliders"
                  @style-update="(newStyle)=>update_style(newStyle)"/>
    <button class="modal__delete" id="reset-button"
            @click="_e=>sliders.forEach((slider)=>slider.resetValue())" >
      Reset All</button>
      </div>

</template>

<style scoped>

.individual-filter{
  min-width:260px;
}
#reset-button {
  background-color: #ac2424;
  color: white;
}

.modal__delete {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 4px 10px;
  font-size: 12px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

</style>