# 🎨 PNG to Figma — BloomX Plugin Guide

Yeh guide simple **Hinglish** mein likhi gayi hai taaki non-coders bhi bina kisi pareshani ke Figma Plugin ko setup aur use kar sakein.

---

## ⚡ Step 1: Backend Server Start Karein (Pehle yeh zaroori hai)

Figma plugin ko chalane ke liye aapka local Python backend running hona chahiye:

1. Apne computer par terminal ya command prompt open karein project folder mein:
   ```bash
   cd "e:\Antigravity project\png2figma"
   ```
2. Virtual environment activate karein aur server start karein:
   ```bash
   .venv\Scripts\python.exe -m uvicorn backend.main:app --host 127.0.0.1 --port 8000
   ```
3. Browser mein open karke check kar sakte hain:
   👉 **http://localhost:8000/health** (Screen par "ok" dikhega)

---

## 🔌 Step 2: Figma Desktop App Mein Plugin Load Karein

> ⚠️ **Note:** Plugin load karne ke liye **Figma Desktop App** use karein (browser version mein local manifest load nahi hota).

1. **Figma Desktop App** open karein aur koi bhi design file (ya New Design File) kholein.
2. Left top menu par click karein:
   - **Menu Icon (Figma logo)** ➔ **Plugins** ➔ **Development** ➔ **Import plugin from manifest...**
   - *(Ya fir canvas par right click karein: **Plugins** ➔ **Development** ➔ **Import plugin from manifest...**)*
3. Ek file picker open hoga. Apne computer mein is path par jayein:
   ```
   e:\Antigravity project\png2figma\figma-plugin\manifest.json
   ```
4. `manifest.json` file ko select karke **Open** par click karein.
5. 🎉 Mubarak ho! Plugin successfully add ho gaya!

---

## 🚀 Step 3: Plugin Ko Use Kaise Karein

Plugin open karne ke liye:
- Figma menu mein jayein: **Plugins** ➔ **Development** ➔ **PNG to Figma — BloomX** par click karein.
- Plugin ka clean blue window open ho jayega.

Aapke paas **2 Options** hain:

### Option A: Direct PNG Upload Karein (Sabse aasan)
1. **"Upload PNG"** tab select karein.
2. Apni PNG/JPG image ko dropzone par drag-and-drop karein (ya click karke select karein).
3. **"Convert & Build Layers"** button par click karein.
4. Screen par live progress dikhega:
   - *"Uploading..."*
   - *"Reading image..."*
   - *"Building layers... 23/45"*
   - *"Done!"*
5. Figma canvas par aapka design center mein zoom hokar fully editable layers (Frames, Texts, Shapes, Images) ke saath ban jayega!

### Option B: Job ID Paste Karein
1. Agar aapne pehle se Dashboard (http://localhost:8000) par image convert ki hui hai, toh wahan se **Job ID** (jaise `1f820f` ya `e4c558`) copy karein.
2. Plugin mein **"Paste Job ID"** tab par jayein.
3. Box mein Job ID paste karein aur **"Fetch Job & Build"** par click karein.
4. Plugin server se layout aur cropped image assets lekar pure design ko Figma par recreate kar dega!

---

## 🔍 Step 4: Figma Console Kaise Kholein (Errors ya Logs Dekhne Ke Liye)

Agar kabhi koi error aaye ya aapko dekhna ho ki background mein kya chal raha hai:

1. **Figma Menu** par click karein:
   - **Plugins** ➔ **Development** ➔ **Open Console**
2. **Keyboard Shortcut:**
   - Windows: `Ctrl + Shift + I` (ya `Ctrl + Alt + I`)
   - Mac: `Cmd + Option + I`
3. Console tab mein aapko:
   - Font loading status
   - Skipped layers ki details (agar koi element skip hua ho)
   - Network calls aur errors
   sab clear dikhenge.

---

## 💡 Common Issues & Solutions (Pareshani Ka Hal)

| Problem | Wajah (Reason) | Solution |
| :--- | :--- | :--- |
| **"Backend is not running — start it first"** | Python server running nahi hai. | Terminal mein `.venv\Scripts\python.exe -m uvicorn backend.main:app --port 8000` run karein. |
| **"Invalid Job ID"** | Job ID galat type ki hai ya purani ho gayi hai. | Dashboard se correct 6-digit Job ID copy karein ya direct "Upload PNG" use karein. |
| **Text font alag dikh raha hai** | Inter font Figma mein default available hota hai. | Plugin automatically standard Inter (Regular, Medium, Bold) load kar leta hai. |
| **Layers editable hain?** | Haan, 100%! | Har text box par double-click karke aap text edit kar sakte hain, buttons aur colors change kar sakte hain. |

---

## 📁 Plugin Files Overview
- `figma-plugin/manifest.json` — Plugin config aur network permissions (`localhost:8000`).
- `figma-plugin/ui.html` — User interface window (BloomX brand colour `#33B6F7`, upload + Job ID tab).
- `figma-plugin/code.js` — Figma engine code jo parent-child layers, shapes, fonts, aur images build karta hai.
