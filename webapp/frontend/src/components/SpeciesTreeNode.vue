<template>
  <div class="stree-node">
    <button
      type="button"
      class="stree-node__row"
      :class="{
        'stree-node__row--leaf': isLeaf,
        'stree-node__row--selected': isLeaf && selected === node.species?.common_name,
      }"
      :style="{ paddingLeft: `${depth * 14 + 6}px` }"
      @click="onRowClick"
    >
      <span
        v-if="!isLeaf"
        class="stree-node__caret"
        @click.stop="expanded = !expanded"
      >{{ expanded ? '−' : '+' }}</span>
      <span v-else class="stree-node__caret stree-node__caret--leaf">·</span>
      <span class="stree-node__label">{{ node.label }}</span>
      <span v-if="isLeaf && node.species?.custom" class="stree-node__badge">custom</span>
      <span v-if="isLeaf && node.species?.scientific" class="stree-node__sci">
        {{ node.species.scientific }}
      </span>
    </button>
    <div v-if="expanded && !isLeaf" class="stree-node__children">
      <SpeciesTreeNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :depth="depth + 1"
        :selected="selected"
        :force-expand="forceExpand"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, watch } from 'vue'

const props = defineProps({
  node:        { type: Object, required: true },
  depth:       { type: Number, default: 0 },
  selected:    { type: String, default: '' },
  forceExpand: { type: Boolean, default: false },
})
const emit = defineEmits(['select'])

const isLeaf = computed(() => !props.node.children?.length)

// Auto-open shallow nodes; deeper nodes start collapsed unless force-expanded
// (used when search filters the tree down to just matching leaves).
const expanded = ref(props.forceExpand || props.depth < 1)
watch(() => props.forceExpand, v => { if (v) expanded.value = true })

function onRowClick() {
  if (isLeaf.value) {
    emit('select', props.node.species)
  } else {
    expanded.value = !expanded.value
  }
}
</script>

<style scoped>
.stree-node__row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 3px 6px;
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  font-size: 12px;
  color: var(--text);
  border-radius: 4px;
}
.stree-node__row:hover { background: var(--surface2); }
.stree-node__row--leaf { font-weight: 500; }
.stree-node__row--selected {
  background: var(--accent, #2d7d46);
  color: white;
}
.stree-node__row--selected .stree-node__sci,
.stree-node__row--selected .stree-node__badge { color: rgba(255,255,255,0.85); }

.stree-node__caret {
  width: 14px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
  color: var(--text-muted);
  user-select: none;
  flex-shrink: 0;
}
.stree-node__caret--leaf { color: var(--border); font-weight: 400; }

.stree-node__label {
  flex: 1;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.stree-node__sci {
  font-size: 11px;
  color: var(--text-muted);
  font-style: italic;
}

.stree-node__badge {
  font-size: 10px;
  background: var(--surface2);
  color: var(--text-muted);
  padding: 1px 5px;
  border-radius: 999px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
</style>
