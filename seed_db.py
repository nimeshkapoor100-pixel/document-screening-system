import json
from database import central_identity_db
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

dummy_records = [
    {
        "document_number": "2341 2341 2346",
        "name": "Siddharth Rao",
        "dob": "14-08-1992",
        "address": "Flat 4B, Sunflower Apartments, Koramangala, Bengaluru, Karnataka 560034",
        "reference_face_path": "sample_docs/dummy_face_1.jpg",
        "blacklisted": False
    },
    {
        "document_number": "P7654321",
        "name": "Ananya Sharma",
        "dob": "22-11-1988",
        "address": "12/A, MG Road, Pune, Maharashtra 411001",
        "reference_face_path": "sample_docs/dummy_face_2.jpg",
        "blacklisted": False
    },
    {
        "document_number": "MH12 20150045678",
        "name": "Rahul Verma",
        "dob": "05-02-1995",
        "address": "Plot 56, Sector 12, Vashi, Navi Mumbai, Maharashtra 400703",
        "reference_face_path": "sample_docs/dummy_face_3.jpg",
        "blacklisted": True
    },
    {
        "document_number": "W5469900",
        "passport_number": "W5469900",
        "name": "Harmeet Singh",
        "dob": "10-11-2002",
        "gender": "Male",
        "nationality": "INDIAN",
        "address": "VILLAGE KURRAIYA KALAN PO/PS BILSANDA, TEHSIL BISALPUR, PILIBHIT, UTTAR PRADESH 262202",
        "blacklisted": False
    },
    {
        "document_number": "B7965523",
        "passport_number": "B7965523",
        "name": "Md Mudassir Kazi",
        "dob": "12-05-1994",
        "gender": "Male",
        "nationality": "INDIAN",
        "address": "NOWDIHA BOKARO, JHARKHAND",
        "blacklisted": False
    },
    {
        "document_number": "L9859125",
        "passport_number": "L9859125",
        "name": "Gurjinder Singh",
        "dob": "04-03-1991",
        "gender": "Male",
        "nationality": "INDIAN",
        "address": "OTTU DHANI SAROOP SINGH, HARYANA",
        "blacklisted": False
    },
    {
        "document_number": "C6149107",
        "visa_number": "C6149107",
        "passport_number": "H8150402",
        "name": "Assia Nasreen",
        "dob": "25-01-1965",
        "gender": "Female",
        "nationality": "INDIAN",
        "blacklisted": False
    },
    {
        "document_number": "H8150402",
        "visa_number": "C6149107",
        "passport_number": "H8150402",
        "name": "Assia Nasreen",
        "dob": "25-01-1965",
        "gender": "Female",
        "nationality": "INDIAN",
        "blacklisted": False
    },
    {
        "document_number": "U4809419",
        "visa_number": "U4809419",
        "passport_number": "Y9036838",
        "name": "Deepanjali Vinodh Kumar",
        "dob": "21-10-1986",
        "gender": "Female",
        "nationality": "INDIAN",
        "blacklisted": False
    },
    {
        "document_number": "Y9036838",
        "visa_number": "U4809419",
        "passport_number": "Y9036838",
        "name": "Deepanjali Vinodh Kumar",
        "dob": "21-10-1986",
        "gender": "Female",
        "nationality": "INDIAN",
        "blacklisted": False
    }
]

officer_accounts = [
    {
        "officer_id": "SSB-88429-DEL",
        "password": "password123",
        "name": "Officer Desk (Delhi)",
        "role": "officer",
        "checkpoint": "igi",
        "status": "active"
    },
    {
        "officer_id": "SSB-10492-ATT",
        "password": "password123",
        "name": "Supervisor Singh (Attari)",
        "role": "supervisor",
        "checkpoint": "attari",
        "status": "active"
    },
    {
        "officer_id": "SSB-99011-RAX",
        "password": "password123",
        "name": "Investigator Verma (Raxaul)",
        "role": "investigator",
        "checkpoint": "nepal",
        "status": "active"
    },
    {
        "officer_id": "ADMIN-001",
        "password": "admin123",
        "name": "System Administrator",
        "role": "admin",
        "checkpoint": "igi",
        "status": "active"
    }
]

def seed():
    from database import create_user
    
    # Seed officer accounts
    try:
        for officer in officer_accounts:
            create_user(
                officer_id=officer["officer_id"],
                password=officer["password"],
                name=officer["name"],
                role=officer["role"],
                checkpoint=officer["checkpoint"],
                status=officer["status"]
            )
        logger.info(f"Successfully seeded {len(officer_accounts)} officer accounts.")
    except Exception as e:
        logger.error(f"Error seeding officer accounts: {e}")

    if central_identity_db is None:
        logger.error("Database connection is not established. Cannot seed central_identity_db.")
        return

    # Safely upsert records without wiping user records
    try:
        for r in dummy_records:
            central_identity_db.update_one(
                {"document_number": r["document_number"]},
                {"$set": r},
                upsert=True
            )
        logger.info(f"Successfully seeded/updated {len(dummy_records)} records in central_identity_db.")
    except Exception as e:
        logger.error(f"Error seeding database: {e}")

if __name__ == "__main__":
    seed()

