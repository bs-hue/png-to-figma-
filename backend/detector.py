"""
High-Fidelity Image Analysis Engine for PNG-to-Figma Converter.
- Prevents overlapping text with Spatial Non-Maximum Suppression (NMS).
- Line fragment stitching: seamlessly reassembles split words (e.g. Chan + ge -> Change).
- Section gradient protection: threshold >= 50 so sections are never sliced by gradients.
- Automatic Video Thumbnail extraction: black boxes with video graphics are exported as Images.
- Pure Image Asset Masking: excludes image regions from OCR to prevent double-text.
- Formats clean, readable typography with contrast-guaranteed text ink colors.
"""
import os
import re
import cv2
import json
import uuid
import time
import shutil
import numpy as np
import pytesseract
from pathlib import Path
from typing import Dict, List, Any, Tuple, Optional

# Ensure Tesseract OCR executable path is configured
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")
if TESSERACT_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
else:
    found_tess = shutil.which("tesseract")
    if found_tess:
        pytesseract.pytesseract.tesseract_cmd = found_tess

def rgb_to_hex(r: int, g: int, b: int) -> str:
    """Format RGB integers to #RRGGBB."""
    return f"#{max(0, min(255, int(r))):02x}{max(0, min(255, int(g))):02x}{max(0, min(255, int(b))):02x}"

def hex_to_rgb_tuple(hex_str: str) -> Tuple[int, int, int]:
    """Parse #RRGGBB to (r, g, b) tuple."""
    if not hex_str or not hex_str.startswith("#") or len(hex_str) < 7:
        return (255, 255, 255)
    try:
        return (int(hex_str[1:3], 16), int(hex_str[3:5], 16), int(hex_str[5:7], 16))
    except Exception:
        return (255, 255, 255)

def get_brightness(r: int, g: int, b: int) -> float:
    """ITU-R BT.601 perceived luminance."""
    return 0.299 * r + 0.587 * g + 0.114 * b

def detect_background_color(img: np.ndarray) -> str:
    """Dominant background color from page borders."""
    try:
        H, W = img.shape[:2]
        pad = max(1, min(30, W // 20, H // 20))
        borders = np.concatenate([
            img[0:pad, :].reshape(-1, 3),
            img[-pad:, :].reshape(-1, 3),
            img[:, 0:pad].reshape(-1, 3),
            img[:, -pad:].reshape(-1, 3)
        ])
        median_bgr = np.median(borders, axis=0).astype(int)
        return rgb_to_hex(int(median_bgr[2]), int(median_bgr[1]), int(median_bgr[0]))
    except Exception:
        return "#ffffff"

def get_text_ink_color(roi_bgr: np.ndarray, parent_bg_color: str = None) -> str:
    """
    Extracts text stroke ink color by separating characters from background.
    Guarantees that text is never colored the same as its background.
    """
    if roi_bgr is None or roi_bgr.size == 0 or roi_bgr.shape[0] < 3 or roi_bgr.shape[1] < 3:
        if parent_bg_color:
            pr, pg, pb = hex_to_rgb_tuple(parent_bg_color)
            return "#ffffff" if get_brightness(pr, pg, pb) < 130 else "#111827"
        return "#111827"

    gray = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2GRAY)
    _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    
    white_ratio = np.count_nonzero(thresh == 255) / float(thresh.size)
    if white_ratio > 0.5:
        # Background is white/light (255), text stroke is dark (0)
        stroke_pixels = roi_bgr[thresh == 0]
        bg_pixels = roi_bgr[thresh == 255]
    else:
        # Background is dark (0), text stroke is light (255)
        stroke_pixels = roi_bgr[thresh == 255]
        bg_pixels = roi_bgr[thresh == 0]

    bg_bright = np.mean(bg_pixels) if len(bg_pixels) > 0 else np.mean(gray)

    if len(stroke_pixels) < 4:
        if parent_bg_color:
            pr, pg, pb = hex_to_rgb_tuple(parent_bg_color)
            return "#ffffff" if get_brightness(pr, pg, pb) < 130 else "#111827"
        return "#ffffff" if bg_bright < 130 else "#111827"

    med = np.median(stroke_pixels, axis=0).astype(int)
    text_color = rgb_to_hex(med[2], med[1], med[0])
    
    # Contrast guarantee
    tr, tg, tb = int(med[2]), int(med[1]), int(med[0])
    text_bright = get_brightness(tr, tg, tb)
    
    if parent_bg_color:
        pr, pg, pb = hex_to_rgb_tuple(parent_bg_color)
        parent_bright = get_brightness(pr, pg, pb)
        if abs(parent_bright - text_bright) < 45:
            return "#ffffff" if parent_bright < 130 else "#111827"
    elif abs(bg_bright - text_bright) < 45:
        return "#ffffff" if bg_bright < 130 else "#111827"

    return text_color

def detect_sections(img: np.ndarray) -> List[Dict[str, Any]]:
    """
    Detects major horizontal full-width background sections of the page.
    Uses threshold >= 50 so subtle gradients within a section (like hero or about)
    do not slice components in half.
    """
    H, W = img.shape[:2]
    margin_w = min(40, max(10, W // 25))
    left_m = img[:, 0:margin_w]
    right_m = img[:, -margin_w:]
    margins = (left_m.mean(axis=1) + right_m.mean(axis=1)) / 2.0
    
    step = 24
    transitions = []
    prev_c = None
    
    for y in range(0, H, step):
        chunk = margins[y:min(H, y+step)]
        c = np.median(chunk, axis=0).astype(int)
        # Real section change threshold >= 50
        if prev_c is None or np.linalg.norm(c - prev_c) >= 50:
            transitions.append((y, c))
            prev_c = c
            
    sections = []
    for i in range(len(transitions)):
        y_start = transitions[i][0]
        y_end = transitions[i+1][0] if i + 1 < len(transitions) else H
        c = transitions[i][1]
        
        # Merge if smaller than 240px to keep components intact
        if sections and (y_end - y_start < 240):
            sections[-1]['h'] += (y_end - y_start)
            continue
            
        hex_c = rgb_to_hex(c[2], c[1], c[0])
        sections.append({
            "id": f"section_{len(sections)+1}",
            "type": "frame",
            "name": f"Section {len(sections)+1} ({W}x{y_end - y_start})",
            "x": 0,
            "y": y_start,
            "w": W,
            "h": y_end - y_start,
            "fill": hex_c,
            "radius": 0,
            "children": []
        })
        
    return sections

def detect_image_assets(
    img: np.ndarray,
    job_id: str,
    images_dir: Path
) -> Tuple[List[Dict[str, Any]], np.ndarray]:
    """
    Detects genuine visual assets (Photos, Screenshots, 3D Mockups, Illustration Collages).
    Saves each as a clean PNG image file and creates an image_mask so OCR will NOT
    extract text inside these images (eliminating double/overlapping text!).
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    blurred = cv2.GaussianBlur(gray, (15, 15), 0)
    edges = cv2.Canny(blurred, 25, 80)
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (25, 25))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    
    cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    image_assets = []
    image_mask = np.zeros((H, W), dtype=np.uint8)
    image_idx = 1
    
    for c in cnts:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if w >= 140 and h >= 120 and area >= 28000 and (w < W * 0.98 or h < 1100):
            roi = img[y:y+h, x:x+w]
            med = np.median(roi, axis=(0,1))
            diff = np.linalg.norm(roi - med, axis=2)
            flat_bg = np.mean(diff < 22)
            std_dev = np.std(roi)
            
            # Genuine visual image has low flat_bg (< 0.38) and high texture variance (std_dev > 38)
            # OR is a large testimonial screenshot row (e.g. WhatsApp screenshots: h > 120, std > 75, flat_bg < 0.60)
            is_visual = (flat_bg < 0.38 and std_dev > 38) or (std_dev > 75 and h > 120 and flat_bg < 0.60)
            
            if is_visual:
                img_filename = f"visual_{image_idx}.png"
                img_path = images_dir / img_filename
                cv2.imwrite(str(img_path), roi)
                
                img_url = f"/jobs/{job_id}/images/{img_filename}"
                image_assets.append({
                    "id": f"img_{image_idx}",
                    "type": "image",
                    "name": f"Visual Image ({w}x{h})",
                    "x": int(x),
                    "y": int(y),
                    "w": int(w),
                    "h": int(h),
                    "fill": None,
                    "radius": 8 if (w < 500 and h < 500) else 0,
                    "stroke": None,
                    "strokeWidth": 0,
                    "text": None,
                    "fontSize": None,
                    "color": None,
                    "imageUrl": img_url,
                    "children": []
                })
                # Mask out this area so OCR text will not extract duplicate text inside it!
                image_mask[y:y+h, x:x+w] = 255
                image_idx += 1
                
    image_assets.sort(key=lambda b: b['y'])
    return image_assets, image_mask

def box_overlap(b1: Dict[str, Any], b2: Dict[str, Any]) -> float:
    """Intersection over Minimum Area (IoMin) to detect containment/heavy overlap."""
    x1 = max(b1['x'], b2['x'])
    y1 = max(b1['y'], b2['y'])
    x2 = min(b1['x'] + b1['w'], b2['x'] + b2['w'])
    y2 = min(b1['y'] + b1['h'], b2['y'] + b2['h'])
    
    iw = max(0, x2 - x1)
    ih = max(0, y2 - y1)
    inter_area = iw * ih
    if inter_area == 0:
        return 0.0
        
    area1 = b1['w'] * b1['h']
    area2 = b2['w'] * b2['h']
    min_area = min(area1, area2)
    return inter_area / float(min_area)

def suppress_overlapping_texts(texts: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Non-Maximum Suppression (NMS) for text:
    Removes duplicate and overlapping text lines caused by multi-strip OCR or partial matches.
    Prioritizes longer, more complete text phrases.
    """
    sorted_texts = sorted(texts, key=lambda t: len(t.get('text', '')), reverse=True)
    kept = []
    
    for t in sorted_texts:
        collides = False
        for k in kept:
            # Check 2D bounding box overlap
            if box_overlap(t, k) > 0.25:
                collides = True
                break
            # Check vertical collision on same horizontal column
            y_diff = abs(t['y'] - k['y'])
            min_h = min(t['h'], k['h'])
            if y_diff < min_h * 0.70:
                x_overlap = max(0, min(t['x'] + t['w'], k['x'] + k['w']) - max(t['x'], k['x']))
                if x_overlap > 15:
                    collides = True
                    break
            # Vertical containment check: prevents line from starting inside another line
            if t['y'] < k['y'] + k['h'] * 0.85 and t['y'] + t['h'] > k['y'] + k['h'] * 0.15:
                x_overlap = max(0, min(t['x'] + t['w'], k['x'] + k['w']) - max(t['x'], k['x']))
                if x_overlap > min(t['w'], k['w']) * 0.40:
                    collides = True
                    break
        if not collides:
            kept.append(t)
            
    kept.sort(key=lambda t: (t['y'], t['x']))
    return kept

def clean_ocr_text(t: str) -> str:
    """Cleans common OCR noise, fixes currency symbols, apostrophes, and icon artifacts."""
    if not t:
        return ""
    t = t.replace('\ufffd', "'")
    t = t.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    t = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', t)
    
    # Fix apostrophes wrongly split by spaces (e.g. "INDIA ' S" or "doesn ' t")
    t = re.sub(r"(\w)\s*'\s*(\w)", r"\1'\2", t)
    
    # Rupee symbol: Tesseract reads ₹ as = or ? before numbers
    t = re.sub(r'^[=\?]\s*(\d)', r'₹\1', t)
    t = re.sub(r'\s+[=\?]\s*(\d)', r' ₹\1', t)
    
    # Common OCR bullet/icon artifacts at start (e.g. "2? ", "? ", "v ", "VY ", "@ ", "| ", "[8 ", "• ", "- ")
    t = re.sub(r'^(?:2\?|\?|VY|v|@|\||\[8|\u2022|\*|#)\s+', '', t)
    
    # Common button text corrections
    t = re.sub(r'\bi\'?l\'?l The Form\b', 'Fill The Form', t, flags=re.IGNORECASE)
    t = re.sub(r'\bill The Form\b', 'Fill The Form', t, flags=re.IGNORECASE)
    t = re.sub(r'\bLimited siots\b', 'Limited slots', t, flags=re.IGNORECASE)
    t = re.sub(r'\bLimited slots every wee\b', 'Limited slots every week', t, flags=re.IGNORECASE)
    t = re.sub(r'\bAfterthecall\b', 'After the call', t, flags=re.IGNORECASE)
    t = re.sub(r'\bAboutus\b', 'About Us', t, flags=re.IGNORECASE)
    
    # Trailing stray symbols or backslashes
    t = re.sub(r'[\s\\\|\-_=]+$', '', t)
    t = re.sub(r'^[~`\-_=\+\\\|\s]+', '', t)
    
    # Normalize multiple spaces
    t = re.sub(r'[ \t]+', ' ', t).strip()
    return t

def extract_text_nodes(img: np.ndarray, image_mask: np.ndarray = None, min_conf: int = 25) -> List[Dict[str, Any]]:
    """
    Extracts all lines and paragraphs of text outside image assets with:
    1. Native Tesseract layout hierarchy (block_num, par_num, line_num).
    2. Split-syllable stitching ONLY for short suffixes (e.g. Chan + ge -> Change),
       never merging whole words like 'Celebrating' and 'industry'.
    3. Column-aware splitting across large horizontal gaps.
    4. Paragraph-level multi-line grouping so Figma renders smooth native typography.
    5. Anti-Overlay Vertical Guarantee: mathematically prevents any two vertically adjacent
       text layers from colliding or drawing over each other.
    6. Contrast-guaranteed ink colors.
    """
    H, W = img.shape[:2]
    data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    n_boxes = len(data['text'])
    
    # 1. Group words by (block_num, par_num, line_num)
    lines_map: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
    for i in range(n_boxes):
        raw_w = str(data['text'][i]).strip()
        conf = int(data['conf'][i]) if str(data['conf'][i]).isdigit() else -1
        if not raw_w or conf < min_conf:
            continue
            
        bx = data['left'][i]
        by = data['top'][i]
        bw = data['width'][i]
        bh = data['height'][i]
        
        # Skip words inside detected image assets (like WhatsApp screenshots, photo mockups)
        cx = min(W - 1, max(0, bx + bw // 2))
        cy = min(H - 1, max(0, by + bh // 2))
        if image_mask is not None and image_mask[cy, cx] == 255:
            continue
            
        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])
        if key not in lines_map:
            lines_map[key] = []
        lines_map[key].append({
            'text': raw_w,
            'left': bx,
            'top': by,
            'width': bw,
            'height': bh,
            'conf': conf
        })

    # Sort lines by top coordinate
    sorted_line_keys = sorted(lines_map.keys(), key=lambda k: min(w['top'] for w in lines_map[k]))
    
    # 2. For each line, sort words left-to-right and stitch ONLY split syllables (<= 3 letters)
    stopwords = {'of', 'in', 'to', 'for', 'with', 'a', 'an', 'the', 'at', 'by', 'on', 'is', 'it', 'or', 'and'}
    segmented_lines = []
    
    for k in sorted_line_keys:
        words = lines_map[k]
        words.sort(key=lambda w: w['left'])
        
        # Stitch split syllables (e.g. "Chan" + "ge" -> "Change")
        # IMPORTANT: only fuse if w2 is a short suffix (<= 3 chars) to avoid merging separate words!
        idx = 0
        while idx < len(words) - 1:
            w1 = words[idx]
            w2 = words[idx + 1]
            gap = w2['left'] - (w1['left'] + w1['width'])
            
            should_fuse = False
            if -3 <= gap <= 7 and not w1['text'].endswith((' ', ',', '.', '?', '!', ':', ';')):
                if len(w2['text']) <= 3 and w2['text'].islower() and w2['text'].lower() not in stopwords:
                    should_fuse = True
                    
            if should_fuse:
                w1['text'] = w1['text'] + w2['text']
                w1['width'] = (w2['left'] + w2['width']) - w1['left']
                w1['height'] = max(w1['height'], w2['height'])
                w1['top'] = min(w1['top'], w2['top'])
                words.pop(idx + 1)
            else:
                idx += 1
                
        # 3. Split line across wide gaps (column/card separation, e.g. stats row or navbar links)
        segments = []
        current = [words[0]]
        for w in words[1:]:
            prev = current[-1]
            gap = w['left'] - (prev['left'] + prev['width'])
            min_h = min(prev['height'], w['height'])
            max_gap = max(30, int(min_h * 2.0))
            if gap > max_gap:
                segments.append(current)
                current = [w]
            else:
                current.append(w)
        if current:
            segments.append(current)
            
        for seg in segments:
            raw_joined = " ".join(w['text'] for w in seg)
            seg_text = clean_ocr_text(raw_joined)
            if not seg_text or len(seg_text) < 2:
                continue
            # Filter isolated non-alphanumeric punctuation
            if re.match(r'^[\W_]{1,3}$', seg_text):
                continue
                
            x_min = min(w['left'] for w in seg)
            y_min = min(w['top'] for w in seg)
            x_max = max(w['left'] + w['width'] for w in seg)
            y_max = max(w['top'] + w['height'] for w in seg)
            sw = max(4, x_max - x_min)
            sh = max(4, y_max - y_min)
            
            # Filter edge-clipped fragments
            if (x_min <= 6 and sw < 80) or (x_max >= W - 6 and sw < 80):
                continue
                
            font_size = max(11, int(sh * 0.78))
            font_weight = "bold" if (font_size >= 24 or sh >= 28) else ("medium" if (font_size >= 16 or sh >= 20) else "regular")
            
            segmented_lines.append({
                'block': k[0],
                'par': k[1],
                'line': k[2],
                'text': seg_text,
                'x': int(x_min),
                'y': int(y_min),
                'w': int(sw),
                'h': int(sh),
                'fontSize': font_size,
                'fontWeight': font_weight,
                'line_count': 1
            })

    # 4. Group consecutive lines within the same paragraph and column into multi-line text blocks
    grouped_nodes = []
    i = 0
    while i < len(segmented_lines):
        base = segmented_lines[i].copy()
        lines_in_block = [base['text']]
        j = i + 1
        
        while j < len(segmented_lines):
            nxt = segmented_lines[j]
            same_par = (nxt['block'] == base['block'] and nxt['par'] == base['par'])
            # Alignment: either start x is within 25px, or overlapping horizontally
            x_aligned = abs(nxt['x'] - base['x']) <= 25 or (max(nxt['x'], base['x']) < min(nxt['x'] + nxt['w'], base['x'] + base['w']))
            v_gap = nxt['y'] - (base['y'] + base['h'])
            font_match = max(base['fontSize'], nxt['fontSize']) / max(1, min(base['fontSize'], nxt['fontSize'])) <= 1.35
            
            if same_par and x_aligned and (-4 <= v_gap <= 24) and font_match:
                lines_in_block.append(nxt['text'])
                new_x = min(base['x'], nxt['x'])
                new_y = min(base['y'], nxt['y'])
                new_r = max(base['x'] + base['w'], nxt['x'] + nxt['w'])
                new_b = max(base['y'] + base['h'], nxt['y'] + nxt['h'])
                base['x'] = new_x
                base['y'] = new_y
                base['w'] = new_r - new_x
                base['h'] = new_b - new_y
                base['line_count'] += 1
                j += 1
            else:
                break
                
        base['text'] = "\n".join(lines_in_block)
        grouped_nodes.append(base)
        i = j

    # 5. Enforce Anti-Overlay Vertical Guarantee:
    # If two text blocks share the same horizontal column and overlap vertically,
    # adjust the lower one down so they never touch or collide!
    grouped_nodes.sort(key=lambda t: (t['y'], t['x']))
    for idx1 in range(len(grouped_nodes)):
        t1 = grouped_nodes[idx1]
        for idx2 in range(idx1 + 1, len(grouped_nodes)):
            t2 = grouped_nodes[idx2]
            col_overlap = max(0, min(t1['x'] + t1['w'], t2['x'] + t2['w']) - max(t1['x'], t2['x']))
            min_width = min(t1['w'], t2['w'])
            if col_overlap > 15 and col_overlap >= min_width * 0.30:
                line_h = int(t1['fontSize'] * 1.35)
                est_figma_h = max(t1['h'], t1['line_count'] * line_h)
                min_top = t1['y'] + est_figma_h + 4
                if t2['y'] < min_top:
                    t2['y'] = min_top

    # 6. Sample accurate contrast-guaranteed text ink colors
    final_nodes = []
    for idx, t in enumerate(grouped_nodes, 1):
        pad = 2
        ry1, ry2 = max(0, t['y'] - pad), min(H, t['y'] + t['h'] + pad)
        rx1, rx2 = max(0, t['x'] - pad), min(W, t['x'] + t['w'] + pad)
        roi = img[ry1:ry2, rx1:rx2]
        
        text_color = get_text_ink_color(roi)
        first_line = t['text'].split('\n')[0].strip()
        name_preview = first_line if len(first_line) <= 24 else f"{first_line[:24]}..."
        
        final_nodes.append({
            "id": f"text_{idx}",
            "type": "text",
            "name": f'"{name_preview}"',
            "x": int(t['x']),
            "y": int(t['y']),
            "w": int(t['w']),
            "h": int(t['h']),
            "fill": None,
            "radius": 0,
            "stroke": None,
            "strokeWidth": 0,
            "text": t['text'],
            "fontSize": t['fontSize'],
            "fontWeight": t['fontWeight'],
            "color": text_color,
            "imageUrl": None,
            "children": []
        })

    # Spatial NMS as safety net for any remaining edge-case duplicates
    clean_nodes = suppress_overlapping_texts(final_nodes)
    return clean_nodes

def detect_ui_components(
    img: np.ndarray,
    sections: List[Dict[str, Any]],
    image_mask: np.ndarray,
    image_assets: List[Dict[str, Any]],
    job_id: str,
    images_dir: Path
) -> List[Dict[str, Any]]:
    """
    Detects clean UI cards, buttons, badges, and form containers.
    If a component is near-black and has visual texture (like video player thumbnails),
    it is saved as a visual Image asset instead of creating a flat solid black box.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    shapes: List[Dict[str, Any]] = []
    shape_idx = 1
    
    for sec in sections:
        sy, sh = sec['y'], sec['h']
        if sh < 35:
            continue
            
        sec_img = img[sy:sy+sh, :]
        sec_gray = gray[sy:sy+sh, :]
        sec_bg_c = sec['fill']
        sec_bg_rgb = hex_to_rgb_tuple(sec_bg_c)
        sec_bg_bgr = np.array([sec_bg_rgb[2], sec_bg_rgb[1], sec_bg_rgb[0]])

        # Multi-scale edge detection catches both strong borders and subtle off-white cards
        edges = cv2.Canny(sec_gray, 12, 45)
        kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
        closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
        
        cnts, _ = cv2.findContours(closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        cnts = sorted(cnts, key=lambda c: cv2.contourArea(c), reverse=True)
        
        sec_shapes: List[Dict[str, Any]] = []
        for cnt in cnts:
            area = cv2.contourArea(cnt)
            if area < 1500 or area > (W * sh * 0.92):
                continue
                
            x, y, w, h = cv2.boundingRect(cnt)
            
            # Check overlap with existing image assets
            if image_mask is not None:
                cx = min(W - 1, max(0, x + w // 2))
                cy = min(H - 1, max(0, sy + y + h // 2))
                if image_mask[cy, cx] == 255:
                    continue
                    
            roi = sec_img[y:y+h, x:x+w]
            if roi.size == 0:
                continue
                
            std_dev = np.std(roi)
            inner_c = np.median(roi, axis=(0, 1)).astype(int)
            fill_hex = rgb_to_hex(inner_c[2], inner_c[1], inner_c[0])
            flat_bg = np.sum(np.all(np.abs(roi - inner_c) < 30, axis=2)) / (w * h)
            color_diff = np.linalg.norm(inner_c - sec_bg_bgr)

            # Video thumbnail detection: If shape has dark/black median but has graphic content (std_dev > 18)
            # save as an Image asset instead of a solid black box!
            if fill_hex in ["#000000", "#010101", "#020202", "#050505", "#0a0a0a", "#111111"] and std_dev > 18:
                next_idx = len(image_assets) + 1
                img_name = f"visual_{next_idx}.png"
                img_path = images_dir / img_name
                cv2.imwrite(str(img_path), roi)
                
                img_url = f"/jobs/{job_id}/images/{img_name}"
                image_assets.append({
                    "id": f"img_{next_idx}",
                    "type": "image",
                    "name": f"Video Thumbnail ({w}x{h})",
                    "x": int(x),
                    "y": int(sy + y),
                    "w": int(w),
                    "h": int(h),
                    "fill": None,
                    "radius": 8,
                    "stroke": None,
                    "strokeWidth": 0,
                    "text": None,
                    "fontSize": None,
                    "color": None,
                    "imageUrl": img_url,
                    "children": []
                })
                continue
                
            # Skip genuine photos (photos have low flat_bg and high std_dev)
            if flat_bg < 0.40 and std_dev > 38:
                continue
            
            # Distinguish UI components: Cards, Buttons, and Badges
            is_button = (36 <= h <= 88 and 160 <= w <= 550 and color_diff >= 35)
            is_card = (w >= 240 and h >= 55 and color_diff >= 8 and flat_bg >= 0.40)
            is_badge = (120 <= w <= 360 and 22 <= h <= 50 and color_diff >= 45)
            
            if not (is_button or is_card or is_badge):
                continue
                
            # Avoid duplicate overlapping shapes
            overlap = False
            for es in sec_shapes:
                if abs(x - es['x']) < 15 and abs(y - (es['y'] - sy)) < 15 and abs(w - es['w']) < 25 and abs(h - es['h']) < 25:
                    overlap = True
                    break
            if overlap:
                continue
                
            shape_name = "Button" if is_button else ("Card" if is_card else "Badge")
            radius = 8 if is_card else (14 if is_button else 16)
            
            sec_shapes.append({
                "id": f"shape_{shape_idx}",
                "type": "frame",
                "name": f"{shape_name} ({w}x{h})",
                "x": int(x),
                "y": int(sy + y),
                "w": int(w),
                "h": int(h),
                "fill": fill_hex,
                "radius": radius,
                "stroke": None,
                "strokeWidth": 0,
                "text": None,
                "fontSize": None,
                "color": None,
                "imageUrl": None,
                "children": []
            })
            shape_idx += 1
            
        shapes.extend(sec_shapes)
        
    return shapes

def is_inside(child: Dict[str, Any], parent: Dict[str, Any], tolerance: int = 6) -> bool:
    """Check if child node is geographically inside parent node."""
    cx = child['x'] + child['w'] / 2.0
    cy = child['y'] + child['h'] / 2.0
    
    px1 = parent['x'] - tolerance
    py1 = parent['y'] - tolerance
    px2 = parent['x'] + parent['w'] + tolerance
    py2 = parent['y'] + parent['h'] + tolerance
    
    return px1 <= cx <= px2 and py1 <= cy <= py2

def build_parent_child_hierarchy(
    sections: List[Dict[str, Any]],
    shapes: List[Dict[str, Any]],
    images: List[Dict[str, Any]],
    texts: List[Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Builds clean semantic hierarchy:
    1. Text inside a Button or Card is placed inside that component (button labeled with text).
    2. Shapes (Cards/Buttons) are placed inside their Section.
    3. Visual Images are placed inside their Section.
    4. Remaining Text is placed inside its Section.
    5. In each container, layers are sorted:
       Cards / Containers / Backgrounds FIRST ➔ Images ➔ TEXT ON TOP (highest z-index).
    """
    assigned_text_ids = set()
    assigned_shape_ids = set()
    assigned_image_ids = set()
    
    cards = [s for s in shapes if "Card" in s['name']]
    non_cards = [s for s in shapes if "Card" not in s['name']]
    
    # Place buttons/badges inside cards if geographically contained
    assigned_subshape_ids = set()
    for sub in non_cards:
        for card in cards:
            if is_inside(sub, card):
                card['children'].append(sub)
                assigned_subshape_ids.add(sub['id'])
                break
                
    # Place visual images inside cards if geographically contained
    for img_node in images:
        for card in cards:
            if is_inside(img_node, card):
                card['children'].append(img_node)
                assigned_image_ids.add(img_node['id'])
                break

    # Place text inside smallest containing shape (button first, then card)
    shapes_by_area = sorted(shapes, key=lambda s: s['w'] * s['h'])
    for t in texts:
        for s in shapes_by_area:
            if is_inside(t, s):
                s['children'].append(t)
                assigned_text_ids.add(t['id'])
                if "Button" in s['name'] and not s['name'].startswith("Button -"):
                    clean_lbl = t['text'][:20].strip()
                    s['name'] = f"Button - {clean_lbl}"
                break
                
    # Place root shapes inside sections
    for s in shapes:
        if s['id'] in assigned_subshape_ids:
            continue
        for sec in sections:
            if is_inside(s, sec):
                sec['children'].append(s)
                assigned_shape_ids.add(s['id'])
                break

    # Place remaining visual images inside sections
    for img_node in images:
        if img_node['id'] in assigned_image_ids:
            continue
        for sec in sections:
            if is_inside(img_node, sec):
                sec['children'].append(img_node)
                assigned_image_ids.add(img_node['id'])
                break

    # Place remaining text inside sections
    for t in texts:
        if t['id'] in assigned_text_ids:
            continue
        for sec in sections:
            if is_inside(t, sec):
                sec['children'].append(t)
                assigned_text_ids.add(t['id'])
                break

    # 5. Layer ordering:
    # 0 = Background shapes/cards, 1 = Images, 2 = Text nodes (at top!)
    def layer_order(child):
        ctype = child.get('type')
        if ctype == 'text':
            return (2, child.get('y', 0))
        elif ctype == 'image':
            return (1, child.get('y', 0))
        return (0, child.get('y', 0))

    for sec in sections:
        sec['children'].sort(key=layer_order)

    root_nodes = []
    for sec in sections:
        root_nodes.append(sec)
        
    for s in shapes:
        if s['id'] not in assigned_shape_ids and s['id'] not in assigned_subshape_ids:
            root_nodes.append(s)

    for img_node in images:
        if img_node['id'] not in assigned_image_ids:
            root_nodes.append(img_node)
            
    for t in texts:
        if t['id'] not in assigned_text_ids:
            root_nodes.append(t)
            
    root_nodes.sort(key=lambda n: (n['y'], n['x']))
    return root_nodes

def escape_xml(s: str) -> str:
    if not s:
        return ""
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;").replace("'", "&apos;")

def render_svg_nodes(nodes: List[Dict[str, Any]]) -> str:
    """Recursively converts node hierarchy to standard SVG elements."""
    svg_parts = []
    for node in nodes:
        ntype = node.get("type", "rectangle")
        x = node.get("x", 0)
        y = node.get("y", 0)
        w = max(1, node.get("w", 10))
        h = max(1, node.get("h", 10))
        nid = escape_xml(node.get("id", ""))
        nname = escape_xml(node.get("name", ""))
        fill = node.get("fill") or "none"
        radius = node.get("radius") or 0
        children = node.get("children", [])

        if ntype in ["frame", "rectangle"]:
            svg_parts.append(f'<g id="{nid}" data-name="{nname}">')
            if fill and fill != "none":
                rx_attr = f' rx="{radius}"' if radius > 0 else ''
                svg_parts.append(f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="{fill}"{rx_attr} />')
            if children:
                svg_parts.append(render_svg_nodes(children))
            svg_parts.append('</g>')

        elif ntype == "image":
            img_url = escape_xml(node.get("imageUrl", ""))
            rx_attr = f' rx="{radius}"' if radius > 0 else ''
            svg_parts.append(
                f'<g id="{nid}" data-name="{nname}">'
                f'  <rect x="{x}" y="{y}" width="{w}" height="{h}" fill="#f1f5f9"{rx_attr} />'
                f'  <image href="{img_url}" x="{x}" y="{y}" width="{w}" height="{h}" preserveAspectRatio="xMidYMid slice" />'
                f'</g>'
            )

        elif ntype == "text":
            text_str = escape_xml(node.get("text", ""))
            color = node.get("color", "#000000")
            font_size = node.get("fontSize", 14)
            font_weight = node.get("fontWeight", "regular")
            weight_val = "bold" if font_weight == "bold" else ("500" if font_weight == "medium" else "normal")
            text_y = y + int(font_size * 0.9)
            svg_parts.append(
                f'<text id="{nid}" data-name="{nname}" x="{x}" y="{text_y}" '
                f'font-family="Inter, sans-serif" font-size="{font_size}" font-weight="{weight_val}" '
                f'fill="{color}">{text_str}</text>'
            )

    return "\n".join(svg_parts)

def generate_figma_svg(layout_data: Dict[str, Any], doc_name: str = "Imported Page") -> str:
    """Generates standard SVG for layout."""
    w = layout_data.get("width", 1440)
    h = layout_data.get("height", 900)
    bg = layout_data.get("backgroundColor", "#ffffff")
    nodes = layout_data.get("nodes", [])

    svg_header = (
        f'<?xml version="1.0" encoding="UTF-8"?>\n'
        f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" '
        f'xmlns="http://www.w3.org/2000/svg">\n'
        f'<title>{escape_xml(doc_name)}</title>\n'
        f'<rect width="{w}" height="{h}" fill="{bg}" />\n'
    )
    svg_body = render_svg_nodes(nodes)
    svg_footer = "\n</svg>"
    return svg_header + svg_body + svg_footer

def generate_figma_script_nodes(nodes: List[Dict[str, Any]], parent_var: str, parent_abs_x: int = 0, parent_abs_y: int = 0) -> List[str]:
    """Generates Figma JavaScript code to build layers in Console with accurate relative coordinates."""
    lines = []
    for i, node in enumerate(nodes):
        ntype = node.get("type", "rectangle")
        x = node.get("x", 0)
        y = node.get("y", 0)
        w = max(1, node.get("w", 10))
        h = max(1, node.get("h", 10))
        rel_x = x - parent_abs_x
        rel_y = y - parent_abs_y
        name = str(node.get("name", "Layer")).replace("'", "\\'")
        fill = node.get("fill")
        radius = node.get("radius", 0)
        children = node.get("children", [])
        var_name = f"node_{node.get('id', f'n_{i}')}"

        if ntype == "frame" or children:
            lines.append(f"  const {var_name} = figma.createFrame();")
            lines.append(f"  {var_name}.name = '{name}';")
            lines.append(f"  {var_name}.resize({w}, {h});")
            lines.append(f"  {var_name}.clipsContent = false;")
            if radius > 0:
                lines.append(f"  {var_name}.cornerRadius = {radius};")
            if fill and fill != "none":
                r, g, b = hex_to_rgb_tuple(fill)
                lines.append(f"  {var_name}.fills = [{{ type: 'SOLID', color: {{ r: {r/255:.3f}, g: {g/255:.3f}, b: {b/255:.3f} }} }}];")
            else:
                lines.append(f"  {var_name}.fills = [];")
            lines.append(f"  {parent_var}.appendChild({var_name});")
            lines.append(f"  {var_name}.x = {rel_x}; {var_name}.y = {rel_y};")
            if children:
                lines.extend(generate_figma_script_nodes(children, var_name, x, y))

        elif ntype == "text":
            text_str = str(node.get("text", "")).replace("'", "\\'").replace("\n", "\\n")
            font_size = node.get("fontSize", 14)
            color = node.get("color", "#000000")
            r, g, b = hex_to_rgb_tuple(color)
            line_height = int(font_size * 1.35)
            has_line_breaks = "\\n" in text_str
            is_long = len(text_str) > 40 and w > 120

            lines.append(f"  const {var_name} = figma.createText();")
            lines.append(f"  {var_name}.name = '{name}';")
            lines.append(f"  {var_name}.characters = '{text_str}';")
            lines.append(f"  {var_name}.fontSize = {font_size};")
            lines.append(f"  {var_name}.lineHeight = {{ value: {line_height}, unit: 'PIXELS' }};")
            if has_line_breaks or is_long:
                lines.append(f"  {var_name}.resize({w}, {var_name}.height);")
                lines.append(f"  {var_name}.textAutoResize = 'HEIGHT';")
            else:
                lines.append(f"  {var_name}.textAutoResize = 'WIDTH_AND_HEIGHT';")
            lines.append(f"  {var_name}.fills = [{{ type: 'SOLID', color: {{ r: {r/255:.3f}, g: {g/255:.3f}, b: {b/255:.3f} }} }}];")
            lines.append(f"  {parent_var}.appendChild({var_name});")
            lines.append(f"  {var_name}.x = {rel_x}; {var_name}.y = {rel_y};")

        elif ntype == "image":
            lines.append(f"  const {var_name} = figma.createRectangle();")
            lines.append(f"  {var_name}.name = '{name}';")
            lines.append(f"  {var_name}.resize({w}, {h});")
            if radius > 0:
                lines.append(f"  {var_name}.cornerRadius = {radius};")
            lines.append(f"  {var_name}.fills = [{{ type: 'SOLID', color: {{ r: 0.92, g: 0.94, b: 0.96 }} }}];")
            lines.append(f"  {parent_var}.appendChild({var_name});")
            lines.append(f"  {var_name}.x = {rel_x}; {var_name}.y = {rel_y};")

        else:
            lines.append(f"  const {var_name} = figma.createRectangle();")
            lines.append(f"  {var_name}.name = '{name}';")
            lines.append(f"  {var_name}.resize({w}, {h});")
            if radius > 0:
                lines.append(f"  {var_name}.cornerRadius = {radius};")
            if fill and fill != "none":
                r, g, b = hex_to_rgb_tuple(fill)
                lines.append(f"  {var_name}.fills = [{{ type: 'SOLID', color: {{ r: {r/255:.3f}, g: {g/255:.3f}, b: {b/255:.3f} }} }}];")
            else:
                lines.append(f"  {var_name}.fills = [];")
            lines.append(f"  {parent_var}.appendChild({var_name});")
            lines.append(f"  {var_name}.x = {rel_x}; {var_name}.y = {rel_y};")

    return lines

def generate_figma_console_script(layout_data: Dict[str, Any], doc_name: str = "Imported Page") -> str:
    """Generates 1-click JavaScript code to paste into Figma Console."""
    w = layout_data.get("width", 1440)
    h = layout_data.get("height", 900)
    safe_name = str(doc_name).replace("'", "\\'")

    header = [
        "// ===================================================================",
        "// 1-Click PNG to Figma Importer Script",
        "// How to run: In Figma, open Console (Plugins -> Development -> Open Console)",
        "// Paste this code and hit Enter!",
        "// ===================================================================",
        "(async () => {",
        "  figma.notify('Starting PNG to Figma import...');",
        "  await figma.loadFontAsync({ family: 'Inter', style: 'Regular' });",
        "  const page = figma.currentPage;",
        "  const rootFrame = figma.createFrame();",
        f"  rootFrame.name = '{safe_name}';",
        f"  rootFrame.resize({w}, {h});",
        "  rootFrame.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 } }];",
        "  page.appendChild(rootFrame);"
    ]

    body = generate_figma_script_nodes(layout_data.get("nodes", []), "rootFrame")

    footer = [
        "  figma.viewport.scrollAndZoomIntoView([rootFrame]);",
        "  figma.notify('✅ PNG converted to Figma layers successfully!');",
        "})();"
    ]

    return "\n".join(header + body + footer)

def process_image(
    image_path: str,
    original_filename: str,
    job_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main detection pipeline.
    Produces high-fidelity layout.json, layout.svg, and figma_script.js.
    """
    if not job_id:
        job_id = uuid.uuid4().hex[:6]
        
    start_time = time.time()
    
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Unable to read image at {image_path}")
        
    H, W = img.shape[:2]
    
    base_job_dir = Path(__file__).resolve().parent / "jobs" / job_id
    images_dir = base_job_dir / "images"
    images_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Page background color
    bg_color = detect_background_color(img)

    # Save original image
    ext = Path(original_filename).suffix or ".png"
    orig_save_path = base_job_dir / f"original{ext}"
    cv2.imwrite(str(orig_save_path), img)
    
    # 2. Detect genuine image assets (photos, screenshots, 3D mockups)
    # and create image_mask to exclude them from text OCR
    image_nodes, image_mask = detect_image_assets(img, job_id, images_dir)
    
    # 3. Horizontal background sections (gradient protected threshold >= 50)
    sections = detect_sections(img)
    
    # 4. Extract text nodes outside image assets with line fragment stitching & Spatial NMS
    text_nodes = extract_text_nodes(img, image_mask, min_conf=25)
    
    # 5. Detect clean UI Components (Cards, Buttons, Video Player Thumbnails)
    shapes = detect_ui_components(img, sections, image_mask, image_nodes, job_id, images_dir)
    
    # 6. Build clean semantic hierarchy
    hierarchical_nodes = build_parent_child_hierarchy(sections, shapes, image_nodes, text_nodes)
    
    # 7. Construct layout.json structure
    layout_data = {
        "job_id": job_id,
        "filename": original_filename,
        "width": int(W),
        "height": int(H),
        "backgroundColor": bg_color,
        "nodes": hierarchical_nodes
    }
    
    layout_file = base_job_dir / "layout.json"
    with open(layout_file, "w", encoding="utf-8") as f:
        json.dump(layout_data, f, indent=2)

    # 8. Generate SVG
    svg_content = generate_figma_svg(layout_data, doc_name=Path(original_filename).stem)
    svg_file = base_job_dir / "layout.svg"
    with open(svg_file, "w", encoding="utf-8") as f:
        f.write(svg_content)

    # 9. Generate 1-click Figma script
    figma_script = generate_figma_console_script(layout_data, doc_name=Path(original_filename).stem)
    script_file = base_job_dir / "figma_script.js"
    with open(script_file, "w", encoding="utf-8") as f:
        f.write(figma_script)
        
    duration = round(time.time() - start_time, 2)
    
    counts = {
        "text": len(text_nodes),
        "shapes": len(sections) + len(shapes),
        "images": len(image_nodes),
        "total": len(text_nodes) + len(sections) + len(shapes) + len(image_nodes)
    }
    
    meta = {
        "job_id": job_id,
        "filename": original_filename,
        "width": W,
        "height": H,
        "backgroundColor": bg_color,
        "counts": counts,
        "duration_seconds": duration,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "original_image_url": f"/jobs/{job_id}/original{ext}",
        "svg_url": f"/job/{job_id}/svg",
        "script_url": f"/job/{job_id}/script",
        "texts": text_nodes,
        "shapes": sections + shapes,
        "images": image_nodes,
        "layout": layout_data
    }
    
    with open(base_job_dir / "meta.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, indent=2)
        
    return meta
