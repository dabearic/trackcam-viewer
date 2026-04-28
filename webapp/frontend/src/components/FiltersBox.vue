<script setup>
import FilterSlider from "./FilterSlider.vue";
import {ref, computed, defineEmits, defineProps} from 'vue'

const props = defineProps(['filterTypes'])
const emit = defineEmits(['styles-update'])
const styles = ref({})
const show = ref(false)


function update_style(src) {
  styles.value[src[0]] = src[1]
  const filtersString =  Object.values(styles.value).reduce((r, c) => r + " " + c, "")
  emit("styles-update",{filter: filtersString})
}

function toggleShow(){
  show.value = !show.value;
}

</script>

<template>
  <div>
    <button @click="(e)=>show=!show">{{ show ? "Hide <" : "Show >" }}</button>
    <div v-if="show">
    <FilterSlider v-for="(filter) in props.filterTypes" :name="filter" ref="sliders"
                  @style-update="(newStyle)=>update_style(newStyle)"/>
    <button id="reset-button" @click="(e)=>$refs.sliders.forEach((slider)=>slider.resetValue())" >Reset All</button>
      </div>
  </div>
</template>

<style scoped>
#reset-button {
  background-color: #ac2424;
  color: white;
}
</style>