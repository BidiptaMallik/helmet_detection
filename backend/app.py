"""
HelmetGuard AI — FastAPI backend

Features:
    1. Helmet detection
    2. Number plate detection
    3. OCR using EasyOCR
    4. MongoDB violation storage
    5. Image detection
    6. Video detection
    7. Live uploaded-video WebSocket detection
    8. Webcam detection
    9. CCTV / RTSP detection
    10. Garbage detection
    11. Pothole detection
    12. Traffic / congestion detection

Run:
    uvicorn app:app --reload --port 8000
"""

# ============================================================
# IMPORTS
# ============================================================

import os
import datetime
import base64
import asyncio
import uuid
import hashlib
import hmac
import re
import secrets
from http.cookies import SimpleCookie
from contextlib import asynccontextmanager

from pathlib import Path
from typing import Optional

import cv2
import numpy as np

from dotenv import load_dotenv

from fastapi import (
    FastAPI,
    UploadFile,
    File,
    Form,
    HTTPException,
    Query,
    Request,
    Response,
    WebSocket,
    WebSocketDisconnect,
)

from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from pydantic import BaseModel, Field

from pymongo import MongoClient
from bson import ObjectId


# ============================================================
# ENVIRONMENT
# ============================================================

load_dotenv()


# ============================================================
# LAZY MODEL VARIABLES
# ============================================================

_YOLO = None
_EASYOCR_READER = None

_helmet_model = None
_plate_model = None
_garbage_model = None
_pothole_model = None
_traffic_model = None

# Lock used by all traffic streams so every stream safely shares
# the SAME loaded congestion.pt YOLO model.
TRAFFIC_INFERENCE_LOCK = asyncio.Lock()


# ============================================================
# BASE DIRECTORY
# ============================================================

BASE_DIR = Path(__file__).resolve().parent


# ============================================================
# MODEL PATHS
# ============================================================

HELMET_MODEL_PATH = str(
    BASE_DIR / "models" / "helmet_model.pt"
)

PLATE_MODEL_PATH = str(
    BASE_DIR / "models" / "plate_model.pt"
)

GARBAGE_MODEL_PATH = str(
    BASE_DIR / "models" / "garbage_model.pt"
)

# Keep your actual filename
POTHOLE_MODEL_PATH = str(
    BASE_DIR / "models" / "pathhole.pt"
)

TRAFFIC_MODEL_PATH = str(
    BASE_DIR / "models" / "congestion.pt"
)


# ============================================================
# MONGODB
# ============================================================

MONGO_URI = os.getenv("MONGO_URI")

if not MONGO_URI:
    raise RuntimeError(
        "MONGO_URI not found in .env file"
    )

MONGO_DB = "traffic_violations"

MODEL_COLLECTIONS = {
    "helmet": "no_helmet_records",
    "traffic": "traffic_records",
    "garbage": "garbage_records",
    "pothole": "pothole_records",
}

# Keep reading existing records while new detections use model collections.
LEGACY_COLLECTION_NAME = "smart_city_records"
AUTH_USERS_COLLECTION = "users"
AUTH_SESSIONS_COLLECTION = "user_sessions"
AUTH_SETTINGS_COLLECTION = "auth_settings"
ISSUE_REPORTS_COLLECTION = "issue_reports"
REPORT_UPDATES_COLLECTION = "report_updates"
SESSION_COOKIE_NAME = "traffic_session"
SESSION_MAX_AGE = 7 * 24 * 60 * 60
MAX_REPORT_PHOTO_BYTES = 8 * 1024 * 1024
VALID_REPORT_TYPES = {"traffic", "garbage", "pothole"}
AUTH_COOKIE_SECURE = os.getenv("AUTH_COOKIE_SECURE", "false").lower() == "true"
ADMIN_SETUP_KEY = os.getenv("ADMIN_SETUP_KEY", "")


# ============================================================
# DIRECTORIES
# ============================================================

SAVE_FRAMES_DIR = BASE_DIR / "violation_frames"
SAVE_FRAMES_DIR.mkdir(
    parents=True,
    exist_ok=True
)

UPLOAD_TMP_DIR = BASE_DIR / "tmp_uploads"
UPLOAD_TMP_DIR.mkdir(
    parents=True,
    exist_ok=True
)

REPORT_PHOTOS_DIR = BASE_DIR / "report_photos"
REPORT_PHOTOS_DIR.mkdir(
    parents=True,
    exist_ok=True
)


# ============================================================
# CONFIDENCE SETTINGS
# ============================================================

# IMPORTANT:
# Increased from 0.2 to 0.5 to reduce false helmet detections.
CONFIDENCE_HELMET = float(
    os.getenv(
        "CONFIDENCE_HELMET",
        0.5
    )
)

CONFIDENCE_PLATE = float(
    os.getenv(
        "CONFIDENCE_PLATE",
        0.3
    )
)

CONFIDENCE_GARBAGE = float(
    os.getenv(
        "CONFIDENCE_GARBAGE",
        0.2
    )
)

CONFIDENCE_POTHOLE = float(
    os.getenv(
        "CONFIDENCE_POTHOLE",
        0.2
    )
)

CONFIDENCE_TRAFFIC = float(
    os.getenv(
        "CONFIDENCE_TRAFFIC",
        0.25
    )
)

# Simple vehicle-count thresholds used to display a congestion level.
# Adjust these for your camera/location if needed.
TRAFFIC_LOW_MAX = int(os.getenv("TRAFFIC_LOW_MAX", "5"))
TRAFFIC_MEDIUM_MAX = int(os.getenv("TRAFFIC_MEDIUM_MAX", "12"))


# ============================================================
# VIDEO SETTINGS
# ============================================================

MAX_VIDEO_FRAMES = 300


# ============================================================
# FASTAPI
# ============================================================

class RoleGateMiddleware:

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope_type = scope.get("type")
        path = scope.get("path", "")
        method = scope.get("method", "").upper()

        protected = (
            path.startswith("/api/")
            or path.startswith("/ws/")
            or path.startswith("/frames/")
        )
        if not protected:
            await self.app(scope, receive, send)
            return

        if scope_type == "http" and (
            (path == "/api/auth/login" and method == "POST")
            or (path == "/api/auth/register" and method == "POST")
            or (path == "/api/auth/admin-setup" and method == "POST")
        ):
            await self.app(scope, receive, send)
            return

        headers = dict(scope.get("headers", []))
        cookie = SimpleCookie()
        try:
            cookie.load(headers.get(b"cookie", b"").decode("latin-1"))
            session_cookie = cookie.get(SESSION_COOKIE_NAME)
            token = session_cookie.value if session_cookie else ""
        except Exception:
            token = ""

        user = (
            await asyncio.to_thread(resolve_session_user, token)
            if token
            else None
        )

        if not user:
            if scope_type == "websocket":
                await send({"type": "websocket.close", "code": 4401})
            else:
                response = JSONResponse(
                    {"detail": "Authentication required"},
                    status_code=401,
                )
                await response(scope, receive, send)
            return

        scope.setdefault("state", {})["current_user"] = user

        is_user_action = (
            (path == "/api/reports" and method == "POST")
            or path in {"/api/auth/me", "/api/auth/logout"}
            or (path == "/api/reports/mine" and method == "GET")
            or (
                method == "DELETE"
                and re.fullmatch(r"/api/reports/[0-9a-fA-F]{24}", path)
            )
            or (
                method == "GET"
                and re.fullmatch(r"/api/reports/[0-9a-fA-F]{24}/updates", path)
            )
            or (
                method == "POST"
                and re.fullmatch(r"/api/reports/[0-9a-fA-F]{24}/rating", path)
            )
            or (
                method == "GET"
                and re.fullmatch(
                    r"/api/reports/[0-9a-fA-F]{24}/photos/(original|resolution|update)",
                    path,
                )
            )
            or (
                method == "GET"
                and re.fullmatch(
                    r"/api/reports/[0-9a-fA-F]{24}/updates/[0-9a-fA-F]{24}/photo",
                    path,
                )
            )
        )
        if not is_user_action and user["role"] != "admin":
            if scope_type == "websocket":
                await send({"type": "websocket.close", "code": 4403})
            else:
                response = JSONResponse(
                    {"detail": "Administrator access required"},
                    status_code=403,
                )
                await response(scope, receive, send)
            return

        await self.app(scope, receive, send)


@asynccontextmanager
async def lifespan(_app):
    await asyncio.to_thread(ensure_model_collections)
    yield


app = FastAPI(
    title="HelmetGuard AI",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(RoleGateMiddleware)


# ============================================================
# CORS
# ============================================================

FRONTEND_ORIGINS = [
    origin.strip()
    for origin in os.getenv(
        "FRONTEND_ORIGINS",
        "http://localhost:5173,http://localhost:5174,"
        "http://localhost:5175,http://127.0.0.1:5173,"
        "http://127.0.0.1:5174,http://127.0.0.1:5175",
    ).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONTEND_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# STATIC FRAMES
# ============================================================

app.mount(
    "/frames",
    StaticFiles(
        directory=str(SAVE_FRAMES_DIR)
    ),
    name="frames"
)


# ============================================================
# MONGODB CLIENT
# ============================================================

_client: Optional[MongoClient] = None


def get_mongo_client():

    global _client

    if _client is None:

        _client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=4000
        )

    return _client


def get_collection():
    return get_model_collection("helmet")


def get_model_collection(feature: str):

    collection_name = MODEL_COLLECTIONS.get(feature)

    if collection_name is None:
        raise ValueError(f"Unknown detection model: {feature}")

    return get_mongo_client()[MONGO_DB][collection_name]


def get_generic_collection():

    client = get_mongo_client()

    return client[
        MONGO_DB
    ][
        LEGACY_COLLECTION_NAME
    ]


def get_users_collection():
    return get_mongo_client()[MONGO_DB][AUTH_USERS_COLLECTION]


def get_sessions_collection():
    return get_mongo_client()[MONGO_DB][AUTH_SESSIONS_COLLECTION]


def get_auth_settings_collection():
    return get_mongo_client()[MONGO_DB][AUTH_SETTINGS_COLLECTION]


def get_issue_reports_collection():
    return get_mongo_client()[MONGO_DB][ISSUE_REPORTS_COLLECTION]


def get_report_updates_collection():
    return get_mongo_client()[MONGO_DB][REPORT_UPDATES_COLLECTION]


def delete_issue_report(report_id: str, owner_id: Optional[str] = None):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")

    report_object_id = ObjectId(report_id)
    query = {"_id": report_object_id}
    if owner_id is not None:
        query["user_id"] = owner_id

    report = get_issue_reports_collection().find_one(query)
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    report_id = str(report_object_id)
    updates = list(
        get_report_updates_collection().find({"report_id": report_id})
    )
    photo_names = {
        report.get("photo_name"),
        report.get("resolution_photo_name"),
        report.get("latest_update_photo_name"),
    }
    for update in updates:
        photo_names.add(update.get("photo_name"))
        photo_names.add(update.get("resolution_photo_name"))

    get_issue_reports_collection().delete_one(query)
    get_report_updates_collection().delete_many({"report_id": report_id})

    for photo_name in photo_names - {None, ""}:
        if Path(photo_name).name != photo_name:
            continue
        try:
            (REPORT_PHOTOS_DIR / photo_name).unlink(missing_ok=True)
        except OSError as error:
            print(f"[REPORT] Could not remove report photo {photo_name}: {error}")

    return {"id": report_id, "deleted": True}


async def save_report_photo(photo: UploadFile, prefix: str) -> str:
    if not (photo.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload an image file.")

    photo_bytes = await photo.read(MAX_REPORT_PHOTO_BYTES + 1)
    if len(photo_bytes) > MAX_REPORT_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="The photo must be 8 MB or smaller.")

    image = cv2.imdecode(np.frombuffer(photo_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="The uploaded photo could not be read.")

    photo_name = f"{prefix}_{uuid.uuid4().hex}.jpg"
    photo_path = REPORT_PHOTOS_DIR / photo_name
    if not cv2.imwrite(str(photo_path), image):
        raise HTTPException(status_code=500, detail="The report photo could not be saved.")
    return photo_name


def utc_now():
    return datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt,
        310_000,
    )
    return f"{salt.hex()}${digest.hex()}"


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        salt_hex, digest_hex = stored_hash.split("$", 1)
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            bytes.fromhex(salt_hex),
            310_000,
        )
        return hmac.compare_digest(digest.hex(), digest_hex)
    except (ValueError, TypeError):
        return False


def safe_user(user: dict) -> dict:
    return {
        "id": str(user["_id"]),
        "name": user["name"],
        "email": user["email"],
        "phone": user.get("phone", ""),
        "role": user["role"],
    }


def resolve_session_user(token: str) -> Optional[dict]:
    token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
    session = get_sessions_collection().find_one({"token_hash": token_hash})
    if not session:
        return None

    if session["expires_at"] <= utc_now():
        get_sessions_collection().delete_one({"_id": session["_id"]})
        return None

    try:
        user_id = ObjectId(session["user_id"])
    except Exception:
        return None

    user = get_users_collection().find_one({"_id": user_id})
    return safe_user(user) if user else None


def create_session(user: dict) -> str:
    token = secrets.token_urlsafe(32)
    now = utc_now()
    get_sessions_collection().insert_one({
        "token_hash": hashlib.sha256(token.encode("utf-8")).hexdigest(),
        "user_id": str(user["_id"]),
        "created_at": now,
        "expires_at": now + datetime.timedelta(seconds=SESSION_MAX_AGE),
    })
    return token


def set_session_cookie(response: Response, user: dict):
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=create_session(user),
        max_age=SESSION_MAX_AGE,
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def ensure_model_collections():

    try:
        database = get_mongo_client()[MONGO_DB]
        existing = set(database.list_collection_names())

        collection_names = [
            *MODEL_COLLECTIONS.values(),
            AUTH_USERS_COLLECTION,
            AUTH_SESSIONS_COLLECTION,
            AUTH_SETTINGS_COLLECTION,
            ISSUE_REPORTS_COLLECTION,
            REPORT_UPDATES_COLLECTION,
        ]
        for collection_name in collection_names:
            if collection_name not in existing:
                database.create_collection(collection_name)
                existing.add(collection_name)

        database[AUTH_USERS_COLLECTION].create_index("email", unique=True)
        database[AUTH_SESSIONS_COLLECTION].create_index(
            "expires_at",
            expireAfterSeconds=0,
        )
        database[ISSUE_REPORTS_COLLECTION].create_index(
            [("created_at", -1)]
        )
        database[REPORT_UPDATES_COLLECTION].create_index(
            [("report_id", 1), ("created_at", 1)]
        )

        admin_email = os.getenv("ADMIN_EMAIL", "").strip().lower()
        admin_password = os.getenv("ADMIN_PASSWORD", "")
        if admin_email and len(admin_password) >= 12:
            now = utc_now()
            database[AUTH_USERS_COLLECTION].update_one(
                {"email": admin_email},
                {
                    "$set": {
                        "name": os.getenv("ADMIN_NAME", "Administrator").strip(),
                        "role": "admin",
                        "password_hash": hash_password(admin_password),
                        "updated_at": now,
                    },
                    "$setOnInsert": {
                        "email": admin_email,
                        "phone": "",
                        "created_at": now,
                    },
                },
                upsert=True,
            )
        elif admin_email or admin_password:
            print(
                "[AUTH] Admin bootstrap needs ADMIN_EMAIL and an "
                "ADMIN_PASSWORD of at least 12 characters."
            )
        elif len(ADMIN_SETUP_KEY) >= 32:
            print(
                "[AUTH] Initial admin setup is enabled at /admin/register."
            )
        else:
            print(
                "[AUTH] No admin account was provisioned. Set ADMIN_EMAIL and "
                "ADMIN_PASSWORD, or a 32+ character ADMIN_SETUP_KEY, in backend/.env."
            )

    except Exception as error:
        print(
            "[MONGO ERROR] Could not initialize application collections: "
            f"{error}"
        )


# ============================================================
# YOLO IMPORT
# ============================================================

def _lazy_imports():

    global _YOLO

    if _YOLO is None:

        from ultralytics import YOLO

        _YOLO = YOLO


# ============================================================
# TRAFFIC / CONGESTION MODEL
# ============================================================

def get_traffic_model():

    global _traffic_model

    _lazy_imports()

    if _traffic_model is None:

        if not os.path.exists(TRAFFIC_MODEL_PATH):

            raise HTTPException(
                status_code=500,
                detail=(
                    "Traffic congestion model weights not found at "
                    f"{TRAFFIC_MODEL_PATH}"
                )
            )

        _traffic_model = _YOLO(
            TRAFFIC_MODEL_PATH
        )

        print(
            f"[MODEL] Traffic model loaded: {TRAFFIC_MODEL_PATH}"
        )

        print(
            f"[MODEL] Traffic classes: {_traffic_model.names}"
        )

    return _traffic_model


# ============================================================
# HELMET MODEL
# ============================================================

def get_helmet_model():

    global _helmet_model

    _lazy_imports()

    if _helmet_model is None:

        if not os.path.exists(
            HELMET_MODEL_PATH
        ):

            raise HTTPException(
                status_code=500,
                detail=(
                    "Helmet model weights not found at "
                    f"{HELMET_MODEL_PATH}"
                )
            )

        _helmet_model = _YOLO(
            HELMET_MODEL_PATH
        )

        print(
            "\n========================================"
        )

        print(
            "HELMET MODEL LOADED"
        )

        print(
            f"Path: {HELMET_MODEL_PATH}"
        )

        print(
            f"Classes: {_helmet_model.names}"
        )

        print(
            f"Confidence threshold: {CONFIDENCE_HELMET}"
        )

        print(
            "========================================\n"
        )

    return _helmet_model


# ============================================================
# PLATE MODEL
# ============================================================

def get_plate_model():

    global _plate_model

    _lazy_imports()

    if _plate_model is None:

        if not os.path.exists(
            PLATE_MODEL_PATH
        ):

            raise HTTPException(
                status_code=500,
                detail=(
                    "Plate model weights not found at "
                    f"{PLATE_MODEL_PATH}"
                )
            )

        _plate_model = _YOLO(
            PLATE_MODEL_PATH
        )

        print(
            f"[MODEL] Plate model loaded: "
            f"{PLATE_MODEL_PATH}"
        )

        print(
            f"[MODEL] Plate classes: "
            f"{_plate_model.names}"
        )

    return _plate_model


# ============================================================
# GARBAGE MODEL
# ============================================================

def get_garbage_model():

    global _garbage_model

    _lazy_imports()

    if _garbage_model is None:

        if not os.path.exists(
            GARBAGE_MODEL_PATH
        ):

            raise HTTPException(
                status_code=500,
                detail=(
                    "Garbage model weights not found at "
                    f"{GARBAGE_MODEL_PATH}"
                )
            )

        _garbage_model = _YOLO(
            GARBAGE_MODEL_PATH
        )

        print(
            f"[MODEL] Garbage model loaded: "
            f"{GARBAGE_MODEL_PATH}"
        )

        print(
            f"[MODEL] Garbage classes: "
            f"{_garbage_model.names}"
        )

    return _garbage_model


# ============================================================
# POTHOLE MODEL
# ============================================================

def get_pothole_model():

    global _pothole_model

    _lazy_imports()

    if _pothole_model is None:

        if not os.path.exists(
            POTHOLE_MODEL_PATH
        ):

            raise HTTPException(
                status_code=500,
                detail=(
                    "Pothole model weights not found at "
                    f"{POTHOLE_MODEL_PATH}"
                )
            )

        _pothole_model = _YOLO(
            POTHOLE_MODEL_PATH
        )

        print(
            f"[MODEL] Pothole model loaded: "
            f"{POTHOLE_MODEL_PATH}"
        )

        print(
            f"[MODEL] Pothole classes: "
            f"{_pothole_model.names}"
        )

    return _pothole_model


# ============================================================
# OCR
# ============================================================

def get_ocr_reader():

    global _EASYOCR_READER

    if _EASYOCR_READER is None:

        import easyocr

        print(
            "[OCR] Loading EasyOCR..."
        )

        _EASYOCR_READER = easyocr.Reader(
            ["en"],
            gpu=False
        )

        print(
            "[OCR] EasyOCR loaded."
        )

    return _EASYOCR_READER


# ============================================================
# PYDANTIC MODELS
# ============================================================

class ViolationOut(BaseModel):

    id: str
    plate_number: str
    timestamp: datetime.datetime
    source: str
    image_url: str


class DetectionBox(BaseModel):

    label: str
    confidence: float
    box: list[int]


class DetectResponse(BaseModel):

    violations_found: int
    plates: list[str]
    detections: list[DetectionBox]
    annotated_image_base64: str
    saved: list[ViolationOut]


class StatsResponse(BaseModel):

    total_violations: int
    today: int
    unique_plates: int
    last_7_days: list[dict]
    traffic_events: int = 0
    garbage_detected: int = 0
    potholes_detected: int = 0
    cars: int = 0
    bikes: int = 0
    rickshaws: int = 0


class GenericRecordOut(BaseModel):

    id: str
    detail: str
    timestamp: datetime.datetime
    source: str
    image_url: str


class GenericDetectResponse(BaseModel):

    detections_found: int
    detections: list[DetectionBox]
    annotated_image_base64: str
    saved: Optional[GenericRecordOut] = None


class LoginRequest(BaseModel):
    email: str
    password: str


class RegisterRequest(BaseModel):
    name: str
    email: str
    phone: str
    password: str


class AdminSetupRequest(BaseModel):
    setup_key: str
    name: str
    email: str
    password: str


class ReportStatusRequest(BaseModel):
    status: str


class ReportRatingRequest(BaseModel):
    rating: int = Field(ge=1, le=5)
    comment: str = Field(default="", max_length=1000)


@app.post("/api/auth/admin-setup")
def setup_initial_admin(body: AdminSetupRequest, response: Response):
    if len(ADMIN_SETUP_KEY) < 32 or not hmac.compare_digest(
        body.setup_key,
        ADMIN_SETUP_KEY,
    ):
        raise HTTPException(status_code=403, detail="Administrator setup is not available.")

    users = get_users_collection()
    if users.count_documents({"role": "admin"}):
        raise HTTPException(
            status_code=409,
            detail="An administrator account already exists.",
        )

    name = body.name.strip()
    email = body.email.strip().lower()
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Enter your name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if len(body.password) < 12:
        raise HTTPException(
            status_code=400,
            detail="Use a password with at least 12 characters.",
        )
    if users.find_one({"email": email}):
        raise HTTPException(status_code=409, detail="An account already uses this email.")

    settings = get_auth_settings_collection()
    claim_id = secrets.token_urlsafe(24)
    now = utc_now()
    try:
        settings.update_one(
            {
                "_id": "initial_admin_setup",
                "complete": {"$ne": True},
                "claim_id": {"$exists": False},
            },
            {"$set": {"claim_id": claim_id, "claimed_at": now}},
            upsert=True,
        )
    except Exception:
        claim = settings.find_one({"_id": "initial_admin_setup"})
        if claim and (claim.get("complete") or claim.get("claim_id")):
            raise HTTPException(
                status_code=409,
                detail="Administrator setup is already complete or underway.",
            )
        raise HTTPException(status_code=503, detail="Administrator setup is unavailable.")

    claim = settings.find_one({"_id": "initial_admin_setup"})
    if not claim or claim.get("claim_id") != claim_id:
        raise HTTPException(
            status_code=409,
            detail="Administrator setup is already complete or underway.",
        )

    user = {
        "name": name,
        "email": email,
        "phone": "",
        "role": "admin",
        "password_hash": hash_password(body.password),
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = users.insert_one(user)
        user["_id"] = result.inserted_id
        settings.update_one(
            {"_id": "initial_admin_setup", "claim_id": claim_id},
            {
                "$set": {
                    "complete": True,
                    "admin_user_id": str(result.inserted_id),
                    "completed_at": utc_now(),
                },
                "$unset": {"claim_id": ""},
            },
        )
    except Exception:
        settings.delete_one({"_id": "initial_admin_setup", "claim_id": claim_id})
        raise HTTPException(status_code=409, detail="Administrator account could not be created.")

    set_session_cookie(response, user)
    return {"user": safe_user(user)}


@app.post("/api/auth/register")
def register_user(body: RegisterRequest, response: Response):
    name = body.name.strip()
    email = body.email.strip().lower()
    phone = body.phone.strip()

    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Enter your name.")
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", email):
        raise HTTPException(status_code=400, detail="Enter a valid email address.")
    if not re.fullmatch(r"[+()\d\s.-]{7,24}", phone):
        raise HTTPException(status_code=400, detail="Enter a valid mobile number.")
    if len(body.password) < 10:
        raise HTTPException(
            status_code=400,
            detail="Use a password with at least 10 characters.",
        )
    if get_users_collection().find_one({"email": email}):
        raise HTTPException(status_code=409, detail="An account already uses this email.")

    now = utc_now()
    user = {
        "name": name,
        "email": email,
        "phone": phone,
        "role": "user",
        "password_hash": hash_password(body.password),
        "created_at": now,
        "updated_at": now,
    }
    try:
        result = get_users_collection().insert_one(user)
    except Exception:
        raise HTTPException(status_code=409, detail="An account already uses this email.")

    user["_id"] = result.inserted_id
    set_session_cookie(response, user)
    return {"user": safe_user(user)}


@app.post("/api/auth/login")
def login_user(body: LoginRequest, response: Response):
    email = body.email.strip().lower()
    user = get_users_collection().find_one({"email": email})
    if not user or not verify_password(body.password, user.get("password_hash", "")):
        raise HTTPException(status_code=401, detail="Email or password is incorrect.")

    set_session_cookie(response, user)
    return {"user": safe_user(user)}


@app.get("/api/auth/me")
def current_user(request: Request):
    return {"user": request.state.current_user}


@app.post("/api/auth/logout")
def logout_user(request: Request, response: Response):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if token:
        token_hash = hashlib.sha256(token.encode("utf-8")).hexdigest()
        get_sessions_collection().delete_one({"token_hash": token_hash})
    response.delete_cookie(
        key=SESSION_COOKIE_NAME,
        path="/",
        httponly=True,
        secure=AUTH_COOKIE_SECURE,
        samesite="lax",
    )
    return {"ok": True}


@app.post("/api/reports", status_code=201)
async def create_issue_report(
    request: Request,
    issue_type: str = Form(...),
    name: str = Form(...),
    phone: str = Form(...),
    location: str = Form(...),
    description: str = Form(...),
    photo: UploadFile = File(...),
):
    issue_type = issue_type.strip().lower()
    name = name.strip()
    phone = phone.strip()
    location = location.strip()
    description = description.strip()

    if issue_type not in VALID_REPORT_TYPES:
        raise HTTPException(status_code=400, detail="Choose a supported issue type.")
    if not name or len(name) > 100:
        raise HTTPException(status_code=400, detail="Enter your name.")
    if not re.fullmatch(r"[+()\d\s.-]{7,24}", phone):
        raise HTTPException(status_code=400, detail="Enter a valid mobile number.")
    if not location or len(location) > 500:
        raise HTTPException(status_code=400, detail="Enter the issue location.")
    if not description or len(description) > 2000:
        raise HTTPException(status_code=400, detail="Describe the issue (up to 2,000 characters).")
    if not (photo.content_type or "").startswith("image/"):
        raise HTTPException(status_code=400, detail="Upload a photo of the issue.")

    photo_bytes = await photo.read(MAX_REPORT_PHOTO_BYTES + 1)
    if len(photo_bytes) > MAX_REPORT_PHOTO_BYTES:
        raise HTTPException(status_code=413, detail="The photo must be 8 MB or smaller.")

    image = cv2.imdecode(np.frombuffer(photo_bytes, np.uint8), cv2.IMREAD_COLOR)
    if image is None:
        raise HTTPException(status_code=400, detail="The uploaded photo could not be read.")

    report_id = uuid.uuid4().hex
    photo_path = REPORT_PHOTOS_DIR / f"{report_id}.jpg"
    success = cv2.imwrite(str(photo_path), image)
    if not success:
        raise HTTPException(status_code=500, detail="The report photo could not be saved.")

    user = request.state.current_user
    report = {
        "issue_type": issue_type,
        "name": name,
        "phone": phone,
        "location": location,
        "description": description,
        "photo_name": photo_path.name,
        "user_id": user["id"],
        "status": "new",
        "created_at": utc_now(),
        "updated_at": utc_now(),
    }
    result = get_issue_reports_collection().insert_one(report)
    return {
        "id": str(result.inserted_id),
        "status": report["status"],
        "created_at": report["created_at"],
    }


@app.get("/api/reports/mine")
def list_my_reports(request: Request, limit: int = Query(100, ge=1, le=200)):
    user = request.state.current_user
    reports = get_issue_reports_collection().find(
        {"user_id": user["id"]}
    ).sort("created_at", -1).limit(limit)

    return [
        {
            "id": str(report["_id"]),
            "issue_type": report["issue_type"],
            "name": report["name"],
            "phone": report["phone"],
            "location": report["location"],
            "description": report["description"],
            "status": report["status"],
            "created_at": report["created_at"],
            "update_message": report.get("latest_update_message", ""),
            "rating": report.get("rating"),
            "rating_comment": report.get("rating_comment", ""),
            "photo_url": f"/api/reports/{report['_id']}/photos/original",
            "resolution_photo_url": (
                f"/api/reports/{report['_id']}/photos/resolution"
                if report.get("resolution_photo_name")
                else None
            ),
            "latest_update_photo_url": (
                f"/api/reports/{report['_id']}/photos/update"
                if report.get("latest_update_photo_name")
                else None
            ),
        }
        for report in reports
    ]


@app.delete("/api/reports/{report_id}")
def delete_my_report(report_id: str, request: Request):
    return delete_issue_report(
        report_id,
        owner_id=request.state.current_user["id"],
    )


@app.get("/api/reports/{report_id}/photos/{photo_kind}")
def get_my_report_photo(report_id: str, photo_kind: str, request: Request):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")

    report = get_issue_reports_collection().find_one({
        "_id": ObjectId(report_id),
        "user_id": request.state.current_user["id"],
    })
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    photo_field = {
        "original": "photo_name",
        "resolution": "resolution_photo_name",
        "update": "latest_update_photo_name",
    }.get(photo_kind)
    photo_name = report.get(photo_field) if photo_field else None
    if not photo_name:
        raise HTTPException(status_code=404, detail="Report photo not found.")

    photo_path = REPORT_PHOTOS_DIR / photo_name
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Report photo not found.")
    return FileResponse(photo_path, media_type="image/jpeg")


@app.get("/api/reports/{report_id}/updates")
def list_my_report_updates(report_id: str, request: Request):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")

    report_id = str(ObjectId(report_id))
    user_id = request.state.current_user["id"]
    report = get_issue_reports_collection().find_one({
        "_id": ObjectId(report_id),
        "user_id": user_id,
    })
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    updates = get_report_updates_collection().find(
        {"report_id": report_id, "user_id": user_id}
    ).sort("created_at", 1)
    return [
        {
            "id": str(update["_id"]),
            "message": update["message"],
            "status": update["status"],
            "created_at": update["created_at"],
            "photo_url": (
                f"/api/reports/{report_id}/updates/{update['_id']}/photo"
                if update.get("photo_name")
                else None
            ),
            "is_resolution_photo": bool(update.get("resolution_photo_name")),
        }
        for update in updates
    ]


@app.get("/api/reports/{report_id}/updates/{update_id}/photo")
def get_my_report_update_photo(report_id: str, update_id: str, request: Request):
    if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(update_id):
        raise HTTPException(status_code=404, detail="Update photo not found.")

    user_id = request.state.current_user["id"]
    report = get_issue_reports_collection().find_one({
        "_id": ObjectId(report_id),
        "user_id": user_id,
    })
    update = get_report_updates_collection().find_one({
        "_id": ObjectId(update_id),
        "report_id": str(ObjectId(report_id)),
        "user_id": user_id,
    })
    if not report or not update or not update.get("photo_name"):
        raise HTTPException(status_code=404, detail="Update photo not found.")

    photo_path = REPORT_PHOTOS_DIR / update["photo_name"]
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Update photo not found.")
    return FileResponse(photo_path, media_type="image/jpeg")


@app.post("/api/reports/{report_id}/rating")
def rate_resolved_report(
    report_id: str,
    body: ReportRatingRequest,
    request: Request,
):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")

    result = get_issue_reports_collection().update_one(
        {
            "_id": ObjectId(report_id),
            "user_id": request.state.current_user["id"],
            "status": "resolved",
            "resolution_photo_name": {"$exists": True},
            "rating": {"$exists": False},
        },
        {
            "$set": {
                "rating": body.rating,
                "rating_comment": body.comment.strip(),
                "rated_at": utc_now(),
            }
        },
    )
    if not result.matched_count:
        raise HTTPException(
            status_code=409,
            detail="This report is not resolved or has already been rated.",
        )
    return {"id": report_id, "rating": body.rating}


@app.get("/api/admin/reports")
def list_issue_reports(
    issue_type: Optional[str] = None,
    status: Optional[str] = None,
    limit: int = Query(200, ge=1, le=500),
):
    query = {}
    if issue_type in VALID_REPORT_TYPES:
        query["issue_type"] = issue_type
    if status in {"new", "in_progress", "resolved"}:
        query["status"] = status

    reports = get_issue_reports_collection().find(query).sort("created_at", -1).limit(limit)
    return [
        {
            "id": str(report["_id"]),
            "issue_type": report["issue_type"],
            "name": report["name"],
            "phone": report["phone"],
            "location": report["location"],
            "description": report["description"],
            "status": report["status"],
            "created_at": report["created_at"],
            "photo_url": f"/api/admin/reports/{report['_id']}/photo",
            "resolution_photo_url": (
                f"/api/admin/reports/{report['_id']}/photos/resolution"
                if report.get("resolution_photo_name")
                else None
            ),
            "latest_update_message": report.get("latest_update_message", ""),
            "rating": report.get("rating"),
            "rating_comment": report.get("rating_comment", ""),
        }
        for report in reports
    ]


@app.delete("/api/admin/reports/{report_id}")
def delete_admin_report(report_id: str):
    return delete_issue_report(report_id)


@app.get("/api/admin/reports/{report_id}/updates")
def list_issue_report_updates(report_id: str):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    report_id = str(ObjectId(report_id))
    if not get_issue_reports_collection().find_one({"_id": ObjectId(report_id)}):
        raise HTTPException(status_code=404, detail="Report not found.")

    updates = get_report_updates_collection().find(
        {"report_id": report_id}
    ).sort("created_at", 1)
    return [
        {
            "id": str(update["_id"]),
            "message": update["message"],
            "status": update["status"],
            "created_at": update["created_at"],
            "photo_url": (
                f"/api/admin/reports/{report_id}/updates/{update['_id']}/photo"
                if update.get("photo_name")
                else None
            ),
        }
        for update in updates
    ]


@app.get("/api/admin/reports/{report_id}/updates/{update_id}/photo")
def get_admin_report_update_photo(report_id: str, update_id: str):
    if not ObjectId.is_valid(report_id) or not ObjectId.is_valid(update_id):
        raise HTTPException(status_code=404, detail="Update photo not found.")

    report_id = str(ObjectId(report_id))
    update = get_report_updates_collection().find_one({
        "_id": ObjectId(update_id),
        "report_id": report_id,
    })
    if not update or not update.get("photo_name"):
        raise HTTPException(status_code=404, detail="Update photo not found.")

    photo_path = REPORT_PHOTOS_DIR / update["photo_name"]
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Update photo not found.")
    return FileResponse(photo_path, media_type="image/jpeg")


@app.post("/api/admin/reports/{report_id}/updates", status_code=201)
async def add_issue_report_update(
    report_id: str,
    request: Request,
    message: str = Form(...),
    status: str = Form(...),
    photo: Optional[UploadFile] = File(None),
):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    if status not in {"new", "in_progress", "resolved"}:
        raise HTTPException(status_code=400, detail="Choose a valid report status.")
    message = message.strip()
    if not message or len(message) > 2000:
        raise HTTPException(status_code=400, detail="Enter an update (up to 2,000 characters).")
    if status == "resolved" and photo is None:
        raise HTTPException(
            status_code=400,
            detail="Attach a photo showing the completed work before resolving the report.",
        )
    report_object_id = ObjectId(report_id)
    report = get_issue_reports_collection().find_one({"_id": report_object_id})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    photo_name = await save_report_photo(photo, f"update_{report_id}") if photo else None

    created_at = utc_now()
    update = {
        "report_id": report_id,
        "user_id": report["user_id"],
        "admin_id": request.state.current_user["id"],
        "message": message,
        "status": status,
        "created_at": created_at,
    }
    if photo_name:
        update["photo_name"] = photo_name
    if status == "resolved" and photo_name:
        update["resolution_photo_name"] = photo_name

    result = get_report_updates_collection().insert_one(update)
    report_changes = {
        "status": status,
        "latest_update_message": message,
        "updated_at": created_at,
    }
    if photo_name:
        report_changes["latest_update_photo_name"] = photo_name
    if status == "resolved" and photo_name:
        report_changes["resolution_photo_name"] = photo_name

    get_issue_reports_collection().update_one(
        {"_id": report_object_id},
        {"$set": report_changes},
    )
    return {
        "id": str(result.inserted_id),
        "status": status,
        "created_at": created_at,
    }


@app.get("/api/admin/reports/{report_id}/photo")
def get_issue_report_photo(report_id: str):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")

    report = get_issue_reports_collection().find_one({"_id": ObjectId(report_id)})
    if not report:
        raise HTTPException(status_code=404, detail="Report not found.")

    photo_path = REPORT_PHOTOS_DIR / report["photo_name"]
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Report photo not found.")
    return FileResponse(photo_path, media_type="image/jpeg")


@app.get("/api/admin/reports/{report_id}/photos/resolution")
def get_admin_resolution_photo(report_id: str):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")

    report = get_issue_reports_collection().find_one({"_id": ObjectId(report_id)})
    if not report or not report.get("resolution_photo_name"):
        raise HTTPException(status_code=404, detail="Resolution photo not found.")

    photo_path = REPORT_PHOTOS_DIR / report["resolution_photo_name"]
    if not photo_path.is_file():
        raise HTTPException(status_code=404, detail="Resolution photo not found.")
    return FileResponse(photo_path, media_type="image/jpeg")


@app.patch("/api/admin/reports/{report_id}/status")
def update_issue_report_status(report_id: str, body: ReportStatusRequest):
    if not ObjectId.is_valid(report_id):
        raise HTTPException(status_code=404, detail="Report not found.")
    if body.status not in {"new", "in_progress", "resolved"}:
        raise HTTPException(status_code=400, detail="Choose a valid report status.")
    if body.status == "resolved":
        raise HTTPException(
            status_code=400,
            detail="Resolve reports through an update with a completion photo.",
        )

    result = get_issue_reports_collection().update_one(
        {"_id": ObjectId(report_id)},
        {"$set": {"status": body.status, "updated_at": utc_now()}},
    )
    if not result.matched_count:
        raise HTTPException(status_code=404, detail="Report not found.")
    return {"id": report_id, "status": body.status}


# ============================================================
# CONVERT MONGO RECORD → API OUTPUT
# ============================================================

def _record_to_out(record) -> ViolationOut:

    frame_name = os.path.basename(
        record["frame_saved"]
    )

    return ViolationOut(
        id=str(
            record["_id"]
        ),
        plate_number=record[
            "plate_number"
        ],
        timestamp=record[
            "timestamp"
        ],
        source=record[
            "source"
        ],
        image_url=(
            f"/frames/{frame_name}"
        ),
    )


# ============================================================
# SAVE HELMET VIOLATION
# ============================================================

def save_violation(
    collection,
    plate_text: str,
    frame,
    source_name: str
) -> ViolationOut:

    timestamp = datetime.datetime.now()

    frame_name = (
        f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    )

    frame_path = (
        SAVE_FRAMES_DIR /
        frame_name
    )

    # Save image
    success = cv2.imwrite(
        str(frame_path),
        frame
    )

    if not success:

        print(
            f"[ERROR] Failed to save image: "
            f"{frame_path}"
        )

        raise RuntimeError(
            f"Could not save violation image: "
            f"{frame_path}"
        )

    record = {

        "plate_number":
            plate_text.strip().upper(),

        "timestamp":
            timestamp,

        "source":
            source_name,

        "frame_saved":
            str(frame_path),
    }

    try:

        result = collection.insert_one(
            record
        )

        print(
            "[MONGO] VIOLATION SAVED | "
            f"Plate: {record['plate_number']} | "
            f"ID: {result.inserted_id}"
        )

    except Exception as e:

        print(
            f"[MONGO ERROR] "
            f"Failed to save violation: {e}"
        )

        raise

    record["_id"] = result.inserted_id

    return _record_to_out(
        record
    )


# ============================================================
# SAVE GARBAGE / POTHOLE RECORD
# ============================================================

def save_generic_record(
    event_type: str,
    detail: str,
    frame,
    source_name: str,
    metadata: Optional[dict] = None,
) -> GenericRecordOut:

    timestamp = datetime.datetime.now()

    frame_name = (
        f"{event_type}_"
        f"{timestamp.strftime('%Y%m%d_%H%M%S_%f')}.jpg"
    )

    frame_path = (
        SAVE_FRAMES_DIR /
        frame_name
    )

    success = cv2.imwrite(
        str(frame_path),
        frame
    )

    if not success:

        print(
            f"[ERROR] Failed to save "
            f"{event_type} image: "
            f"{frame_path}"
        )

        raise RuntimeError(
            "Could not save generic detection image"
        )

    record = {

        "event_type":
            event_type,

        "detail":
            detail,

        "timestamp":
            timestamp,

        "source":
            source_name,

        "frame_saved":
            str(frame_path),
    }

    if metadata:
        record.update(metadata)

    result = get_model_collection(event_type).insert_one(record)

    print(
        f"[MONGO] {event_type.upper()} SAVED | "
        f"ID: {result.inserted_id}"
    )

    return GenericRecordOut(

        id=str(
            result.inserted_id
        ),

        detail=detail,

        timestamp=timestamp,

        source=source_name,

        image_url=(
            f"/frames/{frame_name}"
        ),
    )


def save_traffic_record(
    frame,
    detections,
    vehicle_counts: dict,
    congestion_level: str,
    source_name: str,
) -> Optional[GenericRecordOut]:

    if not detections:
        return None

    detail = (
        f"{len(detections)} vehicle detections; "
        f"{congestion_level.lower()} congestion"
    )

    return save_generic_record(
        "traffic",
        detail,
        frame,
        source_name,
        {
            "detection_count": len(detections),
            "vehicle_counts": vehicle_counts,
            "congestion_level": congestion_level,
        },
    )


# ============================================================
# MAIN HELMET + PLATE + OCR DETECTION
# ============================================================

def run_detection_on_frame(
    frame,
    source_tag: str,
    collection,
    seen_plates: set
):

    helmet_model = get_helmet_model()

    plate_model = get_plate_model()

    reader = get_ocr_reader()

    # --------------------------------------------------------
    # Resize
    # --------------------------------------------------------

    frame = cv2.resize(
        frame,
        (640, 360)
    )

    display = frame.copy()

    boxes_out = []

    saved_out = []


    # ========================================================
    # HELMET DETECTION
    # ========================================================

    helmet_results = helmet_model(
        frame,
        conf=CONFIDENCE_HELMET,
        verbose=False,
        imgsz=640
    )


    # ========================================================
    # DEBUG OUTPUT
    # ========================================================

    print(
        "\n========== HELMET DETECTIONS =========="
    )

    if len(helmet_results[0].boxes) == 0:

        print(
            "NO HELMET DETECTIONS"
        )

    else:

        for det in helmet_results[0].boxes:

            cls_id = int(
                det.cls[0]
            )

            label = helmet_model.names[
                cls_id
            ]

            conf = float(
                det.conf[0]
            )

            x1, y1, x2, y2 = map(
                int,
                det.xyxy[0]
            )

            print(
                f"LABEL={label} | "
                f"CONF={conf:.3f} | "
                f"BOX=({x1},{y1},{x2},{y2})"
            )

    print(
        "=======================================\n"
    )


    # ========================================================
    # PROCESS EACH HELMET DETECTION
    # ========================================================

    for det in helmet_results[0].boxes:

        cls_id = int(
            det.cls[0]
        )

        label = helmet_model.names[
            cls_id
        ]

        label_lower = label.lower()

        conf = float(
            det.conf[0]
        )

        x1, y1, x2, y2 = map(
            int,
            det.xyxy[0]
        )


        # ----------------------------------------------------
        # Add detection to response
        # ----------------------------------------------------

        boxes_out.append(
            DetectionBox(
                label=label,
                confidence=round(
                    conf,
                    3
                ),
                box=[
                    x1,
                    y1,
                    x2,
                    y2
                ]
            )
        )


        # ====================================================
        # WITH HELMET
        # ====================================================

        if label_lower == "with helmet":

            cv2.rectangle(
                display,
                (x1, y1),
                (x2, y2),
                (0, 200, 0),
                2
            )

            cv2.putText(
                display,
                f"HELMET {conf:.2f}",
                (
                    x1,
                    max(
                        20,
                        y1 - 8
                    )
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.55,
                (0, 200, 0),
                2
            )

            continue


        # ====================================================
        # ONLY PROCESS WITHOUT HELMET
        # ====================================================

        if label_lower != "without helmet":

            continue


        # ----------------------------------------------------
        # Extra safety confidence
        # ----------------------------------------------------

        if conf < 0.5:

            print(
                f"[SKIP] Low confidence "
                f"NO HELMET: {conf:.3f}"
            )

            continue


        # ====================================================
        # NO HELMET DRAWING
        # ====================================================

        cv2.rectangle(
            display,
            (x1, y1),
            (x2, y2),
            (0, 0, 220),
            2
        )

        cv2.putText(
            display,
            f"NO HELMET {conf:.2f}",
            (
                x1,
                max(
                    20,
                    y1 - 8
                )
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.6,
            (0, 0, 220),
            2
        )


        print(
            "[VIOLATION CANDIDATE] "
            f"WITHOUT HELMET | "
            f"confidence={conf:.3f}"
        )


        # ====================================================
        # PLATE DETECTION
        # ====================================================

        plate_results = plate_model(
            frame,
            conf=CONFIDENCE_PLATE,
            verbose=False,
            imgsz=640
        )


        # ====================================================
        # NO PLATE FOUND
        # ====================================================

        if len(
            plate_results[0].boxes
        ) == 0:

            # -----------------------------------------------
            # Quantize center so small movement doesn't
            # create a new violation every frame.
            # -----------------------------------------------

            center_x = (
                (x1 + x2) // 2
            ) // 60

            center_y = (
                (y1 + y2) // 2
            ) // 60

            no_plate_key = (
                f"NO_PLATE_"
                f"{center_x}_"
                f"{center_y}"
            )


            if no_plate_key not in seen_plates:

                print(
                    "[VIOLATION] "
                    "WITHOUT HELMET + "
                    "NO PLATE FOUND"
                )

                saved_out.append(
                    save_violation(
                        collection,
                        "NO PLATE FOUND",
                        display.copy(),
                        source_tag
                    )
                )

                seen_plates.add(
                    no_plate_key
                )

            continue


        # ====================================================
        # PLATE FOUND
        # ====================================================

        for pdet in plate_results[0].boxes:

            px1, py1, px2, py2 = map(
                int,
                pdet.xyxy[0]
            )


            # ------------------------------------------------
            # Safety bounds
            # ------------------------------------------------

            px1 = max(
                0,
                px1
            )

            py1 = max(
                0,
                py1
            )

            px2 = min(
                frame.shape[1],
                px2
            )

            py2 = min(
                frame.shape[0],
                py2
            )


            plate_crop = frame[
                py1:py2,
                px1:px2
            ]


            if plate_crop.size == 0:

                continue


            # =================================================
            # OCR
            # =================================================

            ocr_results = reader.readtext(
                plate_crop
            )


            plate_text = " ".join(
                [
                    r[1]
                    for r in ocr_results
                ]
            ).strip()


            if not plate_text:

                plate_text = "UNREADABLE"


            normalized_plate = (
                plate_text
                .strip()
                .upper()
            )


            # =================================================
            # DRAW PLATE
            # =================================================

            cv2.rectangle(
                display,
                (px1, py1),
                (px2, py2),
                (0, 140, 255),
                2
            )

            cv2.putText(
                display,
                normalized_plate,
                (
                    px1,
                    min(
                        frame.shape[0] - 10,
                        py2 + 20
                    )
                ),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.7,
                (0, 140, 255),
                2
            )


            # =================================================
            # SAVE VIOLATION
            # =================================================

            if normalized_plate not in seen_plates:

                print(
                    "[VIOLATION] "
                    f"WITHOUT HELMET | "
                    f"PLATE={normalized_plate}"
                )

                saved_out.append(
                    save_violation(
                        collection,
                        normalized_plate,
                        display.copy(),
                        source_tag
                    )
                )

                seen_plates.add(
                    normalized_plate
                )


    return (
        display,
        boxes_out,
        saved_out
    )


# ============================================================
# TRAFFIC / CONGESTION FRAME DETECTION
# ============================================================

def run_traffic_on_frame(frame):

    traffic_model = get_traffic_model()

    frame = cv2.resize(
        frame,
        (640, 360)
    )

    display = frame.copy()
    boxes_out = []
    counts = {}

    results = traffic_model(
        frame,
        conf=CONFIDENCE_TRAFFIC,
        verbose=False,
        imgsz=640
    )

    for det in results[0].boxes:

        cls_id = int(det.cls[0])
        label = traffic_model.names[cls_id]
        conf = float(det.conf[0])

        x1, y1, x2, y2 = map(
            int,
            det.xyxy[0]
        )

        boxes_out.append(
            DetectionBox(
                label=str(label),
                confidence=round(conf, 3),
                box=[x1, y1, x2, y2]
            )
        )

        counts[str(label)] = counts.get(str(label), 0) + 1

        cv2.rectangle(
            display,
            (x1, y1),
            (x2, y2),
            (0, 255, 0),
            2
        )

        cv2.putText(
            display,
            f"{label} {conf:.2f}",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 255, 0),
            2
        )

    total = len(boxes_out)

    if total <= TRAFFIC_LOW_MAX:
        congestion_level = "LOW"
    elif total <= TRAFFIC_MEDIUM_MAX:
        congestion_level = "MEDIUM"
    else:
        congestion_level = "HIGH"

    cv2.rectangle(
        display,
        (10, 8),
        (300, 52),
        (0, 0, 0),
        -1
    )

    cv2.putText(
        display,
        f"Traffic: {congestion_level} | Vehicles: {total}",
        (18, 38),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.62,
        (0, 255, 255),
        2
    )

    return (
        display,
        boxes_out,
        counts,
        congestion_level
    )


def encode_frame_base64(frame):

    ok, buf = cv2.imencode(
        ".jpg",
        frame
    )

    if not ok:
        return ""

    return base64.b64encode(
        buf.tobytes()
    ).decode("utf-8")


# ============================================================
# HEALTH
# ============================================================

@app.get("/api/health")
def health():

    status = {
        "api": "ok"
    }

    # MongoDB
    try:

        get_collection().estimated_document_count()

        status["mongo"] = "ok"

    except Exception as e:

        status["mongo"] = (
            f"error: {e}"
        )


    # Models
    status[
        "helmet_model_present"
    ] = os.path.exists(
        HELMET_MODEL_PATH
    )

    status[
        "plate_model_present"
    ] = os.path.exists(
        PLATE_MODEL_PATH
    )

    status[
        "garbage_model_present"
    ] = os.path.exists(
        GARBAGE_MODEL_PATH
    )

    status[
        "pothole_model_present"
    ] = os.path.exists(
        POTHOLE_MODEL_PATH
    )


    status[
        "helmet_confidence"
    ] = CONFIDENCE_HELMET

    status[
        "plate_confidence"
    ] = CONFIDENCE_PLATE

    return status


# ============================================================
# HELMET VIOLATIONS
# ============================================================

@app.get(
    "/api/violations",
    response_model=list[ViolationOut]
)
def list_violations(

    limit: int = Query(
        50,
        ge=1,
        le=500
    ),

    skip: int = Query(
        0,
        ge=0
    ),

    search: Optional[str] = None
):

    collection = get_collection()

    query = {}


    if search:

        query[
            "plate_number"
        ] = {
            "$regex":
                search.strip().upper(),
            "$options":
                "i"
        }


    cursor = (
        collection
        .find(query)
        .sort(
            "timestamp",
            -1
        )
        .skip(skip)
        .limit(limit)
    )


    return [
        _record_to_out(r)
        for r in cursor
    ]


# ============================================================
# MODEL DETECTION RECORDS
# ============================================================

@app.get(
    "/api/smart-city-records"
)
def list_smart_city_records(

    event_type: Optional[str] = None,

    limit: int = Query(
        50,
        ge=1,
        le=500
    )
):

    feature_types = ("traffic", "garbage", "pothole")

    if event_type in feature_types:
        collections = [get_model_collection(event_type)]
        if event_type in ("garbage", "pothole"):
            collections.append(get_generic_collection())
    elif event_type:
        collections = [get_generic_collection()]
    else:
        collections = [
            *(get_model_collection(feature) for feature in feature_types),
            get_generic_collection(),
        ]

    records = []
    for collection in collections:
        query = {"event_type": event_type} if event_type else {}
        records.extend(
            collection.find(query)
            .sort("timestamp", -1)
            .limit(limit)
        )

    records.sort(
        key=lambda record: record.get("timestamp", datetime.datetime.min),
        reverse=True,
    )

    results = []
    for r in records[:limit]:

        frame_name = os.path.basename(
            r.get(
                "frame_saved",
                ""
            )
        )


        results.append({

            "id":
                str(r["_id"]),

            "event_type":
                r.get(
                    "event_type",
                    "unknown"
                ),

            "detail":
                r.get(
                    "detail",
                    ""
                ),

            "timestamp":
                r["timestamp"],

            "source":
                r.get(
                    "source",
                    ""
                ),

            "image_url":
                (
                    f"/frames/{frame_name}"
                    if frame_name
                    else ""
                ),
        })


    return results


# ============================================================
# STATISTICS
# ============================================================

@app.get(
    "/api/stats",
    response_model=StatsResponse
)
def stats():

    collection = get_collection()

    total = collection.count_documents({})

    traffic_collection = get_model_collection("traffic")
    traffic_events = traffic_collection.count_documents({})
    vehicle_totals = {"car": 0, "bike": 0, "rickshaw": 0}
    for record in traffic_collection.find({}, {"vehicle_counts": 1}):
        for label, count in (record.get("vehicle_counts") or {}).items():
            normalized_label = str(label).strip().lower()
            if normalized_label in vehicle_totals:
                vehicle_totals[normalized_label] += int(count or 0)

    garbage_detected = get_model_collection("garbage").count_documents({})
    potholes_detected = get_model_collection("pothole").count_documents({})


    now = datetime.datetime.now()

    start_of_day = datetime.datetime(
        now.year,
        now.month,
        now.day
    )


    today = collection.count_documents({

        "timestamp": {
            "$gte":
                start_of_day
        }

    })


    unique_plates = len(
        collection.distinct(
            "plate_number"
        )
    )


    last_7_days = []


    for i in range(
        6,
        -1,
        -1
    ):

        day = (
            start_of_day
            - datetime.timedelta(
                days=i
            )
        )

        next_day = (
            day
            + datetime.timedelta(
                days=1
            )
        )


        count = collection.count_documents({

            "timestamp": {
                "$gte": day,
                "$lt": next_day
            }

        })


        last_7_days.append({

            "date":
                day.strftime(
                    "%Y-%m-%d"
                ),

            "count":
                count

        })


    return StatsResponse(

        total_violations=total,

        today=today,

        unique_plates=unique_plates,

        last_7_days=last_7_days,
        traffic_events=traffic_events,
        garbage_detected=garbage_detected,
        potholes_detected=potholes_detected,
        cars=vehicle_totals["car"],
        bikes=vehicle_totals["bike"],
        rickshaws=vehicle_totals["rickshaw"],
    )


@app.get("/api/admin/detection-events")
def list_detection_events(
    limit: int = Query(100, ge=1, le=500),
    feature: Optional[str] = None,
    vehicle_class: Optional[str] = None,
):
    events = []

    if feature and feature not in MODEL_COLLECTIONS:
        raise HTTPException(status_code=400, detail="Unknown detection model.")
    if vehicle_class and (
        feature != "traffic"
        or vehicle_class not in {"car", "bike", "rickshaw"}
    ):
        raise HTTPException(status_code=400, detail="Unknown traffic class.")

    selected_features = [feature] if feature else list(MODEL_COLLECTIONS)
    for selected_feature in selected_features:
        query = {}
        if vehicle_class:
            query[f"vehicle_counts.{vehicle_class}"] = {"$gt": 0}

        records = get_model_collection(selected_feature).find(query).sort(
            "timestamp",
            -1,
        ).limit(limit)

        for record in records:
            frame_name = os.path.basename(record.get("frame_saved", ""))
            events.append({
                "id": str(record["_id"]),
                "feature": selected_feature,
                "summary": (
                    record.get("plate_number", "Helmet violation")
                    if selected_feature == "helmet"
                    else record.get("detail", record.get("event_type", selected_feature.title()))
                ),
                "source": record.get("source", ""),
                "timestamp": record.get("timestamp"),
                "image_url": f"/frames/{frame_name}" if frame_name else "",
                "vehicle_counts": record.get("vehicle_counts", {}),
            })

    events.sort(
        key=lambda event: event.get("timestamp") or datetime.datetime.min,
        reverse=True,
    )
    return events[:limit]


@app.delete("/api/admin/detection-events/{feature}/{event_id}")
def delete_detection_event(feature: str, event_id: str):
    if feature not in MODEL_COLLECTIONS or not ObjectId.is_valid(event_id):
        raise HTTPException(status_code=404, detail="Detection event not found.")

    collection = get_model_collection(feature)
    record = collection.find_one({"_id": ObjectId(event_id)})
    if not record:
        raise HTTPException(status_code=404, detail="Detection event not found.")

    collection.delete_one({"_id": ObjectId(event_id)})

    frame_saved = record.get("frame_saved")
    if frame_saved:
        remaining_references = sum(
            model_collection.count_documents({"frame_saved": frame_saved})
            for model_collection in (
                get_model_collection(model_feature)
                for model_feature in MODEL_COLLECTIONS
            )
        )
        if remaining_references == 0:
            frame_path = SAVE_FRAMES_DIR / os.path.basename(frame_saved)
            try:
                frame_path.unlink(missing_ok=True)
            except OSError as error:
                print(f"[EVENT] Could not remove detection frame: {error}")

    return {"id": event_id, "feature": feature, "deleted": True}


# ============================================================
# DELETE VIOLATION
# ============================================================

@app.delete(
    "/api/violations/{violation_id}"
)
def delete_violation(
    violation_id: str
):

    collection = get_collection()


    try:

        object_id = ObjectId(
            violation_id
        )

    except Exception:

        raise HTTPException(
            status_code=400,
            detail="Invalid violation ID"
        )


    result = collection.delete_one({

        "_id":
            object_id

    })


    if result.deleted_count == 0:

        raise HTTPException(
            status_code=404,
            detail="Violation not found"
        )


    return {
        "deleted": True
    }


# ============================================================
# HELMET IMAGE DETECTION
# ============================================================

@app.post(
    "/api/detect/image",
    response_model=DetectResponse
)
async def detect_image(
    file: UploadFile = File(...)
):

    contents = await file.read()

    np_arr = np.frombuffer(
        contents,
        np.uint8
    )

    frame = cv2.imdecode(
        np_arr,
        cv2.IMREAD_COLOR
    )


    if frame is None:

        raise HTTPException(
            status_code=400,
            detail="Could not decode image"
        )


    collection = get_collection()

    seen_plates = set()


    annotated, boxes, saved = (
        run_detection_on_frame(
            frame,
            file.filename or "upload",
            collection,
            seen_plates
        )
    )


    ok, buf = cv2.imencode(
        ".jpg",
        annotated
    )


    annotated_b64 = (

        base64.b64encode(
            buf.tobytes()
        ).decode("utf-8")

        if ok

        else ""
    )


    return DetectResponse(

        violations_found=
            len(saved),

        plates=[
            s.plate_number
            for s in saved
        ],

        detections=
            boxes,

        annotated_image_base64=
            annotated_b64,

        saved=
            saved
    )


# ============================================================
# TRAFFIC / CONGESTION IMAGE DETECTION
# ============================================================

@app.post("/api/detect/traffic")
async def detect_traffic(
    file: UploadFile = File(...)
):

    contents = await file.read()

    np_arr = np.frombuffer(
        contents,
        np.uint8
    )

    frame = cv2.imdecode(
        np_arr,
        cv2.IMREAD_COLOR
    )

    if frame is None:
        raise HTTPException(
            status_code=400,
            detail="Could not decode image"
        )

    (
        annotated,
        boxes,
        counts,
        congestion_level
    ) = run_traffic_on_frame(frame)

    saved = save_traffic_record(
        annotated,
        boxes,
        counts,
        congestion_level,
        file.filename or "upload",
    )

    return {
        "feature": "traffic",
        "congestion_level": congestion_level,
        "total_vehicles": len(boxes),
        "vehicle_counts": counts,
        "detections": [
            b.model_dump(mode="json")
            for b in boxes
        ],
        "saved": saved.model_dump(mode="json") if saved else None,
        "annotated_image_base64": encode_frame_base64(annotated)
    }


# ============================================================
# GARBAGE DETECTION
# ============================================================

@app.post(
    "/api/detect/garbage",
    response_model=GenericDetectResponse
)
async def detect_garbage(
    file: UploadFile = File(...)
):

    contents = await file.read()

    np_arr = np.frombuffer(
        contents,
        np.uint8
    )

    frame = cv2.imdecode(
        np_arr,
        cv2.IMREAD_COLOR
    )


    if frame is None:

        raise HTTPException(
            status_code=400,
            detail="Could not decode image"
        )


    garbage_model = (
        get_garbage_model()
    )


    frame = cv2.resize(
        frame,
        (640, 360)
    )

    display = frame.copy()


    boxes_out = []


    results = garbage_model(
        frame,
        conf=CONFIDENCE_GARBAGE,
        verbose=False,
        imgsz=640
    )


    for det in results[0].boxes:

        cls_id = int(
            det.cls[0]
        )

        label = garbage_model.names[
            cls_id
        ]

        conf = float(
            det.conf[0]
        )

        x1, y1, x2, y2 = map(
            int,
            det.xyxy[0]
        )


        boxes_out.append(
            DetectionBox(

                label=label,

                confidence=round(
                    conf,
                    3
                ),

                box=[
                    x1,
                    y1,
                    x2,
                    y2
                ]
            )
        )


        cv2.rectangle(
            display,
            (x1, y1),
            (x2, y2),
            (0, 165, 255),
            2
        )


        cv2.putText(
            display,
            f"{label} {conf:.2f}",
            (
                x1,
                max(
                    20,
                    y1 - 8
                )
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 165, 255),
            2
        )


    ok, buf = cv2.imencode(
        ".jpg",
        display
    )


    annotated_b64 = (

        base64.b64encode(
            buf.tobytes()
        ).decode("utf-8")

        if ok

        else ""
    )


    saved = None


    if boxes_out:

        saved = save_generic_record(

            "garbage",

            (
                f"{len(boxes_out)} "
                "garbage item(s) detected"
            ),

            display,

            file.filename or "upload"
        )


    return GenericDetectResponse(

        detections_found=
            len(boxes_out),

        detections=
            boxes_out,

        annotated_image_base64=
            annotated_b64,

        saved=
            saved
    )


# ============================================================
# POTHOLE DETECTION
# ============================================================

@app.post(
    "/api/detect/pothole",
    response_model=GenericDetectResponse
)
async def detect_pothole(
    file: UploadFile = File(...)
):

    contents = await file.read()

    np_arr = np.frombuffer(
        contents,
        np.uint8
    )

    frame = cv2.imdecode(
        np_arr,
        cv2.IMREAD_COLOR
    )


    if frame is None:

        raise HTTPException(
            status_code=400,
            detail="Could not decode image"
        )


    pothole_model = (
        get_pothole_model()
    )


    frame = cv2.resize(
        frame,
        (640, 360)
    )

    display = frame.copy()


    boxes_out = []


    results = pothole_model(
        frame,
        conf=CONFIDENCE_POTHOLE,
        verbose=False,
        imgsz=640
    )


    for det in results[0].boxes:

        cls_id = int(
            det.cls[0]
        )

        label = pothole_model.names[
            cls_id
        ]

        conf = float(
            det.conf[0]
        )

        x1, y1, x2, y2 = map(
            int,
            det.xyxy[0]
        )


        boxes_out.append(
            DetectionBox(

                label=label,

                confidence=round(
                    conf,
                    3
                ),

                box=[
                    x1,
                    y1,
                    x2,
                    y2
                ]
            )
        )


        cv2.rectangle(
            display,
            (x1, y1),
            (x2, y2),
            (0, 165, 255),
            2
        )


        cv2.putText(
            display,
            f"{label} {conf:.2f}",
            (
                x1,
                max(
                    20,
                    y1 - 8
                )
            ),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 165, 255),
            2
        )


    ok, buf = cv2.imencode(
        ".jpg",
        display
    )


    annotated_b64 = (

        base64.b64encode(
            buf.tobytes()
        ).decode("utf-8")

        if ok

        else ""
    )


    saved = None


    if boxes_out:

        saved = save_generic_record(

            "pothole",

            (
                f"{len(boxes_out)} "
                "pothole(s) detected"
            ),

            display,

            file.filename or "upload"
        )


    return GenericDetectResponse(

        detections_found=
            len(boxes_out),

        detections=
            boxes_out,

        annotated_image_base64=
            annotated_b64,

        saved=
            saved
    )


# ============================================================
# TRAFFIC / CONGESTION VIDEO DETECTION
# ============================================================

@app.post("/api/detect/traffic/video")
async def detect_traffic_video(
    file: UploadFile = File(...),
    sample_every: int = Query(5, ge=1, le=60)
):

    tmp_path = UPLOAD_TMP_DIR / f"traffic_{uuid.uuid4().hex}_{file.filename or 'video.mp4'}"

    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    cap = cv2.VideoCapture(str(tmp_path))

    if not cap.isOpened():
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Could not open uploaded video"
        )

    frame_idx = 0
    processed = 0
    all_boxes = []
    total_counts = {}
    last_annotated = None
    last_level = "LOW"

    try:
        while processed < MAX_VIDEO_FRAMES:
            ret, frame = cap.read()

            if not ret:
                break

            frame_idx += 1

            if frame_idx % sample_every != 0:
                continue

            (
                last_annotated,
                boxes,
                counts,
                last_level
            ) = run_traffic_on_frame(frame)

            all_boxes.extend(boxes)

            for label, count in counts.items():
                total_counts[label] = total_counts.get(label, 0) + count

            processed += 1

    finally:
        cap.release()
        tmp_path.unlink(missing_ok=True)

    if last_annotated is None:
        raise HTTPException(
            status_code=400,
            detail="No usable frames found in video"
        )

    saved = save_traffic_record(
        last_annotated,
        all_boxes,
        total_counts,
        last_level,
        file.filename or "traffic_video",
    )

    return {
        "feature": "traffic",
        "frames_processed": processed,
        "last_frame_number": frame_idx,
        "congestion_level": last_level,
        "vehicle_counts": total_counts,
        "detections": [
            b.model_dump(mode="json")
            for b in all_boxes
        ],
        "saved": saved.model_dump(mode="json") if saved else None,
        "annotated_image_base64": encode_frame_base64(last_annotated)
    }


# ============================================================
# HELMET VIDEO DETECTION
# ============================================================

@app.post(
    "/api/detect/video",
    response_model=DetectResponse
)
async def detect_video(

    file: UploadFile = File(...),

    sample_every: int = Query(
        5,
        ge=1,
        le=60
    )
):

    tmp_path = (
        BASE_DIR /
        f"_tmp_{file.filename}"
    )


    with open(
        tmp_path,
        "wb"
    ) as f:

        f.write(
            await file.read()
        )


    cap = cv2.VideoCapture(
        str(tmp_path)
    )


    if not cap.isOpened():

        tmp_path.unlink(
            missing_ok=True
        )

        raise HTTPException(
            status_code=400,
            detail="Could not open video"
        )


    collection = get_collection()

    seen_plates = set()

    all_boxes = []

    all_saved = []

    last_annotated = None

    frame_idx = 0

    processed = 0


    while (
        processed <
        MAX_VIDEO_FRAMES
    ):

        ret, frame = cap.read()


        if not ret:

            break


        frame_idx += 1


        if (
            frame_idx %
            sample_every
            != 0
        ):

            continue


        processed += 1


        (
            last_annotated,
            boxes,
            saved
        ) = run_detection_on_frame(

            frame,

            file.filename
            or "video",

            collection,

            seen_plates
        )


        all_boxes.extend(
            boxes
        )

        all_saved.extend(
            saved
        )


    cap.release()

    tmp_path.unlink(
        missing_ok=True
    )


    annotated_b64 = ""


    if last_annotated is not None:

        ok, buf = cv2.imencode(
            ".jpg",
            last_annotated
        )


        if ok:

            annotated_b64 = (
                base64.b64encode(
                    buf.tobytes()
                ).decode("utf-8")
            )


    return DetectResponse(

        violations_found=
            len(all_saved),

        plates=[
            s.plate_number
            for s in all_saved
        ],

        detections=
            all_boxes,

        annotated_image_base64=
            annotated_b64,

        saved=
            all_saved
    )


# ============================================================
# UPLOAD VIDEO
# ============================================================

@app.post(
    "/api/upload/video"
)
async def upload_video(
    file: UploadFile = File(...)
):

    video_id = uuid.uuid4().hex


    ext = os.path.splitext(
        file.filename or "video.mp4"
    )[1] or ".mp4"


    saved_name = (
        f"{video_id}{ext}"
    )


    path = (
        UPLOAD_TMP_DIR /
        saved_name
    )


    with open(
        path,
        "wb"
    ) as f:

        f.write(
            await file.read()
        )


    print(
        f"[VIDEO] Uploaded: {path}"
    )


    return {
        "filename":
            saved_name
    }


# ============================================================
# TRAFFIC LIVE UPLOADED-VIDEO WEBSOCKET
# ============================================================

@app.websocket("/ws/traffic/{filename}")
async def ws_traffic_video(
    websocket: WebSocket,
    filename: str,
    sample_every: int = 5
):

    await websocket.accept()

    path = UPLOAD_TMP_DIR / filename

    if not path.exists():
        await websocket.send_json({
            "type": "error",
            "message": "Uploaded video not found"
        })
        await websocket.close()
        return

    cap = cv2.VideoCapture(str(path))

    if not cap.isOpened():
        await websocket.send_json({
            "type": "error",
            "message": "Could not open uploaded video"
        })
        await websocket.close()
        return

    frame_idx = 0
    processed = 0
    saved = None

    try:
        while processed < MAX_VIDEO_FRAMES:
            ret, frame = cap.read()

            if not ret:
                break

            frame_idx += 1

            if frame_idx % max(1, sample_every) != 0:
                continue

            async with TRAFFIC_INFERENCE_LOCK:
                (
                    annotated,
                    boxes,
                    counts,
                    congestion_level
                ) = await asyncio.to_thread(
                    run_traffic_on_frame,
                    frame
                )

            if not record_saved and boxes:
                saved = save_traffic_record(
                    annotated,
                    boxes,
                    counts,
                    congestion_level,
                    filename,
                )

            processed += 1

            await websocket.send_json({
                "type": "frame",
                "frame_number": frame_idx,
                "annotated_image_base64": encode_frame_base64(annotated),
                "detections": [
                    b.model_dump(mode="json")
                    for b in boxes
                ],
                "vehicle_counts": counts,
                "congestion_level": congestion_level
            })

            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        print("[TRAFFIC WS] Client disconnected")

    except Exception as e:
        print(f"[TRAFFIC WS ERROR] {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass

    finally:
        cap.release()
        path.unlink(missing_ok=True)

        try:
            await websocket.send_json({"type": "done"})
        except Exception:
            pass

        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================
# LIVE VIDEO WEBSOCKET
# ============================================================

@app.websocket(
    "/ws/detect/{filename}"
)
async def ws_detect_video(

    websocket: WebSocket,

    filename: str,

    sample_every: int = 5
):

    await websocket.accept()


    path = (
        UPLOAD_TMP_DIR /
        filename
    )


    if not path.exists():

        await websocket.send_json({

            "type":
                "error",

            "message":
                "video not found"

        })

        await websocket.close()

        return


    cap = cv2.VideoCapture(
        str(path)
    )


    if not cap.isOpened():

        await websocket.send_json({

            "type":
                "error",

            "message":
                "could not open video"

        })

        await websocket.close()

        return


    fps = cap.get(
        cv2.CAP_PROP_FPS
    )


    if fps <= 0:

        fps = 30.0


    playback_interval = (
        sample_every /
        fps
    )


    collection = (
        get_collection()
    )

    seen_plates = set()

    frame_idx = 0


    try:

        while True:

            ret, frame = cap.read()


            if not ret:

                break


            frame_idx += 1


            if (
                frame_idx %
                sample_every
                != 0
            ):

                continue


            start_time = (
                asyncio
                .get_running_loop()
                .time()
            )


            (
                annotated,
                boxes,
                saved
            ) = await asyncio.to_thread(

                run_detection_on_frame,

                frame,

                filename,

                collection,

                seen_plates
            )


            ok, buf = cv2.imencode(
                ".jpg",
                annotated
            )


            annotated_b64 = (

                base64.b64encode(
                    buf.tobytes()
                ).decode("utf-8")

                if ok

                else ""
            )


            await websocket.send_json({

                "type":
                    "frame",

                "frame_number":
                    frame_idx,

                "annotated_image_base64":
                    annotated_b64,

                "detections": [

                    b.model_dump(
                        mode="json"
                    )

                    for b in boxes

                ],

                "new_violations": [

                    s.model_dump(
                        mode="json"
                    )

                    for s in saved

                ]

            })


            elapsed = (
                asyncio
                .get_running_loop()
                .time()
                - start_time
            )


            delay = (
                playback_interval
                - elapsed
            )


            if delay > 0:

                await asyncio.sleep(
                    delay
                )


    except WebSocketDisconnect:

        print(
            "[WS] Client disconnected"
        )


    except Exception as e:

        print(
            f"[WS ERROR] {e}"
        )


        try:

            await websocket.send_json({

                "type":
                    "error",

                "message":
                    str(e)

            })

        except Exception:

            pass


    finally:

        cap.release()


        path.unlink(
            missing_ok=True
        )


        try:

            await websocket.send_json({

                "type":
                    "done"

            })

        except Exception:

            pass


        try:

            await websocket.close()

        except Exception:

            pass


# ============================================================
# TRAFFIC / CONGESTION WEBCAM
# ============================================================

@app.post("/api/detect/traffic/webcam")
def detect_traffic_webcam(
    camera_index: int = Query(0),
    num_frames: int = Query(30, ge=1, le=300)
):

    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        raise HTTPException(
            status_code=400,
            detail=f"Could not open webcam at index {camera_index}"
        )

    all_boxes = []
    total_counts = {}
    last_annotated = None
    last_level = "LOW"

    try:
        for _ in range(num_frames):
            ret, frame = cap.read()

            if not ret:
                break

            (
                last_annotated,
                boxes,
                counts,
                last_level
            ) = run_traffic_on_frame(frame)

            all_boxes.extend(boxes)

            for label, count in counts.items():
                total_counts[label] = total_counts.get(label, 0) + count

    finally:
        cap.release()

    if last_annotated is None:
        raise HTTPException(
            status_code=400,
            detail="No frames received from webcam"
        )

    saved = save_traffic_record(
        last_annotated,
        all_boxes,
        total_counts,
        last_level,
        "webcam",
    )

    return {
        "feature": "traffic",
        "frames_processed": num_frames,
        "congestion_level": last_level,
        "vehicle_counts": total_counts,
        "detections": [
            b.model_dump(mode="json")
            for b in all_boxes
        ],
        "saved": saved.model_dump(mode="json") if saved else None,
        "annotated_image_base64": encode_frame_base64(last_annotated)
    }


# ============================================================
# WEBCAM
# ============================================================

@app.post(
    "/api/detect/webcam",
    response_model=DetectResponse
)
def detect_webcam(

    camera_index: int = Query(
        0
    ),

    num_frames: int = Query(
        30,
        ge=1,
        le=300
    )
):

    cap = cv2.VideoCapture(
        camera_index
    )


    if not cap.isOpened():

        raise HTTPException(
            status_code=400,
            detail=(
                f"Could not open webcam "
                f"at index {camera_index}"
            )
        )


    collection = get_collection()

    seen_plates = set()

    all_boxes = []

    all_saved = []

    last_annotated = None


    for _ in range(
        num_frames
    ):

        ret, frame = cap.read()


        if not ret:

            break


        (
            last_annotated,
            boxes,
            saved
        ) = run_detection_on_frame(

            frame,

            "webcam",

            collection,

            seen_plates
        )


        all_boxes.extend(
            boxes
        )

        all_saved.extend(
            saved
        )


    cap.release()


    annotated_b64 = ""


    if last_annotated is not None:

        ok, buf = cv2.imencode(
            ".jpg",
            last_annotated
        )


        if ok:

            annotated_b64 = (
                base64.b64encode(
                    buf.tobytes()
                ).decode("utf-8")
            )


    return DetectResponse(

        violations_found=
            len(all_saved),

        plates=[
            s.plate_number
            for s in all_saved
        ],

        detections=
            all_boxes,

        annotated_image_base64=
            annotated_b64,

        saved=
            all_saved
    )


# ============================================================
# TRAFFIC / CONGESTION CCTV / RTSP
# ============================================================

@app.websocket("/ws/traffic/cctv")
async def ws_traffic_cctv(
    websocket: WebSocket,
    rtsp_url: str,
    sample_every: int = 5
):

    await websocket.accept()

    print(f"[TRAFFIC CCTV] Connecting to: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        await websocket.send_json({
            "type": "error",
            "message": (
                "Could not connect to CCTV stream. "
                "Check RTSP URL, credentials, and network access."
            )
        })
        await websocket.close()
        return

    frame_idx = 0
    record_saved = False

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                await websocket.send_json({
                    "type": "error",
                    "message": "Lost connection to CCTV stream."
                })
                break

            frame_idx += 1

            if frame_idx % max(1, sample_every) != 0:
                continue

            async with TRAFFIC_INFERENCE_LOCK:
                (
                    annotated,
                    boxes,
                    counts,
                    congestion_level
                ) = await asyncio.to_thread(
                    run_traffic_on_frame,
                    frame
                )

            if saved is None and boxes:
                saved = save_traffic_record(
                    annotated,
                    boxes,
                    counts,
                    congestion_level,
                    "cctv",
                )
                record_saved = saved is not None

            await websocket.send_json({
                "type": "frame",
                "frame_number": frame_idx,
                "annotated_image_base64": encode_frame_base64(annotated),
                "detections": [
                    b.model_dump(mode="json")
                    for b in boxes
                ],
                "vehicle_counts": counts,
                "congestion_level": congestion_level
            })

            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        print("[TRAFFIC CCTV] Client disconnected")

    except Exception as e:
        print(f"[TRAFFIC CCTV ERROR] {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass

    finally:
        cap.release()

        try:
            await websocket.send_json({"type": "done"})
        except Exception:
            pass

        try:
            await websocket.close()
        except Exception:
            pass


# ============================================================
# CCTV / RTSP
# ============================================================

@app.websocket(
    "/ws/detect/cctv"
)
async def ws_detect_cctv(

    websocket: WebSocket,

    rtsp_url: str,

    sample_every: int = 5
):

    await websocket.accept()


    print(
        f"[CCTV] Connecting to: "
        f"{rtsp_url}"
    )


    cap = cv2.VideoCapture(
        rtsp_url
    )


    if not cap.isOpened():

        await websocket.send_json({

            "type":
                "error",

            "message":
                (
                    "Could not connect "
                    "to CCTV stream. "
                    "Check RTSP URL, "
                    "credentials, and "
                    "network access."
                )

        })

        await websocket.close()

        return


    collection = (
        get_collection()
    )

    seen_plates = set()

    frame_idx = 0


    try:

        while True:

            ret, frame = cap.read()


            if not ret:

                await websocket.send_json({

                    "type":
                        "error",

                    "message":
                        "Lost connection to CCTV stream."

                })

                break


            frame_idx += 1


            if (
                frame_idx %
                sample_every
                != 0
            ):

                continue


            (
                annotated,
                boxes,
                saved
            ) = await asyncio.to_thread(

                run_detection_on_frame,

                frame,

                "cctv",

                collection,

                seen_plates
            )


            ok, buf = cv2.imencode(
                ".jpg",
                annotated
            )


            annotated_b64 = (

                base64.b64encode(
                    buf.tobytes()
                ).decode("utf-8")

                if ok

                else ""
            )


            await websocket.send_json({

                "type":
                    "frame",

                "frame_number":
                    frame_idx,

                "annotated_image_base64":
                    annotated_b64,

                "detections": [

                    b.model_dump(
                        mode="json"
                    )

                    for b in boxes

                ],

                "new_violations": [

                    s.model_dump(
                        mode="json"
                    )

                    for s in saved

                ]

            })


            await asyncio.sleep(
                0.01
            )


    except WebSocketDisconnect:

        print(
            "[CCTV] Client disconnected"
        )


    except Exception as e:

        print(
            f"[CCTV ERROR] {e}"
        )


    finally:

        cap.release()


        try:

            await websocket.send_json({

                "type":
                    "done"

            })

        except Exception:

            pass


        try:

            await websocket.close()

        except Exception:

            pass



# ============================================================
# FEATURE-SPECIFIC API COMPATIBILITY ROUTES
# ============================================================
# These routes intentionally mirror the frontend feature names.
# The original /api/detect/* routes remain available too.

# -----------------------------
# HELMET
# -----------------------------

@app.post("/api/helmet/image")
async def helmet_image(file: UploadFile = File(...)):
    return await detect_image(file)


@app.post("/api/helmet/video")
async def helmet_video(
    file: UploadFile = File(...),
    sample_every: int = Query(5, ge=1, le=60)
):
    return await detect_video(file, sample_every)


@app.post("/api/helmet/webcam")
def helmet_webcam(
    camera_index: int = Query(0),
    num_frames: int = Query(30, ge=1, le=300)
):
    return detect_webcam(camera_index, num_frames)


# -----------------------------
# TRAFFIC / CONGESTION
# -----------------------------

@app.post("/api/traffic/image")
async def traffic_image(file: UploadFile = File(...)):
    return await detect_traffic(file)


@app.post("/api/traffic/video")
async def traffic_video(
    file: UploadFile = File(...),
    sample_every: int = Query(5, ge=1, le=60)
):
    return await detect_traffic_video(file, sample_every)


@app.post("/api/traffic/webcam")
def traffic_webcam(
    camera_index: int = Query(0),
    num_frames: int = Query(30, ge=1, le=300)
):
    return detect_traffic_webcam(camera_index, num_frames)


# -----------------------------
# GENERIC GARBAGE / POTHOLE FRAME DETECTOR
# -----------------------------

def run_generic_feature_on_frame(frame, feature: str, source_name: str, save_event: bool = True):
    """
    Run either the garbage or pothole YOLO model on one frame.
    Returns annotated frame, DetectionBox list, and optional saved record.
    """

    feature = feature.lower().strip()

    if feature == "garbage":
        model = get_garbage_model()
        confidence = CONFIDENCE_GARBAGE
        event_type = "garbage"
        title = "garbage"
    elif feature == "pothole":
        model = get_pothole_model()
        confidence = CONFIDENCE_POTHOLE
        event_type = "pothole"
        title = "pothole"
    else:
        raise HTTPException(
            status_code=400,
            detail="feature must be garbage or pothole"
        )

    if frame is None:
        raise HTTPException(
            status_code=400,
            detail="Invalid frame"
        )

    frame = cv2.resize(frame, (640, 360))
    display = frame.copy()
    boxes_out = []

    results = model(
        frame,
        conf=confidence,
        verbose=False,
        imgsz=640
    )

    names = model.names

    for det in results[0].boxes:
        cls_id = int(det.cls[0])
        label = names[cls_id] if isinstance(names, dict) else names[cls_id]
        conf = float(det.conf[0])

        x1, y1, x2, y2 = map(int, det.xyxy[0])

        boxes_out.append(
            DetectionBox(
                label=label,
                confidence=round(conf, 3),
                box=[x1, y1, x2, y2]
            )
        )

        cv2.rectangle(
            display,
            (x1, y1),
            (x2, y2),
            (0, 165, 255),
            2
        )

        cv2.putText(
            display,
            f"{label} {conf:.2f}",
            (x1, max(20, y1 - 8)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            (0, 165, 255),
            2
        )

    saved = None

    # Save one event record for an image/request. For continuous video/live
    # detection, the caller controls how often records are saved.
    if boxes_out and save_event:
        saved = save_generic_record(
            event_type,
            f"{len(boxes_out)} {title} detection(s)",
            display,
            source_name
        )

    return display, boxes_out, saved


async def _generic_feature_video(
    file: UploadFile,
    feature: str,
    sample_every: int = 5
):
    """Video endpoint for garbage/pothole."""

    tmp_path = (
        UPLOAD_TMP_DIR /
        f"{feature}_{uuid.uuid4().hex}_{file.filename or 'video.mp4'}"
    )

    with open(tmp_path, "wb") as f:
        f.write(await file.read())

    cap = cv2.VideoCapture(str(tmp_path))

    if not cap.isOpened():
        tmp_path.unlink(missing_ok=True)
        raise HTTPException(
            status_code=400,
            detail="Could not open uploaded video"
        )

    frame_idx = 0
    processed = 0
    all_boxes = []
    last_annotated = None
    saved = None

    try:
        while processed < MAX_VIDEO_FRAMES:
            ret, frame = cap.read()

            if not ret:
                break

            frame_idx += 1

            if frame_idx % sample_every != 0:
                continue

            processed += 1

            annotated, boxes, current_saved = run_generic_feature_on_frame(
                frame,
                feature,
                file.filename or f"{feature}_video",
                False
            )

            last_annotated = annotated
            all_boxes.extend(boxes)

            # Save only the first detected event in a video request.
            if saved is None and boxes:
                event_type = feature
                saved = save_generic_record(
                    event_type,
                    f"{len(boxes)} {feature} detection(s)",
                    annotated,
                    file.filename or f"{feature}_video"
                )

    finally:
        cap.release()
        tmp_path.unlink(missing_ok=True)

    if last_annotated is None:
        raise HTTPException(
            status_code=400,
            detail="No usable frames found in video"
        )

    return {
        "feature": feature,
        "frames_processed": processed,
        "last_frame_number": frame_idx,
        "detections_found": len(all_boxes),
        "detections": [
            b.model_dump(mode="json") for b in all_boxes
        ],
        "annotated_image_base64": encode_frame_base64(last_annotated),
        "saved": saved.model_dump(mode="json") if saved else None
    }


@app.post("/api/garbage/video")
async def garbage_video(
    file: UploadFile = File(...),
    sample_every: int = Query(5, ge=1, le=60)
):
    return await _generic_feature_video(file, "garbage", sample_every)


@app.post("/api/pothole/video")
async def pothole_video(
    file: UploadFile = File(...),
    sample_every: int = Query(5, ge=1, le=60)
):
    return await _generic_feature_video(file, "pothole", sample_every)


# -----------------------------
# GARBAGE / POTHOLE WEBCAM
# -----------------------------

def _generic_feature_webcam(
    feature: str,
    camera_index: int = 0,
    num_frames: int = 30
):
    cap = cv2.VideoCapture(camera_index)

    if not cap.isOpened():
        raise HTTPException(
            status_code=400,
            detail=f"Could not open webcam at index {camera_index}"
        )

    all_boxes = []
    last_annotated = None
    saved = None

    try:
        for _ in range(num_frames):
            ret, frame = cap.read()

            if not ret:
                break

            annotated, boxes, current_saved = run_generic_feature_on_frame(
                frame,
                feature,
                "webcam",
                False
            )

            last_annotated = annotated
            all_boxes.extend(boxes)

            if saved is None and boxes:
                saved = save_generic_record(
                    feature,
                    f"{len(boxes)} {feature} detection(s)",
                    annotated,
                    "webcam"
                )

    finally:
        cap.release()

    if last_annotated is None:
        raise HTTPException(
            status_code=400,
            detail="No frames received from webcam"
        )

    return {
        "feature": feature,
        "detections_found": len(all_boxes),
        "detections": [
            b.model_dump(mode="json") for b in all_boxes
        ],
        "annotated_image_base64": encode_frame_base64(last_annotated),
        "saved": saved.model_dump(mode="json") if saved else None
    }


@app.post("/api/garbage/webcam")
def garbage_webcam(
    camera_index: int = Query(0),
    num_frames: int = Query(30, ge=1, le=300)
):
    return _generic_feature_webcam("garbage", camera_index, num_frames)


@app.post("/api/pothole/webcam")
def pothole_webcam(
    camera_index: int = Query(0),
    num_frames: int = Query(30, ge=1, le=300)
):
    return _generic_feature_webcam("pothole", camera_index, num_frames)


# -----------------------------
# WEBSOCKET ALIASES
# -----------------------------
# Helmet and traffic use their existing implementations.

@app.websocket("/ws/multistream/{feature}/{filename}")
async def ws_multistream_video(
    websocket: WebSocket,
    feature: str,
    filename: str,
    sample_every: int = 5,
):
    await websocket.accept()

    feature = feature.lower().strip()
    if feature not in MODEL_COLLECTIONS:
        await websocket.send_json({
            "type": "error",
            "message": "Unknown detection model",
        })
        await websocket.close()
        return

    safe_filename = Path(filename).name
    if safe_filename != filename:
        await websocket.send_json({
            "type": "error",
            "message": "Invalid uploaded video name",
        })
        await websocket.close()
        return

    path = UPLOAD_TMP_DIR / safe_filename
    if not path.is_file():
        await websocket.send_json({
            "type": "error",
            "message": "Uploaded video not found",
        })
        await websocket.close()
        return

    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        path.unlink(missing_ok=True)
        await websocket.send_json({
            "type": "error",
            "message": "Could not open uploaded video",
        })
        await websocket.close()
        return

    sample_every = max(1, sample_every)
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if fps <= 0:
        fps = 30.0

    playback_interval = sample_every / fps
    frame_idx = 0
    processed = 0
    record_saved = False
    seen_plates = set()
    helmet_collection = get_collection() if feature == "helmet" else None

    try:
        while processed < MAX_VIDEO_FRAMES:
            ret, frame = cap.read()
            if not ret:
                break

            frame_idx += 1
            if frame_idx % sample_every != 0:
                continue

            started_at = asyncio.get_running_loop().time()
            vehicle_counts = {}
            congestion_level = None
            saved = None
            violations = []

            if feature == "traffic":
                async with TRAFFIC_INFERENCE_LOCK:
                    annotated, boxes, vehicle_counts, congestion_level = (
                        await asyncio.to_thread(run_traffic_on_frame, frame)
                    )
                if boxes and not record_saved:
                    saved = await asyncio.to_thread(
                        save_traffic_record,
                        annotated,
                        boxes,
                        vehicle_counts,
                        congestion_level,
                        safe_filename,
                    )
            elif feature == "helmet":
                annotated, boxes, violations = await asyncio.to_thread(
                    run_detection_on_frame,
                    frame,
                    safe_filename,
                    helmet_collection,
                    seen_plates,
                )
            else:
                annotated, boxes, _ = await asyncio.to_thread(
                    run_generic_feature_on_frame,
                    frame,
                    feature,
                    safe_filename,
                    False,
                )
                if boxes and not record_saved:
                    saved = await asyncio.to_thread(
                        save_generic_record,
                        feature,
                        f"{len(boxes)} {feature} detection(s)",
                        annotated,
                        safe_filename,
                    )

            if saved:
                record_saved = True

            processed += 1
            await websocket.send_json({
                "type": "frame",
                "frame_number": frame_idx,
                "annotated_image_base64": encode_frame_base64(annotated),
                "detections": [
                    box.model_dump(mode="json") for box in boxes
                ],
                "vehicle_counts": vehicle_counts,
                "congestion_level": congestion_level,
                "saved": saved.model_dump(mode="json") if saved else None,
                "new_violations": [
                    violation.model_dump(mode="json")
                    for violation in violations
                ],
            })

            delay = playback_interval - (
                asyncio.get_running_loop().time() - started_at
            )
            if delay > 0:
                await asyncio.sleep(delay)

    except WebSocketDisconnect:
        print(f"[{feature.upper()} MULTISTREAM] Client disconnected")
    except Exception as error:
        print(f"[{feature.upper()} MULTISTREAM ERROR] {error}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(error),
            })
        except Exception:
            pass
    finally:
        cap.release()
        path.unlink(missing_ok=True)
        try:
            await websocket.send_json({"type": "done"})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass

@app.websocket("/ws/helmet/{filename}")
async def ws_helmet_alias(
    websocket: WebSocket,
    filename: str,
    sample_every: int = 5
):
    await ws_detect_video(websocket, filename, sample_every)


@app.websocket("/ws/traffic-feature/{filename}")
async def ws_traffic_alias(
    websocket: WebSocket,
    filename: str,
    sample_every: int = 5
):
    await ws_traffic_video(websocket, filename, sample_every)


@app.websocket("/ws/helmet/cctv")
async def ws_helmet_cctv_alias(
    websocket: WebSocket,
    rtsp_url: str,
    sample_every: int = 5
):
    await ws_detect_cctv(websocket, rtsp_url, sample_every)


@app.websocket("/ws/traffic-feature/cctv")
async def ws_traffic_cctv_alias(
    websocket: WebSocket,
    rtsp_url: str,
    sample_every: int = 5
):
    await ws_traffic_cctv(websocket, rtsp_url, sample_every)


async def _generic_feature_cctv(
    websocket: WebSocket,
    rtsp_url: str,
    feature: str,
    sample_every: int = 5
):
    await websocket.accept()

    print(f"[{feature.upper()} CCTV] Connecting to: {rtsp_url}")

    cap = cv2.VideoCapture(rtsp_url)

    if not cap.isOpened():
        await websocket.send_json({
            "type": "error",
            "message": (
                "Could not connect to CCTV stream. "
                "Check RTSP URL, credentials, and network access."
            )
        })
        await websocket.close()
        return

    frame_idx = 0
    record_saved = False

    try:
        while True:
            ret, frame = cap.read()

            if not ret:
                await websocket.send_json({
                    "type": "error",
                    "message": "Lost connection to CCTV stream."
                })
                break

            frame_idx += 1

            if frame_idx % max(1, sample_every) != 0:
                continue

            annotated, boxes, _ = await asyncio.to_thread(
                run_generic_feature_on_frame,
                frame,
                feature,
                "cctv",
                False
            )

            frame_saved = None
            if not record_saved and boxes:
                frame_saved = save_generic_record(
                    feature,
                    f"{len(boxes)} {feature} detection(s)",
                    annotated,
                    "cctv",
                )
                record_saved = frame_saved is not None

            await websocket.send_json({
                "type": "frame",
                "frame_number": frame_idx,
                "annotated_image_base64": encode_frame_base64(annotated),
                "detections": [
                    b.model_dump(mode="json") for b in boxes
                ],
                "saved": (
                    frame_saved.model_dump(mode="json")
                    if frame_saved else None
                )
            })

            await asyncio.sleep(0.01)

    except WebSocketDisconnect:
        print(f"[{feature.upper()} CCTV] Client disconnected")

    except Exception as e:
        print(f"[{feature.upper()} CCTV ERROR] {e}")
        try:
            await websocket.send_json({
                "type": "error",
                "message": str(e)
            })
        except Exception:
            pass

    finally:
        cap.release()
        try:
            await websocket.send_json({"type": "done"})
        except Exception:
            pass
        try:
            await websocket.close()
        except Exception:
            pass


@app.websocket("/ws/garbage/cctv")
async def ws_garbage_cctv(
    websocket: WebSocket,
    rtsp_url: str,
    sample_every: int = 5
):
    await _generic_feature_cctv(
        websocket, rtsp_url, "garbage", sample_every
    )


@app.websocket("/ws/pothole/cctv")
async def ws_pothole_cctv(
    websocket: WebSocket,
    rtsp_url: str,
    sample_every: int = 5
):
    await _generic_feature_cctv(
        websocket, rtsp_url, "pothole", sample_every
    )


# Image aliases for garbage and pothole already use the original handlers.
@app.post("/api/garbage/image")
async def garbage_image(file: UploadFile = File(...)):
    return await detect_garbage(file)


@app.post("/api/pothole/image")
async def pothole_image(file: UploadFile = File(...)):
    return await detect_pothole(file)


# ============================================================
# START SERVER
# ============================================================

if __name__ == "__main__":

    import uvicorn

    uvicorn.run(
        "app:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )