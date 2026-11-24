"""
Core Engine: Image to Figma converter using OpenCV and Tesseract OCR.
Offline, CPU-only, no cloud API required.
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
from PIL import Image
from pathlib import Path
from typing import Dict, List, Any, Tuple

# Import our configuration to ensure Tesseract path is set
import config

def rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"

def sample_region_color(img: np.ndarray, x: int, y: int, w: int, h: int) -> Tuple[int, int, int]:
    """Sample the representative median color in a bounding box."""
    H, W = img.shape[:2]
    x1, y1 = max(0, x), max(0, y)
    x2, y2 = min(W, x + w), min(H, y + h)
    
    if x2 <= x1 or y2 <= y1:
        return (255, 255, 255)
        
    roi = img[y1:y2, x1:x2]
    # Sample center if region is large to avoid boundary noise
    margin_x = int(w * 0.15)
    margin_y = int(h * 0.15)
    if w > 20 and h > 20 and (w - 2 * margin_x > 5) and (h - 2 * margin_y > 5):
        inner_roi = roi[margin_y:h-margin_y, margin_x:w-margin_x]
        if inner_roi.size > 0:
            roi = inner_roi

    # Compute median color in BGR then convert to RGB
    median_bgr = np.median(roi.reshape(-1, 3), axis=0).astype(int)
    return (int(median_bgr[2]), int(median_bgr[1]), int(median_bgr[0]))

def clean_text_str(s: str) -> str:
    if not s:
        return ""
    s = s.replace('\ufffd', "'")
    s = s.replace('‘', "'").replace('’', "'").replace('“', '"').replace('”', '"')
    s = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]', '', s)
    s = re.sub(r"(\w)\s*'\s*(\w)", r"\1'\2", s)
    s = re.sub(r'^[=\?]\s*(\d)', r'₹\1', s)
    s = re.sub(r'\s+[=\?]\s*(\d)', r' ₹\1', s)
    s = re.sub(r'^(?:2\?|\?|VY|v|@|\||\[8|\u2022|\*|#)\s+', '', s)
    s = re.sub(r'[\s\\\|\-_=]+$', '', s)
    s = re.sub(r'^[~`\-_=\+\\\|\s]+', '', s)
    s = re.sub(r'[ \t]+', ' ', s).strip()
    return s

def group_words_to_lines(ocr_data: Dict[str, list], min_conf: int = 25) -> List[Dict[str, Any]]:
    """
    Groups OCR word bounding boxes into coherent lines of text
    based on block_num, par_num, and line_num with column splitting
    and anti-collision guarantee.
    """
    n_boxes = len(ocr_data['text'])
    line_groups: Dict[Tuple[int, int, int], List[Dict[str, Any]]] = {}
    
    for i in range(n_boxes):
        text = str(ocr_data['text'][i]).strip()
        conf = int(ocr_data['conf'][i]) if str(ocr_data['conf'][i]).isdigit() else -1
        
        if not text or conf < min_conf:
            continue
            
        key = (ocr_data['block_num'][i], ocr_data['par_num'][i], ocr_data['line_num'][i])
        if key not in line_groups:
            line_groups[key] = []
        line_groups[key].append({
            'text': text,
            'left': ocr_data['left'][i],
            'top': ocr_data['top'][i],
            'width': ocr_data['width'][i],
            'height': ocr_data['height'][i],
            'conf': conf
        })
        
    sorted_keys = sorted(line_groups.keys(), key=lambda k: min(w['top'] for w in line_groups[k]))
    stopwords = {'of', 'in', 'to', 'for', 'with', 'a', 'an', 'the', 'at', 'by', 'on', 'is', 'it', 'or', 'and'}
    segmented_lines = []
    
    for key in sorted_keys:
        words = line_groups[key]
        words.sort(key=lambda w: w['left'])
        
        # Stitch split syllables (e.g. "Chan" + "ge" -> "Change")
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
                
        # Split across wide column gaps
        segments = []
        current = [words[0]]
        for w in words[1:]:
            prev = current[-1]
            gap = w['left'] - (prev['left'] + prev['width'])
            min_h = min(prev['height'], w['height'])
            if gap > max(30, int(min_h * 2.0)):
                segments.append(current)
                current = [w]
            else:
                current.append(w)
        if current:
            segments.append(current)
            
        for seg in segments:
            clean_t = clean_text_str(" ".join(w['text'] for w in seg))
            if not clean_t or len(clean_t) < 2 or re.match(r'^[\W_]{1,3}$', clean_t):
                continue
            x_min = min(w['left'] for w in seg)
            y_min = min(w['top'] for w in seg)
            x_max = max(w['left'] + w['width'] for w in seg)
            y_max = max(w['top'] + w['height'] for w in seg)
            sw = max(4, x_max - x_min)
            sh = max(4, y_max - y_min)
            font_size = max(11, int(sh * 0.78))
            avg_conf = sum(w['conf'] for w in seg) / len(seg)
            
            segmented_lines.append({
                'block': key[0],
                'par': key[1],
                'text': clean_t,
                'x': int(x_min),
                'y': int(y_min),
                'w': int(sw),
                'h': int(sh),
                'fontSize': font_size,
                'confidence': round(avg_conf, 1),
                'line_count': 1
            })

    # Group paragraph lines
    grouped = []
    i = 0
    while i < len(segmented_lines):
        base = segmented_lines[i].copy()
        lines = [base['text']]
        j = i + 1
        while j < len(segmented_lines):
            nxt = segmented_lines[j]
            same_par = (nxt['block'] == base['block'] and nxt['par'] == base['par'])
            x_aligned = abs(nxt['x'] - base['x']) <= 25 or (max(nxt['x'], base['x']) < min(nxt['x'] + nxt['w'], base['x'] + base['w']))
            v_gap = nxt['y'] - (base['y'] + base['h'])
            font_match = max(base['fontSize'], nxt['fontSize']) / max(1, min(base['fontSize'], nxt['fontSize'])) <= 1.35
            if same_par and x_aligned and (-4 <= v_gap <= 24) and font_match:
                lines.append(nxt['text'])
                nx = min(base['x'], nxt['x'])
                ny = min(base['y'], nxt['y'])
                nr = max(base['x'] + base['w'], nxt['x'] + nxt['w'])
                nb = max(base['y'] + base['h'], nxt['y'] + nxt['h'])
                base['x'] = nx
                base['y'] = ny
                base['w'] = nr - nx
                base['h'] = nb - ny
                base['line_count'] += 1
                j += 1
            else:
                break
        base['text'] = "\n".join(lines)
        grouped.append(base)
        i = j

    # Enforce vertical non-collision
    grouped.sort(key=lambda t: (t['y'], t['x']))
    for idx1 in range(len(grouped)):
        t1 = grouped[idx1]
        for idx2 in range(idx1 + 1, len(grouped)):
            t2 = grouped[idx2]
            col_ol = max(0, min(t1['x'] + t1['w'], t2['x'] + t2['w']) - max(t1['x'], t2['x']))
            if col_ol > 15 and col_ol >= min(t1['w'], t2['w']) * 0.3:
                line_h = int(t1['fontSize'] * 1.35)
                est_h = max(t1['h'], t1['line_count'] * line_h)
                min_top = t1['y'] + est_h + 4
                if t2['y'] < min_top:
                    t2['y'] = min_top

    text_elements: List[Dict[str, Any]] = []
    for text_idx, item in enumerate(grouped, 1):
        first_line = item['text'].split('\n')[0].strip()
        preview = first_line[:24] + "..." if len(first_line) > 24 else first_line
        text_elements.append({
            "id": f"text_{text_idx}",
            "type": "TEXT",
            "name": f'Text - "{preview}"',
            "text": item['text'],
            "x": item['x'],
            "y": item['y'],
            "width": item['w'],
            "height": item['h'],
            "fontSize": item['fontSize'],
            "confidence": item['confidence'],
            "color": "#111827",
            "rgba": [17, 24, 39, 1.0]
        })
        
    return text_elements

def detect_shapes_and_containers(img: np.ndarray, text_boxes: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
    """
    Detects rectangular shapes (buttons, cards, banners, containers) and images/icons
    using OpenCV contour detection and edge variance analysis.
    """
    H, W = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    
    # Create mask to blank out detected text so text strokes don't break container contours
    clean_gray = gray.copy()
    for tb in text_boxes:
        tx, ty, tw, th = tb['x'], tb['y'], tb['width'], tb['height']
        pad = 2
        x1, y1 = max(0, tx - pad), max(0, ty - pad)
        x2, y2 = min(W, tx + tw + pad), min(H, ty + th + pad)
        # Fill with local median
        local_val = int(np.median(clean_gray[y1:y2, x1:x2])) if x2 > x1 and y2 > y1 else 255
        clean_gray[y1:y2, x1:x2] = local_val

    # Edge detection & thresholding
    edges = cv2.Canny(clean_gray, 40, 140)
    
    # Morphological close to bridge gaps in rounded corners and borders
    kernel = cv2.getStructuringElement(cv2.MORPH_RECT, (5, 5))
    closed = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel)
    
    contours, hierarchy = cv2.findContours(closed, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    
    shapes: List[Dict[str, Any]] = []
    images: List[Dict[str, Any]] = []
    
    min_area = 400  # min 20x20
    max_area = W * H * 0.98  # ignore full canvas boundary
    
    occupied_rects = []
    shape_idx = 1
    img_idx = 1
    
    # Sort contours by area descending so parent containers can be processed
    filtered_contours = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < min_area or area > max_area:
            continue
        filtered_contours.append((cnt, area))
        
    filtered_contours.sort(key=lambda x: x[1], reverse=True)
    
    for cnt, area in filtered_contours:
        x, y, w, h = cv2.boundingRect(cnt)
        
        # Check aspect ratio
        aspect = w / float(h)
        if aspect < 0.05 or aspect > 20:
            continue
            
        # Avoid duplicate near-identical rectangles
        is_duplicate = False
        for ox, oy, ow, oh in occupied_rects:
            if abs(x - ox) < 6 and abs(y - oy) < 6 and abs(w - ow) < 10 and abs(h - oh) < 10:
                is_duplicate = True
                break
        if is_duplicate:
            continue
            
        occupied_rects.append((x, y, w, h))
        
        # Analyze region texture to determine if it is a Shape (card/button) or an Image/Graphic
        roi_bgr = img[y:y+h, x:x+w]
        roi_hsv = cv2.cvtColor(roi_bgr, cv2.COLOR_BGR2HSV)
        
        # Compute color variance
        std_dev = np.std(roi_bgr)
        sat_mean = np.mean(roi_hsv[:, :, 1])
        
        # Sample representative fill color
        r, g, b = sample_region_color(img, x, y, w, h)
        hex_color = rgb_to_hex(r, g, b)
        
        # Check if region is an Image / Graphic:
        # High texture variance with complex colors, and not a standard button
        is_image = False
        if std_dev > 48 and sat_mean > 35 and (w > 60 and h > 60):
            # Check if it has lots of internal text
            inner_texts = [tb for tb in text_boxes if (
                tb['x'] >= x and tb['y'] >= y and
                tb['x'] + tb['width'] <= x + w and
                tb['y'] + tb['height'] <= y + h
            )]
            # If large variance but low text count, classify as Image / Illustration
            if len(inner_texts) <= 2:
                is_image = True
                
        if is_image:
            images.append({
                "id": f"img_{img_idx}",
                "type": "IMAGE",
                "name": f"Image - {w}x{h} ({'Photo' if w > 200 else 'Icon'})",
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "fillColor": hex_color,
                "rgba": [r, g, b, 1.0],
                "cornerRadius": 8 if (w < 200 and h < 200) else 0
            })
            img_idx += 1
        else:
            # Classify shape type
            shape_type_name = "Card"
            border_radius = 0
            if h <= 65 and w <= 320 and w > 40:
                shape_type_name = "Button"
                border_radius = min(8, int(h / 3))
            elif h <= 60 and w > 320:
                shape_type_name = "Bar / Banner"
            elif w > W * 0.7:
                shape_type_name = "Section Container"
            else:
                shape_type_name = "Container Card"
                border_radius = 8
                
            shapes.append({
                "id": f"shape_{shape_idx}",
                "type": "SHAPE",
                "subType": shape_type_name,
                "name": f"Shape - {shape_type_name} ({w}x{h})",
                "x": int(x),
                "y": int(y),
                "width": int(w),
                "height": int(h),
                "fillColor": hex_color,
                "rgba": [r, g, b, 1.0],
                "cornerRadius": border_radius
            })
            shape_idx += 1
            
    # Sample text colors accurately
    for tb in text_boxes:
        tr, tg, tb_col = sample_region_color(img, tb['x'], tb['y'], tb['width'], tb['height'])
        tb['color'] = rgb_to_hex(tr, tg, tb_col)
        tb['rgba'] = [tr, tg, tb_col, 1.0]
        
    return shapes, images

def build_figma_node_tree(
    image_width: int,
    image_height: int,
    texts: List[Dict[str, Any]],
    shapes: List[Dict[str, Any]],
    images: List[Dict[str, Any]],
    doc_name: str = "Converted Page"
) -> Dict[str, Any]:
    """
    Constructs a valid Figma JSON design tree with parent-child hierarchy.
    """
    # Root frame
    root_node = {
        "id": "0:1",
        "name": doc_name,
        "type": "FRAME",
        "blendMode": "PASS_THROUGH",
        "children": [],
        "absoluteBoundingBox": {
            "x": 0,
            "y": 0,
            "width": image_width,
            "height": image_height
        },
        "fills": [
            {
                "type": "SOLID",
                "visible": True,
                "opacity": 1,
                "blendMode": "NORMAL",
                "color": {"r": 1.0, "g": 1.0, "b": 1.0, "a": 1.0}
            }
        ],
        "clipsContent": True
    }
    
    # Sort shapes by area descending (larger containers act as parents)
    sorted_shapes = sorted(shapes, key=lambda s: s['width'] * s['height'], reverse=True)
    
    # Map elements to Figma nodes
    all_elements: List[Dict[str, Any]] = []
    
    for s in sorted_shapes:
        r, g, b, a = s['rgba']
        node = {
            "id": f"s_{s['id']}",
            "name": s['name'],
            "type": "FRAME" if "Container" in s['name'] or "Card" in s['name'] else "RECTANGLE",
            "x": s['x'],
            "y": s['y'],
            "width": s['width'],
            "height": s['height'],
            "cornerRadius": s.get('cornerRadius', 0),
            "fills": [
                {
                    "type": "SOLID",
                    "visible": True,
                    "opacity": 1,
                    "color": {"r": round(r/255.0, 3), "g": round(g/255.0, 3), "b": round(b/255.0, 3), "a": 1.0}
                }
            ],
            "children": []
        }
        all_elements.append(node)
        
    for img_el in images:
        r, g, b, a = img_el['rgba']
        node = {
            "id": f"i_{img_el['id']}",
            "name": img_el['name'],
            "type": "RECTANGLE",
            "x": img_el['x'],
            "y": img_el['y'],
            "width": img_el['width'],
            "height": img_el['height'],
            "cornerRadius": img_el.get('cornerRadius', 0),
            "fills": [
                {
                    "type": "IMAGE",
                    "visible": True,
                    "opacity": 1,
                    "scaleMode": "FILL"
                }
            ]
        }
        all_elements.append(node)
        
    for t in texts:
        r, g, b, a = t['rgba']
        node = {
            "id": f"t_{t['id']}",
            "name": t['name'],
            "type": "TEXT",
            "x": t['x'],
            "y": t['y'],
            "width": t['width'],
            "height": t['height'],
            "characters": t['text'],
            "style": {
                "fontFamily": "Inter",
                "fontSize": t['fontSize'],
                "fontWeight": 400,
                "textAlignHorizontal": "LEFT",
                "letterSpacing": 0,
                "lineHeightPx": int(t['height'])
            },
            "fills": [
                {
                    "type": "SOLID",
                    "visible": True,
                    "opacity": 1,
                    "color": {"r": round(r/255.0, 3), "g": round(g/255.0, 3), "b": round(b/255.0, 3), "a": 1.0}
                }
            ]
        }
        all_elements.append(node)
        
    root_node["children"] = all_elements
    
    return {
        "document": root_node,
        "name": doc_name,
        "schemaVersion": 0,
        "generator": "Offline-PNG2Figma-OpenCV-Tesseract"
    }

def generate_figma_plugin_script(figma_json: Dict[str, Any]) -> str:
    """
    Generates a 1-click JavaScript snippet that can be pasted directly into
    Figma's Dev Console or a Quick Plugin to recreate all nodes instantly.
    """
    doc = figma_json.get("document", {})
    width = doc.get("absoluteBoundingBox", {}).get("width", 1440)
    height = doc.get("absoluteBoundingBox", {}).get("height", 900)
    
    code_lines = [
        "// 1-Click Offline PNG-to-Figma Importer Script",
        "// Paste this snippet into Figma Console (Plugins -> Development -> Open Console)",
        "(async () => {",
        "  await figma.loadFontAsync({ family: 'Inter', style: 'Regular' });",
        "  const page = figma.currentPage;",
        f"  const rootFrame = figma.createFrame();",
        f"  rootFrame.name = '{doc.get('name', 'Imported PNG')}';",
        f"  rootFrame.resize({width}, {height});",
        "  rootFrame.fills = [{ type: 'SOLID', color: { r: 1, g: 1, b: 1 } }];",
        "  page.appendChild(rootFrame);",
        "  figma.viewport.scrollAndZoomIntoView([rootFrame]);",
        ""
    ]
    
    for child in doc.get("children", []):
        ctype = child.get("type")
        x = child.get("x", 0)
        y = child.get("y", 0)
        w = max(1, child.get("width", 10))
        h = max(1, child.get("height", 10))
        name = child.get("name", "").replace("'", "\\'")
        
        fills = child.get("fills", [{}])
        first_fill = fills[0] if fills else {}
        color = first_fill.get("color", {"r": 0.5, "g": 0.5, "b": 0.5})
        cr, cg, cb = color.get("r", 0.5), color.get("g", 0.5), color.get("b", 0.5)
        
        if ctype == "TEXT":
            chars = child.get("characters", "").replace("'", "\\'").replace("\n", "\\n")
            fsize = child.get("style", {}).get("fontSize", 16)
            line_h = int(fsize * 1.35)
            has_line_breaks = "\\n" in chars
            is_long = len(chars) > 40 and w > 120
            code_lines.extend([
                "  {",
                "    const t = figma.createText();",
                f"    t.name = '{name}';",
                f"    t.characters = '{chars}';",
                f"    t.fontSize = {fsize};",
                f"    t.lineHeight = {{ value: {line_h}, unit: 'PIXELS' }};",
                f"    {'t.resize(' + str(w) + ', t.height); t.textAutoResize = \\'HEIGHT\\';' if (has_line_breaks or is_long) else 't.textAutoResize = \\'WIDTH_AND_HEIGHT\\';'}",
                f"    t.fills = [{{ type: 'SOLID', color: {{ r: {cr}, g: {cg}, b: {cb} }} }}];",
                "    rootFrame.appendChild(t);",
                f"    t.x = {x}; t.y = {y};",
                "  }"
            ])
        else:
            radius = child.get("cornerRadius", 0)
            code_lines.extend([
                "  {",
                "    const r = figma.createRectangle();",
                f"    r.name = '{name}';",
                f"    r.resize({w}, {h});",
                f"    r.cornerRadius = {radius};",
                f"    r.fills = [{{ type: 'SOLID', color: {{ r: {cr}, g: {cg}, b: {cb} }} }}];",
                "    rootFrame.appendChild(r);",
                f"    r.x = {x}; r.y = {y};",
                "  }"
            ])
            
    code_lines.extend([
        "",
        "  figma.notify('PNG imported into Figma successfully!');",
        "})();"
    ])
    
    return "\n".join(code_lines)

def process_image_file(image_path: str, filename: str) -> Dict[str, Any]:
    """
    Full pipeline: runs OCR and OpenCV on the target image and produces
    structured conversion output with counts, elements, Figma JSON, and script.
    """
    job_id = uuid.uuid4().hex[:6]
    start_time = time.time()
    
    img = cv2.imread(image_path)
    if img is None:
        raise ValueError(f"Could not read image file at {image_path}")
        
    H, W = img.shape[:2]
    
    # 1. Tesseract OCR for text
    ocr_data = pytesseract.image_to_data(img, output_type=pytesseract.Output.DICT)
    texts = group_words_to_lines(ocr_data, min_conf=35)
    
    # 2. OpenCV for shapes and images
    shapes, images = detect_shapes_and_containers(img, texts)
    
    # 3. Build Figma JSON
    figma_json = build_figma_node_tree(W, H, texts, shapes, images, doc_name=Path(filename).stem)
    
    # 4. Generate Figma Plugin script
    plugin_script = generate_figma_plugin_script(figma_json)
    
    # 5. Combined elements list for UI
    all_elements_list = []
    for t in texts:
        all_elements_list.append({
            "id": t["id"],
            "category": "text",
            "name": t["name"],
            "detail": t["text"],
            "x": t["x"], "y": t["y"], "width": t["width"], "height": t["height"],
            "color": t["color"],
            "tag": f"Text ({t['fontSize']}px)"
        })
    for s in shapes:
        all_elements_list.append({
            "id": s["id"],
            "category": "shape",
            "name": s["name"],
            "detail": s["subType"],
            "x": s["x"], "y": s["y"], "width": s["width"], "height": s["height"],
            "color": s["fillColor"],
            "tag": s["subType"]
        })
    for im in images:
        all_elements_list.append({
            "id": im["id"],
            "category": "image",
            "name": im["name"],
            "detail": f"{im['width']}x{im['height']} Graphic",
            "x": im["x"], "y": im["y"], "width": im["width"], "height": im["height"],
            "color": im["fillColor"],
            "tag": "Graphic"
        })
        
    # Sort elements by Y coordinate (top to bottom reading order)
    all_elements_list.sort(key=lambda e: (e['y'], e['x']))
    
    duration = round(time.time() - start_time, 2)
    
    result = {
        "job_id": job_id,
        "filename": filename,
        "dimensions": {"width": W, "height": H},
        "counts": {
            "text": len(texts),
            "shapes": len(shapes),
            "images": len(images),
            "total": len(texts) + len(shapes) + len(images)
        },
        "texts": texts,
        "shapes": shapes,
        "images": images,
        "elements": all_elements_list,
        "figma_json": figma_json,
        "plugin_script": plugin_script,
        "duration_seconds": duration,
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S")
    }
    
    return result
