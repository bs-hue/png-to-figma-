// PNG to Figma — BloomX Plugin
// Plain JavaScript Figma Plugin Sandbox Code

figma.showUI(__html__, { width: 380, height: 540, themeColors: true });

// Convert #RRGGBB to Figma 0..1 RGB object
function hexToRgb(hex) {
  if (!hex || typeof hex !== 'string' || !hex.startsWith('#') || hex.length < 7) {
    return { r: 0.9, g: 0.9, b: 0.9 };
  }
  try {
    const r = parseInt(hex.slice(1, 3), 16) / 255;
    const g = parseInt(hex.slice(3, 5), 16) / 255;
    const b = parseInt(hex.slice(5, 7), 16) / 255;
    return {
      r: Math.max(0, Math.min(1, r)),
      g: Math.max(0, Math.min(1, g)),
      b: Math.max(0, Math.min(1, b))
    };
  } catch (e) {
    return { r: 0.9, g: 0.9, b: 0.9 };
  }
}

// Count total nodes recursively for accurate progress updates
function countTotalNodes(nodes) {
  let count = 0;
  function walk(list) {
    if (!Array.isArray(list)) return;
    for (const n of list) {
      count++;
      if (n.children && n.children.length > 0) {
        walk(n.children);
      }
    }
  }
  walk(nodes);
  return count;
}

// Generate clean, readable layer names
function getReadableLayerName(node, type, imageCounter) {
  if (type === 'text') {
    const textSnippet = String(node.text || '').replace(/\s+/g, ' ').trim();
    const cleanSnippet = textSnippet.length > 24 ? textSnippet.slice(0, 24) + '...' : textSnippet;
    const size = Number(node.fontSize) || 14;
    if (size >= 24) {
      return `Heading - ${cleanSnippet || 'Text'}`;
    } else if (size >= 18) {
      return `Subheading - ${cleanSnippet || 'Text'}`;
    }
    return `Text - ${cleanSnippet || 'Paragraph'}`;
  }

  if (type === 'frame') {
    if (node.name && node.name.startsWith('Button')) {
      return node.name;
    }
    // Check if children contain a text node to label button
    if (node.children && node.children.length > 0) {
      const textChild = node.children.find(function(c) { return c.type === 'text' && c.text; });
      if (textChild && node.h <= 70 && node.w <= 380) {
        const btnText = textChild.text.replace(/\s+/g, ' ').trim().slice(0, 20);
        return `Button - ${btnText}`;
      }
    }
    if (node.name && !node.name.includes('shape_')) {
      return node.name.replace(/\s*\(\d+x\d+\)/, '');
    }
    return 'Container Frame';
  }

  if (type === 'image') {
    return `Image ${imageCounter}`;
  }

  if (type === 'rectangle') {
    if (node.name && !node.name.includes('shape_')) {
      return node.name.replace(/\s*\(\d+x\d+\)/, '');
    }
    return 'Rectangle';
  }

  return node.name || 'Layer';
}

// Apply stroke styling if present
function applyStroke(figmaNode, node) {
  const strokeColor = node.strokeColor || node.stroke;
  if (strokeColor && strokeColor !== 'none') {
    figmaNode.strokes = [{ type: 'SOLID', color: hexToRgb(strokeColor) }];
    figmaNode.strokeWeight = Math.max(1, Number(node.strokeWidth) || Number(node.strokeWeight) || 1);
  } else {
    figmaNode.strokes = [];
  }
}

// Pre-load Inter font styles
async function preloadFonts() {
  const styles = ['Regular', 'Medium', 'Bold'];
  for (const style of styles) {
    try {
      await figma.loadFontAsync({ family: 'Inter', style: style });
    } catch (e) {
      console.warn(`Font Inter ${style} preload failed:`, e);
    }
  }
}

// Build text node with exact font loading, explicit line-height, and smart wrapping
async function buildTextNode(node, parentFigmaNode, relX, relY) {
  const textNode = figma.createText();

  // 1. Pick font weight style based on fontWeight or fontSize
  let fontStyle = 'Regular';
  const fw = String(node.fontWeight || '').toLowerCase();
  if (fw.includes('bold') || fw === '700' || fw === '800' || fw === '900') {
    fontStyle = 'Bold';
  } else if (fw.includes('med') || fw === '500' || fw === '600') {
    fontStyle = 'Medium';
  } else if (node.fontSize && node.fontSize >= 24) {
    fontStyle = 'Bold';
  } else if (node.fontSize && node.fontSize >= 18) {
    fontStyle = 'Medium';
  }

  const fontToLoad = { family: 'Inter', style: fontStyle };
  try {
    await figma.loadFontAsync(fontToLoad);
    textNode.fontName = fontToLoad;
  } catch (err) {
    await figma.loadFontAsync({ family: 'Inter', style: 'Regular' });
    textNode.fontName = { family: 'Inter', style: 'Regular' };
  }

  // 2. Append to parent FIRST so relative coordinate system is accurately bound
  parentFigmaNode.appendChild(textNode);

  // 3. Set text characters and sizing
  const rawText = String(node.text != null ? node.text : 'Text').replace(/\r\n/g, '\n');
  textNode.characters = rawText || ' ';
  const fontSize = Math.max(8, Number(node.fontSize) || 14);
  textNode.fontSize = fontSize;

  // 4. Explicit proportional line-height (135%) prevents descenders from overlapping adjacent lines
  const lineHeightPx = Math.round(fontSize * 1.35);
  textNode.lineHeight = { value: lineHeightPx, unit: 'PIXELS' };

  // 5. Smart auto-resize:
  // If multi-line (has \n) or long paragraph text with given width, constrain width to prevent horizontal overlap
  const hasLineBreaks = rawText.includes('\n');
  const isLongParagraph = rawText.length > 35 && typeof node.w === 'number' && node.w > 120;
  if (hasLineBreaks || isLongParagraph) {
    const targetW = Math.max(60, Number(node.w) || 200);
    textNode.resize(targetW, textNode.height);
    textNode.textAutoResize = 'HEIGHT';
  } else {
    textNode.textAutoResize = 'WIDTH_AND_HEIGHT';
  }

  // 6. Set relative position
  textNode.x = relX;
  textNode.y = relY;

  // 7. Styling
  const color = node.color || '#000000';
  textNode.fills = [{ type: 'SOLID', color: hexToRgb(color) }];
  textNode.name = getReadableLayerName(node, 'text');

  return textNode;
}

// Build image node using figma.createImage with byte data
function buildImageNode(node, parentFigmaNode, relX, relY, w, h, imagesData, imgCounter) {
  const rect = figma.createRectangle();
  rect.name = getReadableLayerName(node, 'image', imgCounter);
  rect.resize(w, h);

  if (typeof node.radius === 'number' && node.radius > 0) {
    rect.cornerRadius = node.radius;
  }
  applyStroke(rect, node);

  let bytes = null;
  if (imagesData) {
    if (node.id && imagesData[node.id]) {
      bytes = imagesData[node.id];
    } else if (node.imageUrl && imagesData[node.imageUrl]) {
      bytes = imagesData[node.imageUrl];
    }
  }

  if (bytes && bytes.length > 0) {
    try {
      const uint8 = bytes instanceof Uint8Array ? bytes : new Uint8Array(bytes);
      const figmaImage = figma.createImage(uint8);
      rect.fills = [{
        type: 'IMAGE',
        scaleMode: 'FILL',
        imageHash: figmaImage.hash
      }];
    } catch (imgErr) {
      console.warn('Could not create figma.createImage from bytes:', imgErr);
      rect.fills = [{ type: 'SOLID', color: { r: 0.92, g: 0.94, b: 0.97 } }];
    }
  } else {
    // Subtle placeholder fill if bytes unavailable
    rect.fills = [{ type: 'SOLID', color: { r: 0.92, g: 0.94, b: 0.97 } }];
  }

  parentFigmaNode.appendChild(rect);
  rect.x = relX;
  rect.y = relY;
  return rect;
}

// Build simple rectangle node
function buildRectangleNode(node, parentFigmaNode, relX, relY, w, h) {
  const rect = figma.createRectangle();
  rect.name = getReadableLayerName(node, 'rectangle');
  rect.resize(w, h);

  if (typeof node.radius === 'number' && node.radius > 0) {
    rect.cornerRadius = node.radius;
  }

  if (node.fill && node.fill !== 'none') {
    rect.fills = [{ type: 'SOLID', color: hexToRgb(node.fill) }];
  } else {
    rect.fills = [];
  }

  applyStroke(rect, node);
  parentFigmaNode.appendChild(rect);
  rect.x = relX;
  rect.y = relY;
  return rect;
}

// Build container Frame and recursively place children relative to parent
async function buildFrameNode(node, parentFigmaNode, relX, relY, w, h, imagesData, state) {
  const frame = figma.createFrame();
  frame.name = getReadableLayerName(node, 'frame');
  frame.resize(w, h);
  frame.clipsContent = false;

  if (typeof node.radius === 'number' && node.radius > 0) {
    frame.cornerRadius = node.radius;
  }

  if (node.fill && node.fill !== 'none') {
    frame.fills = [{ type: 'SOLID', color: hexToRgb(node.fill) }];
  } else {
    frame.fills = [];
  }

  applyStroke(frame, node);
  parentFigmaNode.appendChild(frame);
  frame.x = relX;
  frame.y = relY;

  // Recursively process children
  // Always render frames/rectangles first and text nodes last so text is on top of z-order!
  if (node.children && node.children.length > 0) {
    const sorted = node.children.slice().sort(function(a, b) {
      const aIsText = a.type === 'text' ? 1 : 0;
      const bIsText = b.type === 'text' ? 1 : 0;
      return aIsText - bIsText;
    });
    for (const child of sorted) {
      await renderNodeSafely(child, frame, node.x, node.y, imagesData, state);
    }
  }

  return frame;
}

// Safe node dispatcher with error boundary for each layer
async function renderNodeSafely(node, parentFigmaNode, parentAbsX, parentAbsY, imagesData, state) {
  try {
    const hasChildren = node.children && node.children.length > 0;
    const type = node.type || (hasChildren ? 'frame' : 'rectangle');
    const x = typeof node.x === 'number' ? node.x : 0;
    const y = typeof node.y === 'number' ? node.y : 0;
    const w = Math.max(1, typeof node.w === 'number' ? node.w : 10);
    const h = Math.max(1, typeof node.h === 'number' ? node.h : 10);

    const relX = x - parentAbsX;
    const relY = y - parentAbsY;

    if (type === 'frame' || hasChildren) {
      await buildFrameNode(node, parentFigmaNode, relX, relY, w, h, imagesData, state);
    } else if (type === 'text') {
      await buildTextNode(node, parentFigmaNode, relX, relY);
    } else if (type === 'image') {
      state.imgCounter++;
      buildImageNode(node, parentFigmaNode, relX, relY, w, h, imagesData, state.imgCounter);
    } else {
      buildRectangleNode(node, parentFigmaNode, relX, relY, w, h);
    }

    state.builtCount++;

    // Send progress to UI
    figma.ui.postMessage({
      type: 'progress',
      current: state.builtCount,
      total: state.totalNodes,
      message: `Building layers... ${state.builtCount}/${state.totalNodes}`
    });

  } catch (err) {
    state.skippedCount++;
    const layerName = node.name || node.text || node.id || 'Layer';
    const reason = `${layerName}: ${err.message || 'Render failed'}`;
    state.skippedReasons.push(reason);
    console.error('Skipping node due to error:', node, err);
  }
}

// Main message handler
figma.ui.onmessage = async function(msg) {
  if (msg.type === 'build-layout') {
    try {
      const layout = msg.layout;
      if (!layout || !layout.nodes) {
        figma.notify('❌ Invalid layout data received.');
        figma.ui.postMessage({ type: 'error', message: 'Invalid layout data' });
        return;
      }

      // Step 1: Preload fonts
      figma.ui.postMessage({ type: 'progress', current: 0, total: 100, message: 'Loading fonts...' });
      await preloadFonts();

      const totalNodes = countTotalNodes(layout.nodes);
      const state = {
        totalNodes: totalNodes,
        builtCount: 0,
        skippedCount: 0,
        skippedReasons: [],
        imgCounter: 0
      };

      figma.ui.postMessage({
        type: 'progress',
        current: 0,
        total: totalNodes,
        message: `Building layers... 0/${totalNodes}`
      });

      // Step 2: Create root frame named after the file with exact dimensions and background
      const width = Number(layout.width) || 1440;
      const height = Number(layout.height) || 900;
      const bgColor = layout.backgroundColor || '#ffffff';
      const frameTitle = msg.filename || layout.filename || 'Converted Design';

      const page = figma.currentPage;
      const rootFrame = figma.createFrame();
      rootFrame.name = frameTitle.replace(/\.[^/.]+$/, ''); // clean filename
      rootFrame.resize(width, height);
      rootFrame.fills = [{ type: 'SOLID', color: hexToRgb(bgColor) }];
      page.appendChild(rootFrame);

      // Step 3: Recursively build all layers
      const imagesData = msg.imagesData || {};
      const rootSorted = layout.nodes.slice().sort(function(a, b) {
        const aIsText = a.type === 'text' ? 1 : 0;
        const bIsText = b.type === 'text' ? 1 : 0;
        return aIsText - bIsText;
      });
      for (const node of rootSorted) {
        await renderNodeSafely(node, rootFrame, 0, 0, imagesData, state);
      }

      // Step 4: Center frame in viewport and zoom to it
      figma.viewport.scrollAndZoomIntoView([rootFrame]);

      // Step 5: Final summary report
      let summaryText = '';
      if (state.skippedCount === 0) {
        summaryText = `Built ${state.builtCount} of ${state.totalNodes} layers`;
        figma.notify(`✅ ${summaryText}`);
      } else {
        const preview = state.skippedReasons.slice(0, 2).join('; ');
        summaryText = `Built ${state.builtCount} of ${state.totalNodes} layers, skipped ${state.skippedCount}: ${preview}`;
        figma.notify(`⚠️ ${summaryText}`, { timeout: 6000 });
      }

      figma.ui.postMessage({
        type: 'done',
        message: summaryText,
        built: state.builtCount,
        total: state.totalNodes,
        skipped: state.skippedCount,
        reasons: state.skippedReasons
      });

    } catch (fatalErr) {
      console.error('Fatal error during build:', fatalErr);
      figma.notify(`❌ Build failed: ${fatalErr.message}`);
      figma.ui.postMessage({ type: 'error', message: fatalErr.message });
    }
  }
};
