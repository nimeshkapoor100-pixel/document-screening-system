from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import asyncio
    from winrt.windows.media.ocr import OcrEngine
    from winrt.windows.graphics.imaging import BitmapDecoder
    from winrt.windows.storage import StorageFile
    from winrt.windows.globalization import Language
    USE_WINRT = True
except ImportError:
    USE_WINRT = False
    import cv2
    import numpy as np
    import easyocr
    _reader = None

def get_reader():
    global _reader
    if _reader is None:
        try:
            _reader = easyocr.Reader(["en", "hi"], gpu=True)
        except Exception:
            _reader = easyocr.Reader(["en", "hi"], gpu=False)
    return _reader

def reconstruct_reading_order(boxes: list[tuple[float, float, str]]) -> str:
    if not boxes:
        return ""
    
    # 1. Sort all boxes by y_center
    boxes.sort(key=lambda b: b[0])
    
    rows = []
    current_row = [boxes[0]]
    
    for box in boxes[1:]:
        y_center = box[0]
        row_y_centers = [b[0] for b in current_row]
        median_y = sorted(row_y_centers)[len(row_y_centers)//2]
        
        # 2. Group boxes into rows based on a 15-pixel threshold
        if abs(y_center - median_y) <= 15:
            current_row.append(box)
        else:
            rows.append(current_row)
            current_row = [box]
    rows.append(current_row)
    
    lines = []
    for row in rows:
        # 3. Sort boxes in each row left-to-right by x_left
        row.sort(key=lambda b: b[1])
        # 4. Join boxes with spaces
        lines.append(" ".join(b[2] for b in row))
        
    return "\n".join(lines)

async def _extract_text_async(image_path: Path) -> str:
    abs_path = os.path.abspath(str(image_path))
    file = await StorageFile.get_file_from_path_async(abs_path)
    stream = await file.open_async(0)
    decoder = await BitmapDecoder.create_async(stream)
    software_bitmap = await decoder.get_software_bitmap_async()
    
    engine = OcrEngine.try_create_from_language(Language("en-US"))
    if not engine:
        raise RuntimeError("Failed to create WinRT OcrEngine")
        
    result = await engine.recognize_async(software_bitmap)
    
    boxes = []
    for line in result.lines:
        for word in line.words:
            y_center = word.bounding_rect.y + word.bounding_rect.height / 2
            x_left = word.bounding_rect.x
            boxes.append((y_center, x_left, word.text))
            
    return reconstruct_reading_order(boxes)

def _deskew_image(gray: Any) -> Any:
    import cv2
    import numpy as np
    
    thresh = cv2.bitwise_not(gray)
    thresh = cv2.threshold(thresh, 0, 255, cv2.THRESH_BINARY | cv2.THRESH_OTSU)[1]
    coords = np.column_stack(np.where(thresh > 0))
    if len(coords) == 0:
        return gray
        
    angle = cv2.minAreaRect(coords)[-1]
    if angle < -45:
        angle = -(90 + angle)
    else:
        angle = -angle
        
    if abs(angle) < 0.5:
        return gray

    (h, w) = gray.shape[:2]
    center = (w // 2, h // 2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    rotated = cv2.warpAffine(gray, M, (w, h), flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)
    return rotated

def _preprocess_for_ocr(image_path: Path, method: str = "clahe") -> str | Any:
    """Enhance image contrast and scale to improve OCR accuracy for EasyOCR."""
    try:
        import cv2
        img = cv2.imread(str(image_path))
        if img is None:
            return str(image_path)
            
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        
        height, width = gray.shape
        if width < 1200:
            scale_factor = 1200.0 / width
            gray = cv2.resize(gray, None, fx=scale_factor, fy=scale_factor, interpolation=cv2.INTER_CUBIC)
            
        if method == "adaptive_deskew":
            gray = _deskew_image(gray)
            processed = cv2.adaptiveThreshold(gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
            return processed
        else:
            clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
            enhanced = clahe.apply(gray)
            filtered = cv2.bilateralFilter(enhanced, 5, 50, 50)
            return filtered
    except Exception:
        return str(image_path)

def extract_text(image_path: str | Path, method: str = "clahe") -> str:
    path = Path(image_path)
    if not path.is_file():
        raise FileNotFoundError(f"Image not found: {path}")
    if path.stat().st_size == 0:
        raise ValueError(f"Image is empty: {path}")
        
    if USE_WINRT:
        if method == "adaptive_deskew":
            # WinRT natively requires a file path. We'd have to save temp file.
            # For simplicity, if WinRT is used, we'll try to let WinRT handle it natively 
            # or we create a temp file. Let's create a temp file.
            try:
                import cv2
                import tempfile
                processed = _preprocess_for_ocr(path, method="adaptive_deskew")
                if isinstance(processed, str):
                    return asyncio.run(_extract_text_async(path))
                
                with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                    temp_path = tmp.name
                cv2.imwrite(temp_path, processed)
                try:
                    result = asyncio.run(_extract_text_async(Path(temp_path)))
                finally:
                    os.unlink(temp_path)
                return result
            except Exception:
                return asyncio.run(_extract_text_async(path))
        else:
            return asyncio.run(_extract_text_async(path))
    else:
        source = _preprocess_for_ocr(path, method=method)
        raw_results = get_reader().readtext(source, detail=1, paragraph=False)
        boxes = []
        for bbox, text, conf in raw_results:
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            y_center = sum(ys) / 4
            x_left = min(xs)
            boxes.append((y_center, x_left, text))
        return reconstruct_reading_order(boxes)
