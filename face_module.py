import cv2
import os
import logging
import numpy as np
from skimage.metrics import structural_similarity as ssim

logger = logging.getLogger(__name__)

# Initialize OpenCV DNN models
base_dir = os.path.dirname(os.path.abspath(__file__))
yunet_path = os.path.join(base_dir, "models", "face_detection_yunet_2023mar.onnx")
sface_path = os.path.join(base_dir, "models", "face_recognition_sface_2021dec.onnx")

detector = None
recognizer = None

if os.path.exists(yunet_path) and os.path.exists(sface_path):
    # We set default input size, it will be updated dynamically per image
    detector = cv2.FaceDetectorYN.create(yunet_path, "", (320, 320), 0.9, 0.3, 5000)
    recognizer = cv2.FaceRecognizerSF.create(sface_path, "")
else:
    logger.warning("OpenCV DNN face models not found in models/ directory. Face matching will fail.")

def detect_face(image):
    """Detect face using YuNet and return the best face."""
    if detector is None:
        return None
    height, width, _ = image.shape
    detector.setInputSize((width, height))
    _, faces = detector.detect(image)
    if faces is not None and len(faces) > 0:
        # Return the most prominent face (largest bounding box area)
        return max(faces, key=lambda f: f[2] * f[3])
    return None

def extract_face_from_document(document_image_path: str, output_path: str = None) -> str:
    """
    Extracts and crops the face from the document or live image using OpenCV YuNet.
    """
    if not document_image_path or not os.path.exists(document_image_path):
        logger.error(f"Image not found at {document_image_path}")
        return None

    try:
        img = cv2.imread(document_image_path)
        if img is None:
            return None
            
        face = detect_face(img)
        if face is not None:
            x, y, w, h = (int(face[0]), int(face[1]), int(face[2]), int(face[3]))
            
            # Generous proportional padding for a natural passport/ID portrait crop (hair, chin, collar, ears)
            pad_top = max(15, int(h * 0.45))
            pad_bottom = max(15, int(h * 0.35))
            pad_side = max(15, int(w * 0.30))
            x1 = max(0, x - pad_side)
            y1 = max(0, y - pad_top)
            x2 = min(img.shape[1], x + w + pad_side)
            y2 = min(img.shape[0], y + h + pad_bottom)

            cropped_face = img[y1:y2, x1:x2]

            if output_path is None:
                dir_name = os.path.dirname(document_image_path)
                base_name = os.path.basename(document_image_path)
                output_path = os.path.join(dir_name, f"cropped_{base_name}")

            cv2.imwrite(output_path, cropped_face)
            return output_path
        else:
            logger.warning("No face detected in image.")
            return None
    except Exception as e:
        logger.error(f"Face extraction failed: {e}")
        return None

def verify_identity(cropped_face_path: str, reference_face_path: str):
    """
    Verifies if the face in cropped_face_path matches reference_face_path using OpenCV SFace.
    Returns (similarity_score, is_match).
    """
    if not cropped_face_path or not os.path.exists(cropped_face_path):
        logger.error(f"Cropped face path invalid: {cropped_face_path}")
        return 0.0, False
    if not reference_face_path or not os.path.exists(reference_face_path):
        logger.error(f"Reference face path invalid: {reference_face_path}")
        return 0.0, False

    if recognizer is None:
        logger.error("FaceRecognizerSF not loaded.")
        return 0.0, False

    try:
        img1 = cv2.imread(cropped_face_path)
        img2 = cv2.imread(reference_face_path)
        
        if img1 is None or img2 is None:
            return 0.0, False

        face1 = detect_face(img1)
        face2 = detect_face(img2)

        if face1 is None or face2 is None:
            logger.warning("Could not detect face in one or both images for verification.")
            return 0.0, False

        # Align faces
        aligned_face1 = recognizer.alignCrop(img1, face1)
        aligned_face2 = recognizer.alignCrop(img2, face2)

        # Extract features
        feat1 = recognizer.feature(aligned_face1)
        feat2 = recognizer.feature(aligned_face2)

        # Calculate Cosine Similarity
        cosine_score = recognizer.match(feat1, feat2, cv2.FaceRecognizerSF_FR_COSINE)
        
        # SFace threshold for Cosine is typically >= 0.363 for a match
        is_match = cosine_score >= 0.363
        
        # Scale score somewhat for UI (tasks.py checks for score >= 0.55)
        if cosine_score >= 0.363:
            scaled_score = 0.55 + ((cosine_score - 0.363) / (1.0 - 0.363)) * (1.0 - 0.55)
        else:
            scaled_score = max(0.0, (cosine_score / 0.363) * 0.55)
            
        return scaled_score, is_match

    except Exception as e:
        logger.error(f"Face verification failed: {e}")
        return 0.0, False
