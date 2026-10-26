import logging
from datetime import datetime, timezone
from pymongo import MongoClient
from werkzeug.security import generate_password_hash, check_password_hash
from config import Config

logger = logging.getLogger(__name__)

# Initialize MongoDB client
try:
    client = MongoClient(Config.MONGO_URI, serverSelectionTimeoutMS=5000)
    db = client[Config.MONGO_DB_NAME]
    tasks_collection = db["tasks"]
    central_identity_db = db["central_identity_db"]
    users_collection = db["users"]
except Exception as e:
    logger.error(f"Failed to connect to MongoDB: {e}")
    db = None
    tasks_collection = None
    central_identity_db = None
    users_collection = None

def create_task_record(task_id: str, file_path: str):
    """Create a new task record in MongoDB."""
    if tasks_collection is None:
        logger.error("Database connection is not established.")
        return

    record = {
        "_id": task_id,
        "status": "pending",
        "file_path": file_path,
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
        "extracted_data": None,
        "validation_details": None,
        "error": None,
        "reviewed_by": None,
        "officer_decision": None,
        "reviewed_at": None,
        "review_notes": None,
        "document_type": None,
        "raw_text": None,
        "processing_time_seconds": None
    }
    
    try:
        tasks_collection.insert_one(record)
        logger.info(f"Created task record for {task_id}")
    except Exception as e:
        logger.error(f"Error creating task record {task_id}: {e}")

def update_task_record(task_id: str, updates: dict):
    """Update an existing task record."""
    if tasks_collection is None:
        return

    updates["updated_at"] = datetime.now(timezone.utc)
    try:
        tasks_collection.update_one({"_id": task_id}, {"$set": updates})
        logger.info(f"Updated task record for {task_id} with status: {updates.get('status')}")
    except Exception as e:
        logger.error(f"Error updating task record {task_id}: {e}")

def get_task_record(task_id: str) -> dict:
    """Retrieve a task record by ID."""
    if tasks_collection is None:
        return None
    
    try:
        return tasks_collection.find_one({"_id": task_id})
    except Exception as e:
        logger.error(f"Error retrieving task record {task_id}: {e}")
        return None

def list_task_records(limit: int = 50, status_filter: str = None, doc_type_filter: str = None) -> list:
    """Retrieve a list of task records, sorted by creation date descending."""
    if tasks_collection is None:
        return []
        
    query = {}
    if status_filter and status_filter.lower() != "all":
        query["status"] = status_filter.lower()
    if doc_type_filter and doc_type_filter.lower() != "all":
        query["document_type"] = {"$regex": f"^{doc_type_filter}$", "$options": "i"}
        
    projection = {
        "_id": 1,
        "document_type": 1,
        "status": 1,
        "created_at": 1,
        "reviewed_by": 1,
        "officer_decision": 1,
        "validation_details.final_trust_score": 1,
        "rejection_reason": 1
    }
    
    try:
        cursor = tasks_collection.find(query, projection).sort("created_at", -1).limit(limit)
        return list(cursor)
    except Exception as e:
        logger.error(f"Error listing task records: {e}")
        return []

# -------------------------------------------------------------------------
# User Authentication & Management
# -------------------------------------------------------------------------

# In-memory fallback accounts (ensures system runs even if Mongo is unseeded/offline)
FALLBACK_USERS = {
    "SSB-88429-DEL": {
        "officer_id": "SSB-88429-DEL",
        "password_hash": generate_password_hash("password123"),
        "name": "Officer Desk",
        "role": "officer",
        "checkpoint": "igi",
        "status": "active"
    },
    "SSB-10492-ATT": {
        "officer_id": "SSB-10492-ATT",
        "password_hash": generate_password_hash("password123"),
        "name": "Supervisor Singh",
        "role": "supervisor",
        "checkpoint": "attari",
        "status": "active"
    },
    "SSB-99011-RAX": {
        "officer_id": "SSB-99011-RAX",
        "password_hash": generate_password_hash("password123"),
        "name": "Investigator Verma",
        "role": "investigator",
        "checkpoint": "nepal",
        "status": "active"
    },
    "ADMIN-001": {
        "officer_id": "ADMIN-001",
        "password_hash": generate_password_hash("admin123"),
        "name": "System Admin",
        "role": "admin",
        "checkpoint": "igi",
        "status": "active"
    }
}

def get_user_by_officer_id(officer_id: str) -> dict | None:
    """Retrieve an officer by officer_id from MongoDB or fallback storage."""
    if not officer_id:
        return None
    
    officer_id = officer_id.strip()
    
    if users_collection is not None:
        try:
            user = users_collection.find_one({"officer_id": {"$regex": f"^{officer_id}$", "$options": "i"}})
            if user:
                return user
        except Exception as e:
            logger.error(f"Error querying user from MongoDB: {e}")
            
    # Check fallback in-memory users
    for key, user in FALLBACK_USERS.items():
        if key.lower() == officer_id.lower():
            return user
            
    return None

def create_user(officer_id: str, password: str, name: str = "Officer Desk", 
                role: str = "officer", checkpoint: str = "igi", status: str = "active") -> bool:
    """Create or upsert an officer account."""
    if not officer_id or not password:
        return False
        
    officer_id = officer_id.strip()
    user_doc = {
        "_id": officer_id,
        "officer_id": officer_id,
        "password_hash": generate_password_hash(password),
        "name": name,
        "role": role,
        "checkpoint": checkpoint,
        "status": status,
        "created_at": datetime.now(timezone.utc),
        "last_login": None,
        "last_checkpoint": checkpoint
    }
    
    # Store in fallback
    FALLBACK_USERS[officer_id] = user_doc
    
    if users_collection is not None:
        try:
            users_collection.update_one(
                {"officer_id": officer_id},
                {"$set": user_doc},
                upsert=True
            )
            logger.info(f"Created/updated user {officer_id} in MongoDB")
            return True
        except Exception as e:
            logger.error(f"Error saving user to MongoDB: {e}")
            return False
    return True

def verify_user(officer_id: str, password: str, role: str = None, checkpoint: str = None) -> tuple[bool, dict | None, str]:
    """Verify officer credentials.
    
    Returns:
        (is_valid: bool, user_info: dict | None, error_message: str)
    """
    if not officer_id or not password:
        return False, None, "Officer ID and Password are required."
        
    officer_id = officer_id.strip()
    user = get_user_by_officer_id(officer_id)
    if not user:
        return False, None, "Invalid Officer ID or Service Number."
        
    if user.get("status") and user.get("status") != "active":
        return False, None, f"Account is {user.get('status')}. Contact station administrator."
        
    pw_hash = user.get("password_hash")
    valid_pw = False
    if pw_hash:
        try:
            valid_pw = check_password_hash(pw_hash, password)
        except Exception:
            valid_pw = False
            
    # Backwards-compatible plain-text check if not hashed
    if not valid_pw and user.get("password") == password:
        valid_pw = True
        
    if not valid_pw:
        return False, None, "Invalid password or security PIN."
        
    user_role = user.get("role", "officer")
    if role and user_role != "admin" and role.lower() != user_role.lower():
        return False, None, f"Officer {officer_id} is not authorized for designated role '{role}'."
        
    updates = {
        "last_login": datetime.now(timezone.utc),
        "last_checkpoint": checkpoint or user.get("checkpoint")
    }
    
    if users_collection is not None:
        try:
            users_collection.update_one({"officer_id": user["officer_id"]}, {"$set": updates})
        except Exception as e:
            logger.warning(f"Could not update last_login for {officer_id}: {e}")
            
    user_info = {
        "officer_id": user["officer_id"],
        "name": user.get("name", "Officer Desk"),
        "role": role or user.get("role", "officer"),
        "checkpoint": checkpoint or user.get("checkpoint", "igi")
    }
    return True, user_info, ""

