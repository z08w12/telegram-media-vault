<script setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';
import Plyr from 'plyr';
import 'plyr/dist/plyr.css';

const props = defineProps({
  src: { type: String, required: true },
  poster: { type: String, default: '' },
  title: { type: String, default: '' },
  mediaId: { type: [Number, String], required: true },
});
const video = ref(null);
let player;
let lastSavedSecond = -1;
const preferenceKey = 'telegram-media-player-preferences';
const positionKey = `telegram-media-player-position-${props.mediaId}`;

function readStorage(key, fallback = null) {
  try { return JSON.parse(localStorage.getItem(key)) ?? fallback; } catch { return fallback; }
}
function writeStorage(key, value) {
  try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* Storage can be unavailable in private mode. */ }
}
function rememberPreferences() {
  writeStorage(preferenceKey, { volume: player.volume, muted: player.muted, speed: player.speed });
}
function rememberPosition() {
  const current = Math.floor(player.currentTime || 0);
  if (current === lastSavedSecond || current < 1) return;
  lastSavedSecond = current;
  writeStorage(positionKey, current);
}

onMounted(() => {
  const preferences = readStorage(preferenceKey, {});
  player = new Plyr(video.value, {
    iconUrl: `${import.meta.env.BASE_URL}plyr.svg`,
    loadSprite: true,
    seekTime: 10,
    speed: { selected: Number(preferences.speed) || 1, options: [0.5, 0.75, 1, 1.25, 1.5, 2] },
    volume: Number.isFinite(preferences.volume) ? preferences.volume : 1,
    muted: Boolean(preferences.muted),
    fullscreen: { enabled: true, fallback: true, iosNative: true },
    keyboard: { focused: true, global: true },
    tooltips: { controls: true, seek: true },
    controls: ['play-large', 'restart', 'rewind', 'play', 'fast-forward', 'progress', 'current-time', 'duration', 'mute', 'volume', 'settings', 'pip', 'fullscreen'],
    settings: ['speed'],
    i18n: {
      restart: '重新播放', rewind: '后退 {seektime} 秒', play: '播放', pause: '暂停', fastForward: '前进 {seektime} 秒',
      seek: '定位', seekLabel: '{currentTime} / {duration}', played: '已播放', buffered: '已缓冲', currentTime: '当前时间',
      duration: '时长', volume: '音量', mute: '静音', unmute: '取消静音', enableCaptions: '开启字幕', disableCaptions: '关闭字幕',
      download: '下载', enterFullscreen: '进入全屏', exitFullscreen: '退出全屏', frameTitle: '{title} 播放器', captions: '字幕',
      settings: '设置', pip: '画中画', menuBack: '返回上级菜单', speed: '播放速度', normal: '正常', quality: '清晰度', loop: '循环',
    },
  });
  player.on('loadedmetadata', () => {
    const saved = Number(readStorage(positionKey, 0));
    if (saved > 0 && Number.isFinite(player.duration) && saved < player.duration - 10) player.currentTime = saved;
  });
  player.on('timeupdate', () => {
    if (Math.floor(player.currentTime || 0) % 5 === 0) rememberPosition();
  });
  player.on('volumechange ratechange', rememberPreferences);
  player.on('ended', () => { try { localStorage.removeItem(positionKey); } catch { /* Storage might be unavailable. */ } });
});

onBeforeUnmount(() => {
  if (player) { rememberPosition(); player.destroy(); }
});
</script>

<template>
  <div class="video-player">
    <video ref="video" controls playsinline preload="metadata" :poster="poster" :aria-label="title || '视频播放器'">
      <source :src="src" />
    </video>
  </div>
</template>
