"""
forgery_detection.py — Multi-layered Editing & Forgery Detection Module
==========================================================================
Part of: Sentinel Oversight — Document Screening System

This module provides three independent forensic analysis layers:
  1. EXIF / Metadata Analysis   — detects editing-tool signatures in image metadata
  2. Error Level Analysis (ELA) — detects recompressed / spliced regions
  3. Noise / Edge Inconsistency — detects cloned patches or smudged-text anomalies

Public API
----------
    detect_forgery(file_path: str) -> dict
        {
            "is_forged": bool,
            "flag_reason": list[str],
            "risk_score": float,          # 0.0 - 1.0  (higher = more suspicious)
            "ela_score": float,           # raw ELA deviation (0 - 255)
            "noise_score": float,         # noise inconsistency score
            "exif_flags": list[str],      # human-readable EXIF anomalies
        }

Graceful degradation
--------------------
* PDFs and other non-raster formats: ELA and edge checks are skipped; only metadata
  is inspected where possible. No exception is raised.
* Missing EXIF data: treated as "no flags" - not penalised.
* Any individual check failure is caught, logged, and skipped without killing the
  pipeline.
"""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Tuneable thresholds
# ---------------------------------------------------------------------------
# ELA: mean absolute pixel difference (0-255) above this value is suspicious
ELA_SUSPICIOUS_THRESHOLD: float = 8.0
# ELA: above this value is "highly likely tampered"
ELA_HIGH_THRESHOLD: float = 18.0

# Noise: standard-deviation ratio between image quadrants. If the ratio of
# max/min std exceeds this, regions likely have different noise origins.
NOISE_RATIO_THRESHOLD: float = 2.5
# Edge: Laplacian variance ratio between quadrants
EDGE_RATIO_THRESHOLD: float = 3.0

# Known editing-tool software signatures (case-insensitive partial match)
EDITING_TOOL_SIGNATURES: list[str] = [
    "adobe photoshop",
    "adobe illustrator",
    "adobe lightroom",
    "adobe acrobat",
    "adobe indesign",
    "gimp",
    "canva",
    "inkscape",
    "paint.net",
    "affinity photo",
    "affinity designer",
    "pixelmator",
    "corel draw",
    "coreldraw",
    "paintshop",
    "fotor",
    "snapseed",
    "facetune",
    "meitu",
    "picsart",
    "photopea",
    "lunapic",
    "befunky",
    "pixlr",
    "photofiltre",
]

# JPEG quality used to re-save during ELA
ELA_RESAVE_QUALITY: int = 90


# ===========================================================================
# Helper utilities
# ===========================================================================

def _is_raster_image(file_path: str) -> bool:
    """Return True if the file is a raster image that PIL and OpenCV can open."""
    suffix = Path(file_path).suffix.lower().lstrip(".")
    non_raster = {"pdf"}
    return suffix not in non_raster


def _load_pil_image(file_path: str):
    """Load a PIL Image, returning None on failure."""
    try:
        from PIL import Image
        img = Image.open(file_path)
        img.load()  # force decode
        return img
    except Exception as exc:
        logger.warning("PIL could not open '%s': %s", file_path, exc)
        return None


def _load_cv2_image(file_path: str):
    """Load image as a BGR numpy array via OpenCV, returning None on failure."""
    try:
        img = cv2.imread(file_path)
        if img is None:
            raise ValueError("cv2.imread returned None")
        return img
    except Exception as exc:
        logger.warning("OpenCV could not open '%s': %s", file_path, exc)
        return None


# ===========================================================================
# 1. EXIF / Metadata Analysis
# ===========================================================================

def check_exif_metadata(file_path: str) -> dict[str, Any]:
    """
    Inspect EXIF / XMP metadata for editing-tool fingerprints.

    Returns
    -------
    dict with keys:
        "flags"      : list[str]  -- human-readable anomaly descriptions
        "risk_delta" : float      -- contribution to overall risk score (0.0 - 0.4)
    """
    flags: list[str] = []
    risk_delta: float = 0.0

    pil_img = _load_pil_image(file_path)
    if pil_img is None:
        return {"flags": flags, "risk_delta": risk_delta}

    # Gather candidate metadata strings
    metadata_strings: list[tuple[str, str]] = []  # (field_name, value)

    try:
        exif_data = pil_img._getexif()  # type: ignore[attr-defined]
        if exif_data:
            from PIL.ExifTags import TAGS
            for tag_id, value in exif_data.items():
                tag_name = TAGS.get(tag_id, str(tag_id))
                if isinstance(value, (str, bytes)):
                    decoded = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value
                    metadata_strings.append((tag_name, decoded))
    except (AttributeError, Exception):
        pass  # Non-JPEG formats (PNG, BMP) may not have _getexif

    # Also check PIL's generic info dict (covers PNG tEXt chunks, etc.)
    try:
        for key, value in (pil_img.info or {}).items():
            if isinstance(value, (str, bytes)):
                decoded = value.decode("utf-8", errors="ignore") if isinstance(value, bytes) else value
                metadata_strings.append((str(key), decoded))
    except Exception:
        pass

    # Compare against known editing-tool signatures
    detected_tools: set[str] = set()
    for field_name, value in metadata_strings:
        value_lower = value.lower()
        for sig in EDITING_TOOL_SIGNATURES:
            if sig in value_lower and sig not in detected_tools:
                detected_tools.add(sig)
                flags.append(
                    f"Editing tool detected in EXIF field '{field_name}': "
                    f"'{value.strip()[:120]}'"
                )

    # Extra: check Software / Creator fields for post-processing keywords
    software_entries = [v for (k, v) in metadata_strings if k.lower() in ("software", "creator", "producer")]
    if software_entries:
        combined = " ".join(software_entries).lower()
        if any(tok in combined for tok in ("edit", "retouch", "enhance", "filter", "adjust")):
            flags.append(
                f"Metadata 'Software' field contains post-processing keyword: "
                f"'{software_entries[0].strip()[:80]}'"
            )

    # Unusual DPI is a weak signal of repurposed / rescaled image
    dpi = pil_img.info.get("dpi")
    if dpi:
        dpi_x = dpi[0] if isinstance(dpi, (tuple, list)) else dpi
        if isinstance(dpi_x, (int, float)) and dpi_x not in (72, 96, 150, 200, 300, 400, 600):
            risk_delta += 0.03

    if detected_tools:
        # Weight by number of distinct tools found (max cap at 0.4)
        risk_delta += min(0.15 * len(detected_tools), 0.40)

    return {"flags": flags, "risk_delta": risk_delta}


# ===========================================================================
# 2. Error Level Analysis (ELA)
# ===========================================================================

def check_ela(file_path: str, quality: int = ELA_RESAVE_QUALITY) -> dict[str, Any]:
    """
    Error Level Analysis: re-save at a known JPEG quality, compute absolute
    pixel differences, and return a tampering score.

    Only meaningful for JPEG / lossy-compressed raster images. PNG, BMP, etc.
    will show artificially high ELA; the function adjusts interpretation.

    Returns
    -------
    dict with keys:
        "ela_score"  : float  -- mean absolute difference (0 - 255)
        "flags"      : list[str]
        "risk_delta" : float  -- contribution to overall risk (0.0 - 0.5)
    """
    ela_score: float = 0.0
    flags: list[str] = []
    risk_delta: float = 0.0

    if not _is_raster_image(file_path):
        logger.debug("ELA skipped: '%s' is not a raster image.", file_path)
        return {"ela_score": ela_score, "flags": flags, "risk_delta": risk_delta}

    pil_img = _load_pil_image(file_path)
    if pil_img is None:
        return {"ela_score": ela_score, "flags": flags, "risk_delta": risk_delta}

    try:
        # Convert to RGB to normalise colour modes (RGBA, L, P, etc.)
        orig_rgb = pil_img.convert("RGB")

        # Re-save at known quality into a memory buffer
        buf = io.BytesIO()
        orig_rgb.save(buf, format="JPEG", quality=quality)
        buf.seek(0)

        from PIL import Image
        resaved = Image.open(buf).convert("RGB")

        # Compute absolute difference
        orig_arr = np.array(orig_rgb, dtype=np.float32)
        resaved_arr = np.array(resaved, dtype=np.float32)
        diff = np.abs(orig_arr - resaved_arr)

        ela_score = float(diff.mean())
        ela_max = float(diff.max())
        ela_std = float(diff.std())

        suffix = Path(file_path).suffix.lower().lstrip(".")
        is_lossy_source = suffix in ("jpg", "jpeg", "webp")

        if is_lossy_source:
            # For originally-JPEG images, ELA score should be near zero after one
            # resave cycle. High score implies prior editing with a different
            # compression history.
            if ela_score > ELA_HIGH_THRESHOLD:
                flags.append(
                    f"ELA score {ela_score:.2f} (max={ela_max:.1f}, sigma={ela_std:.2f}) "
                    f"strongly suggests multiple compression cycles -- possible tampering."
                )
                risk_delta += 0.50
            elif ela_score > ELA_SUSPICIOUS_THRESHOLD:
                flags.append(
                    f"ELA score {ela_score:.2f} (max={ela_max:.1f}, sigma={ela_std:.2f}) "
                    f"indicates possible re-encoding -- document may have been edited."
                )
                risk_delta += 0.25
        else:
            # Lossless sources (PNG/BMP) always have high ELA -- only flag extreme
            # outliers at a lower risk weight.
            if ela_score > 35.0:
                flags.append(
                    f"ELA score {ela_score:.2f} is unusually high for a lossless source "
                    f"(PNG/BMP). May indicate embedded edited JPEG content."
                )
                risk_delta += 0.20

    except Exception as exc:
        logger.warning("ELA check failed for '%s': %s", file_path, exc)

    return {"ela_score": ela_score, "flags": flags, "risk_delta": risk_delta}


# ===========================================================================
# 3. Noise / Edge Inconsistency Check
# ===========================================================================

def check_noise_edge_inconsistency(file_path: str) -> dict[str, Any]:
    """
    Divide the image into quadrants and compare noise (local standard deviation)
    and edge sharpness (Laplacian variance) across regions.

    Authentic scanned / photographed documents should have uniform sensor noise
    and consistent blur characteristics. Spliced images or documents with
    pasted/replaced regions show statistical discontinuities.

    Returns
    -------
    dict with keys:
        "noise_score" : float  -- max/min noise std ratio (1.0 = perfectly uniform)
        "flags"       : list[str]
        "risk_delta"  : float  -- contribution to overall risk (0.0 - 0.35)
    """
    noise_score: float = 1.0
    flags: list[str] = []
    risk_delta: float = 0.0

    if not _is_raster_image(file_path):
        logger.debug("Noise/edge check skipped: '%s' is not a raster image.", file_path)
        return {"noise_score": noise_score, "flags": flags, "risk_delta": risk_delta}

    bgr = _load_cv2_image(file_path)
    if bgr is None:
        return {"noise_score": noise_score, "flags": flags, "risk_delta": risk_delta}

    try:
        gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
        h, w = gray.shape

        # Need a meaningful minimum size to split into quadrants
        if h < 64 or w < 64:
            logger.debug("Image too small for noise analysis (%dx%d).", w, h)
            return {"noise_score": noise_score, "flags": flags, "risk_delta": risk_delta}

        # Quadrant decomposition
        mid_h, mid_w = h // 2, w // 2
        quadrants = {
            "top-left":     gray[:mid_h, :mid_w],
            "top-right":    gray[:mid_h, mid_w:],
            "bottom-left":  gray[mid_h:, :mid_w],
            "bottom-right": gray[mid_h:, mid_w:],
        }

        # Noise estimation via residual after Gaussian smoothing
        noise_stds: dict[str, float] = {}
        for name, quad in quadrants.items():
            blurred = cv2.GaussianBlur(quad, (5, 5), 0)
            residual = quad - blurred
            noise_stds[name] = float(np.std(residual))

        std_values = list(noise_stds.values())
        min_std = max(min(std_values), 1e-6)  # avoid division by zero
        max_std = max(std_values)
        noise_ratio = max_std / min_std
        noise_score = round(noise_ratio, 3)

        if noise_ratio > NOISE_RATIO_THRESHOLD:
            noisiest = max(noise_stds, key=noise_stds.get)   # type: ignore[arg-type]
            quietest = min(noise_stds, key=noise_stds.get)   # type: ignore[arg-type]
            flags.append(
                f"Noise inconsistency detected: '{noisiest}' quadrant (sigma={noise_stds[noisiest]:.2f}) "
                f"vs '{quietest}' (sigma={noise_stds[quietest]:.2f}). "
                f"Ratio {noise_ratio:.2f}x -- possible spliced region."
            )
            risk_delta += min(0.10 * (noise_ratio / NOISE_RATIO_THRESHOLD), 0.20)

        # Edge sharpness via Laplacian variance
        lap_vars: dict[str, float] = {}
        for name, quad in quadrants.items():
            lap = cv2.Laplacian(quad.astype(np.uint8), cv2.CV_64F)
            lap_vars[name] = float(lap.var())

        lap_values = list(lap_vars.values())
        min_lap = max(min(lap_values), 1e-6)
        max_lap = max(lap_values)
        edge_ratio = max_lap / min_lap

        if edge_ratio > EDGE_RATIO_THRESHOLD:
            sharpest = max(lap_vars, key=lap_vars.get)   # type: ignore[arg-type]
            blurriest = min(lap_vars, key=lap_vars.get)  # type: ignore[arg-type]
            flags.append(
                f"Edge sharpness inconsistency: '{sharpest}' (var={lap_vars[sharpest]:.1f}) "
                f"vs '{blurriest}' (var={lap_vars[blurriest]:.1f}). "
                f"Ratio {edge_ratio:.2f}x -- may indicate text smudging or pasted content."
            )
            risk_delta += min(0.08 * (edge_ratio / EDGE_RATIO_THRESHOLD), 0.15)

        # Global blur / sharpness sanity check
        overall_lap_var = float(cv2.Laplacian(gray.astype(np.uint8), cv2.CV_64F).var())
        if overall_lap_var < 20.0:
            flags.append(
                f"Document appears extremely blurry (Laplacian variance={overall_lap_var:.2f}). "
                f"Text regions may have been intentionally smudged."
            )
            risk_delta += 0.10

    except Exception as exc:
        logger.warning("Noise/edge check failed for '%s': %s", file_path, exc)

    return {"noise_score": noise_score, "flags": flags, "risk_delta": risk_delta}

# ===========================================================================
# 4. Stamp Forgery Check
# ===========================================================================

def check_stamp_forgery(file_path: str) -> dict[str, Any]:
    """
    Identify potential ink stamps (blue/red) and compare their noise signature
    against the background to detect digitally superimposed stamps.
    """
    stamp_score: float = 0.0
    flags: list[str] = []
    risk_delta: float = 0.0

    if not _is_raster_image(file_path):
        return {"stamp_score": stamp_score, "flags": flags, "risk_delta": risk_delta}

    bgr = _load_cv2_image(file_path)
    if bgr is None:
        return {"stamp_score": stamp_score, "flags": flags, "risk_delta": risk_delta}

    try:
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        
        # Blue ink mask
        lower_blue = np.array([90, 50, 50])
        upper_blue = np.array([130, 255, 255])
        mask_blue = cv2.inRange(hsv, lower_blue, upper_blue)

        # Red/purple ink masks
        lower_red1 = np.array([0, 50, 50])
        upper_red1 = np.array([10, 255, 255])
        mask_red1 = cv2.inRange(hsv, lower_red1, upper_red1)

        lower_red2 = np.array([160, 50, 50])
        upper_red2 = np.array([180, 255, 255])
        mask_red2 = cv2.inRange(hsv, lower_red2, upper_red2)

        stamp_mask = mask_blue | mask_red1 | mask_red2
        stamp_pixels = cv2.countNonZero(stamp_mask)
        total_pixels = bgr.shape[0] * bgr.shape[1]
        
        # Only analyze if stamp is present but doesn't cover the whole image
        if stamp_pixels > 100 and (stamp_pixels / total_pixels) < 0.2:
            gray = cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY).astype(np.float32)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            residual = np.abs(gray - blurred)
            
            stamp_noise = np.mean(residual[stamp_mask > 0])
            bg_noise = np.mean(residual[stamp_mask == 0])
            
            if bg_noise > 0:
                noise_ratio = max(stamp_noise / bg_noise, bg_noise / stamp_noise)
                stamp_score = float(noise_ratio)
                
                if noise_ratio > 2.5:
                    flags.append(f"Stamp region noise inconsistency (ratio {noise_ratio:.2f}x). Stamp may be digitally superimposed.")
                    risk_delta += 0.35
                elif noise_ratio > 1.8:
                    flags.append(f"Stamp region noise slightly inconsistent (ratio {noise_ratio:.2f}x).")
                    risk_delta += 0.15
    except Exception as exc:
        logger.warning("Stamp check failed for '%s': %s", file_path, exc)

    return {"stamp_score": stamp_score, "flags": flags, "risk_delta": risk_delta}


# ===========================================================================
# Master wrapper
# ===========================================================================

def detect_forgery(file_path: str) -> dict[str, Any]:
    """
    Run all forensic checks and return a consolidated forgery verdict.

    Parameters
    ----------
    file_path : str
        Absolute or relative path to the document image (JPEG, PNG, BMP, TIFF,
        WEBP) or PDF.  PDFs are partially supported (metadata only).

    Returns
    -------
    dict
        {
            "is_forged"    : bool,
            "flag_reason"  : list[str],   # human-readable reasons
            "risk_score"   : float,       # 0.0 - 1.0
            "ela_score"    : float,       # raw ELA mean difference
            "noise_score"  : float,       # noise ratio (quadrant max/min)
            "exif_flags"   : list[str],   # EXIF-sourced anomalies
        }

    This function NEVER raises -- all errors are caught internally and logged.
    """
    logger.info("[ForgeryDetection] Starting analysis on: %s", file_path)

    # Validate file existence
    if not os.path.isfile(file_path):
        logger.error("[ForgeryDetection] File not found: %s", file_path)
        return {
            "is_forged": False,
            "flag_reason": [f"File not found: {file_path}"],
            "risk_score": 0.0,
            "ela_score": 0.0,
            "noise_score": 1.0,
            "stamp_score": 0.0,
            "exif_flags": [],
        }

    all_flags: list[str] = []
    cumulative_risk: float = 0.0
    ela_score: float = 0.0
    noise_score: float = 1.0
    stamp_score: float = 0.0
    exif_flags: list[str] = []

    # Layer 1: EXIF / Metadata
    try:
        exif_result = check_exif_metadata(file_path)
        exif_flags = exif_result["flags"]
        all_flags.extend(exif_flags)
        cumulative_risk += exif_result["risk_delta"]
        logger.debug(
            "[ForgeryDetection] EXIF check done. risk_delta=%.3f, flags=%d",
            exif_result["risk_delta"], len(exif_flags),
        )
    except Exception as exc:
        logger.warning("[ForgeryDetection] EXIF check raised unexpectedly: %s", exc)

    # Layer 2: Error Level Analysis
    try:
        ela_result = check_ela(file_path)
        ela_score = ela_result["ela_score"]
        all_flags.extend(ela_result["flags"])
        cumulative_risk += ela_result["risk_delta"]
        logger.debug(
            "[ForgeryDetection] ELA done. ela_score=%.3f, risk_delta=%.3f",
            ela_score, ela_result["risk_delta"],
        )
    except Exception as exc:
        logger.warning("[ForgeryDetection] ELA check raised unexpectedly: %s", exc)

    # Layer 3: Noise / Edge Inconsistency
    try:
        noise_result = check_noise_edge_inconsistency(file_path)
        noise_score = noise_result["noise_score"]
        all_flags.extend(noise_result["flags"])
        cumulative_risk += noise_result["risk_delta"]
        logger.debug(
            "[ForgeryDetection] Noise check done. noise_score=%.3f, risk_delta=%.3f",
            noise_score, noise_result["risk_delta"],
        )
    except Exception as exc:
        logger.warning("[ForgeryDetection] Noise/edge check raised unexpectedly: %s", exc)

    # Layer 4: Stamp Forgery Check
    try:
        stamp_result = check_stamp_forgery(file_path)
        stamp_score = stamp_result["stamp_score"]
        all_flags.extend(stamp_result["flags"])
        cumulative_risk += stamp_result["risk_delta"]
        logger.debug(
            "[ForgeryDetection] Stamp check done. stamp_score=%.3f, risk_delta=%.3f",
            stamp_score, stamp_result["risk_delta"],
        )
    except Exception as exc:
        logger.warning("[ForgeryDetection] Stamp check raised unexpectedly: %s", exc)

    # Consolidate
    risk_score = round(min(cumulative_risk, 1.0), 4)

    # A document is forged if risk score >= 0.35
    is_forged = risk_score >= 0.35

    result = {
        "is_forged": is_forged,
        "flag_reason": all_flags,
        "risk_score": risk_score,
        "ela_score": round(ela_score, 4),
        "noise_score": round(noise_score, 4),
        "stamp_score": round(stamp_score, 4),
        "exif_flags": exif_flags,
    }

    logger.info(
        "[ForgeryDetection] Result -- is_forged=%s, risk_score=%.4f, flags=%d",
        is_forged, risk_score, len(all_flags),
    )
    return result