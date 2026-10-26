import os

class Config:
    SECRET_KEY = os.environ.get("SECRET_KEY", "sentinel-oversight-border-secret-key-2024")
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REDIS_URL = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
    MONGO_URI = os.environ.get("MONGO_URI", "mongodb://localhost:27017/")
    MONGO_DB_NAME = os.environ.get("MONGO_DB_NAME", "document_screening")
    MAX_CONTENT_LENGTH = 20 * 1024 * 1024  # 20 MB max upload
