<script setup>
import { onBeforeUnmount, watch } from 'vue';
import PhotoSwipe from 'photoswipe';
import 'photoswipe/style.css';

const props = defineProps({
  open: { type: Boolean, default: false },
  items: { type: Array, default: () => [] },
  index: { type: Number, default: 0 },
});
const emit = defineEmits(['close', 'change']);
let lightbox;

function closeLightbox() {
  if (!lightbox) return;
  const instance = lightbox;
  lightbox = null;
  instance.destroy();
}
function openLightbox() {
  closeLightbox();
  if (!props.items.length) return;
  lightbox = new PhotoSwipe({
    dataSource: props.items,
    index: Math.max(0, props.index),
    bgOpacity: 0.96,
    loop: false,
    wheelToZoom: true,
    pinchToClose: true,
    closeOnVerticalDrag: true,
    showHideAnimationType: 'zoom',
    preloaderDelay: 0,
  });
  lightbox.on('change', () => emit('change', lightbox.currIndex));
  lightbox.on('close', () => emit('close'));
  lightbox.on('destroy', () => { lightbox = null; });
  lightbox.init();
}

watch(() => props.open, (open) => { if (open) openLightbox(); else closeLightbox(); });
watch(() => props.index, (index) => { if (lightbox && lightbox.currIndex !== index && index >= 0) lightbox.goTo(index); });
onBeforeUnmount(closeLightbox);
</script>

<template><span aria-hidden="true" /></template>
