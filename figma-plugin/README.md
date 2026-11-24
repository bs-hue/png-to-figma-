# 🎨 PNG to Figma — BloomX Plugin

Yeh plugin **PNG/JPG images** ko Figma ke andar fully editable native layers (Frames, Shapes, Text, Images) mein convert karta hai.

---

## 🚀 Quick Start Guide (Hinglish)

### 1. Backend Server Run Karein
Pehle terminal mein backend chalayein:
```bash
cd "e:\Antigravity project\png2figma"
.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000
```
Health check: [http://localhost:8000/health](http://localhost:8000/health)

### 2. Figma Desktop App Mein Plugin Load Karein
1. **Figma Desktop App** open karein.
2. Menu click karein: **Plugins** ➔ **Development** ➔ **Import plugin from manifest...**
3. Select karein: `figma-plugin/manifest.json`

### 3. Use Kaise Karein
- **Option A:** "Upload PNG" tab mein image drag-drop karein aur "Convert & Build Layers" par click karein.
- **Option B:** "Paste Job ID" tab mein dashboard ka Job ID (jaise `1f820f`) daalein aur "Fetch Job & Build" par click karein.

### 4. Figma Console Kholna (Errors Dekhne Ke Liye)
- Menu: **Plugins** ➔ **Development** ➔ **Open Console**
- Shortcut: `Ctrl + Shift + I` (Windows) ya `Cmd + Option + I` (Mac)
