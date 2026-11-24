"""
FastAPI Server for Offline PNG-to-Figma Converter.
Serves REST API and responsive frontend UI.
"""
import os
import json
import shutil
from pathlib import Path
from typing import List, Dict, Any, Optional

from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
import cv2
import pytesseract

import config
import converter

BASE_DIR = Path(__file__).resolve().parent
UPLOADS_DIR = BASE_DIR / "uploads"
STORAGE_DIR = BASE_DIR / "storage"
JOBS_DIR = STORAGE_DIR / "jobs"
SAMPLES_DIR = BASE_DIR / "samples"
STATIC_DIR = BASE_DIR / "static"
RECENT_JOBS_FILE = STORAGE_DIR / "recent_jobs.json"

for d in [UPLOADS_DIR, STORAGE_DIR, JOBS_DIR, STATIC_DIR]:
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="PNG to Figma Converter", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory cache of recent job results
job_cache: Dict[str, Dict[str, Any]] = {}

def load_recent_jobs() -> List[Dict[str, Any]]:
    if RECENT_JOBS_FILE.exists():
        try:
            with open(RECENT_JOBS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_recent_job(job_summary: Dict[str, Any]):
    recent = load_recent_jobs()
    # Filter out existing with same job_id or filename
    recent = [j for j in recent if j.get("job_id") != job_summary.get("job_id")]
    recent.insert(0, job_summary)
    # Keep last 15
    recent = recent[:15]
    with open(RECENT_JOBS_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f, indent=2)

@app.get("/api/health")
def health_check():
    """Returns backend status for the live status badge."""
    tess_version = "unknown"
    try:
        tess_version = pytesseract.get_tesseract_version()
    except Exception:
        pass
        
    return {
        "status": "online",
        "backend": "🟢",
        "opencv_version": cv2.__version__,
        "tesseract_version": str(tess_version),
        "tesseract_cmd": pytesseract.pytesseract.tesseract_cmd
    }

@app.get("/api/samples")
def list_samples():
    """Lists available sample PNGs in the samples folder."""
    samples = []
    if SAMPLES_DIR.exists():
        for f in SAMPLES_DIR.glob("*.png"):
            samples.append({
                "filename": f.name,
                "size_mb": round(f.stat().st_size / (1024 * 1024), 2),
                "url": f"/samples/{f.name}"
            })
    return {"samples": samples}

@app.post("/api/convert")
async def convert_image(file: UploadFile = File(...)):
    """Receives a PNG file and runs the OCR and shape detection pipeline."""
    if not file.filename.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
        raise HTTPException(status_code=400, detail="Only PNG, JPG, or WEBP images are supported.")
        
    safe_filename = Path(file.filename).name
    temp_path = UPLOADS_DIR / f"{safe_filename}"
    
    with open(temp_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)
        
    try:
        result = converter.process_image_file(str(temp_path), safe_filename)
        result["image_url"] = f"/uploads/{safe_filename}"
        
        # Save to cache and disk
        job_id = result["job_id"]
        job_cache[job_id] = result
        
        with open(JOBS_DIR / f"{job_id}.json", "w", encoding="utf-8") as jf:
            json.dump(result, jf, indent=2)
            
        save_recent_job({
            "job_id": job_id,
            "filename": safe_filename,
            "counts": result["counts"],
            "timestamp": result["timestamp"],
            "image_url": result["image_url"]
        })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")

@app.post("/api/convert-sample/{filename}")
def convert_sample(filename: str):
    """Runs conversion on a predefined sample PNG from the samples directory."""
    sample_path = SAMPLES_DIR / filename
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found.")
        
    try:
        result = converter.process_image_file(str(sample_path), filename)
        result["image_url"] = f"/samples/{filename}"
        
        job_id = result["job_id"]
        job_cache[job_id] = result
        
        with open(JOBS_DIR / f"{job_id}.json", "w", encoding="utf-8") as jf:
            json.dump(result, jf, indent=2)
            
        save_recent_job({
            "job_id": job_id,
            "filename": filename,
            "counts": result["counts"],
            "timestamp": result["timestamp"],
            "image_url": result["image_url"]
        })
        
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion error: {str(e)}")

@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    """Retrieves conversion job results by job_id."""
    if job_id in job_cache:
        return job_cache[job_id]
        
    job_file = JOBS_DIR / f"{job_id}.json"
    if job_file.exists():
        with open(job_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            job_cache[job_id] = data
            return data
            
    raise HTTPException(status_code=404, detail="Job not found.")

@app.get("/api/job/{job_id}/figma.json")
def download_figma_json(job_id: str):
    """Direct download of the Figma-compatible JSON."""
    job_data = get_job(job_id)
    json_path = JOBS_DIR / f"{job_id}_figma.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(job_data.get("figma_json", {}), f, indent=2)
        
    return FileResponse(
        path=str(json_path),
        filename=f"{Path(job_data['filename']).stem}_figma.json",
        media_type="application/json"
    )

@app.get("/api/job/{job_id}/plugin.js")
def download_figma_plugin_js(job_id: str):
    """Direct download of the 1-click Figma Plugin JavaScript script."""
    job_data = get_job(job_id)
    script_path = JOBS_DIR / f"{job_id}_plugin.js"
    with open(script_path, "w", encoding="utf-8") as f:
        f.write(job_data.get("plugin_script", "// No script generated"))
        
    return FileResponse(
        path=str(script_path),
        filename=f"{Path(job_data['filename']).stem}_figma_plugin.js",
        media_type="text/javascript"
    )

@app.get("/api/recent")
def get_recent():
    """Returns the list of recent conversions."""
    return {"recent": load_recent_jobs()}

# Mount directories for static files and image serving
if SAMPLES_DIR.exists():
    app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
app.mount("/uploads", StaticFiles(directory=str(UPLOADS_DIR)), name="uploads")
app.mount("/", StaticFiles(directory=str(STATIC_DIR), html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("server:app", host="127.0.0.1", port=8000, reload=False)
