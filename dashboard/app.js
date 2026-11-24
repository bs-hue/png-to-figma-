/**
 * PNG → Figma Converter Dashboard Logic
 * Light Theme, Tailwind CSS, Pure Vanilla JS (No build step)
 */

// Application State
const appState = {
  currentJob: null,
  currentMeta: null,
  filterText: true,
  filterShape: true,
  filterImage: true,
  backendOnline: false
};

// DOM Elements
const backendDot = document.getElementById('backend-dot');
const backendStatusText = document.getElementById('backend-status-text');

const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const loadingSpinner = document.getElementById('loading-spinner');
const loadingTitle = document.getElementById('loading-title');
const loadingDesc = document.getElementById('loading-desc');

const viewportOrig = document.getElementById('viewport-orig');
const imgOriginal = document.getElementById('img-original');
const origPlaceholder = document.getElementById('orig-placeholder');
const origSizeLabel = document.getElementById('orig-size-label');

const viewportDetected = document.getElementById('viewport-detected');
const detectedContainer = document.getElementById('detected-canvas-container');
const imgDetectedBg = document.getElementById('img-detected-bg');
const svgDetectionLayer = document.getElementById('svg-detection-layer');
const detectedPlaceholder = document.getElementById('detected-placeholder');

const checkText = document.getElementById('check-text');
const checkShape = document.getElementById('check-shape');
const checkImage = document.getElementById('check-image');
const badgeTextCount = document.getElementById('badge-text-count');
const badgeShapeCount = document.getElementById('badge-shape-count');
const badgeImageCount = document.getElementById('badge-image-count');

const sumText = document.getElementById('sum-text');
const sumShapes = document.getElementById('sum-shapes');
const sumImages = document.getElementById('sum-images');
const jobIdCode = document.getElementById('job-id-code');

const btnCopyJob = document.getElementById('btn-copy-job');
const btnDownloadJson = document.getElementById('btn-download-json');
const btnDownloadSvg = document.getElementById('btn-download-svg');
const btnCopyScript = document.getElementById('btn-copy-script');
const btnFigmaGuide = document.getElementById('btn-figma-guide');
const btnViewRawJson = document.getElementById('btn-view-raw-json');
const btnResetView = document.getElementById('btn-reset-view');

const figmaGuideModal = document.getElementById('figma-guide-modal');
const btnCloseGuide = document.getElementById('btn-close-guide');
const btnGuideOk = document.getElementById('btn-guide-ok');

const elementsTableBody = document.getElementById('elements-table-body');
const tableSearch = document.getElementById('table-search');
const recentJobsList = document.getElementById('recent-jobs-list');

const floatingTooltip = document.getElementById('floating-tooltip');
const tooltipHeader = document.getElementById('tooltip-header');
const tooltipBody = document.getElementById('tooltip-body');

const jsonModal = document.getElementById('json-modal');
const jsonCodeView = document.getElementById('json-code-view');
const btnCloseModal = document.getElementById('btn-close-modal');
const btnCopyModalJson = document.getElementById('btn-copy-modal-json');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  setupSyncScroll();
  checkHealth();
  loadRecentJobs();
  setInterval(checkHealth, 5000);
});

// --- Health Check ---
async function checkHealth() {
  try {
    const res = await fetch('/health');
    const text = await res.text();
    if (res.ok && text.trim() === 'ok') {
      backendDot.className = 'w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-xs';
      backendStatusText.textContent = 'Backend Online';
      appState.backendOnline = true;
    } else {
      setBackendOffline();
    }
  } catch (err) {
    setBackendOffline();
  }
}

function setBackendOffline() {
  backendDot.className = 'w-2.5 h-2.5 rounded-full bg-red-500';
  backendStatusText.textContent = 'Backend Offline';
  appState.backendOnline = false;
}

// --- Event Listeners ---
function setupEventListeners() {
  // File Upload
  dropZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleUpload(e.target.files[0]);
    }
  });

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('border-brand', 'bg-brand-50/20');
  });

  ['dragleave', 'dragend', 'drop'].forEach(type => {
    dropZone.addEventListener(type, () => {
      dropZone.classList.remove('border-brand', 'bg-brand-50/20');
    });
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleUpload(e.dataTransfer.files[0]);
    }
  });

  // Sample Buttons
  document.querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const filename = btn.getAttribute('data-file');
      handleSampleConvert(filename);
    });
  });

  // Layer Toggles
  checkText.addEventListener('change', (e) => {
    appState.filterText = e.target.checked;
    updateSvgVisibility();
    filterTable();
  });

  checkShape.addEventListener('change', (e) => {
    appState.filterShape = e.target.checked;
    updateSvgVisibility();
    filterTable();
  });

  checkImage.addEventListener('change', (e) => {
    appState.filterImage = e.target.checked;
    updateSvgVisibility();
    filterTable();
  });

  // Search Table
  tableSearch.addEventListener('input', () => {
    filterTable();
  });

  // Actions
  btnCopyJob.addEventListener('click', () => {
    if (appState.currentJob) {
      navigator.clipboard.writeText(appState.currentJob);
      showToast('Copied Job ID to clipboard!');
    }
  });

  btnDownloadJson.addEventListener('click', () => {
    if (appState.currentJob) {
      window.location.href = `/job/${appState.currentJob}/download`;
      showToast('Downloading layout.json...');
    }
  });

  btnDownloadSvg.addEventListener('click', () => {
    if (appState.currentJob) {
      window.location.href = `/job/${appState.currentJob}/svg`;
      showToast('Downloading Figma-compatible SVG... (Drag into Figma!)');
    }
  });

  btnCopyScript.addEventListener('click', async () => {
    if (appState.currentJob) {
      try {
        const res = await fetch(`/job/${appState.currentJob}/script`);
        if (!res.ok) throw new Error('Could not fetch script');
        const scriptCode = await res.text();
        await navigator.clipboard.writeText(scriptCode);
        showToast('Copied 1-Click Figma Console script to clipboard!');
      } catch (e) {
        showToast('Failed to copy script: ' + e.message, 'error');
      }
    }
  });

  btnFigmaGuide.addEventListener('click', () => {
    figmaGuideModal.classList.remove('hidden');
  });

  btnCloseGuide.addEventListener('click', () => {
    figmaGuideModal.classList.add('hidden');
  });

  btnGuideOk.addEventListener('click', () => {
    figmaGuideModal.classList.add('hidden');
  });

  btnViewRawJson.addEventListener('click', () => {
    if (appState.currentMeta && appState.currentMeta.layout) {
      jsonCodeView.textContent = JSON.stringify(appState.currentMeta.layout, null, 2);
      jsonModal.classList.remove('hidden');
    }
  });

  btnCloseModal.addEventListener('click', () => jsonModal.classList.add('hidden'));
  btnCopyModalJson.addEventListener('click', () => {
    if (appState.currentMeta && appState.currentMeta.layout) {
      navigator.clipboard.writeText(JSON.stringify(appState.currentMeta.layout, null, 2));
      showToast('Copied layout.json to clipboard!');
    }
  });

  btnResetView.addEventListener('click', () => {
    viewportOrig.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
    viewportDetected.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
  });
}

// --- Synchronized Scrolling ---
function setupSyncScroll() {
  let syncingLeft = false;
  let syncingRight = false;

  viewportOrig.addEventListener('scroll', () => {
    if (syncingLeft) return;
    syncingRight = true;
    viewportDetected.scrollTop = viewportOrig.scrollTop;
    viewportDetected.scrollLeft = viewportOrig.scrollLeft;
    setTimeout(() => { syncingRight = false; }, 30);
  });

  viewportDetected.addEventListener('scroll', () => {
    if (syncingRight) return;
    syncingLeft = true;
    viewportOrig.scrollTop = viewportDetected.scrollTop;
    viewportOrig.scrollLeft = viewportDetected.scrollLeft;
    setTimeout(() => { syncingLeft = false; }, 30);
  });
}

// --- Upload Handler ---
async function handleUpload(file) {
  if (!appState.backendOnline) {
    showToast('Backend is not running. Please start the server first.', 'error');
    return;
  }

  // 1. Validate extension
  const validExts = ['.png', '.jpg', '.jpeg', '.webp'];
  const ext = '.' + file.name.split('.').pop().toLowerCase();
  if (!validExts.includes(ext)) {
    showToast('Only PNG/JPG allowed. Please choose a valid image.', 'error');
    return;
  }

  // 2. Validate size (10 MB)
  const maxBytes = 10 * 1024 * 1024;
  if (file.size > maxBytes) {
    showToast('File too big. Maximum file size allowed is 10 MB.', 'error');
    return;
  }

  showLoading(true, `Uploading ${file.name}...`, 'Extracting text with Tesseract OCR & detecting shapes with OpenCV...');

  const formData = new FormData();
  formData.append('file', file);

  try {
    const res = await fetch('/convert', {
      method: 'POST',
      body: formData
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Conversion failed.');
    }

    const meta = await res.json();
    renderConversion(meta);
    loadRecentJobs();
    showToast(`Conversion complete! (${meta.counts.total} elements in ${meta.duration_seconds}s)`);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    showLoading(false);
  }
}

// --- Sample Convert ---
async function handleSampleConvert(filename) {
  if (!appState.backendOnline) {
    showToast('Backend not running. Please start the server.', 'error');
    return;
  }

  showLoading(true, `Converting sample ${filename}...`, 'Running OCR + OpenCV container detection...');

  try {
    const res = await fetch(`/convert-sample/${encodeURIComponent(filename)}`, {
      method: 'POST'
    });

    if (!res.ok) {
      const err = await res.json();
      throw new Error(err.detail || 'Sample conversion failed.');
    }

    const meta = await res.json();
    renderConversion(meta);
    loadRecentJobs();
    showToast(`Loaded sample "${filename}" (${meta.counts.total} elements)`);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    showLoading(false);
  }
}

// --- Reopen from Recent Jobs ---
async function reopenJob(jobId) {
  showLoading(true, `Reopening Job ${jobId}...`, 'Retrieving layout data...');
  try {
    const res = await fetch(`/job/${jobId}/meta`);
    if (!res.ok) throw new Error('Job not found or expired (jobs auto-delete after 24h).');
    const meta = await res.json();
    renderConversion(meta);
    showToast(`Reopened Job ${jobId}`);
  } catch (err) {
    showToast(err.message, 'error');
  } finally {
    showLoading(false);
  }
}

// --- Render Result ---
function renderConversion(meta) {
  appState.currentJob = meta.job_id;
  appState.currentMeta = meta;

  // Summary counts
  sumText.textContent = meta.counts.text;
  sumShapes.textContent = meta.counts.shapes;
  sumImages.textContent = meta.counts.images;

  badgeTextCount.textContent = meta.counts.text;
  badgeShapeCount.textContent = meta.counts.shapes;
  badgeImageCount.textContent = meta.counts.images;

  jobIdCode.textContent = meta.job_id;
  origSizeLabel.textContent = `${meta.width} × ${meta.height} px`;

  // Enable buttons
  btnDownloadJson.disabled = false;
  btnDownloadSvg.disabled = false;
  btnCopyScript.disabled = false;
  btnViewRawJson.disabled = false;

  // Original image
  imgOriginal.src = meta.original_image_url;
  imgOriginal.classList.remove('hidden');
  origPlaceholder.classList.add('hidden');

  // Detected image & SVG
  imgDetectedBg.src = meta.original_image_url;
  detectedContainer.classList.remove('hidden');
  detectedPlaceholder.classList.add('hidden');

  renderSvgBoxes(meta);
  renderTable(meta);

  // Scroll to top
  viewportOrig.scrollTo({ top: 0, left: 0 });
  viewportDetected.scrollTo({ top: 0, left: 0 });
}

// --- Render SVG Boxes ---
function renderSvgBoxes(meta) {
  const W = meta.width;
  const H = meta.height;

  svgDetectionLayer.setAttribute('viewBox', `0 0 ${W} ${H}`);
  svgDetectionLayer.innerHTML = '';

  const fragment = document.createDocumentFragment();

  // 1. Shapes (blue)
  (meta.shapes || []).forEach(s => {
    const rect = createSvgBox(s, 'shape', 'svg-bbox-shape');
    fragment.appendChild(rect);
  });

  // 2. Images (orange)
  (meta.images || []).forEach(im => {
    const rect = createSvgBox(im, 'image', 'svg-bbox-image');
    fragment.appendChild(rect);
  });

  // 3. Texts (green)
  (meta.texts || []).forEach(t => {
    const rect = createSvgBox(t, 'text', 'svg-bbox-text');
    fragment.appendChild(rect);
  });

  svgDetectionLayer.appendChild(fragment);
  updateSvgVisibility();
}

function createSvgBox(item, category, className) {
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', item.x);
  rect.setAttribute('y', item.y);
  rect.setAttribute('width', item.w);
  rect.setAttribute('height', item.h);
  if (item.radius) {
    rect.setAttribute('rx', item.radius);
  }
  rect.setAttribute('class', `svg-bbox ${className}`);
  rect.setAttribute('data-id', item.id);
  rect.setAttribute('data-cat', category);

  // Hover details
  rect.addEventListener('mouseenter', (e) => {
    highlightElement(item.id, true);
    showTooltip(e, item, category);
  });

  rect.addEventListener('mousemove', (e) => {
    moveTooltip(e);
  });

  rect.addEventListener('mouseleave', () => {
    highlightElement(item.id, false);
    hideTooltip();
  });

  rect.addEventListener('click', () => {
    scrollToRow(item.id);
  });

  return rect;
}

function updateSvgVisibility() {
  document.querySelectorAll('.svg-bbox[data-cat="text"]').forEach(el => {
    el.style.display = appState.filterText ? 'block' : 'none';
  });
  document.querySelectorAll('.svg-bbox[data-cat="shape"]').forEach(el => {
    el.style.display = appState.filterShape ? 'block' : 'none';
  });
  document.querySelectorAll('.svg-bbox[data-cat="image"]').forEach(el => {
    el.style.display = appState.filterImage ? 'block' : 'none';
  });
}

// --- Floating Tooltip ---
function showTooltip(e, item, category) {
  let catBadge = '';
  if (category === 'text') catBadge = '<span class="text-emerald-400 font-bold">[TEXT]</span>';
  else if (category === 'shape') catBadge = '<span class="text-blue-400 font-bold">[SHAPE]</span>';
  else catBadge = '<span class="text-amber-400 font-bold">[IMAGE]</span>';

  tooltipHeader.innerHTML = `${catBadge} ${escapeHtml(item.name || category)}`;
  
  let details = `
    <div><strong>Size:</strong> ${item.w} × ${item.h} px</div>
    <div><strong>Pos:</strong> (${item.x}, ${item.y})</div>
  `;
  if (item.text) {
    details += `<div><strong>Content:</strong> "${escapeHtml(item.text)}"</div>`;
  }
  if (item.fill) {
    details += `<div class="flex items-center gap-1.5"><strong>Fill:</strong> <span class="w-3 h-3 rounded-xs border border-white/30 inline-block" style="background:${item.fill}"></span> ${item.fill}</div>`;
  }
  if (item.color) {
    details += `<div class="flex items-center gap-1.5"><strong>Color:</strong> <span class="w-3 h-3 rounded-xs border border-white/30 inline-block" style="background:${item.color}"></span> ${item.color}</div>`;
  }
  if (item.fontSize) {
    details += `<div><strong>Font Size:</strong> ${item.fontSize} px</div>`;
  }

  tooltipBody.innerHTML = details;
  floatingTooltip.classList.remove('hidden');
  moveTooltip(e);
}

function moveTooltip(e) {
  const pad = 14;
  floatingTooltip.style.left = `${e.clientX + pad}px`;
  floatingTooltip.style.top = `${e.clientY + pad}px`;
}

function hideTooltip() {
  floatingTooltip.classList.add('hidden');
}

// --- Element List Table ---
function renderTable(meta) {
  filterTable();
}

function filterTable() {
  if (!appState.currentMeta) return;

  const meta = appState.currentMeta;
  const query = tableSearch.value.trim().toLowerCase();

  // Combine flat list
  const all = [];
  if (appState.filterText) {
    (meta.texts || []).forEach(t => all.push({ ...t, cat: 'text' }));
  }
  if (appState.filterShape) {
    (meta.shapes || []).forEach(s => all.push({ ...s, cat: 'shape' }));
  }
  if (appState.filterImage) {
    (meta.images || []).forEach(im => all.push({ ...im, cat: 'image' }));
  }

  // Sort top-to-bottom
  all.sort((a, b) => a.y - b.y);

  // Search filter
  const filtered = all.filter(item => {
    if (!query) return true;
    return (
      (item.name && item.name.toLowerCase().includes(query)) ||
      (item.text && item.text.toLowerCase().includes(query)) ||
      (item.cat && item.cat.toLowerCase().includes(query))
    );
  });

  if (filtered.length === 0) {
    elementsTableBody.innerHTML = `
      <tr>
        <td colspan="5" class="py-10 text-center text-slate-400">
          No matching elements found.
        </td>
      </tr>
    `;
    return;
  }

  let html = '';
  filtered.forEach(item => {
    let catClass = 'bg-slate-100 text-slate-700';
    let catLabel = item.cat.toUpperCase();
    if (item.cat === 'text') catClass = 'bg-emerald-50 text-emerald-700 border border-emerald-200';
    else if (item.cat === 'shape') catClass = 'bg-blue-50 text-blue-700 border border-blue-200';
    else if (item.cat === 'image') catClass = 'bg-amber-50 text-amber-700 border border-amber-200';

    const colorVal = item.color || item.fill || '#e2e8f0';

    html += `
      <tr id="row-${item.id}" data-id="${item.id}" class="element-table-row hover:bg-slate-50 transition-colors">
        <td class="py-2.5 px-4">
          <span class="inline-block px-2 py-0.5 rounded text-[10px] font-bold ${catClass}">${catLabel}</span>
        </td>
        <td class="py-2.5 px-4 font-medium text-slate-800">
          <div>${escapeHtml(item.name || item.text || '')}</div>
          ${item.text && item.name !== item.text ? `<div class="text-[11px] text-slate-400 truncate max-w-sm">"${escapeHtml(item.text)}"</div>` : ''}
        </td>
        <td class="py-2.5 px-4 font-mono text-slate-500">
          ${item.w} × ${item.h}
        </td>
        <td class="py-2.5 px-4">
          <div class="flex items-center gap-1.5 font-mono text-[11px] text-slate-600">
            <span class="w-3.5 h-3.5 rounded-xs border border-slate-300 shadow-2xs inline-block" style="background-color: ${colorVal};"></span>
            <span>${colorVal}</span>
          </div>
        </td>
        <td class="py-2.5 px-4 text-right">
          <button onclick="focusElement('${item.id}', ${item.x}, ${item.y})" class="px-2 py-1 text-[11px] font-medium text-brand hover:text-brand-600 hover:bg-brand-50 rounded transition-colors">
            Focus
          </button>
        </td>
      </tr>
    `;
  });

  elementsTableBody.innerHTML = html;

  // Add hover bindings to rows
  document.querySelectorAll('.element-table-row').forEach(row => {
    const id = row.getAttribute('data-id');
    row.addEventListener('mouseenter', () => highlightElement(id, true));
    row.addEventListener('mouseleave', () => highlightElement(id, false));
  });
}

function highlightElement(id, active) {
  const svgEl = document.querySelector(`.svg-bbox[data-id="${id}"]`);
  if (svgEl) {
    if (active) svgEl.classList.add('active-highlight');
    else svgEl.classList.remove('active-highlight');
  }

  const rowEl = document.getElementById(`row-${id}`);
  if (rowEl) {
    if (active) rowEl.classList.add('bg-brand-50/70');
    else rowEl.classList.remove('bg-brand-50/70');
  }
}

window.focusElement = function(id, x, y) {
  highlightElement(id, true);
  const viewportH = viewportDetected.clientHeight;
  const viewportW = viewportDetected.clientWidth;
  
  viewportDetected.scrollTo({
    top: Math.max(0, y - viewportH / 3),
    left: Math.max(0, x - viewportW / 3),
    behavior: 'smooth'
  });
};

function scrollToRow(id) {
  const rowEl = document.getElementById(`row-${id}`);
  if (rowEl) {
    rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    highlightElement(id, true);
    setTimeout(() => highlightElement(id, false), 1500);
  }
}

// --- Recent Conversions List ---
async function loadRecentJobs() {
  try {
    const res = await fetch('/recent');
    if (!res.ok) return;
    const data = await res.json();
    const jobs = data.recent || [];

    if (jobs.length === 0) {
      recentJobsList.innerHTML = '<span class="text-xs text-slate-400">No conversions yet.</span>';
      return;
    }

    recentJobsList.innerHTML = jobs.map(job => `
      <button onclick="reopenJob('${job.job_id}')" class="group inline-flex items-center gap-2 px-3 py-1.5 bg-slate-50 hover:bg-brand-50 border border-slate-200 hover:border-brand-300 rounded-xl text-xs text-slate-700 transition-all shadow-2xs">
        <span class="font-medium truncate max-w-[130px]">${escapeHtml(job.filename)}</span>
        <span class="font-mono text-[10px] px-1.5 py-0.5 rounded bg-white group-hover:bg-brand-100 text-slate-500 group-hover:text-brand-700 border border-slate-200">${job.job_id}</span>
      </button>
    `).join('');
  } catch (err) {
    console.warn('Failed to load recent jobs:', err);
  }
}

// --- Loading & Toasts ---
function showLoading(show, title = '', desc = '') {
  if (show) {
    loadingTitle.textContent = title;
    loadingDesc.textContent = desc;
    loadingSpinner.classList.remove('hidden');
  } else {
    loadingSpinner.classList.add('hidden');
  }
}

function showToast(message, type = 'info') {
  const container = document.getElementById('toast-container');
  const toast = document.createElement('div');
  
  let bg = 'bg-slate-900 text-white border-slate-800';
  let icon = '✓';
  if (type === 'error') {
    bg = 'bg-red-600 text-white border-red-700';
    icon = '✕';
  }

  toast.className = `${bg} pointer-events-auto flex items-center gap-2.5 px-4 py-2.5 rounded-xl border text-xs font-medium shadow-lg transition-all duration-300 opacity-0 translate-y-2`;
  toast.innerHTML = `<span class="font-bold">${icon}</span> <span>${escapeHtml(message)}</span>`;

  container.appendChild(toast);

  requestAnimationFrame(() => {
    toast.classList.remove('opacity-0', 'translate-y-2');
    toast.classList.add('opacity-100', 'translate-y-0');
  });

  setTimeout(() => {
    toast.classList.remove('opacity-100', 'translate-y-0');
    toast.classList.add('opacity-0', 'translate-y-2');
    setTimeout(() => toast.remove(), 300);
  }, 3200);
}

function escapeHtml(str) {
  if (!str) return '';
  return str.replace(/[&<>"']/g, m => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;'
  })[m]);
}
