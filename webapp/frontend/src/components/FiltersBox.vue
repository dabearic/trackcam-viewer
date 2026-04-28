<script setup>
import FilterSlider from "./FilterSlider.vue";
import {ref, computed, defineEmits, defineProps} from 'vue'

const props = defineProps(['filterTypes'])
const emit = defineEmits(['styles-update'])
const styles = ref({})


function update_style(src) {
  styles.value[src[0]] = src[1]
  const filtersString =  Object.values(styles.value).reduce((r, c) => r + " " + c, "")
  emit("styles-update",{filter: filtersString})
}

</script>

<template>
  <div>
    <FilterSlider v-for="(filter) in props.filterTypes" :name="filter" ref="sliders"
                  @style-update="(newStyle)=>update_style(newStyle)"/>
  </div>
</template>