"""Flask API server that bridges the Satark Sarthi GUI to the OCR/validation backend.

Endpoints:
    GET  /           → serve index.html (or redirect to /login if unauthenticated)
    GET  /login      → serve login.html (or redirect to / if already logged in)
    POST /login      → officer credential verification & session creation
    GET  /logout     → terminate session & redirect to /login
    GET  /api/me     → get current authenticated officer info
    POST /api/analyze → accept image upload, create task, return task_id
    GET  /api/status/<task_id> → return task status and result
"""

from __future__ import annotations

import os
import uuid
import logging
import tempfile
from pathlib import Path

from flask import Flask, jsonify, request, send_from_directory, session, redirect, url_for
from flask_cors import CORS

from datetime import datetime, timezone
import cv2
from PIL import Image

from config import Config
from database import (
    create_task_record, 
    get_task_record, 
    update_task_record, 
    list_task_records,
    verify_user,
    get_user_by_officer_id
)
from tasks import process_document_task
from forgery_detection import ELA_HIGH_THRESHOLD, NOISE_RATIO_THRESHOLD

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

app.config.from_object(Config)
app.secret_key = app.config.get("SECRET_KEY", "sentinel-oversight-border-secret-key-2024")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png", "pdf", "bmp", "tiff", "tif", "webp"}

def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route("/")
def index():
    # Require officer authentication
    if "user" not in session:
        return redirect(url_for("login"))
    # Check if a specific dashboard variant is requested
    variant = request.args.get("variant")
    if variant == "corp":
        return send_from_directory(".", "index_corp.html")
    return send_from_directory(".", "index.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        if "user" in session:
            return redirect(url_for("index"))
        return send_from_directory(".", "login.html")

    # POST: Handle credentials from JSON or Form submission
    if request.is_json:
        data = request.get_json(silent=True) or {}
    else:
        data = request.form.to_dict() if request.form else {}

    officer_id = data.get("officerId") or data.get("officer_id")
    password = data.get("password")
    role = data.get("roleSelect") or data.get("role")
    checkpoint = data.get("checkpointSelect") or data.get("checkpoint")

    if not officer_id or not password:
        err = "Officer ID and Password are required."
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "message": err}), 400
        return redirect(url_for("login", error=err))

    is_valid, user_info, err_msg = verify_user(
        officer_id=officer_id, 
        password=password, 
        role=role, 
        checkpoint=checkpoint
    )

    if not is_valid:
        if request.is_json or request.headers.get("Accept") == "application/json":
            return jsonify({"status": "error", "message": err_msg}), 401
        return redirect(url_for("login", error=err_msg))

    # Save to session
    session["user"] = user_info
    session.permanent = True

    # Redirect target (can switch to index_corp.html if specified or supervisor)
    redirect_target = "/"

    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({
            "status": "success",
            "message": "Login successful",
            "redirect": redirect_target,
            "user": user_info
        }), 200

    return redirect(redirect_target)

@app.route("/logout", methods=["GET", "POST"])
def logout():
    session.clear()
    if request.is_json or request.headers.get("Accept") == "application/json":
        return jsonify({"status": "success", "message": "Logged out successfully", "redirect": "/login"})
    return redirect(url_for("login"))

@app.route("/api/me", methods=["GET"])
def get_current_user():
    user = session.get("user")
    if not user:
        return jsonify({"authenticated": False, "error": "Not authenticated"}), 401
    return jsonify({"authenticated": True, "user": user})

@app.route("/api/analyze", methods=["POST"])
def analyze():
    if "file" not in request.files:
        return jsonify({"error": "No file provided", "validation_status": "Failed"}), 400

    file = request.files["file"]

    if file.filename == "":
        return jsonify({"error": "Empty filename", "validation_status": "Failed"}), 400

    if not _allowed_file(file.filename):
        return jsonify({
            "error": f"Unsupported file type. Allowed: {', '.join(ALLOWED_EXTENSIONS)}",
            "validation_status": "Failed",
        }), 415

    suffix = Path(file.filename).suffix or ".jpg"
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        file.save(tmp.name)
        tmp.close()
        
        if os.path.getsize(tmp.name) == 0:
            os.unlink(tmp.name)
            return jsonify({"error": "File is empty", "validation_status": "Failed"}), 400
            
        if suffix.lower() != ".pdf":
            try:
                img = cv2.imread(tmp.name)
                if img is None:
                    img = Image.open(tmp.name)
                    img.verify()
            except Exception:
                os.unlink(tmp.name)
                return jsonify({"error": "File is not a valid or decodable image", "validation_status": "Failed"}), 400

        task_id = str(uuid.uuid4())
        
        # Create MongoDB record
        create_task_record(task_id, tmp.name)
        
        face_file = request.files.get("face_file")
        live_face_path = None
        if face_file and face_file.filename != "" and _allowed_file(face_file.filename):
            f_suffix = Path(face_file.filename).suffix or ".jpg"
            f_tmp = tempfile.NamedTemporaryFile(delete=False, suffix=f_suffix)
            face_file.save(f_tmp.name)
            f_tmp.close()
            live_face_path = f_tmp.name
        
        # Push task to Celery
        process_document_task.delay(task_id, tmp.name, live_face_path)
        
        return jsonify({"task_id": task_id, "status": "pending"})

    except Exception as exc:
        logger.exception("Failed to initialize task")
        try:
            os.unlink(tmp.name)
        except OSError:
            pass
        return jsonify({"error": f"Processing error: {exc}", "validation_status": "Failed"}), 500

@app.route("/api/status/<task_id>", methods=["GET"])
def get_status(task_id: str):
    record = get_task_record(task_id)
    if not record:
        return jsonify({"error": "Task not found"}), 404
        
    # MongoDB returns datetime objects, need to serialize them
    response = {
        "task_id": record["_id"],
        "status": record["status"],
        "created_at": record["created_at"].isoformat() if record.get("created_at") else None,
        "updated_at": record["updated_at"].isoformat() if record.get("updated_at") else None,
    }
    
    if record["status"] in ["approved", "rejected", "flagged"]:
        response["fields"] = record.get("extracted_data")
        vd = record.get("validation_details", {})
        response["validation_details"] = vd
        
        try:
            # Extract clean top-level numeric fields for the frontend (0-100 scale)
            ft = vd.get("final_trust_score", {})
            if "reason" in ft and "Score:" in ft["reason"]:
                response["final_trust_score"] = float(ft["reason"].replace("Score:", "").strip()) * 100
                
            dbf = vd.get("database_face_match", {})
            if "score" in dbf and dbf["score"] is not None:
                response["database_face_score"] = float(dbf["score"]) * 100
                
            lf = vd.get("live_identity_match", {})
            if "score" in lf and lf["score"] is not None:
                response["live_face_score"] = float(lf["score"]) * 100
                
            tc = vd.get("tampering_check", {})
            if "risk_score" in tc: response["tampering_risk_score"] = float(tc["risk_score"]) * 100
            
            if "ela_score" in tc: 
                ela = float(tc["ela_score"])
                response["ela_score"] = min(100.0, (ela / ELA_HIGH_THRESHOLD) * 100.0)
                
            if "noise_score" in tc: 
                noise = float(tc["noise_score"])
                response["noise_score"] = min(100.0, max(0.0, (noise - 1.0) / (NOISE_RATIO_THRESHOLD - 1.0)) * 100.0)
                
            if "stamp_score" in tc: 
                stamp = float(tc["stamp_score"])
                response["stamp_score"] = min(100.0, (stamp / 2.5) * 100.0) if stamp > 0 else 0.0
                
            if "exif_flags" in tc:
                response["exif_flags"] = tc["exif_flags"]
        except Exception as e:
            logger.warning(f"Failed to parse numeric fields: {e}")
        response["validation_status"] = "Passed" if record["status"] == "approved" else "Failed"
        response["document_type"] = record.get("document_type")
        response["raw_text"] = record.get("raw_text")
        response["processing_time_seconds"] = record.get("processing_time_seconds")
        if "rejection_reason" in record:
            response["rejection_reason"] = record["rejection_reason"]
    elif record["status"] == "failed":
        response["error"] = record.get("error")
        response["validation_status"] = "Failed"
        response["document_type"] = record.get("document_type")
        response["raw_text"] = record.get("raw_text")
        if "rejection_reason" in record:
            response["rejection_reason"] = record["rejection_reason"]
        
    response["cropped_doc_face"] = record.get("cropped_doc_face") or (record.get("extracted_data") or {}).get("cropped_doc_face")
    response["cropped_live_face"] = record.get("cropped_live_face") or (record.get("extracted_data") or {}).get("cropped_live_face")

    return jsonify(response)

@app.route("/api/history", methods=["GET"])
def history():
    try:
        limit = int(request.args.get("limit", 50))
    except ValueError:
        limit = 50
        
    status_filter = request.args.get("status")
    doc_type_filter = request.args.get("document_type")
    
    records = list_task_records(limit=limit, status_filter=status_filter, doc_type_filter=doc_type_filter)
    
    results = []
    for r in records:
        item = {
            "task_id": r["_id"],
            "document_type": r.get("document_type"),
            "status": r.get("status"),
            "created_at": r["created_at"].isoformat() if r.get("created_at") else None,
            "reviewed_by": r.get("reviewed_by"),
            "officer_decision": r.get("officer_decision"),
            "rejection_reason": r.get("rejection_reason")
        }
        
        vd = r.get("validation_details", {}) or {}
        ft = vd.get("final_trust_score", {}) or {}
        if isinstance(ft, dict) and "reason" in ft and "Score:" in ft["reason"]:
            try:
                item["final_trust_score"] = float(ft["reason"].replace("Score:", "").strip()) * 100
            except:
                pass
            
        results.append(item)
        
    return jsonify({"history": results})

@app.route("/api/history/<task_id>", methods=["GET"])
def get_history_detail(task_id: str):
    return get_status(task_id)

@app.route("/api/review/<task_id>", methods=["POST"])
def review_task(task_id: str):
    record = get_task_record(task_id)
    if not record:
        return jsonify({"error": "Task not found"}), 404
        
    data = request.json
    if not data or "decision" not in data or "officer_name" not in data:
        return jsonify({"error": "Missing decision or officer_name"}), 400
        
    decision = data["decision"]
    if decision not in ["approve", "reject"]:
        return jsonify({"error": "Invalid decision"}), 400
        
    updates = {
        "status": "approved" if decision == "approve" else "rejected",
        "officer_decision": decision,
        "reviewed_by": data["officer_name"],
        "review_notes": data.get("notes", ""),
        "reviewed_at": datetime.now(timezone.utc)
    }
    
    update_task_record(task_id, updates)
    return jsonify({"status": "success", "task_id": task_id, "new_status": updates["status"]})

@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "message": "Satark Sarthi API is running"})

if __name__ == "__main__":
    print("=" * 60)
    print("  Satark Sarthi — Document Screening System")
    print("  Starting Flask server on http://localhost:5000")
    print("=" * 60)
    app.run(host="0.0.0.0", port=5000, debug=False)
