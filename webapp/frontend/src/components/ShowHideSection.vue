<script setup>
import {ref, defineProps} from "vue";

const props = defineProps(['name','showByDefault', "onName", "offName"])
const show=ref((props.showByDefault === 'true'))
</script>

<template>
  <div>
    <h4 class="panel__heading">{{ name }}
    <button class="modal__toggle"
            :class="{'modal__toggle--off': !show, 'modal__toggle--active': show}"
            @click="show=!show">{{show ? offName : onName}}</button>
    </h4>
    <div v-if="show">
      <slot/>
    </div>
  </div>
</template>

<style scoped>
.modal__toggle
{
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  color: var(--text-muted);
  padding: 4px 10px;
  font-size: 12px;
  transition: color 0.15s, border-color 0.15s, background 0.15s;
}

.modal__toggle--off {
  color: var(--text);
  background: var(--surface2);
}
.panel__heading {
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--text-muted);
}


</style>