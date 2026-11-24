/**
 * PNG → Figma Converter Frontend Logic
 * Full offline client handling drag & drop, SVG overlay, sync zoom/scroll,
 * element filtering, and Figma exports.
 */

// Application State
const state = {
  currentJob: null,
  scale: 1,
  filterText: true,
  filterShape: true,
  filterImage: true,
  syncScroll: true,
  recentJobs: []
};

// DOM Elements
const dropZone = document.getElementById('drop-zone');
const fileInput = document.getElementById('file-input');
const processingOverlay = document.getElementById('processing-overlay');
const processingTitle = document.getElementById('processing-title');
const processingDesc = document.getElementById('processing-desc');

// Viewports
const origViewport = document.getElementById('orig-viewport');
const origImg = document.getElementById('orig-img');
const origPlaceholder = document.getElementById('orig-placeholder');
const origDimensions = document.getElementById('orig-dimensions');

const detectedViewport = document.getElementById('detected-viewport');
const detectedBgImg = document.getElementById('detected-bg-img');
const detectionSvg = document.getElementById('detection-svg');
const detectedPlaceholder = document.getElementById('detected-placeholder');

// Filters
const toggleText = document.getElementById('toggle-text');
const toggleShape = document.getElementById('toggle-shape');
const toggleImage = document.getElementById('toggle-image');
const countTextFilter = document.getElementById('count-text-filter');
const countShapeFilter = document.getElementById('count-shape-filter');
const countImageFilter = document.getElementById('count-image-filter');

// Results & Actions
const foundText = document.getElementById('found-text');
const foundShapes = document.getElementById('found-shapes');
const foundImages = document.getElementById('found-images');
const jobIdText = document.getElementById('job-id-text');
const btnCopyJob = document.getElementById('btn-copy-job');
const btnDownloadJson = document.getElementById('btn-download-json');
const btnCopyScript = document.getElementById('btn-copy-script');
const btnViewTree = document.getElementById('btn-view-tree');

// Elements Table
const elementsTableBody = document.getElementById('elements-table-body');
const elementsSearch = document.getElementById('elements-search');
const elementCountPill = document.getElementById('element-count-pill');

// Recent
const recentChips = document.getElementById('recent-chips');

// Backend Status
const backendStatus = document.getElementById('backend-status');
const backendIndicator = document.getElementById('backend-indicator');
const backendMeta = document.getElementById('backend-meta');

// Modal & Toast
const treeModal = document.getElementById('tree-modal');
const treeJsonDisplay = document.getElementById('tree-json-display');
const modalCloseBtn = document.getElementById('modal-close-btn');
const modalCloseBackdrop = document.getElementById('modal-close-backdrop');
const modalCopyJson = document.getElementById('modal-copy-json');
const toast = document.getElementById('toast');

// --- Initialization ---
document.addEventListener('DOMContentLoaded', () => {
  setupEventListeners();
  setupSynchronizedScrolling();
  checkBackendHealth();
  fetchRecentJobs();
  // Poll backend health every 6 seconds
  setInterval(checkBackendHealth, 6000);
});

// --- Event Listeners ---
function setupEventListeners() {
  // Drop Zone Upload
  dropZone.addEventListener('click', () => fileInput.click());
  fileInput.addEventListener('change', (e) => {
    if (e.target.files && e.target.files[0]) {
      handleFileUpload(e.target.files[0]);
    }
  });

  dropZone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropZone.classList.add('dragover');
  });

  ['dragleave', 'dragend'].forEach(type => {
    dropZone.addEventListener(type, () => dropZone.classList.remove('dragover'));
  });

  dropZone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropZone.classList.remove('dragover');
    if (e.dataTransfer.files && e.dataTransfer.files[0]) {
      handleFileUpload(e.dataTransfer.files[0]);
    }
  });

  // Sample buttons
  document.querySelectorAll('.sample-btn').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const sampleName = btn.getAttribute('data-sample');
      convertSample(sampleName);
    });
  });

  // Filters
  toggleText.addEventListener('change', (e) => {
    state.filterText = e.target.checked;
    updateSvgVisibility();
    filterTableElements();
  });

  toggleShape.addEventListener('change', (e) => {
    state.filterShape = e.target.checked;
    updateSvgVisibility();
    filterTableElements();
  });

  toggleImage.addEventListener('change', (e) => {
    state.filterImage = e.target.checked;
    updateSvgVisibility();
    filterTableElements();
  });

  // Search
  elementsSearch.addEventListener('input', () => {
    filterTableElements();
  });

  // Fit view buttons
  document.getElementById('btn-fit-orig').addEventListener('click', resetViewports);
  document.getElementById('btn-fit-detected').addEventListener('click', resetViewports);

  // Actions
  btnCopyJob.addEventListener('click', () => {
    if (state.currentJob) {
      navigator.clipboard.writeText(state.currentJob.job_id);
      showToast(`Copied Job ID: ${state.currentJob.job_id}`);
    }
  });

  btnDownloadJson.addEventListener('click', () => {
    if (state.currentJob) {
      window.location.href = `/api/job/${state.currentJob.job_id}/figma.json`;
      showToast('Downloading Figma JSON file...');
    }
  });

  btnCopyScript.addEventListener('click', () => {
    if (state.currentJob && state.currentJob.plugin_script) {
      navigator.clipboard.writeText(state.currentJob.plugin_script);
      showToast('Copied 1-Click Figma Importer script to clipboard!');
    }
  });

  btnViewTree.addEventListener('click', () => {
    if (state.currentJob) {
      treeJsonDisplay.textContent = JSON.stringify(state.currentJob.figma_json, null, 2);
      treeModal.classList.remove('hidden');
    }
  });

  modalCloseBtn.addEventListener('click', () => treeModal.classList.add('hidden'));
  modalCloseBackdrop.addEventListener('click', () => treeModal.classList.add('hidden'));
  modalCopyJson.addEventListener('click', () => {
    if (state.currentJob) {
      navigator.clipboard.writeText(JSON.stringify(state.currentJob.figma_json, null, 2));
      showToast('Copied full Figma JSON!');
    }
  });
}

// --- Synchronized Scrolling ---
function setupSynchronizedScrolling() {
  let isSyncingLeft = false;
  let isSyncingRight = false;

  origViewport.addEventListener('scroll', () => {
    if (!state.syncScroll || isSyncingLeft) return;
    isSyncingRight = true;
    detectedViewport.scrollTop = origViewport.scrollTop;
    detectedViewport.scrollLeft = origViewport.scrollLeft;
    setTimeout(() => { isSyncingRight = false; }, 40);
  });

  detectedViewport.addEventListener('scroll', () => {
    if (!state.syncScroll || isSyncingRight) return;
    isSyncingLeft = true;
    origViewport.scrollTop = detectedViewport.scrollTop;
    origViewport.scrollLeft = detectedViewport.scrollLeft;
    setTimeout(() => { isSyncingLeft = false; }, 40);
  });
}

function resetViewports() {
  origViewport.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
  detectedViewport.scrollTo({ top: 0, left: 0, behavior: 'smooth' });
}

// --- Backend Health Check ---
async function checkBackendHealth() {
  try {
    const res = await fetch('/api/health');
    if (res.ok) {
      const data = await res.json();
      backendIndicator.textContent = '🟢 Online';
      backendMeta.textContent = `OpenCV ${data.opencv_version} | Tesseract ${data.tesseract_version}`;
      backendStatus.classList.remove('offline');
    } else {
      markOffline();
    }
  } catch (err) {
    markOffline();
  }
}

function markOffline() {
  backendIndicator.textContent = '🔴 Offline';
  backendMeta.textContent = 'Server unreachable';
  backendStatus.classList.add('offline');
}

// --- Upload and Conversion ---
async function handleFileUpload(file) {
  showProcessing(true, `Processing ${file.name}...`, 'Extracting text with Tesseract OCR & detecting shapes with OpenCV...');
  
  const formData = new FormData();
  formData.append('file', file);

  try {
    const response = await fetch('/api/convert', {
      method: 'POST',
      body: formData
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Conversion failed.');
    }

    const data = await response.json();
    renderJobResult(data);
    fetchRecentJobs();
    showToast(`Conversion complete! (${data.counts.total} elements in ${data.duration_seconds}s)`);
  } catch (error) {
    alert(`Error: ${error.message}`);
  } finally {
    showProcessing(false);
  }
}

async function convertSample(filename) {
  showProcessing(true, `Analyzing sample: ${filename}...`, 'Running offline OCR and shape contour analysis...');
  try {
    const response = await fetch(`/api/convert-sample/${encodeURIComponent(filename)}`, {
      method: 'POST'
    });

    if (!response.ok) {
      const err = await response.json();
      throw new Error(err.detail || 'Sample conversion failed.');
    }

    const data = await response.json();
    renderJobResult(data);
    fetchRecentJobs();
    showToast(`Loaded sample "${filename}" (${data.counts.total} elements)`);
  } catch (error) {
    alert(`Error: ${error.message}`);
  } finally {
    showProcessing(false);
  }
}

async function loadJobById(jobId) {
  showProcessing(true, `Loading Job ${jobId}...`, 'Retrieving layout data...');
  try {
    const response = await fetch(`/api/job/${jobId}`);
    if (!response.ok) throw new Error('Could not load job');
    const data = await response.json();
    renderJobResult(data);
    showToast(`Loaded Job ${jobId}`);
  } catch (err) {
    alert(err.message);
  } finally {
    showProcessing(false);
  }
}

function showProcessing(show, title = '', desc = '') {
  if (show) {
    processingTitle.textContent = title;
    processingDesc.textContent = desc;
    processingOverlay.classList.remove('hidden');
  } else {
    processingOverlay.classList.add('hidden');
  }
}

// --- Render Results ---
function renderJobResult(data) {
  state.currentJob = data;

  // Update Summary Counters
  foundText.textContent = data.counts.text;
  foundShapes.textContent = data.counts.shapes;
  foundImages.textContent = data.counts.images;

  countTextFilter.textContent = data.counts.text;
  countShapeFilter.textContent = data.counts.shapes;
  countImageFilter.textContent = data.counts.images;

  jobIdText.textContent = data.job_id;
  origDimensions.textContent = `${data.dimensions.width} × ${data.dimensions.height} px`;

  // Enable action buttons
  btnDownloadJson.disabled = false;
  btnCopyScript.disabled = false;
  btnViewTree.disabled = false;

  // Render Original Image
  origImg.src = data.image_url;
  origImg.style.display = 'block';
  origPlaceholder.style.display = 'none';

  // Render Detected Viewport
  detectedBgImg.src = data.image_url;
  detectedBgImg.style.display = 'block';
  detectedPlaceholder.style.display = 'none';

  // Render SVG Bounding Boxes
  renderDetectionSvg(data);

  // Render Elements Table
  renderElementsTable(data.elements);

  // Reset scroll
  resetViewports();
}

function renderDetectionSvg(data) {
  const W = data.dimensions.width;
  const H = data.dimensions.height;

  detectionSvg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  detectionSvg.innerHTML = '';

  const fragment = document.createDocumentFragment();

  // 1. Shapes (blue)
  data.shapes.forEach(s => {
    const rect = createSvgRect(s, 'shape', 'bbox-shape');
    fragment.appendChild(rect);
  });

  // 2. Images (orange)
  data.images.forEach(img => {
    const rect = createSvgRect(img, 'image', 'bbox-image');
    fragment.appendChild(rect);
  });

  // 3. Texts (green) - render on top
  data.texts.forEach(t => {
    const rect = createSvgRect(t, 'text', 'bbox-text');
    fragment.appendChild(rect);
  });

  detectionSvg.appendChild(fragment);
  updateSvgVisibility();
}

function createSvgRect(item, category, className) {
  const rect = document.createElementNS('http://www.w3.org/2000/svg', 'rect');
  rect.setAttribute('x', item.x);
  rect.setAttribute('y', item.y);
  rect.setAttribute('width', item.width);
  rect.setAttribute('height', item.height);
  if (item.cornerRadius) {
    rect.setAttribute('rx', item.cornerRadius);
  }
  rect.setAttribute('class', `svg-bbox ${className}`);
  rect.setAttribute('data-id', item.id);
  rect.setAttribute('data-category', category);

  // Tooltip title
  const title = document.createElementNS('http://www.w3.org/2000/svg', 'title');
  const label = item.text ? `"${item.text}"` : (item.name || category);
  title.textContent = `[${category.toUpperCase()}] ${label}\nPos: (${item.x}, ${item.y}) Size: ${item.width}×${item.height}px`;
  rect.appendChild(title);

  // Interactive hover highlight
  rect.addEventListener('mouseenter', () => highlightElement(item.id, true));
  rect.addEventListener('mouseleave', () => highlightElement(item.id, false));
  rect.addEventListener('click', () => scrollToTableRow(item.id));

  return rect;
}

function updateSvgVisibility() {
  document.querySelectorAll('.svg-bbox[data-category="text"]').forEach(el => {
    el.style.display = state.filterText ? 'block' : 'none';
  });
  document.querySelectorAll('.svg-bbox[data-category="shape"]').forEach(el => {
    el.style.display = state.filterShape ? 'block' : 'none';
  });
  document.querySelectorAll('.svg-bbox[data-category="image"]').forEach(el => {
    el.style.display = state.filterImage ? 'block' : 'none';
  });
}

// --- Render Elements Table ---
function renderElementsTable(elements) {
  elementCountPill.textContent = `${elements.length} items`;
  filterTableElements();
}

function filterTableElements() {
  if (!state.currentJob) return;

  const query = elementsSearch.value.trim().toLowerCase();
  const elements = state.currentJob.elements || [];

  const filtered = elements.filter(item => {
    // Category toggle check
    if (item.category === 'text' && !state.filterText) return false;
    if (item.category === 'shape' && !state.filterShape) return false;
    if (item.category === 'image' && !state.filterImage) return false;

    // Search query check
    if (!query) return true;
    return (
      (item.name && item.name.toLowerCase().includes(query)) ||
      (item.detail && item.detail.toLowerCase().includes(query)) ||
      (item.tag && item.tag.toLowerCase().includes(query))
    );
  });

  elementCountPill.textContent = `${filtered.length} of ${elements.length} items`;

  if (filtered.length === 0) {
    elementsTableBody.innerHTML = `
      <tr class="empty-row">
        <td colspan="5">No matching elements found. Try adjusting your search or filters.</td>
      </tr>
    `;
    return;
  }

  let html = '';
  filtered.forEach(item => {
    const badgeClass = item.category === 'text' 
      ? 'badge-tag-text' 
      : (item.category === 'shape' ? 'badge-tag-shape' : 'badge-tag-image');

    html += `
      <tr id="row-${item.id}" data-id="${item.id}" class="element-row">
        <td>
          <span class="badge-tag ${badgeClass}">${item.category.toUpperCase()}</span>
        </td>
        <td>
          <div class="elem-name-cell">
            <span class="elem-title">${escapeHtml(item.name)}</span>
            <span class="elem-detail" title="${escapeHtml(item.detail || '')}">${escapeHtml(item.detail || '')}</span>
          </div>
        </td>
        <td>
          <span class="dim-code">${item.width} × ${item.height}</span>
        </td>
        <td>
          <div class="color-cell">
            <span class="color-swatch" style="background-color: ${item.color || '#333'};"></span>
            <span>${item.color || '#---'}</span>
          </div>
        </td>
        <td style="text-align: right;">
          <button class="tool-btn" onclick="focusElement('${item.id}', ${item.x}, ${item.y})">Focus</button>
        </td>
      </tr>
    `;
  });

  elementsTableBody.innerHTML = html;

  // Add hover bindings to rows
  document.querySelectorAll('.element-row').forEach(row => {
    const id = row.getAttribute('data-id');
    row.addEventListener('mouseenter', () => highlightElement(id, true));
    row.addEventListener('mouseleave', () => highlightElement(id, false));
  });
}

function highlightElement(id, active) {
  // Highlight SVG Box
  const svgEl = document.querySelector(`.svg-bbox[data-id="${id}"]`);
  if (svgEl) {
    if (active) svgEl.classList.add('highlighted');
    else svgEl.classList.remove('highlighted');
  }

  // Highlight Table Row
  const rowEl = document.getElementById(`row-${id}`);
  if (rowEl) {
    if (active) rowEl.classList.add('active-row');
    else rowEl.classList.remove('active-row');
  }
}

window.focusElement = function(id, x, y) {
  highlightElement(id, true);
  // Scroll canvas to focus on element
  const viewportH = detectedViewport.clientHeight;
  const viewportW = detectedViewport.clientWidth;
  
  detectedViewport.scrollTo({
    top: Math.max(0, y - viewportH / 3),
    left: Math.max(0, x - viewportW / 3),
    behavior: 'smooth'
  });
};

function scrollToTableRow(id) {
  const rowEl = document.getElementById(`row-${id}`);
  if (rowEl) {
    rowEl.scrollIntoView({ behavior: 'smooth', block: 'center' });
    highlightElement(id, true);
    setTimeout(() => highlightElement(id, false), 1500);
  }
}

// --- Recent Conversions ---
async function fetchRecentJobs() {
  try {
    const res = await fetch('/api/recent');
    if (!res.ok) return;
    const data = await res.json();
    state.recentJobs = data.recent || [];

    if (state.recentJobs.length === 0) {
      recentChips.innerHTML = '<span class="no-recent">No recent conversions yet</span>';
      return;
    }

    recentChips.innerHTML = state.recentJobs.map(job => `
      <button class="recent-chip" onclick="loadJobById('${job.job_id}')" title="${job.timestamp} (${job.counts.total} items)">
        <span>${escapeHtml(job.filename)}</span>
        <span class="tag local-badge">${job.job_id}</span>
      </button>
    `).join('');
  } catch (err) {
    console.warn('Failed to load recent jobs:', err);
  }
}

// --- Utilities ---
function showToast(msg) {
  toast.textContent = msg;
  toast.classList.remove('hidden');
  clearTimeout(toast._timer);
  toast._timer = setTimeout(() => {
    toast.classList.add('hidden');
  }, 2800);
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
