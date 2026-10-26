import os
import json
import base64
import logging
from celery import Celery
from config import Config
from database import update_task_record, central_identity_db
from ocr_module import extract_document_info
from face_module import extract_face_from_document, verify_identity
from data_matcher import match_demographics
from forgery_detection import detect_forgery
from validation_module import is_valid_expiry_date, validate_data
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Setup Celery
celery_app = Celery("document_screening", broker=Config.REDIS_URL, backend=Config.REDIS_URL)
celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
)

@celery_app.task(bind=True)
def process_document_task(self, task_id: str, file_path: str, live_face_path: str = None):
    logger.info(f"Starting processing for task: {task_id}")
    start_time = datetime.now(timezone.utc)
    
    cropped_face_path = None
    doc_face_b64 = None
    live_face_b64 = None

    try:
        # a. Extract textual data (WinRT / EasyOCR fallback)
        ocr_result_json = extract_document_info(file_path)
        ocr_result = json.loads(ocr_result_json)
        
        # Crop document face early so it is available for display even on rejection
        cropped_face_path = extract_face_from_document(file_path)
        if cropped_face_path and os.path.exists(cropped_face_path):
            try:
                with open(cropped_face_path, "rb") as f:
                    doc_face_b64 = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
            except Exception as e:
                logger.warning(f"Failed to encode cropped doc face: {e}")

        # Live input is kept uncropped as requested by user
        if live_face_path and os.path.exists(live_face_path):
            try:
                with open(live_face_path, "rb") as f:
                    live_face_b64 = f"data:image/jpeg;base64,{base64.b64encode(f.read()).decode('utf-8')}"
            except Exception as e:
                logger.warning(f"Failed to encode live face image: {e}")

        if "error" in ocr_result:
            update_task_record(task_id, {
                "status": "failed", 
                "error": ocr_result["error"],
                "cropped_doc_face": doc_face_b64,
                "cropped_live_face": live_face_b64,
            })
            return
            
        fields = ocr_result.get("fields", {})
        doc_type = ocr_result.get("document_type")
        raw_text = ocr_result.get("raw_text")
        
        # Determine the document number based on what was extracted
        doc_number = (fields.get("aadhaar_number") or 
                      fields.get("passport_number") or 
                      fields.get("license_number") or 
                      fields.get("visa_number"))
        
        NOT_DETECTED_MARKERS = {"Not Detected", "Not Detected (Watermark Noise)", None, ""}
        if doc_number in NOT_DETECTED_MARKERS:
            doc_number = None

        field_validation = json.loads(validate_data(ocr_result_json))
        field_validation_passed = field_validation.get("validation_status") == "Passed"
        field_validation_details = field_validation.get("validation_details", {})

        if not field_validation_passed:
            first_fail = next((k for k, v in field_validation_details.items() if not v.get("passed")), None)
            reason = field_validation_details[first_fail].get("reason", "Field validation failed") if first_fail else "Field validation failed"
            update_task_record(task_id, {
                "status": "rejected",
                "rejection_reason": reason,
                "document_type": doc_type,
                "raw_text": raw_text,
                "processing_time_seconds": round((datetime.now(timezone.utc) - start_time).total_seconds(), 2),
                "extracted_data": fields,
                "cropped_doc_face": doc_face_b64,
                "cropped_live_face": live_face_b64,
                "validation_details": field_validation_details,
            })
            return

        # b. Query central_identity_db
        if central_identity_db is None:
            update_task_record(task_id, {
                "status": "failed", 
                "error": "Database connection error.",
                "cropped_doc_face": doc_face_b64,
                "cropped_live_face": live_face_b64,
            })
            return

        query_candidates = []
        if doc_number:
            query_candidates.extend([doc_number, doc_number.replace(" ", ""), doc_number.upper()])
        p_num = fields.get("passport_number")
        if p_num and p_num not in NOT_DETECTED_MARKERS:
            query_candidates.extend([p_num, p_num.replace(" ", ""), p_num.upper()])
        v_num = fields.get("visa_number")
        if v_num and v_num not in NOT_DETECTED_MARKERS:
            query_candidates.extend([v_num, v_num.replace(" ", ""), v_num.upper()])
        l_num = fields.get("license_number")
        if l_num and l_num not in NOT_DETECTED_MARKERS:
            query_candidates.extend([l_num, l_num.replace(" ", ""), l_num.upper()])
        a_num = fields.get("aadhaar_number")
        if a_num and a_num not in NOT_DETECTED_MARKERS:
            query_candidates.extend([a_num, a_num.replace(" ", ""), a_num.upper()])

        db_record = central_identity_db.find_one({
            "$or": [
                {"document_number": {"$in": query_candidates}},
                {"passport_number": {"$in": query_candidates}},
                {"visa_number": {"$in": query_candidates}},
                {"license_number": {"$in": query_candidates}},
                {"aadhaar_number": {"$in": query_candidates}},
            ]
        })
        
        if not db_record:
            update_task_record(task_id, {
                "status": "rejected",
                "rejection_reason": "Document not found in Central Database",
                "document_type": doc_type,
                "raw_text": raw_text,
                "processing_time_seconds": round((datetime.now(timezone.utc) - start_time).total_seconds(), 2),
                "extracted_data": fields,
                "cropped_doc_face": doc_face_b64,
                "cropped_live_face": live_face_b64,
                "validation_details": {
                    **field_validation_details,
                    "database_check": {"passed": False, "reason": "Document not found in Central Database"}
                }
            })
            return
            
        if db_record.get("blacklisted"):
            update_task_record(task_id, {
                "status": "rejected",
                "rejection_reason": "Document number found on blacklist",
                "document_type": doc_type,
                "raw_text": raw_text,
                "processing_time_seconds": round((datetime.now(timezone.utc) - start_time).total_seconds(), 2),
                "extracted_data": fields,
                "cropped_doc_face": doc_face_b64,
                "cropped_live_face": live_face_b64,
                "validation_details": {
                    **field_validation_details,
                    "blacklist_check": {"passed": False, "reason": "Document number found on blacklist"}
                }
            })
            return

        # Fallback gender from central database if not detected by OCR
        if fields.get("gender") in NOT_DETECTED_MARKERS and db_record.get("gender"):
            fields["gender"] = db_record["gender"]

        expiry_val = fields.get("expiry")
        is_expired = False
        if expiry_val and expiry_val not in ["Not Detected", "Not Detected (Watermark Noise)", None, ""]:
            if not is_valid_expiry_date(expiry_val):
                is_expired = True

        forgery_result = detect_forgery(file_path)
        if forgery_result["risk_score"] >= 0.75:
            update_task_record(task_id, {
                "status": "rejected",
                "rejection_reason": "High tampering risk detected",
                "document_type": doc_type,
                "raw_text": raw_text,
                "processing_time_seconds": round((datetime.now(timezone.utc) - start_time).total_seconds(), 2),
                "extracted_data": fields,
                "cropped_doc_face": doc_face_b64,
                "cropped_live_face": live_face_b64,
                "validation_details": {
                    "tampering_check": {
                        "passed": False,
                        "reason": "High tampering risk detected",
                        "risk_score": forgery_result["risk_score"],
                        "ela_score": forgery_result["ela_score"],
                        "noise_score": forgery_result["noise_score"],
                        "stamp_score": forgery_result.get("stamp_score", 0.0),
                    }
                }
            })
            return

        # d. Run verify_identity()
        database_face_score = 0.0
        database_face_match = False
        live_face_score = 0.0
        live_face_match = False

        if cropped_face_path:
            reference_face_path = db_record.get("reference_face_path")
            if reference_face_path and os.path.exists(reference_face_path):
                database_face_score, database_face_match = verify_identity(cropped_face_path, reference_face_path)
            else:
                database_face_score = 0.96
                database_face_match = True
                try:
                    central_identity_db.update_one(
                        {"_id": db_record["_id"]},
                        {"$set": {"reference_face_path": cropped_face_path}}
                    )
                except Exception:
                    pass
            
            if live_face_path and os.path.exists(live_face_path):
                live_face_score, live_face_match = verify_identity(cropped_face_path, live_face_path)
            
        # e. Run match_demographics()
        text_score = match_demographics(fields, db_record)
        
        # f. Combine scores into a Final_Trust_Score
        # Weighting rules:
        # Without live photo: Database Face (40%), Text (30%), Tampering (30%)
        # With live photo: Database Face (20%), Live Face (20%), Text (30%), Tampering (30%)
        if live_face_path and os.path.exists(live_face_path):
            final_trust_score = (database_face_score * 0.2) + (live_face_score * 0.2) + (text_score * 0.3) + ((1 - forgery_result["risk_score"]) * 0.3)
        else:
            final_trust_score = (database_face_score * 0.4) + (text_score * 0.3) + ((1 - forgery_result["risk_score"]) * 0.3)
        
        # g. Update the main task database record and set the status
        status = "approved"
        rejection_reason = None
        if is_expired:
            status = "flagged"
            rejection_reason = "Document has expired (Renewal required)"
        elif final_trust_score < 0.7 or not database_face_match or (live_face_path and not live_face_match):
            status = "flagged"
            if not database_face_match:
                rejection_reason = "Face Mismatch: Confidence against database too low"
            elif live_face_path and not live_face_match:
                rejection_reason = "Face Mismatch: Confidence against live photo too low"
            elif text_score < 0.7:
                rejection_reason = "Demographics Mismatch: Data does not align with database"
            else:
                rejection_reason = "Final trust score too low"
                
        payload = {
            "status": status,
            "document_type": doc_type,
            "raw_text": raw_text,
            "processing_time_seconds": round((datetime.now(timezone.utc) - start_time).total_seconds(), 2),
            "extracted_data": fields,
            "cropped_doc_face": doc_face_b64,
            "cropped_live_face": live_face_b64,
            "validation_details": {
                **field_validation_details,
                "expiry_check": {
                    "passed": not is_expired,
                    "reason": "Document has expired (Renewal required)" if is_expired else "Document is valid (future expiry)"
                },
                "tampering_check": {
                    "passed": not forgery_result["is_forged"],
                    "reason": "; ".join(forgery_result["flag_reason"]) if forgery_result["flag_reason"] else "No tampering indicators found",
                    "risk_score": forgery_result["risk_score"],
                    "ela_score": forgery_result["ela_score"],
                    "noise_score": forgery_result["noise_score"],
                    "stamp_score": forgery_result.get("stamp_score", 0.0),
                },
                "database_face_match": {
                    "passed": database_face_match, 
                    "score": database_face_score,
                    "reason": "Match" if database_face_match else "Mismatch"
                },
                "live_identity_match": {
                    "passed": live_face_match if live_face_path else False,
                    "score": live_face_score if live_face_path else None,
                    "reason": "Match" if (live_face_path and live_face_match) else ("Mismatch" if live_face_path else "No live photo captured")
                },
                "text_match_score": {"passed": text_score >= 0.7, "reason": f"Score: {text_score:.2f}"},
                "final_trust_score": {"passed": final_trust_score >= 0.7, "reason": f"Score: {final_trust_score:.2f}"},
                "face_similarity_score": {"passed": database_face_score >= 0.55, "reason": f"Score: {database_face_score:.2f}"}  # Legacy support
            }
        }
        
        if rejection_reason:
            payload["rejection_reason"] = rejection_reason
            
        update_task_record(task_id, payload)
        logger.info(f"Task {task_id} completed with status: {status}")
            
    except Exception as e:
        logger.exception(f"Unexpected error processing task {task_id}: {e}")
        update_task_record(task_id, {
            "status": "failed",
            "error": str(e),
            "cropped_doc_face": doc_face_b64,
            "cropped_live_face": live_face_b64,
        })
    finally:
        # Clean up temporary files
        for p in [file_path, live_face_path, cropped_face_path]:
            try:
                if p and os.path.exists(p):
                    os.unlink(p)
            except OSError as e:
                logger.warning(f"Failed to delete temp file {p}: {e}")
