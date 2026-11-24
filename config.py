"""
Configuration module for PNG-to-Figma offline tool.
Points Python and PyTesseract to the local Tesseract OCR executable.
"""
import os
import shutil
from pathlib import Path
import pytesseract

# Primary Windows path for Tesseract OCR installed via winget
TESSERACT_EXE = Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

if TESSERACT_EXE.exists():
    pytesseract.pytesseract.tesseract_cmd = str(TESSERACT_EXE)
else:
    # Fallback to PATH lookup
    found_path = shutil.which("tesseract")
    if found_path:
        pytesseract.pytesseract.tesseract_cmd = found_path
