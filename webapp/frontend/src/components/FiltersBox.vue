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
  <div id="main">

    <FilterSlider class="indiv-filter" v-for="(filter) in props.filterTypes" :name="filter" ref="sliders"
                  @style-update="(newStyle)=>update_style(newStyle)"/>
    <button class="modal__delete" id="reset-button" @click="(e)=>$refs.sliders.forEach((slider)=>slider.resetValue())" >Reset All</button>
      </div>

</template>

<style scoped>

.main {
  min-width: 260px;
}
.indiv-filter{
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