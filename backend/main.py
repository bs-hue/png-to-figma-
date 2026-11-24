"""
FastAPI Server for PNG-to-Figma Converter.
Serves REST API, cropped assets, and interactive dashboard as ONE unified service.
"""
import os
import json
import time
import shutil
import asyncio
from pathlib import Path
from typing import Dict, Any, List

from fastapi import FastAPI, File, UploadFile, HTTPException, Request
from fastapi.responses import JSONResponse, FileResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
import uvicorn

from backend import detector

BASE_DIR = Path(__file__).resolve().parent.parent
BACKEND_DIR = BASE_DIR / "backend"
JOBS_DIR = BACKEND_DIR / "jobs"
SAMPLES_DIR = BASE_DIR / "samples"
DASHBOARD_DIR = BASE_DIR / "dashboard"
RECENT_FILE = JOBS_DIR / "recent.json"

JOBS_DIR.mkdir(parents=True, exist_ok=True)
DASHBOARD_DIR.mkdir(parents=True, exist_ok=True)

MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB

app = FastAPI(title="PNG → Figma Converter", version="2.0.0")

# Allow CORS so Figma plugins (Origin: null) or other clients can call it freely
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.middleware("http")
async def add_cors_headers(request: Request, call_next):
    if request.method == "OPTIONS":
        from fastapi.responses import Response
        response = Response(status_code=204)
    else:
        response = await call_next(request)
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

def cleanup_old_jobs():
    """Deletes jobs older than 24 hours (86,400 seconds)."""
    now = time.time()
    twenty_four_hours = 24 * 3600
    if not JOBS_DIR.exists():
        return
        
    for item in JOBS_DIR.iterdir():
        if item.is_dir() and (now - item.stat().st_mtime) > twenty_four_hours:
            try:
                shutil.rmtree(item)
            except Exception as e:
                print(f"Error deleting old job {item.name}: {e}")

def load_recent_jobs() -> List[Dict[str, Any]]:
    if RECENT_FILE.exists():
        try:
            with open(RECENT_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return []
    return []

def save_recent_job(job_entry: Dict[str, Any]):
    recent = load_recent_jobs()
    recent = [j for j in recent if j.get("job_id") != job_entry.get("job_id")]
    recent.insert(0, job_entry)
    recent = recent[:10]  # Keep last 10 jobs
    with open(RECENT_FILE, "w", encoding="utf-8") as f:
        json.dump(recent, f, indent=2)

@app.on_event("startup")
async def startup_event():
    cleanup_old_jobs()

@app.get("/health", response_class=PlainTextResponse)
def health():
    """Health check endpoint. Returns 'ok'."""
    return "ok"

@app.get("/api/health")
def api_health():
    """JSON health check with engine versions."""
    import cv2, pytesseract
    tess_ver = "unknown"
    try:
        tess_ver = str(pytesseract.get_tesseract_version())
    except Exception:
        pass
    return {
        "status": "ok",
        "backend": "online",
        "opencv_version": cv2.__version__,
        "tesseract_version": tess_ver
    }

@app.post("/convert")
async def convert(file: UploadFile = File(...)):
    """
    POST /convert: upload a PNG/JPG (max 10 MB),
    run OCR + shape detection, build parent-child layout, and save layout.json.
    """
    cleanup_old_jobs()
    
    # 1. Validate file format
    ext = Path(file.filename).suffix.lower()
    if ext not in [".png", ".jpg", ".jpeg", ".webp"]:
        raise HTTPException(
            status_code=400,
            detail="Only PNG/JPG allowed. Please upload a .png, .jpg, or .webp image."
        )

    # 2. Validate file size (max 10 MB)
    contents = await file.read()
    if len(contents) > MAX_FILE_SIZE:
        raise HTTPException(
            status_code=400,
            detail="File too big. Maximum file size allowed is 10 MB."
        )

    job_id = detector.uuid.uuid4().hex[:6]
    temp_dir = JOBS_DIR / job_id
    temp_dir.mkdir(parents=True, exist_ok=True)
    
    temp_image_path = temp_dir / f"input{ext}"
    with open(temp_image_path, "wb") as f:
        f.write(contents)

    try:
        meta = detector.process_image(str(temp_image_path), file.filename, job_id=job_id)
        
        save_recent_job({
            "job_id": job_id,
            "filename": file.filename,
            "counts": meta["counts"],
            "timestamp": meta["timestamp"],
            "original_image_url": meta["original_image_url"]
        })
        
        return meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.post("/convert-sample/{filename}")
def convert_sample(filename: str):
    """Convenience endpoint to convert one of the sample images in samples/."""
    cleanup_old_jobs()
    sample_path = SAMPLES_DIR / filename
    if not sample_path.exists():
        raise HTTPException(status_code=404, detail="Sample image not found.")

    if sample_path.stat().st_size > MAX_FILE_SIZE:
        raise HTTPException(status_code=400, detail="File too big. Maximum allowed size is 10 MB.")

    job_id = detector.uuid.uuid4().hex[:6]
    try:
        meta = detector.process_image(str(sample_path), filename, job_id=job_id)
        save_recent_job({
            "job_id": job_id,
            "filename": filename,
            "counts": meta["counts"],
            "timestamp": meta["timestamp"],
            "original_image_url": meta["original_image_url"]
        })
        return meta
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.get("/job/{job_id}")
def get_job(job_id: str):
    """GET /job/{job_id}: returns layout.json for the specified job."""
    layout_file = JOBS_DIR / job_id / "layout.json"
    if not layout_file.exists():
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or expired.")
        
    with open(layout_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    if "job_id" not in data:
        data["job_id"] = job_id
    if "backgroundColor" not in data:
        data["backgroundColor"] = "#ffffff"
    if "filename" not in data:
        data["filename"] = f"Job {job_id}"
    return data

@app.get("/job/{job_id}/meta")
def get_job_meta(job_id: str):
    """Returns full metadata for the dashboard (with counts, flat elements, etc.)."""
    meta_file = JOBS_DIR / job_id / "meta.json"
    if not meta_file.exists():
        raise HTTPException(status_code=404, detail=f"Job {job_id} not found or expired.")
        
    with open(meta_file, "r", encoding="utf-8") as f:
        return json.load(f)

@app.get("/job/{job_id}/download")
def download_layout_json(job_id: str):
    """GET /job/{job_id}/download: direct download of layout.json."""
    layout_file = JOBS_DIR / job_id / "layout.json"
    if not layout_file.exists():
        raise HTTPException(status_code=404, detail="Layout file not found.")
        
    return FileResponse(
        path=str(layout_file),
        filename=f"layout_{job_id}.json",
        media_type="application/json"
    )

@app.get("/job/{job_id}/svg")
def download_figma_svg(job_id: str):
    """GET /job/{job_id}/svg: download layered SVG ready to drag & drop into Figma."""
    svg_file = JOBS_DIR / job_id / "layout.svg"
    if not svg_file.exists():
        raise HTTPException(status_code=404, detail="SVG file not found.")
        
    return FileResponse(
        path=str(svg_file),
        filename=f"figma_design_{job_id}.svg",
        media_type="image/svg+xml"
    )

@app.get("/job/{job_id}/script")
def download_figma_script(job_id: str):
    """GET /job/{job_id}/script: download 1-click script for Figma console."""
    script_file = JOBS_DIR / job_id / "figma_script.js"
    if not script_file.exists():
        raise HTTPException(status_code=404, detail="Figma script not found.")
        
    return FileResponse(
        path=str(script_file),
        filename=f"figma_importer_{job_id}.js",
        media_type="text/javascript"
    )

@app.get("/recent")
def get_recent():
    """Returns the last 10 jobs."""
    return {"recent": load_recent_jobs()}

@app.get("/samples-list")
def get_samples_list():
    """Returns available sample files."""
    files = []
    if SAMPLES_DIR.exists():
        for f in SAMPLES_DIR.glob("*.*"):
            if f.suffix.lower() in [".png", ".jpg", ".jpeg", ".webp"]:
                files.append({
                    "filename": f.name,
                    "size_mb": round(f.stat().st_size / (1024 * 1024), 2)
                })
    return {"samples": files}

# Mount static asset directories
app.mount("/jobs", StaticFiles(directory=str(JOBS_DIR)), name="jobs")
if SAMPLES_DIR.exists():
    app.mount("/samples", StaticFiles(directory=str(SAMPLES_DIR)), name="samples")
app.mount("/", StaticFiles(directory=str(DASHBOARD_DIR), html=True), name="dashboard")

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=False)
