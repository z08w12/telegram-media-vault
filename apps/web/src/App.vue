<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue';

const authenticated = ref(false), password = ref(''), error = ref(''), loading = ref(false);
const items = ref([]), tags = ref([]), albums = ref([]), total = ref(0), page = ref(1);
const stats = ref({ files: 0, bytes: 0, images: 0, videos: 0 });
const kind = ref(''), query = ref(''), favorite = ref(false), trash = ref(false), activeTag = ref(''), activeAlbum = ref('');
const selected = ref(null), selectedTagIds = ref([]), selectedAlbumIds = ref([]), tagManagerOpen = ref(false), albumManagerOpen = ref(false);
const newTagName = ref(''), newTagColor = ref('#55c6f5');
const newAlbumName = ref(''), newAlbumDescription = ref('');
const bulkMode = ref(false), checkedIds = ref([]), bulkTagIds = ref([]), bulkAlbumIds = ref([]);
const imageFullscreen = ref(false), modalRef = ref(null);
const API_BASE = '/telegram/api';
let searchTimer;
let touchStartX = null;
let previousBodyOverflow = '';

async function api(url, options = {}) {
  const response = await fetch(url, { ...options, headers: { 'Content-Type': 'application/json', ...(options.headers || {}) } });
  const data = response.status === 204 ? null : await response.json().catch(() => null);
  if (!response.ok) throw new Error(data?.error || `请求失败 (${response.status})`);
  return data;
}
async function login() {
  error.value = ''; loading.value = true;
  try { await api(`${API_BASE}/auth/login`, { method: 'POST', body: JSON.stringify({ password: password.value }) }); password.value = ''; authenticated.value = true; await refresh(); }
  catch (e) { error.value = e.message; } finally { loading.value = false; }
}
async function logout() { await api(`${API_BASE}/auth/logout`, { method: 'POST' }); authenticated.value = false; items.value = []; }
async function load() {
  if (!authenticated.value) return;
  loading.value = true; error.value = '';
  const params = new URLSearchParams({ page: String(page.value), pageSize: '30' });
  if (kind.value) params.set('kind', kind.value); if (query.value.trim()) params.set('q', query.value.trim());
  if (favorite.value) params.set('favorite', 'true'); if (trash.value) params.set('trash', 'true'); if (activeTag.value) params.set('tag', activeTag.value); if (activeAlbum.value) params.set('album', activeAlbum.value);
  try { const result = await api(`${API_BASE}/media?${params}`); items.value = result.items; total.value = result.total; checkedIds.value = []; }
  catch (e) { if (e.message === '请先登录') authenticated.value = false; else error.value = e.message; }
  finally { loading.value = false; }
}
async function loadTags() { const result = await api(`${API_BASE}/tags`); tags.value = result.items; }
async function loadAlbums() { const result = await api(`${API_BASE}/albums`); albums.value = result.items; }
async function refresh() { await Promise.all([load(), loadTags(), loadAlbums(), api(`${API_BASE}/stats`).then((data) => { stats.value = data; })]); }
function openItem(item) { if (bulkMode.value) { toggleChecked(item.id); return; } selected.value = item; selectedTagIds.value = (item.tags || []).map((tag) => tag.id); selectedAlbumIds.value = (item.albums || []).map((album) => album.id); }
async function toggleFavorite(item) {
  await api(`${API_BASE}/media/${item.id}/favorite`, { method: 'PATCH', body: JSON.stringify({ favorite: !item.is_favorite }) });
  item.is_favorite = item.is_favorite ? 0 : 1; if (favorite.value && !item.is_favorite) items.value = items.value.filter((x) => x.id !== item.id);
}
async function saveMediaTags() {
  const result = await api(`${API_BASE}/media/${selected.value.id}/tags`, { method: 'PUT', body: JSON.stringify({ tag_ids: selectedTagIds.value }) });
  selected.value.tags = result.tags; const item = items.value.find((entry) => entry.id === selected.value.id); if (item) item.tags = result.tags; await loadTags();
}
async function saveMediaAlbums() {
  const result = await api(`${API_BASE}/media/${selected.value.id}/albums`, { method: 'PUT', body: JSON.stringify({ album_ids: selectedAlbumIds.value }) });
  selected.value.albums = result.albums; const item = items.value.find((entry) => entry.id === selected.value.id); if (item) item.albums = result.albums; await loadAlbums();
}
async function createTag() {
  if (!newTagName.value.trim()) return;
  try { await api(`${API_BASE}/tags`, { method: 'POST', body: JSON.stringify({ name: newTagName.value, color: newTagColor.value }) }); newTagName.value = ''; await loadTags(); }
  catch (e) { error.value = e.message; }
}
async function renameTag(tag) {
  const name = prompt('新的标签名', tag.name); if (!name || name === tag.name) return;
  try { await api(`${API_BASE}/tags/${tag.id}`, { method: 'PATCH', body: JSON.stringify({ name, color: tag.color }) }); if (activeTag.value === tag.name) activeTag.value = name.trim().replace(/^#/, ''); await refresh(); }
  catch (e) { error.value = e.message; }
}
async function changeTagColor(tag, color) { try { await api(`${API_BASE}/tags/${tag.id}`, { method: 'PATCH', body: JSON.stringify({ name: tag.name, color }) }); await loadTags(); await load(); } catch (e) { error.value = e.message; } }
async function deleteTag(tag) { if (!confirm(`删除标签“${tag.name}”？媒体文件不会被删除。`)) return; await api(`${API_BASE}/tags/${tag.id}`, { method: 'DELETE' }); if (activeTag.value === tag.name) activeTag.value = ''; await refresh(); }
async function createAlbum() {
  if (!newAlbumName.value.trim()) return;
  try { await api(`${API_BASE}/albums`, { method: 'POST', body: JSON.stringify({ name: newAlbumName.value, description: newAlbumDescription.value }) }); newAlbumName.value = ''; newAlbumDescription.value = ''; await loadAlbums(); }
  catch (e) { error.value = e.message; }
}
async function editAlbum(album) {
  const name = prompt('相册名称', album.name); if (!name) return;
  const description = prompt('相册说明', album.description || '') ?? album.description;
  try { await api(`${API_BASE}/albums/${album.id}`, { method: 'PATCH', body: JSON.stringify({ name, description }) }); await refresh(); }
  catch (e) { error.value = e.message; }
}
async function deleteAlbum(album) {
  if (!confirm(`删除相册“${album.name}”？相册内媒体文件不会被删除。`)) return;
  await api(`${API_BASE}/albums/${album.id}`, { method: 'DELETE' }); if (String(activeAlbum.value) === String(album.id)) activeAlbum.value = ''; await refresh();
}
function toggleChecked(id) { checkedIds.value = checkedIds.value.includes(id) ? checkedIds.value.filter((value) => value !== id) : [...checkedIds.value, id]; }
function toggleAllVisible() { checkedIds.value = checkedIds.value.length === items.value.length ? [] : items.value.map((item) => item.id); }
async function applyBulkTags(action) {
  try { await api(`${API_BASE}/media/bulk-tags`, { method: 'POST', body: JSON.stringify({ media_ids: checkedIds.value, tag_ids: bulkTagIds.value, action }) }); bulkTagIds.value = []; await Promise.all([load(), loadTags()]); }
  catch (e) { error.value = e.message; }
}
async function applyBulkAlbums(action) {
  try { await api(`${API_BASE}/media/bulk-albums`, { method: 'POST', body: JSON.stringify({ media_ids: checkedIds.value, album_ids: bulkAlbumIds.value, action }) }); bulkAlbumIds.value = []; await Promise.all([load(), loadAlbums()]); }
  catch (e) { error.value = e.message; }
}
async function applyBulkAction(action) {
  const warnings = { trash: '将选中项目移至回收站？', permanent: '永久删除选中项目及文件？此操作无法恢复。' };
  if (warnings[action] && !confirm(warnings[action])) return;
  try { await api(`${API_BASE}/media/bulk`, { method: 'POST', body: JSON.stringify({ media_ids: checkedIds.value, action }) }); await refresh(); }
  catch (e) { error.value = e.message; }
}
async function moveToTrash(item) { if (!confirm(`将“${item.original_name || `媒体 #${item.id}`}”移至回收站？`)) return; await api(`${API_BASE}/media/${item.id}`, { method: 'DELETE' }); selected.value = null; await refresh(); }
async function restore(item) { await api(`${API_BASE}/media/${item.id}/restore`, { method: 'POST' }); selected.value = null; await load(); }
async function removeForever(item) { if (!confirm('永久删除后无法恢复，确定继续吗？')) return; await api(`${API_BASE}/media/${item.id}/permanent`, { method: 'DELETE' }); selected.value = null; await load(); }
function formatBytes(value) { const bytes = Number(value || 0); if (bytes < 1024) return `${bytes} B`; const units = ['KB', 'MB', 'GB', 'TB']; let size = bytes / 1024, unit = units[0]; for (let i = 1; i < units.length && size >= 1024; i += 1) { size /= 1024; unit = units[i]; } return `${size.toFixed(size >= 10 ? 1 : 2)} ${unit}`; }
function formatDate(value) { return new Intl.DateTimeFormat('zh-CN', { dateStyle: 'medium', timeStyle: 'short' }).format(new Date(Number(value) * 1000)); }

const pageCount = computed(() => Math.max(1, Math.ceil(total.value / 30)));
const imageItems = computed(() => items.value.filter((item) => item.kind === 'image'));
const selectedImageIndex = computed(() => imageItems.value.findIndex((item) => item.id === selected.value?.id));
function navigateImage(step) { if (selected.value?.kind !== 'image') return; const target = imageItems.value[selectedImageIndex.value + step]; if (target) openItem(target); }
async function enterImageFullscreen() {
  if (selected.value?.kind !== 'image') return;
  imageFullscreen.value = true;
  await nextTick();
  if (modalRef.value?.requestFullscreen && !document.fullscreenElement) {
    try { await modalRef.value.requestFullscreen({ navigationUI: 'hide' }); } catch { /* CSS viewport fallback for iOS and restricted browsers. */ }
  }
}
async function exitImageFullscreen() {
  imageFullscreen.value = false;
  if (document.fullscreenElement) {
    try { await document.exitFullscreen(); } catch { /* The CSS state is already restored. */ }
  }
}
function toggleImageFullscreen() { if (imageFullscreen.value) exitImageFullscreen(); else enterImageFullscreen(); }
function closeViewer() { if (imageFullscreen.value || document.fullscreenElement) exitImageFullscreen(); selected.value = null; }
function fullscreenChanged() { if (!document.fullscreenElement && imageFullscreen.value) imageFullscreen.value = false; }
function imageTouchStart(event) { if (event.touches.length === 1) touchStartX = event.touches[0].clientX; }
function imageTouchEnd(event) {
  if (touchStartX === null || event.changedTouches.length !== 1) { touchStartX = null; return; }
  const distance = event.changedTouches[0].clientX - touchStartX;
  touchStartX = null;
  if (Math.abs(distance) >= 50) navigateImage(distance > 0 ? -1 : 1);
}
function keyboard(event) {
  const editing = ['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target?.tagName) || event.target?.isContentEditable;
  if (event.key === 'Escape') { if (imageFullscreen.value) exitImageFullscreen(); else if (selected.value) closeViewer(); tagManagerOpen.value = false; albumManagerOpen.value = false; return; }
  if (!selected.value || editing) return;
  if (event.key === 'ArrowLeft') navigateImage(-1);
  if (event.key === 'ArrowRight') navigateImage(1);
  if (selected.value.kind === 'image' && event.key.toLowerCase() === 'f') toggleImageFullscreen();
}
watch([kind, favorite, trash, activeTag, activeAlbum], () => { page.value = 1; load(); });
watch(query, () => { clearTimeout(searchTimer); searchTimer = setTimeout(() => { page.value = 1; load(); }, 300); });
watch(page, load); watch(bulkMode, (enabled) => { if (!enabled) { checkedIds.value = []; bulkTagIds.value = []; bulkAlbumIds.value = []; } });
watch(selected, (value, previousValue) => {
  if (value && !previousValue) { previousBodyOverflow = document.body.style.overflow; document.body.style.overflow = 'hidden'; }
  else if (!value && previousValue) { document.body.style.overflow = previousBodyOverflow; if (imageFullscreen.value || document.fullscreenElement) exitImageFullscreen(); }
});
onMounted(async () => { window.addEventListener('keydown', keyboard); document.addEventListener('fullscreenchange', fullscreenChanged); try { await api(`${API_BASE}/auth/session`); authenticated.value = true; await refresh(); } catch { authenticated.value = false; } });
onBeforeUnmount(() => { window.removeEventListener('keydown', keyboard); document.removeEventListener('fullscreenchange', fullscreenChanged); document.body.style.overflow = previousBodyOverflow; clearTimeout(searchTimer); });
</script>

<template>
  <main v-if="!authenticated" class="login-shell"><form class="login-card" @submit.prevent="login"><div class="brand-mark">T</div><p class="eyebrow">PRIVATE VAULT</p><h1>Telegram 媒体库</h1><p class="muted">登录后查看保存在 VPS 上的私人图片和视频。</p><label>访问密码<input v-model="password" type="password" autocomplete="current-password" required autofocus placeholder="输入管理密码" /></label><p v-if="error" class="error">{{ error }}</p><button class="primary" :disabled="loading">{{ loading ? '正在验证…' : '进入媒体库' }}</button></form></main>
  <div v-else class="app-shell">
    <header><div><p class="eyebrow">PRIVATE VAULT</p><h1>Telegram 媒体库</h1></div><button class="ghost" @click="logout">退出</button></header>
    <section class="stats"><div><strong>{{ stats.files }}</strong><span>全部媒体</span></div><div><strong>{{ stats.images || 0 }}</strong><span>图片</span></div><div><strong>{{ stats.videos || 0 }}</strong><span>视频</span></div><div><strong>{{ formatBytes(stats.bytes) }}</strong><span>占用空间</span></div></section>
    <nav class="toolbar"><div class="tabs"><button :class="{ active: kind === '' }" @click="kind = ''">全部</button><button :class="{ active: kind === 'image' }" @click="kind = 'image'">图片</button><button :class="{ active: kind === 'video' }" @click="kind = 'video'">视频</button><button :class="{ active: kind === 'document' }" @click="kind = 'document'">文件</button></div><input v-model="query" class="search" type="search" placeholder="搜索文件名、说明或来源" /><button :class="['filter', { active: favorite }]" @click="favorite = !favorite">★ 收藏</button><button :class="['filter', { active: trash }]" @click="trash = !trash">回收站</button><button :class="['filter', { active: bulkMode }]" @click="bulkMode = !bulkMode">批量操作</button><button class="ghost" @click="tagManagerOpen = true">管理标签</button><button class="ghost" @click="albumManagerOpen = true">管理相册</button></nav>
    <div v-if="tags.length" class="tag-filters"><button :class="{ active: !activeTag }" @click="activeTag = ''">全部标签</button><button v-for="tag in tags" :key="tag.id" :class="{ active: activeTag === tag.name }" @click="activeTag = activeTag === tag.name ? '' : tag.name"><i :style="{ background: tag.color }"></i>{{ tag.name }} <small>{{ tag.mediaCount }}</small></button></div>
    <div v-if="albums.length" class="album-filters"><button :class="{ active: !activeAlbum }" @click="activeAlbum = ''">全部相册</button><button v-for="album in albums" :key="album.id" :class="{ active: String(activeAlbum) === String(album.id) }" @click="activeAlbum = String(activeAlbum) === String(album.id) ? '' : album.id">▣ {{ album.name }} <small>{{ album.mediaCount }}</small></button></div>
    <section v-if="bulkMode" class="bulk-panel"><div class="bulk-heading"><strong>已选 {{ checkedIds.length }} 项</strong><button @click="toggleAllVisible">{{ checkedIds.length === items.length ? '取消全选' : '选择本页全部' }}</button></div><div class="bulk-row"><span>标签</span><div class="tag-checks"><label v-for="tag in tags" :key="tag.id"><input v-model="bulkTagIds" type="checkbox" :value="tag.id" /><i :style="{ background: tag.color }"></i>{{ tag.name }}</label></div><button :disabled="!checkedIds.length || !bulkTagIds.length" @click="applyBulkTags('add')">添加</button><button :disabled="!checkedIds.length || !bulkTagIds.length" @click="applyBulkTags('remove')">移除</button></div><div class="bulk-row"><span>相册</span><div class="tag-checks"><label v-for="album in albums" :key="album.id"><input v-model="bulkAlbumIds" type="checkbox" :value="album.id" />▣ {{ album.name }}</label></div><button :disabled="!checkedIds.length || !bulkAlbumIds.length" @click="applyBulkAlbums('add')">加入</button><button :disabled="!checkedIds.length || !bulkAlbumIds.length" @click="applyBulkAlbums('remove')">移出</button></div><div class="bulk-actions"><button :disabled="!checkedIds.length" @click="applyBulkAction('favorite')">加入收藏</button><button :disabled="!checkedIds.length" @click="applyBulkAction('unfavorite')">取消收藏</button><button v-if="!trash" class="danger" :disabled="!checkedIds.length" @click="applyBulkAction('trash')">移至回收站</button><button v-if="trash" :disabled="!checkedIds.length" @click="applyBulkAction('restore')">恢复</button><button v-if="trash" class="danger" :disabled="!checkedIds.length" @click="applyBulkAction('permanent')">永久删除</button></div></section>
    <p v-if="error" class="error banner">{{ error }}</p>
    <section v-if="items.length" class="media-grid"><article v-for="item in items" :key="item.id" :class="['media-card', { checked: checkedIds.includes(item.id) }]" @click="openItem(item)"><div class="preview"><img v-if="item.kind !== 'document'" :src="`${API_BASE}/media/${item.id}/thumbnail`" :alt="item.original_name || ''" loading="lazy" /><div v-else class="document-icon">▤</div><span v-if="item.kind === 'video'" class="play">▶</span><span v-if="bulkMode" class="select-box">{{ checkedIds.includes(item.id) ? '✓' : '' }}</span><button v-else class="star" :title="item.is_favorite ? '取消收藏' : '收藏'" @click.stop="toggleFavorite(item)">{{ item.is_favorite ? '★' : '☆' }}</button></div><div class="card-meta"><strong>{{ item.original_name || `媒体 #${item.id}` }}</strong><div v-if="item.tags?.length" class="card-tags"><span v-for="tag in item.tags" :key="tag.id"><i :style="{ background: tag.color }"></i>{{ tag.name }}</span></div><div v-if="item.albums?.length" class="card-albums"><span v-for="album in item.albums" :key="album.id">▣ {{ album.name }}</span></div><span>{{ formatBytes(item.size_bytes) }} · {{ formatDate(item.created_at) }}</span></div></article></section>
    <section v-else class="empty"><span>{{ loading ? '正在加载…' : '这里还没有媒体' }}</span><p v-if="!loading && !trash">把图片或视频转发给 Telegram Bot，它会自动出现在这里。</p></section>
    <footer v-if="pageCount > 1" class="pager"><button :disabled="page <= 1" @click="page--">上一页</button><span>{{ page }} / {{ pageCount }}</span><button :disabled="page >= pageCount" @click="page++">下一页</button></footer>
  </div>
  <div v-if="selected" ref="modalRef" :class="['modal', { 'image-fullscreen': imageFullscreen }]" @click.self="closeViewer">
    <button class="modal-close" aria-label="关闭预览" @click="closeViewer">×</button>
    <button v-if="selected.kind === 'image'" class="fullscreen-toggle" :aria-label="imageFullscreen ? '退出全屏' : '全屏预览'" :title="imageFullscreen ? '退出全屏 (F)' : '全屏预览 (F)'" @click="toggleImageFullscreen">{{ imageFullscreen ? '退出全屏' : '⛶ 全屏' }}</button>
    <button v-if="selected.kind === 'image'" class="image-nav previous" :disabled="selectedImageIndex <= 0" aria-label="上一张" @click="navigateImage(-1)">‹</button>
    <button v-if="selected.kind === 'image'" class="image-nav next" :disabled="selectedImageIndex < 0 || selectedImageIndex >= imageItems.length - 1" aria-label="下一张" @click="navigateImage(1)">›</button>
    <div class="viewer" @touchstart.passive="imageTouchStart" @touchend.passive="imageTouchEnd">
      <img v-if="selected.kind === 'image'" :src="`${API_BASE}/media/${selected.id}/content`" :alt="selected.original_name || ''" />
      <video v-else-if="selected.kind === 'video'" :src="`${API_BASE}/media/${selected.id}/content`" controls autoplay playsinline />
      <div v-else class="document-large">▤</div>
    </div>
    <aside class="details"><p class="eyebrow">{{ selected.kind }}</p><h2>{{ selected.original_name || `媒体 #${selected.id}` }}</h2><p v-if="selected.caption">{{ selected.caption }}</p><section class="media-tags"><h3>标签</h3><div class="tag-checks"><label v-for="tag in tags" :key="tag.id"><input v-model="selectedTagIds" type="checkbox" :value="tag.id" /><i :style="{ background: tag.color }"></i>{{ tag.name }}</label></div><button class="ghost" @click="saveMediaTags">保存标签</button></section><section class="media-tags"><h3>相册</h3><div class="tag-checks"><label v-for="album in albums" :key="album.id"><input v-model="selectedAlbumIds" type="checkbox" :value="album.id" />▣ {{ album.name }}</label></div><button class="ghost" @click="saveMediaAlbums">保存相册</button></section><dl><dt>大小</dt><dd>{{ formatBytes(selected.size_bytes) }}</dd><dt>转存时间</dt><dd>{{ formatDate(selected.created_at) }}</dd><dt v-if="selected.source_name">来源</dt><dd v-if="selected.source_name">{{ selected.source_name }}</dd></dl><div class="actions"><a class="primary button" :href="`${API_BASE}/media/${selected.id}/download`">下载原文件</a><button v-if="!trash" class="ghost" @click="toggleFavorite(selected)">{{ selected.is_favorite ? '取消收藏' : '加入收藏' }}</button><button v-if="!trash" class="danger" @click="moveToTrash(selected)">移至回收站</button><button v-if="trash" class="ghost" @click="restore(selected)">恢复</button><button v-if="trash" class="danger" @click="removeForever(selected)">永久删除</button></div></aside>
  </div>
  <div v-if="tagManagerOpen" class="dialog-backdrop" @click.self="tagManagerOpen = false"><section class="tag-manager"><button class="dialog-close" @click="tagManagerOpen = false">×</button><p class="eyebrow">ORGANIZE</p><h2>管理标签</h2><form class="new-tag" @submit.prevent="createTag"><input v-model="newTagName" maxlength="32" placeholder="新标签名称" /><input v-model="newTagColor" type="color" aria-label="标签颜色" /><button class="primary">添加</button></form><div class="tag-list"><div v-for="tag in tags" :key="tag.id"><i :style="{ background: tag.color }"></i><strong>{{ tag.name }}</strong><small>{{ tag.mediaCount }} 项</small><input :value="tag.color" type="color" aria-label="修改颜色" @change="changeTagColor(tag, $event.target.value)" /><button @click="renameTag(tag)">重命名</button><button class="danger" @click="deleteTag(tag)">删除</button></div><p v-if="!tags.length" class="muted">还没有标签。</p></div><p class="hint">转发时在说明里加入 #标签，也会自动创建并关联标签。</p></section></div>
  <div v-if="albumManagerOpen" class="dialog-backdrop" @click.self="albumManagerOpen = false"><section class="tag-manager"><button class="dialog-close" @click="albumManagerOpen = false">×</button><p class="eyebrow">COLLECTIONS</p><h2>管理相册</h2><form class="new-album" @submit.prevent="createAlbum"><input v-model="newAlbumName" maxlength="64" placeholder="相册名称" /><input v-model="newAlbumDescription" maxlength="500" placeholder="相册说明（可选）" /><button class="primary">创建相册</button></form><div class="album-list"><div v-for="album in albums" :key="album.id"><div class="album-cover"><img v-if="album.coverMediaId" :src="`${API_BASE}/media/${album.coverMediaId}/thumbnail`" alt="" /><span v-else>▣</span></div><div><strong>{{ album.name }}</strong><p>{{ album.description || '暂无说明' }}</p></div><small>{{ album.mediaCount }} 项</small><button @click="editAlbum(album)">编辑</button><button class="danger" @click="deleteAlbum(album)">删除</button></div><p v-if="!albums.length" class="muted">还没有相册，可先创建后批量加入媒体。</p></div></section></div>
</template>

