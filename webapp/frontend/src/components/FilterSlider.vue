<script setup>
  import {ref, computed, watch, capitalize} from 'vue'
  const props = defineProps(['name'])
  const emit = defineEmits(["style-update"])
  const filter_ratio = ref(0.0)
  const style_text = computed(()=>{
    return props.name + '('+ Math.pow(5,filter_ratio.value)+')'
  })
  watch(style_text, (old_style, new_style)=>{
    //emit name so that the parent FilterBox can keep track of
    //which filter has which value
    emit('style-update', [props.name, style_text.value])
  })
</script>

<template>
  <label>{{capitalize(name)}}: {{filter_ratio.toFixed(2)}}</label>
  <input type="range" class="effect-slider-{{name}}" max="1.0" min="-1.0" step=".05" v-model.number="filter_ratio">
</template>
