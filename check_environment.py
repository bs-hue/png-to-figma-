"""
Verification script for PNG-to-Figma offline environment.
Tests that Python, OpenCV, and Tesseract OCR can communicate properly.
"""
import sys
import cv2
import pytesseract
import config  # sets Tesseract executable path

def main():
    print("=" * 50)
    print("ENVIRONMENT VERIFICATION CHECK")
    print("=" * 50)
    print(f"Python Version:    {sys.version.split()[0]}")
    print(f"OpenCV Version:    {cv2.__version__}")
    
    try:
        tess_version = pytesseract.get_tesseract_version()
        print(f"Tesseract Version: {tess_version}")
        print(f"Tesseract Path:    {pytesseract.pytesseract.tesseract_cmd}")
        print("-" * 50)
        print("SUCCESS: Both OpenCV and Tesseract OCR are working properly!")
    except Exception as e:
        print(f"ERROR: Tesseract OCR verification failed: {e}")
        sys.exit(1)
    print("=" * 50)

if __name__ == "__main__":
    main()
