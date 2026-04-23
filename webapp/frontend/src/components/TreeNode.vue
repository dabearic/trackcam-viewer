<template>
  <div class="tree-node">
    <button
      class="tree-node__row"
      :class="{ 'tree-node__row--selected': selectedPath === node.path }"
      :style="{ paddingLeft: `${depth * 14 + 6}px` }"
      @click="$emit('select', node)"
    >
      <span
        v-if="node.children.length"
        class="tree-node__caret"
        @click.stop="expanded = !expanded"
      >{{ expanded ? '−' : '+' }}</span>
      <span v-else class="tree-node__caret tree-node__caret--leaf">·</span>
      <span class="tree-node__label">{{ node.label }}</span>
      <span class="tree-node__count">{{ node.count }}</span>
    </button>
    <div v-if="expanded && node.children.length" class="tree-node__children">
      <TreeNode
        v-for="child in node.children"
        :key="child.path"
        :node="child"
        :depth="depth + 1"
        :selected-path="selectedPath"
        :force-expand="node.children.length === 1"
        @select="$emit('select', $event)"
      />
    </div>
  </div>
</template>

<script setup>
import { ref, watch } from 'vue'

const props = defineProps({
  node: Object,
  depth: { type: Number, default: 0 },
  selectedPath: String,
  forceExpand: { type: Boolean, default: false },
})
defineEmits(['select'])

const expanded = ref(props.depth < 1 || props.forceExpand)

// When the parent expands and has only one child, auto-expand this node too.
watch(() => props.forceExpand, val => { if (val) expanded.value = true })
</script>

<style scoped>
.tree-node__row {
  display: flex;
  align-items: center;
  gap: 6px;
  width: 100%;
  padding: 4px 6px 4px 6px;
  background: none;
  border: none;
  text-align: left;
  cursor: pointer;
  font-size: 15px;
  color: var(--text, #222);
  border-radius: 4px;
}
.tree-node__row:hover { background: rgba(0, 0, 0, 0.05); }
.tree-node__row--selected {
  background: var(--accent, #2d7d46);
  color: white;
}
.tree-node__row--selected .tree-node__count { color: rgba(255, 255, 255, 0.8); }

.tree-node__caret {
  width: 16px;
  font-size: 16px;
  font-weight: 600;
  line-height: 1;
  text-align: center;
  color: #666;
  user-select: none;
  flex-shrink: 0;
}
.tree-node__caret--leaf { color: #ccc; font-weight: 400; }

.tree-node__label { flex: 1; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.tree-node__count {
  font-size: 13px;
  color: #888;
  margin-left: 4px;
  flex-shrink: 0;
}
</style>
